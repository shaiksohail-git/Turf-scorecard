"""Retirement and return-to-batting commands.

Retirements are separate innings events, not deliveries. The rule set decides
which types are enabled; ``retired_out`` adds a wicket and is final, while the
other two types leave the batter eligible to return later.
"""

from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import select

from ..errors import ConflictError, NotFoundError, ValidationError
from ..extensions import db
from ..models import Innings, Player, Retirement, Team, utcnow
from .innings_manager import (
    _lock_innings,
    _recompute_innings,
    active_deliveries,
    current_state,
    get_match_for,
    record_audit,
    rules_for_match,
)


def list_retirements(innings: Innings) -> list[Retirement]:
    return list(
        db.session.execute(
            select(Retirement)
            .where(Retirement.innings_id == innings.id)
            .order_by(Retirement.retired_after_sequence, Retirement.id)
        ).scalars()
    )


def _batting_team(innings: Innings) -> Team:
    team = db.session.get(Team, innings.batting_team_id)
    if team is None:
        raise ValidationError("The batting team for this innings no longer exists.")
    return team


def eligible_replacements(innings: Innings) -> list[Player]:
    """Players who may come in for a retired batter, in batting order."""
    state = current_state(innings)
    at_crease = {state.striker_id, state.non_striker_id}
    excluded = (
        at_crease
        | set(state.out_player_ids)
        | set(state.retired_out_ids)
        | set(state.retired_active_ids)
    )
    return [
        player
        for player in sorted(_batting_team(innings).players, key=lambda p: p.batting_order)
        if player.id not in excluded
    ]


def record_retirement(
    innings: Innings, payload: Mapping[str, Any], actor: str = "scorer"
) -> Retirement:
    match = get_match_for(innings)
    rules = rules_for_match(match)
    if not isinstance(payload, Mapping):
        raise ValidationError("The JSON body must be an object.", code="invalid_body")
    if match.status != "live" or innings.status != "live":
        raise ConflictError(
            "A batter can only retire while the innings is live.",
            code="innings_not_live",
            details={"status": innings.status},
        )
    if not rules.retired_player_option:
        raise ConflictError(
            "Retirements are disabled for this match.", code="retirements_disabled"
        )

    retirement_type = payload.get("retirement_type")
    if retirement_type not in rules.retirement_types:
        raise ValidationError(
            "Unknown retirement type for this match.",
            details={
                "field": "retirement_type",
                "allowed": list(rules.retirement_types),
            },
        )

    player_id = payload.get("player_id")
    if isinstance(player_id, bool) or not isinstance(player_id, int):
        raise ValidationError(
            "player_id is required.", details={"field": "player_id"}
        )

    reason = payload.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise ValidationError("reason must be a string.", details={"field": "reason"})

    state = current_state(innings)
    if player_id not in {state.striker_id, state.non_striker_id}:
        raise ValidationError(
            "That player is not at the crease.",
            details={"field": "player_id", "player_id": player_id},
        )

    active = db.session.execute(
        select(Retirement).where(
            Retirement.innings_id == innings.id,
            Retirement.player_id == player_id,
            Retirement.returned_at.is_(None),
            Retirement.retirement_type != "retired_out",
        )
    ).scalar_one_or_none()
    if active is not None:
        raise ConflictError(
            "That player has already retired and has not returned.",
            code="already_retired",
        )

    replacement_id = payload.get("replacement_player_id")
    if replacement_id is not None:
        if isinstance(replacement_id, bool) or not isinstance(replacement_id, int):
            raise ValidationError(
                "replacement_player_id must be a player id.",
                details={"field": "replacement_player_id"},
            )
        if replacement_id == player_id:
            raise ValidationError(
                "A batter cannot replace themselves.",
                details={"field": "replacement_player_id"},
            )
        allowed = {player.id for player in eligible_replacements(innings)}
        if replacement_id not in allowed:
            raise ValidationError(
                "The replacement batter is not eligible to bat.",
                details={"field": "replacement_player_id"},
            )
    else:
        candidates = eligible_replacements(innings)
        replacement_id = candidates[0].id if candidates else None

    try:
        _lock_innings(innings)
        db.session.refresh(innings)
        state = current_state(innings)
        event = Retirement(
            innings_id=innings.id,
            player_id=player_id,
            retirement_type=retirement_type,
            reason=(reason or "").strip()[:200] or None,
            replacement_player_id=replacement_id,
            retired_after_sequence=len(active_deliveries(innings)),
            retired_at=utcnow(),
        )
        db.session.add(event)
        db.session.flush()

        _recompute_innings(innings, match, rules)
        record_audit(
            match,
            innings.id,
            None,
            "player.retired",
            {
                "player_id": player_id,
                "retirement_type": retirement_type,
                "reason": event.reason,
                "replacement_player_id": replacement_id,
            },
            actor,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return event


def return_to_batting(
    innings: Innings, retirement_id: int, actor: str = "scorer"
) -> Retirement:
    match = get_match_for(innings)
    rules = rules_for_match(match)
    retirement = db.session.get(Retirement, retirement_id)
    if retirement is None or retirement.innings_id != innings.id:
        raise NotFoundError(
            "Retirement not found for this innings.",
            details={"retirement_id": retirement_id},
        )
    if retirement.retirement_type == "retired_out":
        raise ConflictError(
            "A retired out batter cannot return.", code="retired_out_cannot_return"
        )
    if retirement.returned_at is not None:
        raise ConflictError("That batter has already returned.", code="already_returned")
    if match.status != "live" or innings.status != "live":
        raise ConflictError(
            "A batter can only return while the innings is live.",
            code="innings_not_live",
        )

    state = current_state(innings)
    if retirement.player_id in state.out_player_ids:
        raise ConflictError("That batter is out and cannot return.", code="batter_out")

    try:
        _lock_innings(innings)
        db.session.refresh(innings)
        retirement.returned_after_sequence = len(active_deliveries(innings))
        retirement.returned_at = utcnow()
        db.session.flush()

        _recompute_innings(innings, match, rules)
        record_audit(
            match,
            innings.id,
            None,
            "player.returned",
            {"player_id": retirement.player_id, "retirement_id": retirement.id},
            actor,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return retirement
