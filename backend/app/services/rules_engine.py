"""Configurable scoring rules.

Three presets ship with the app:

* ``full_t20``      - a complete 20 over, 11-a-side match.
* ``custom_match``  - the same shape as T20 but every setting editable.
* ``custom_turf``   - the 6 over, 5-a-side turf format (see the spec defaults).

A match stores a frozen snapshot of the rules that were in force when it was
created. Nothing rewrites that snapshot, so a historical match keeps scoring
under its original rules even if presets change in a later release.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import NotFoundError, ValidationError

RETIREMENT_TYPES = ("retired_not_out", "retired_out", "retired_hurt")
EXTRA_TYPES = ("wide", "no_ball", "bye", "leg_bye")
WICKET_TYPES = (
    "bowled",
    "caught",
    "lbw",
    "stumped",
    "run_out",
    "hit_wicket",
    "obstructing_the_field",
    "hit_the_ball_twice",
    "timed_out",
)

PRESET_FULL_T20 = "full_t20"
PRESET_CUSTOM_MATCH = "custom_match"
PRESET_CUSTOM_TURF = "custom_turf"

ALL_RUNS = (0, 1, 2, 3, 4, 5, 6)


@dataclass(frozen=True)
class RuleSet:
    """Immutable, fully resolved rules for one match."""

    preset: str
    overs: int
    balls_per_over: int
    players_per_team: int
    wide_penalty: int
    wide_counts_as_legal_ball: bool
    no_ball_penalty: int
    no_ball_counts_as_legal_ball: bool
    free_hit_enabled: bool
    solo_batting_enabled: bool
    allowed_runs: tuple[int, ...]
    retired_player_option: bool
    retirement_types: tuple[str, ...]
    max_overs_per_bowler: int | None = None

    @property
    def total_balls(self) -> int:
        return self.overs * self.balls_per_over

    @property
    def max_wickets(self) -> int:
        """Wickets that end the innings.

        With solo batting the last remaining batter keeps batting alone, so
        every player can be dismissed; otherwise the innings ends when only
        one batter is left (``players_per_team - 1`` wickets).
        """
        return self.players_per_team if self.solo_batting_enabled else self.players_per_team - 1

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe snapshot. Only configuration fields are stored."""
        return {
            "preset": self.preset,
            "overs": self.overs,
            "balls_per_over": self.balls_per_over,
            "players_per_team": self.players_per_team,
            "wide_penalty": self.wide_penalty,
            "wide_counts_as_legal_ball": self.wide_counts_as_legal_ball,
            "no_ball_penalty": self.no_ball_penalty,
            "no_ball_counts_as_legal_ball": self.no_ball_counts_as_legal_ball,
            "free_hit_enabled": self.free_hit_enabled,
            "solo_batting_enabled": self.solo_batting_enabled,
            "allowed_runs": list(self.allowed_runs),
            "retired_player_option": self.retired_player_option,
            "retirement_types": list(self.retirement_types),
            "max_overs_per_bowler": self.max_overs_per_bowler,
        }

    def to_public(self) -> dict[str, Any]:
        """Snapshot plus derived values that are useful to the UI."""
        data = self.to_dict()
        data["total_balls"] = self.total_balls
        data["max_wickets"] = self.max_wickets
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RuleSet":
        if not isinstance(data, Mapping):
            raise ValidationError("Rules must be an object.", code="invalid_rules")
        required = (
            "preset",
            "overs",
            "balls_per_over",
            "players_per_team",
            "wide_penalty",
            "wide_counts_as_legal_ball",
            "no_ball_penalty",
            "no_ball_counts_as_legal_ball",
            "free_hit_enabled",
            "solo_batting_enabled",
            "allowed_runs",
            "retired_player_option",
            "retirement_types",
        )
        missing = [field for field in required if field not in data]
        if missing:
            raise ValidationError(
                "Rules snapshot is incomplete.", code="invalid_rules", details={"missing": missing}
            )
        try:
            max_overs = data.get("max_overs_per_bowler")
            rules = cls(
                preset=str(data["preset"]),
                overs=int(data["overs"]),
                balls_per_over=int(data["balls_per_over"]),
                players_per_team=int(data["players_per_team"]),
                wide_penalty=int(data["wide_penalty"]),
                wide_counts_as_legal_ball=bool(data["wide_counts_as_legal_ball"]),
                no_ball_penalty=int(data["no_ball_penalty"]),
                no_ball_counts_as_legal_ball=bool(data["no_ball_counts_as_legal_ball"]),
                free_hit_enabled=bool(data["free_hit_enabled"]),
                solo_batting_enabled=bool(data["solo_batting_enabled"]),
                allowed_runs=tuple(int(run) for run in data["allowed_runs"]),
                retired_player_option=bool(data["retired_player_option"]),
                retirement_types=tuple(str(kind) for kind in data["retirement_types"]),
                max_overs_per_bowler=None if max_overs is None else int(max_overs),
            )
        except (TypeError, ValueError, KeyError) as exc:
            raise ValidationError(
                "Rules snapshot is invalid.", code="invalid_rules", details={"reason": str(exc)}
            ) from exc
        validate_ruleset(rules)
        return rules


