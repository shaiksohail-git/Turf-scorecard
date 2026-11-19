"""Extras: penalties, legality and which dismissals are possible."""

from __future__ import annotations

import pytest

from app.errors import DeliveryValidationError
from app.services.rules_engine import build_ruleset
from app.services.scoring_engine import DeliveryRequest, InningsSnapshot, compute_delivery

TURF = build_ruleset("custom_turf")


def snapshot(**overrides) -> InningsSnapshot:
    base = {
        "legal_balls": 0,
        "wickets": 0,
        "runs": 0,
        "pending_free_hit": False,
        "striker_id": 1,
        "non_striker_id": 2,
        "target": None,
        "is_complete": False,
    }
    base.update(overrides)
    return InningsSnapshot(**base)


def test_wide_penalty_and_legality():
    outcome = compute_delivery(TURF, snapshot(), DeliveryRequest(extra_type="wide"))

    assert outcome.penalty_runs == 1
    assert outcome.extras_runs == 1
    assert outcome.total_runs == 1
    assert outcome.is_legal_ball is False
    assert outcome.is_free_hit is False


def test_wide_with_runs_run_counts_penalty_plus_runs():
    outcome = compute_delivery(TURF, snapshot(), DeliveryRequest(extra_type="wide", extra_runs=2))

    assert outcome.total_runs == 3
    assert outcome.strike_rotated is False


def test_wide_with_one_run_run_rotates_the_strike():
    outcome = compute_delivery(TURF, snapshot(), DeliveryRequest(extra_type="wide", extra_runs=1))

    assert outcome.total_runs == 2
    assert outcome.strike_rotated is True


def test_wide_can_count_as_a_legal_ball_when_configured():
    rules = build_ruleset("custom_match", {"wide_counts_as_legal_ball": True})
    outcome = compute_delivery(rules, snapshot(), DeliveryRequest(extra_type="wide"))

    assert outcome.is_legal_ball is True
    assert outcome.ball_in_over == 1


def test_no_ball_penalty_plus_runs_off_the_bat():
    outcome = compute_delivery(
        TURF, snapshot(), DeliveryRequest(extra_type="no_ball", runs_off_bat=4)
    )

    assert outcome.runs_off_bat == 4
    assert outcome.penalty_runs == 1
    assert outcome.extras_runs == 1
    assert outcome.total_runs == 5
    assert outcome.is_legal_ball is False


def test_no_ball_can_count_as_a_legal_ball_when_configured():
    rules = build_ruleset("custom_match", {"no_ball_counts_as_legal_ball": True})
    outcome = compute_delivery(rules, snapshot(), DeliveryRequest(extra_type="no_ball"))
    assert outcome.is_legal_ball is True


def test_bye_counts_as_a_legal_ball_without_a_penalty():
    outcome = compute_delivery(TURF, snapshot(), DeliveryRequest(extra_type="bye", extra_runs=2))

    assert outcome.total_runs == 2
    assert outcome.penalty_runs == 0
    assert outcome.is_legal_ball is True
    assert outcome.ball_in_over == 1


def test_leg_bye_requires_at_least_one_run():
    with pytest.raises(DeliveryValidationError) as error:
        compute_delivery(TURF, snapshot(), DeliveryRequest(extra_type="leg_bye", extra_runs=0))
    assert error.value.code == "invalid_extra_runs"


def test_runs_off_the_bat_are_rejected_for_a_wide():
    with pytest.raises(DeliveryValidationError) as error:
        compute_delivery(TURF, snapshot(), DeliveryRequest(extra_type="wide", runs_off_bat=1))
    assert error.value.code == "invalid_runs"


def test_extra_runs_require_an_extra_type():
    with pytest.raises(DeliveryValidationError) as error:
        compute_delivery(TURF, snapshot(), DeliveryRequest(extra_runs=1))
    assert error.value.code == "invalid_extra_runs"


def test_caught_is_impossible_off_a_wide():
    with pytest.raises(DeliveryValidationError) as error:
        compute_delivery(
            TURF,
            snapshot(),
            DeliveryRequest(extra_type="wide", is_wicket=True, wicket_type="caught"),
        )
    assert error.value.code == "wicket_not_allowed_off_wide"


def test_stumped_is_possible_off_a_wide():
    outcome = compute_delivery(
        TURF,
        snapshot(),
        DeliveryRequest(extra_type="wide", is_wicket=True, wicket_type="stumped"),
    )
    assert outcome.is_wicket is True
    assert outcome.total_runs == 1


def test_bowled_is_impossible_off_a_no_ball():
    with pytest.raises(DeliveryValidationError) as error:
        compute_delivery(
            TURF,
            snapshot(),
            DeliveryRequest(extra_type="no_ball", is_wicket=True, wicket_type="bowled"),
        )
    assert error.value.code == "wicket_not_allowed_off_no_ball"


def test_run_out_is_possible_off_a_no_ball():
    outcome = compute_delivery(
        TURF,
        snapshot(),
        DeliveryRequest(extra_type="no_ball", is_wicket=True, wicket_type="run_out"),
    )
    assert outcome.is_wicket is True
    # The no-ball still arms a free hit for the next delivery.
    assert outcome.free_hit_next is True
