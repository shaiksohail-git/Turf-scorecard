"""Rules preset and override validation."""

from __future__ import annotations

import pytest

from app.errors import NotFoundError, ValidationError
from app.services.rules_engine import (
    RETIREMENT_TYPES,
    RuleSet,
    build_ruleset,
    preset_catalog,
    validate_ruleset,
)


def test_custom_turf_defaults_match_the_specification():
    rules = build_ruleset("custom_turf")

    assert rules.overs == 6
    assert rules.players_per_team == 5
    assert rules.balls_per_over == 6
    assert rules.wide_penalty == 1
    assert rules.wide_counts_as_legal_ball is False
    assert rules.no_ball_penalty == 1
    assert rules.no_ball_counts_as_legal_ball is False
    assert rules.free_hit_enabled is True
    assert rules.solo_batting_enabled is True
    assert rules.allowed_runs == (0, 1, 2, 3, 4, 5, 6)
    assert rules.retired_player_option is True
    assert rules.retirement_types == RETIREMENT_TYPES
    assert rules.total_balls == 36
    assert rules.max_wickets == 5


def test_full_t20_defaults():
    rules = build_ruleset("full_t20")

    assert rules.overs == 20
    assert rules.players_per_team == 11
    assert rules.max_overs_per_bowler == 4
    assert rules.solo_batting_enabled is False
    assert rules.max_wickets == 10
    assert rules.total_balls == 120


def test_custom_match_is_t20_shaped_but_editable():
    rules = build_ruleset("custom_match")

    assert rules.overs == 20
    assert rules.players_per_team == 11
    assert rules.max_overs_per_bowler is None


def test_unknown_preset_raises_not_found():
    with pytest.raises(NotFoundError) as error:
        build_ruleset("street_cricket")
    assert error.value.code == "unknown_preset"


def test_overrides_are_applied():
    rules = build_ruleset(
        "custom_turf",
        {"overs": 8, "players_per_team": 7, "wide_penalty": 2, "free_hit_enabled": False},
    )

    assert rules.overs == 8
    assert rules.players_per_team == 7
    assert rules.wide_penalty == 2
    assert rules.free_hit_enabled is False
    assert rules.total_balls == 48
    # Defaults that were not overridden stay at the preset values.
    assert rules.solo_batting_enabled is True


def test_unknown_override_field_is_rejected():
    with pytest.raises(ValidationError) as error:
        build_ruleset("custom_turf", {"powerplay_overs": 2})
    assert error.value.code == "invalid_rules"
    assert error.value.details["fields"] == ["powerplay_overs"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("overs", 0),
        ("overs", 51),
        ("balls_per_over", 0),
        ("players_per_team", 1),
        ("wide_penalty", -1),
        ("no_ball_penalty", 9),
        ("overs", "6"),
        ("free_hit_enabled", "yes"),
    ],
)
def test_invalid_override_values_are_rejected(field, value):
    with pytest.raises(ValidationError):
        build_ruleset("custom_turf", {field: value})


def test_allowed_runs_must_be_a_valid_sorted_subset():
    rules = build_ruleset("custom_turf", {"allowed_runs": [6, 4, 1, 1]})
    assert rules.allowed_runs == (1, 4, 6)

    with pytest.raises(ValidationError):
        build_ruleset("custom_turf", {"allowed_runs": []})
    with pytest.raises(ValidationError):
        build_ruleset("custom_turf", {"allowed_runs": [7]})
    with pytest.raises(ValidationError):
        build_ruleset("custom_turf", {"allowed_runs": [True]})


def test_retirement_types_are_validated():
    rules = build_ruleset("custom_turf", {"retirement_types": ["retired_hurt"]})
    assert rules.retirement_types == ("retired_hurt",)

    with pytest.raises(ValidationError):
        build_ruleset("custom_turf", {"retirement_types": ["injured"]})
    with pytest.raises(ValidationError):
        build_ruleset("custom_turf", {"retirement_types": []})


def test_bowler_over_limit_cannot_exceed_innings():
    with pytest.raises(ValidationError):
        build_ruleset("custom_turf", {"max_overs_per_bowler": 7})


def test_snapshot_round_trip_is_lossless():
    rules = build_ruleset("custom_turf", {"overs": 4, "allowed_runs": [0, 1, 4, 6]})
    snapshot = rules.to_dict()

    assert isinstance(snapshot["allowed_runs"], list)
    assert RuleSet.from_dict(snapshot) == rules


def test_snapshot_missing_fields_is_rejected():
    snapshot = build_ruleset("custom_turf").to_dict()
    snapshot.pop("overs")

    with pytest.raises(ValidationError) as error:
        RuleSet.from_dict(snapshot)
    assert error.value.code == "invalid_rules"
    assert error.value.details["missing"] == ["overs"]


def test_public_rules_include_derived_values():
    public = build_ruleset("custom_turf").to_public()

    assert public["total_balls"] == 36
    assert public["max_wickets"] == 5
    assert public["preset"] == "custom_turf"


def test_validate_ruleset_rejects_unsorted_allowed_runs():
    tampered = RuleSet.from_dict({**build_ruleset("custom_turf").to_dict()})
    tampered = RuleSet(**{**tampered.__dict__, "allowed_runs": (4, 1)})

    with pytest.raises(ValidationError):
        validate_ruleset(tampered)


def test_preset_catalog_lists_all_three_formats():
    catalog = preset_catalog()
    keys = [preset["key"] for preset in catalog]

    assert keys == ["full_t20", "custom_match", "custom_turf"]
    for preset in catalog:
        assert preset["label"]
        assert preset["rules"]["total_balls"] > 0
