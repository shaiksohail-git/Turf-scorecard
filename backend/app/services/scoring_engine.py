"""Pure delivery scoring engine.

This module is the single place where a ball is interpreted. It turns the
match's frozen :class:`RuleSet`, a snapshot of the innings and one delivery
request into every derived value (runs, legality, over position, strike
rotation, free hit state, innings completion).

There is no database or Flask dependency beyond the shared validation
exception, so the same function is used for live scoring and for replaying
stored events. That is what keeps a corrected innings consistent with its
scorecard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import DeliveryValidationError
from .rules_engine import EXTRA_TYPES, WICKET_TYPES, RuleSet

# --- Dismissal rules ------------------------------------------------------
# On a free hit only running/obstruction dismissals are possible.
WICKETS_ON_FREE_HIT = frozenset({"run_out", "obstructing_the_field", "hit_the_ball_twice"})
# A wide can only produce a stumping or a running dismissal.
WICKETS_OFF_WIDE = frozenset({"stumped", "run_out", "obstructing_the_field", "hit_the_ball_twice"})
# A no-ball can only produce a running dismissal.
WICKETS_OFF_ILLEGAL_DELIVERY = WICKETS_ON_FREE_HIT
# Byes and leg byes are legal deliveries but no batter can be out off the bat.
WICKETS_OFF_BYE = WICKETS_ON_FREE_HIT
# These dismissals end the ball with no runs credited to the bat.
WICKETS_REQUIRING_ZERO_BAT_RUNS = frozenset(
    {"bowled", "caught", "lbw", "stumped", "hit_wicket", "timed_out"}
)
DISMISSAL_ROLES = ("striker", "non_striker")
MAX_EXTRA_RUNS = 6

PAYLOAD_KEYS = frozenset(
    {
        "runs_off_bat",
        "runs",
        "extra_type",
        "extra",
        "extra_runs",
        "is_wicket",
        "wicket_type",
        "dismissed_player",
        "striker_id",
        "non_striker_id",
        "bowler_id",
        "client_event_id",
        "expected_revision",
    }
)


@dataclass(frozen=True)
class DeliveryRequest:
    """A validated-in-shape delivery command coming from the scorer UI."""

    runs_off_bat: int = 0
    extra_type: str | None = None
    extra_runs: int = 0
    is_wicket: bool = False
    wicket_type: str | None = None
    dismissed_player: str | None = None
    striker_id: int | None = None
    non_striker_id: int | None = None
    bowler_id: int | None = None
    client_event_id: str | None = None
    expected_revision: int | None = None


@dataclass(frozen=True)
class InningsSnapshot:
    """Everything the engine needs to know about the innings so far."""

    legal_balls: int = 0
    wickets: int = 0
    runs: int = 0
    pending_free_hit: bool = False
    striker_id: int | None = None
    non_striker_id: int | None = None
    target: int | None = None
    is_complete: bool = False


@dataclass(frozen=True)
class DeliveryOutcome:
    """Fully derived result of one delivery."""

    over_number: int
    ball_in_over: int
    runs_off_bat: int
    extra_runs: int
    penalty_runs: int
    extras_runs: int
    total_runs: int
    is_legal_ball: bool
    is_free_hit: bool
    is_wicket: bool
    wicket_type: str | None
    dismissed_player: str | None
    strike_rotated: bool
    ends_over: bool
    free_hit_next: bool
    innings_complete: bool
    description: str


def _invalid(message: str, code: str, **details: Any) -> DeliveryValidationError:
    return DeliveryValidationError(message, code=code, details=details)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_runs(rules: RuleSet, request: DeliveryRequest) -> None:
    bat_runs = request.runs_off_bat
    if not _is_int(bat_runs):
        raise _invalid("runs_off_bat must be an integer.", "invalid_runs", field="runs_off_bat")
    if bat_runs < 0:
        raise _invalid("runs_off_bat cannot be negative.", "invalid_runs", field="runs_off_bat")
    if bat_runs not in rules.allowed_runs:
        raise _invalid(
            f"{bat_runs} run(s) off the bat is not allowed by these rules.",
            "runs_not_allowed",
            allowed_runs=list(rules.allowed_runs),
        )

    extra_runs = request.extra_runs
    if not _is_int(extra_runs):
        raise _invalid("extra_runs must be an integer.", "invalid_extra_runs", field="extra_runs")
    if extra_runs < 0:
        raise _invalid("extra_runs cannot be negative.", "invalid_extra_runs", field="extra_runs")
    if extra_runs > MAX_EXTRA_RUNS:
        raise _invalid(
            f"A delivery can carry at most {MAX_EXTRA_RUNS} extra runs.",
            "invalid_extra_runs",
            field="extra_runs",
        )

    if request.extra_type is None and extra_runs:
        raise _invalid(
            "extra_runs requires an extra_type.", "invalid_extra_runs", field="extra_runs"
        )
    if request.extra_type in {"wide", "bye", "leg_bye"} and bat_runs:
        raise _invalid(
            "No runs can be credited off the bat from a wide, bye or leg bye.",
            "invalid_runs",
            extra_type=request.extra_type,
        )
    if request.extra_type in {"bye", "leg_bye"} and extra_runs < 1:
        raise _invalid(
            "A bye or leg bye needs at least one run.",
            "invalid_extra_runs",
            extra_type=request.extra_type,
        )


def _validate_wicket(
    rules: RuleSet, snapshot: InningsSnapshot, request: DeliveryRequest
) -> None:
    if not request.is_wicket:
        if request.wicket_type is not None:
            raise _invalid(
                "wicket_type is only valid when is_wicket is true.", "wicket_type_without_wicket"
            )
        return

    wicket_type = request.wicket_type
    if wicket_type not in WICKET_TYPES:
        raise _invalid(
            f"Unknown wicket type '{wicket_type}'.",
            "invalid_wicket_type",
            allowed=list(WICKET_TYPES),
        )

    if snapshot.pending_free_hit and wicket_type not in WICKETS_ON_FREE_HIT:
        raise _invalid(
            "On a free hit only a run out, obstruction or hitting the ball twice can dismiss a batter.",
            "wicket_not_allowed_on_free_hit",
            wicket_type=wicket_type,
        )
    if request.extra_type == "wide" and wicket_type not in WICKETS_OFF_WIDE:
        raise _invalid(
            f"A batter cannot be {wicket_type} off a wide.",
            "wicket_not_allowed_off_wide",
            wicket_type=wicket_type,
        )
    if request.extra_type == "no_ball" and wicket_type not in WICKETS_OFF_ILLEGAL_DELIVERY:
        raise _invalid(
            f"A batter cannot be {wicket_type} off a no-ball.",
            "wicket_not_allowed_off_no_ball",
            wicket_type=wicket_type,
        )
    if request.extra_type in {"bye", "leg_bye"} and wicket_type not in WICKETS_OFF_BYE:
        raise _invalid(
            f"A batter cannot be {wicket_type} off a bye.",
            "wicket_not_allowed_off_bye",
            wicket_type=wicket_type,
        )
    if wicket_type in WICKETS_REQUIRING_ZERO_BAT_RUNS and request.runs_off_bat:
        raise _invalid(
            f"No runs can be credited to the bat when a batter is {wicket_type}.",
            "wicket_runs_conflict",
            wicket_type=wicket_type,
        )

    role = request.dismissed_player or "striker"
    if role not in DISMISSAL_ROLES:
        raise _invalid(
            "dismissed_player must be 'striker' or 'non_striker'.",
            "invalid_dismissed_player",
            allowed=list(DISMISSAL_ROLES),
        )
    if role == "non_striker":
        if wicket_type != "run_out":
            raise _invalid(
                "Only a run out can dismiss the non-striker.",
                "invalid_dismissal_role",
                wicket_type=wicket_type,
            )
        if snapshot.non_striker_id is None:
            raise _invalid(
                "There is no non-striker to dismiss.", "no_non_striker", wicket_type=wicket_type
            )
    if snapshot.wickets + 1 > rules.max_wickets:
        raise _invalid(
            "The innings has no wickets left.", "wicket_limit_reached", max_wickets=rules.max_wickets
        )


def _penalty_for(rules: RuleSet, extra_type: str | None) -> int:
    if extra_type == "wide":
        return rules.wide_penalty
    if extra_type == "no_ball":
        return rules.no_ball_penalty
    return 0


def _is_legal(rules: RuleSet, extra_type: str | None) -> bool:
    if extra_type == "wide":
        return rules.wide_counts_as_legal_ball
    if extra_type == "no_ball":
        return rules.no_ball_counts_as_legal_ball
    return True


_EXTRA_LABELS = {"wide": "Wide", "no_ball": "No ball", "bye": "Bye", "leg_bye": "Leg bye"}


def _describe(request: DeliveryRequest, total_runs: int, wicket_type: str | None) -> str:
    parts: list[str] = []
    if request.extra_type:
        parts.append(_EXTRA_LABELS[request.extra_type])
    if request.runs_off_bat:
        suffix = "" if request.runs_off_bat == 1 else "s"
        parts.append(f"{request.runs_off_bat} run{suffix} off the bat")
    elif request.extra_runs:
        suffix = "" if request.extra_runs == 1 else "s"
        parts.append(f"{request.extra_runs} run{suffix} run")
    if request.is_wicket and wicket_type:
        role = (request.dismissed_player or "striker").replace("_", " ")
        parts.append(f"wicket ({wicket_type.replace('_', ' ')}, {role})")
    if not parts:
        return "Dot ball"
    if total_runs and not request.is_wicket:
        parts.append(f"{total_runs} run{'s' if total_runs != 1 else ''} total")
    return ", ".join(parts)


def compute_delivery(
    rules: RuleSet,
    snapshot: InningsSnapshot,
    request: DeliveryRequest | Mapping[str, Any],
) -> DeliveryOutcome:
    """Interpret one delivery against the rules and the current innings state.

    Raises :class:`DeliveryValidationError` with a stable ``code`` for every
    rule violation, so the API can return precise feedback.
    """
    if isinstance(request, Mapping):
        request = parse_delivery_payload(request)
    if not isinstance(request, DeliveryRequest):
        raise TypeError("request must be a DeliveryRequest or a mapping")
    if snapshot.is_complete:
        raise _invalid("This innings is already complete.", "innings_complete")

    if request.extra_type is not None and request.extra_type not in EXTRA_TYPES:
        raise _invalid(
            f"Unknown extra type '{request.extra_type}'.",
            "invalid_extra_type",
            allowed=list(EXTRA_TYPES),
        )

    _validate_runs(rules, request)
    _validate_wicket(rules, snapshot, request)

    penalty_runs = _penalty_for(rules, request.extra_type)
    extras_runs = penalty_runs + request.extra_runs if request.extra_type else 0
    total_runs = request.runs_off_bat + extras_runs
    legal_ball = _is_legal(rules, request.extra_type)

    over_number = snapshot.legal_balls // rules.balls_per_over + 1
    ball_in_over = snapshot.legal_balls % rules.balls_per_over + 1
    legal_balls_after = snapshot.legal_balls + (1 if legal_ball else 0)
    wickets_after = snapshot.wickets + (1 if request.is_wicket else 0)

    # Penalty runs never rotate the strike; runs physically run do. With solo
    # batting there is no partner, so no rotation can happen.
    strike_rotated = (
        snapshot.non_striker_id is not None
        and (request.runs_off_bat + request.extra_runs) % 2 == 1
    )
    ends_over = legal_ball and legal_balls_after % rules.balls_per_over == 0

    # A free hit carries over if the free-hit delivery itself was illegal.
    free_hit_next = bool(
        rules.free_hit_enabled
        and (
            request.extra_type == "no_ball"
            or (snapshot.pending_free_hit and not legal_ball)
        )
    )

    innings_complete = (
        legal_balls_after >= rules.total_balls or wickets_after >= rules.max_wickets
    )
    if snapshot.target is not None and snapshot.runs + total_runs >= snapshot.target:
        innings_complete = True

    return DeliveryOutcome(
        over_number=over_number,
        ball_in_over=ball_in_over,
        runs_off_bat=request.runs_off_bat,
        extra_runs=request.extra_runs,
        penalty_runs=penalty_runs,
        extras_runs=extras_runs,
        total_runs=total_runs,
        is_legal_ball=legal_ball,
        is_free_hit=snapshot.pending_free_hit,
        is_wicket=request.is_wicket,
        wicket_type=request.wicket_type if request.is_wicket else None,
        dismissed_player=(request.dismissed_player or "striker") if request.is_wicket else None,
        strike_rotated=strike_rotated,
        ends_over=ends_over,
        free_hit_next=free_hit_next,
        innings_complete=innings_complete,
        description=_describe(request, total_runs, request.wicket_type if request.is_wicket else None),
    )


def _optional_id(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if not _is_int(value) or value <= 0:
        raise _invalid(f"{field} must be a positive integer.", "invalid_player_id", field=field)
    return value


def parse_delivery_payload(payload: Mapping[str, Any]) -> DeliveryRequest:
    """Validate the shape of a delivery payload (rule checks happen later)."""
    if not isinstance(payload, Mapping):
        raise _invalid("Request body must be a JSON object.", "invalid_body")

    unknown = sorted(set(payload) - PAYLOAD_KEYS)
    if unknown:
        raise _invalid(
            "Unknown delivery field(s).",
            "unknown_fields",
            fields=unknown,
            allowed=sorted(PAYLOAD_KEYS),
        )

    # Aliases are accepted for convenience, but two disagreeing values are a
    # malformed command rather than something to guess about.
    if "runs" in payload and "runs_off_bat" in payload:
        if payload["runs"] != payload["runs_off_bat"]:
            raise _invalid(
                "runs and runs_off_bat must agree when both are supplied.",
                "conflicting_fields",
                fields=["runs", "runs_off_bat"],
            )
    if "extra" in payload and "extra_type" in payload:
        alias = payload["extra"]
        canonical = payload["extra_type"]
        alias_key = alias.strip().lower() or None if isinstance(alias, str) else alias
        canonical_key = (
            canonical.strip().lower() or None if isinstance(canonical, str) else canonical
        )
        if alias_key != canonical_key:
            raise _invalid(
                "extra and extra_type must agree when both are supplied.",
                "conflicting_fields",
                fields=["extra", "extra_type"],
            )

    runs = payload.get("runs_off_bat", payload.get("runs", 0))
    extra_type = payload.get("extra_type", payload.get("extra"))
    extra_runs = payload.get("extra_runs", 0)
    is_wicket = payload.get("is_wicket", False)
    wicket_type = payload.get("wicket_type")
    dismissed_player = payload.get("dismissed_player")
    client_event_id = payload.get("client_event_id")
    expected_revision = payload.get("expected_revision")

    if isinstance(extra_type, str):
        extra_type = extra_type.strip().lower() or None
    if isinstance(wicket_type, str):
        wicket_type = wicket_type.strip().lower() or None
    if isinstance(dismissed_player, str):
        dismissed_player = dismissed_player.strip().lower() or None

    if not isinstance(is_wicket, bool):
        raise _invalid("is_wicket must be true or false.", "invalid_wicket_flag")
    if not _is_int(runs):
        raise _invalid("runs_off_bat must be an integer.", "invalid_runs", field="runs_off_bat")
    if not _is_int(extra_runs):
        raise _invalid("extra_runs must be an integer.", "invalid_extra_runs", field="extra_runs")
    if extra_type is not None and not isinstance(extra_type, str):
        raise _invalid("extra_type must be a string.", "invalid_extra_type")
    if is_wicket and not isinstance(wicket_type, str):
        raise _invalid("wicket_type is required for a wicket.", "invalid_wicket_type")
    if not is_wicket and wicket_type is not None:
        raise _invalid(
            "wicket_type is only valid when is_wicket is true.", "wicket_type_without_wicket"
        )
    if client_event_id is not None:
        if not isinstance(client_event_id, str) or not client_event_id.strip():
            raise _invalid("client_event_id must be a non-empty string.", "invalid_client_event_id")
        client_event_id = client_event_id.strip()
        if len(client_event_id) > 64:
            raise _invalid("client_event_id is too long.", "invalid_client_event_id")
    if expected_revision is not None:
        if not _is_int(expected_revision) or expected_revision < 0:
            raise _invalid(
                "expected_revision must be a non-negative integer.", "invalid_expected_revision"
            )

    return DeliveryRequest(
        runs_off_bat=runs,
        extra_type=extra_type,
        extra_runs=extra_runs,
        is_wicket=is_wicket,
        wicket_type=wicket_type,
        dismissed_player=dismissed_player,
        striker_id=_optional_id(payload.get("striker_id"), "striker_id"),
        non_striker_id=_optional_id(payload.get("non_striker_id"), "non_striker_id"),
        bowler_id=_optional_id(payload.get("bowler_id"), "bowler_id"),
        client_event_id=client_event_id,
        expected_revision=expected_revision,
    )
