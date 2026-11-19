"""Delivery scoring: runs, strike rotation, overs, free hits and completion."""

from __future__ import annotations

import pytest

from app.errors import DeliveryValidationError
from app.services.rules_engine import build_ruleset
from app.services.scoring_engine import (
    DeliveryRequest,
    InningsSnapshot,
    compute_delivery,
    parse_delivery_payload,
)

TURF = build_ruleset("custom_turf")
STRIKER = 1
NON_STRIKER = 2


def snapshot(**overrides) -> InningsSnapshot:
    base = {
        "legal_balls": 0,
        "wickets": 0,
        "runs": 0,
        "pending_free_hit": False,
        "striker_id": STRIKER,
        "non_striker_id": NON_STRIKER,
        "target": None,
        "is_complete": False,
    }
    base.update(overrides)
    return InningsSnapshot(**base)


def test_dot_ball():
    outcome = compute_delivery(TURF, snapshot(), DeliveryRequest())

    assert outcome.total_runs == 0
    assert outcome.is_legal_ball is True
    assert outcome.over_number == 1
    assert outcome.ball_in_over == 1
    assert outcome.strike_rotated is False
    assert outcome.ends_over is False
    assert outcome.is_free_hit is False
    assert outcome.free_hit_next is False
    assert outcome.innings_complete is False


def test_single_rotates_the_strike():
    outcome = compute_delivery(TURF, snapshot(), DeliveryRequest(runs_off_bat=1))
    assert outcome.total_runs == 1
    assert outcome.strike_rotated is True


def test_boundary_keeps_the_strike():
    outcome = compute_delivery(TURF, snapshot(), DeliveryRequest(runs_off_bat=4))
    assert outcome.total_runs == 4
    assert outcome.strike_rotated is False


def test_two_runs_keep_the_strike_and_three_rotate():
    assert compute_delivery(TURF, snapshot(), DeliveryRequest(runs_off_bat=2)).strike_rotated is False
    assert compute_delivery(TURF, snapshot(), DeliveryRequest(runs_off_bat=3)).strike_rotated is True


def test_sixth_legal_ball_ends_the_over():
    outcome = compute_delivery(TURF, snapshot(legal_balls=5), DeliveryRequest(runs_off_bat=1))

    assert outcome.ball_in_over == 6
    assert outcome.ends_over is True
    assert outcome.over_number == 1


def test_next_delivery_starts_the_next_over():
    outcome = compute_delivery(TURF, snapshot(legal_balls=6), DeliveryRequest())
    assert outcome.over_number == 2
    assert outcome.ball_in_over == 1


def test_illegal_delivery_does_not_advance_the_ball_count():
    outcome = compute_delivery(TURF, snapshot(legal_balls=5), DeliveryRequest(extra_type="wide"))

    assert outcome.ball_in_over == 6
    assert outcome.is_legal_ball is False
    assert outcome.ends_over is False


def test_runs_outside_the_allowed_set_are_rejected():
    with pytest.raises(DeliveryValidationError) as error:
        compute_delivery(TURF, snapshot(), DeliveryRequest(runs_off_bat=7))
    assert error.value.code == "runs_not_allowed"


def test_negative_runs_are_rejected():
    with pytest.raises(DeliveryValidationError) as error:
        compute_delivery(TURF, snapshot(), DeliveryRequest(runs_off_bat=-1))
    assert error.value.code == "invalid_runs"


def test_allowed_runs_can_be_restricted():
    rules = build_ruleset("custom_turf", {"allowed_runs": [0, 1, 4, 6]})
    assert compute_delivery(rules, snapshot(), DeliveryRequest(runs_off_bat=6)).total_runs == 6
    with pytest.raises(DeliveryValidationError):
        compute_delivery(rules, snapshot(), DeliveryRequest(runs_off_bat=3))


def test_no_ball_arms_a_free_hit():
    outcome = compute_delivery(
        TURF, snapshot(), DeliveryRequest(extra_type="no_ball", runs_off_bat=1)
    )
    assert outcome.free_hit_next is True
    assert outcome.is_legal_ball is False
    assert outcome.total_runs == 2


def test_free_hit_survives_another_illegal_delivery():
    outcome = compute_delivery(
        TURF, snapshot(legal_balls=1, pending_free_hit=True), DeliveryRequest(extra_type="wide")
    )
    assert outcome.free_hit_next is True


def test_free_hit_is_consumed_by_a_legal_ball():
    outcome = compute_delivery(
        TURF, snapshot(legal_balls=1, pending_free_hit=True), DeliveryRequest(runs_off_bat=4)
    )
    assert outcome.is_free_hit is True
    assert outcome.free_hit_next is False


def test_free_hit_can_be_disabled():
    rules = build_ruleset("custom_turf", {"free_hit_enabled": False})
    outcome = compute_delivery(rules, snapshot(), DeliveryRequest(extra_type="no_ball"))
    assert outcome.free_hit_next is False


def test_innings_completes_after_the_last_scheduled_ball():
    outcome = compute_delivery(TURF, snapshot(legal_balls=35), DeliveryRequest())
    assert outcome.innings_complete is True


def test_completed_innings_rejects_more_deliveries():
    with pytest.raises(DeliveryValidationError) as error:
        compute_delivery(TURF, snapshot(legal_balls=36, is_complete=True), DeliveryRequest())
    assert error.value.code == "innings_complete"


def test_reaching_the_target_completes_the_innings():
    outcome = compute_delivery(
        TURF, snapshot(runs=9, target=10), DeliveryRequest(runs_off_bat=1)
    )
    assert outcome.total_runs == 1
    assert outcome.innings_complete is True


def test_parse_rejects_unknown_fields():
    with pytest.raises(DeliveryValidationError) as error:
        parse_delivery_payload({"runs_off_bat": 1, "shot": "cover drive"})
    assert error.value.code == "unknown_fields"
    assert error.value.details["fields"] == ["shot"]


def test_parse_accepts_short_runs_alias_and_normalises():
    request = parse_delivery_payload({"runs": 2, "extra": "WIDE", "extra_runs": 1})
    assert request.runs_off_bat == 2
    assert request.extra_type == "wide"


def test_parse_requires_wicket_type_for_a_wicket():
    with pytest.raises(DeliveryValidationError) as error:
        parse_delivery_payload({"is_wicket": True})
    assert error.value.code == "invalid_wicket_type"


def test_parse_rejects_wicket_type_without_wicket():
    with pytest.raises(DeliveryValidationError) as error:
        parse_delivery_payload({"wicket_type": "bowled"})
    assert error.value.code == "wicket_type_without_wicket"