FULL_T20_RULES = RuleSet(
    preset=PRESET_FULL_T20,
    overs=20,
    balls_per_over=6,
    players_per_team=11,
    wide_penalty=1,
    wide_counts_as_legal_ball=False,
    no_ball_penalty=1,
    no_ball_counts_as_legal_ball=False,
    free_hit_enabled=True,
    solo_batting_enabled=False,
    allowed_runs=ALL_RUNS,
    retired_player_option=True,
    retirement_types=RETIREMENT_TYPES,
    max_overs_per_bowler=4,
)

CUSTOM_MATCH_RULES = RuleSet(
    preset=PRESET_CUSTOM_MATCH,
    overs=20,
    balls_per_over=6,
    players_per_team=11,
    wide_penalty=1,
    wide_counts_as_legal_ball=False,
    no_ball_penalty=1,
    no_ball_counts_as_legal_ball=False,
    free_hit_enabled=True,
    solo_batting_enabled=False,
    allowed_runs=ALL_RUNS,
    retired_player_option=True,
    retirement_types=RETIREMENT_TYPES,
    max_overs_per_bowler=None,
)

# The Custom Turf preset must always start from these defaults.
CUSTOM_TURF_RULES = RuleSet(
    preset=PRESET_CUSTOM_TURF,
    overs=6,
    balls_per_over=6,
    players_per_team=5,
    wide_penalty=1,
    wide_counts_as_legal_ball=False,
    no_ball_penalty=1,
    no_ball_counts_as_legal_ball=False,
    free_hit_enabled=True,
    solo_batting_enabled=True,
    allowed_runs=ALL_RUNS,
    retired_player_option=True,
    retirement_types=RETIREMENT_TYPES,
    max_overs_per_bowler=None,
)

PRESETS: dict[str, dict[str, Any]] = {
    PRESET_FULL_T20: {
        "label": "Full T20",
        "description": "Standard 20 over match, 11 players a side, 4 overs per bowler.",
        "rules": FULL_T20_RULES,
    },
    PRESET_CUSTOM_MATCH: {
        "label": "Custom Match",
        "description": "Build any match length and squad size before the toss.",
        "rules": CUSTOM_MATCH_RULES,
    },
    PRESET_CUSTOM_TURF: {
        "label": "Custom Turf",
        "description": "6 overs, 5 players a side, solo batting and free hits.",
        "rules": CUSTOM_TURF_RULES,
    },
}

PRESET_KEYS = tuple(PRESETS)

EDITABLE_FIELDS = frozenset(
    {
        "overs",
        "balls_per_over",
        "players_per_team",
        "wide_penalty",
        "wide_counts_as_legal_ball",
        "no_ball_penalty",
        "no_ball_counts_as_legal_ball",
        "free_hit_enabled",
        "solo_batting_enabled",
        "allowed_runs",
        "retired_player_option",
        "retirement_types",
        "max_overs_per_bowler",
    }
)

_INT_LIMITS: dict[str, tuple[int, int]] = {
    "overs": (1, 50),
    "balls_per_over": (1, 12),
    "players_per_team": (2, 11),
    "wide_penalty": (0, 5),
    "no_ball_penalty": (0, 5),
}

_BOOL_FIELDS = (
    "wide_counts_as_legal_ball",
    "no_ball_counts_as_legal_ball",
    "free_hit_enabled",
    "solo_batting_enabled",
    "retired_player_option",
)


def get_preset(preset_key: str) -> dict[str, Any]:
    if preset_key not in PRESETS:
        raise NotFoundError(
            f"Unknown rules preset '{preset_key}'.",
            code="unknown_preset",
            details={"allowed": list(PRESET_KEYS)},
        )
    return PRESETS[preset_key]


def preset_catalog() -> list[dict[str, Any]]:
    """Serialisable description of every preset for the frontend."""
    return [
        {
            "key": key,
            "label": preset["label"],
            "description": preset["description"],
            "rules": preset["rules"].to_public(),
        }
        for key, preset in PRESETS.items()
    ]


