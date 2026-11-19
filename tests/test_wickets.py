"""Wickets: legality per delivery type, dismissal roles and innings limits."""

from __future__ import annotations

import pytest

from app.errors import DeliveryValidationError
from app.services.rules_engine import build_ruleset
from app.services.scoring_engine import DeliveryRequest, InningsSnapshot, compute_delivery

TURF = build_ruleset("custom_turf")


def snapshot(**overrides) -> InningsSnapshot:
    base = {
        "legal_balls": 3,
        "wickets": 0,
        "runs": 10,
        "pending_free_hit": False,
        "striker_id": 1,
        "non_striker_id": 2,
        "target": None,
        "is_complete": False,
    }
    base.update(overrides)
    return InningsSnapshot(**base)


def test_bowled_striker_is_a_legal_wicket():
    outcome = compute_delivery(
        TURF, snapshot(), DeliveryRequest(is_wicket=True, wicket_type="bowled")
    )

    assert outcome.is_wicket is True
    assert outcome.wicket_type == "bowled"
    assert outcome.dismissed_player == "striker"
    assert outcome.total_runs == 0
    assert outcome.is_legal_ball is True


def test_caught_cannot_carry_runs_off_the_bat():
    with pytest.raises(DeliveryValidationError) as error:
        compute_delivery(
            TURF,
            snapshot(),
            DeliveryRequest(runs_off_bat=1, is_wicket=True, wicket_type="caught"),
        )
    assert error.value.code == "wicket_runs_conflict"


def test_non_striker_can_only_be_run_out():
    with pytest.raises(DeliveryValidationError) as error:
        compute_delivery(
            TURF,
            snapshot(),
            DeliveryRequest(
                is_wicket=True, wicket_type="bowled", dismissed_player="non_striker"
            ),
        )
    assert error.value.code == "invalid_dismissal_role"


def test_run_out_of_the_non_striker_is_allowed():
    outcome = compute_delivery(
        TURF,
        snapshot(),
        DeliveryRequest(
            is_wicket=True, wicket_type="run_out", dismissed_player="non_striker"
        ),
    )
    assert outcome.dismissed_player == "non_striker"


def test_non_striker_run_out_requires_a_non_striker():
    with pytest.raises(DeliveryValidationError) as error:
        compute_delivery(
            TURF,
            snapshot(non_striker_id=None),
            DeliveryRequest(
                is_wicket=True, wicket_type="run_out", dismissed_player="non_striker"
            ),
        )
    assert error.value.code == "no_non_striker"


def test_caught_is_not_allowed_on_a_free_hit():
    with pytest.raises(DeliveryValidationError) as error:
        compute_delivery(
            TURF,
            snapshot(pending_free_hit=True),
            DeliveryRequest(is_wicket=True, wicket_type="caught"),
        )
    assert error.value.code == "wicket_not_allowed_on_free_hit"


def test_run_out_is_allowed_on_a_free_hit():
    outcome = compute_delivery(
        TURF,
        snapshot(pending_free_hit=True),
        DeliveryRequest(is_wicket=True, wicket_type="run_out"),
    )
    assert outcome.is_wicket is True
    assert outcome.is_free_hit is True


def test_last_wicket_completes_the_innings_with_solo_batting():
    outcome = compute_delivery(
        TURF, snapshot(wickets=4), DeliveryRequest(is_wicket=True, wicket_type="bowled")
    )
    assert outcome.innings_complete is True


def test_wickets_beyond_the_limit_are_rejected():
    rules = build_ruleset("custom_match")
    with pytest.raises(DeliveryValidationError) as error:
        compute_delivery(
            rules,
            snapshot(wickets=10, non_striker_id=2),
            DeliveryRequest(is_wicket=True, wicket_type="bowled"),
        )
    assert error.value.code == "wicket_limit_reached"


def test_wicket_on_the_last_ball_still_counts_the_runs():
    outcome = compute_delivery(
        TURF,
        snapshot(legal_balls=35),
        DeliveryRequest(
            runs_off_bat=2, is_wicket=True, wicket_type="run_out", dismissed_player="non_striker"
        ),
    )
    assert outcome.total_runs == 2
    assert outcome.innings_complete is True