def _validated_value(field: str, value: Any) -> Any:
    if field in _INT_LIMITS:
        minimum, maximum = _INT_LIMITS[field]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError(
                f"{field} must be an integer.", code="invalid_rules", details={"field": field}
            )
        if not minimum <= value <= maximum:
            raise ValidationError(
                f"{field} must be between {minimum} and {maximum}.",
                code="invalid_rules",
                details={"field": field, "min": minimum, "max": maximum},
            )
        return value

    if field in _BOOL_FIELDS:
        if not isinstance(value, bool):
            raise ValidationError(
                f"{field} must be true or false.", code="invalid_rules", details={"field": field}
            )
        return value

    if field == "allowed_runs":
        if not isinstance(value, (list, tuple)) or not value:
            raise ValidationError(
                "allowed_runs must be a non-empty list of run values.",
                code="invalid_rules",
                details={"field": field},
            )
        cleaned: list[int] = []
        for run in value:
            if isinstance(run, bool) or not isinstance(run, int) or run not in ALL_RUNS:
                raise ValidationError(
                    "allowed_runs may only contain whole numbers from 0 to 6.",
                    code="invalid_rules",
                    details={"field": field, "value": run},
                )
            if run not in cleaned:
                cleaned.append(run)
        return tuple(sorted(cleaned))

    if field == "retirement_types":
        if not isinstance(value, (list, tuple)):
            raise ValidationError(
                "retirement_types must be a list.", code="invalid_rules", details={"field": field}
            )
        cleaned = []
        for kind in value:
            if kind not in RETIREMENT_TYPES:
                raise ValidationError(
                    f"Unknown retirement type '{kind}'.",
                    code="invalid_rules",
                    details={"field": field, "allowed": list(RETIREMENT_TYPES)},
                )
            if kind not in cleaned:
                cleaned.append(kind)
        if not cleaned:
            raise ValidationError(
                "At least one retirement type is required.",
                code="invalid_rules",
                details={"field": field},
            )
        return tuple(cleaned)

    if field == "max_overs_per_bowler":
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError(
                "max_overs_per_bowler must be an integer or null.",
                code="invalid_rules",
                details={"field": field},
            )
        if not 1 <= value <= 50:
            raise ValidationError(
                "max_overs_per_bowler must be between 1 and 50.",
                code="invalid_rules",
                details={"field": field},
            )
        return value

    raise ValidationError(
        f"'{field}' cannot be configured.", code="invalid_rules", details={"field": field}
    )


def validate_ruleset(rules: RuleSet) -> RuleSet:
    """Cross-field consistency checks shared by presets, overrides and snapshots."""
    if rules.preset not in PRESETS:
        raise ValidationError(
            f"Unknown rules preset '{rules.preset}'.",
            code="invalid_rules",
            details={"allowed": list(PRESET_KEYS)},
        )
    for field in _INT_LIMITS:
        _validated_value(field, getattr(rules, field))
    if not rules.allowed_runs:
        raise ValidationError("allowed_runs must not be empty.", code="invalid_rules")
    for run in rules.allowed_runs:
        if run not in ALL_RUNS:
            raise ValidationError(
                "allowed_runs may only contain whole numbers from 0 to 6.", code="invalid_rules"
            )
    if rules.allowed_runs != tuple(sorted(set(rules.allowed_runs))):
        raise ValidationError("allowed_runs must be unique and sorted.", code="invalid_rules")

    unknown_retirements = [kind for kind in rules.retirement_types if kind not in RETIREMENT_TYPES]
    if unknown_retirements:
        raise ValidationError(
            "Unknown retirement type.",
            code="invalid_rules",
            details={"allowed": list(RETIREMENT_TYPES)},
        )
    if rules.retired_player_option and not rules.retirement_types:
        raise ValidationError(
            "Retirement types are required when the retired player option is on.",
            code="invalid_rules",
        )
    if rules.max_overs_per_bowler is not None and rules.max_overs_per_bowler > rules.overs:
        raise ValidationError(
            "max_overs_per_bowler cannot exceed the innings length.",
            code="invalid_rules",
            details={"field": "max_overs_per_bowler"},
        )
    return rules


def build_ruleset(preset_key: str, overrides: Mapping[str, Any] | None = None) -> RuleSet:
    """Resolve a preset plus user overrides into a validated, immutable RuleSet."""
    preset = get_preset(preset_key)
    base: RuleSet = preset["rules"]
    if overrides is None:
        return base
    if not isinstance(overrides, Mapping):
        raise ValidationError("rules must be an object.", code="invalid_rules")

    unknown = sorted(set(overrides) - EDITABLE_FIELDS)
    if unknown:
        raise ValidationError(
            "Unknown rule field(s).",
            code="invalid_rules",
            details={"fields": unknown, "editable": sorted(EDITABLE_FIELDS)},
        )

    values = base.to_dict()
    for field, raw_value in overrides.items():
        values[field] = _validated_value(field, raw_value)
    return validate_ruleset(RuleSet.from_dict(values))
