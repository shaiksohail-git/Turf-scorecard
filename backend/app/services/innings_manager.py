"""Innings state, delivery recording and safe undo.

Every scoring mutation runs in one database transaction: the innings row is
locked, the delivery is validated against a replay of the current events,
persisted, and the innings aggregates are recomputed from the events before the
commit. Deliveries are never deleted - an undo marks the last delivery void and
replays the innings, which keeps the audit trail intact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ..errors import ConflictError, NotFoundError, ValidationError
from ..extensions import db
from ..models import Delivery, Innings, Match, MatchEvent, Player, Retirement, utcnow
from .rules_engine import RuleSet
from .scoring_engine import (
    DeliveryRequest,
    InningsSnapshot,
    compute_delivery,
    parse_delivery_payload,
)


@dataclass
class LiveState:
    """Replay-derived state of an innings after its last active event."""

    striker_id: int | None
    non_striker_id: int | None
    next_batter_index: int
    pending_free_hit: bool
    legal_balls: int
    wickets: int
    runs: int
    is_complete: bool
    target: int | None = None
    last_bowler_id: int | None = None
    solo_mode: bool = False
    out_player_ids: tuple[int, ...] = ()
    retired_out_ids: tuple[int, ...] = ()
    retired_active_ids: tuple[int, ...] = ()
    returned_player_ids: tuple[int, ...] = ()
    available_player_ids: tuple[int, ...] = ()

    @property
    def can_score(self) -> bool:
        return self.striker_id is not None and not self.is_complete

    def snapshot(self) -> InningsSnapshot:
        return InningsSnapshot(
            legal_balls=self.legal_balls,
            wickets=self.wickets,
            runs=self.runs,
            pending_free_hit=self.pending_free_hit,
            striker_id=self.striker_id,
            non_striker_id=self.non_striker_id,
            target=self.target,
            is_complete=self.is_complete,
        )


# --- lookups --------------------------------------------------------------


def get_innings(innings_id: int) -> Innings:
    innings = db.session.get(Innings, innings_id)
    if innings is None:
        raise NotFoundError("Innings not found.", details={"innings_id": innings_id})
    return innings


def get_match_for(innings: Innings) -> Match:
    match = db.session.get(Match, innings.match_id)
    if match is None:
        raise NotFoundError("Match not found for this innings.", details={"innings_id": innings.id})
    return match


def rules_for_match(match: Match) -> RuleSet:
    return RuleSet.from_dict(match.rules)


def active_deliveries(innings: Innings) -> list[Delivery]:
    """Non-voided deliveries in scoring order, queried fresh from the database."""
    rows = db.session.execute(
        select(Delivery)
        .where(Delivery.innings_id == innings.id, Delivery.is_voided.is_(False))
        .order_by(Delivery.sequence)
    ).scalars()
    return list(rows)


def all_deliveries(innings: Innings) -> list[Delivery]:
    rows = db.session.execute(
        select(Delivery)
        .where(Delivery.innings_id == innings.id)
        .order_by(Delivery.sequence)
    ).scalars()
    return list(rows)


def retirements_for(innings: Innings) -> list[Retirement]:
    """Retirement events for an innings, in the order they happened."""
    rows = db.session.execute(
        select(Retirement)
        .where(Retirement.innings_id == innings.id)
        .order_by(Retirement.retired_after_sequence, Retirement.id)
    ).scalars()
    return list(rows)


# --- replay ---------------------------------------------------------------


def replay(
    innings: Innings,
    rules: RuleSet,
    deliveries: list[Delivery],
    retirements: list[Retirement] | None = None,
) -> LiveState:
    """Rebuild the live innings state from deliveries and retirements.

    A retirement is anchored to the number of deliveries that had been scored
    when it happened, so replay can place it between the correct balls. A
    non-dismissal retirement removes the batter from the crease without adding a
    wicket; ``retired_out`` does add one. Solo batting keeps the last batter on
    strike once no partner is left and disables normal strike rotation.
    """
    retirements = list(retirements or [])
    order = [int(player_id) for player_id in (innings.batting_order or [])]

    retired_at: dict[int, list[Retirement]] = {}
    returned_at: dict[int, list[Retirement]] = {}
    for row in retirements:
        retired_at.setdefault(row.retired_after_sequence, []).append(row)
        if row.returned_after_sequence is not None:
            returned_at.setdefault(row.returned_after_sequence, []).append(row)

    striker = order[0] if order else None
    non_striker = order[1] if len(order) > 1 else None
    next_index = 2 if len(order) > 1 else len(order)

    pending_free_hit = False
    legal_balls = 0
    wickets = 0
    runs = 0
    last_bowler_id = None
    retirement_wickets = 0
    out_ids: set[int] = set()
    retired_out: set[int] = set()
    retired_active: dict[int, str] = {}
    returned_queue: list[int] = []
    applied_sequences: set[int] = set()

    def take_batter() -> int | None:
        """Return the next eligible batter: a return first, then batting order."""
        nonlocal next_index
        while returned_queue:
            candidate = returned_queue.pop(0)
            if candidate in out_ids or candidate in retired_active or candidate in retired_out:
                continue
            if candidate in {striker, non_striker}:
                continue
            return candidate
        while next_index < len(order):
            candidate = order[next_index]
            next_index += 1
            if candidate in out_ids or candidate in retired_active or candidate in retired_out:
                continue
            if candidate in {striker, non_striker}:
                continue
            return candidate
        return None

    def apply_retirement(row: Retirement) -> None:
        nonlocal striker, non_striker, retirement_wickets
        player_id = row.player_id
        if player_id == striker:
            slot = "striker"
        elif player_id == non_striker:
            slot = "non_striker"
        else:
            # The event no longer matches the crease (for example after an undo).
            return

        replacement = row.replacement_player_id
        if replacement is not None and (
            replacement in out_ids
            or replacement in retired_active
            or replacement in retired_out
            or replacement in {striker, non_striker}
        ):
            replacement = None
        if replacement is None:
            replacement = take_batter()

        if slot == "striker":
            striker = replacement
        else:
            non_striker = replacement

        if row.retirement_type == "retired_out":
            out_ids.add(player_id)
            retired_out.add(player_id)
            retirement_wickets += 1
        else:
            retired_active[player_id] = row.retirement_type

        if replacement is None:
            survivor = non_striker if slot == "striker" else striker
            if survivor is not None:
                striker, non_striker = survivor, None

    def apply_return(row: Retirement) -> None:
        nonlocal striker, non_striker
        player_id = row.player_id
        if player_id in out_ids or player_id in retired_out:
            return
        retired_active.pop(player_id, None)
        if player_id in {striker, non_striker}:
            return
        if striker is None:
            striker = player_id
        elif non_striker is None:
            non_striker = player_id
        else:
            returned_queue.append(player_id)

    def apply_events(sequence: int) -> None:
        if sequence in applied_sequences:
            return
        applied_sequences.add(sequence)
        for retirement in retired_at.get(sequence, []):
            apply_retirement(retirement)
        for retirement in returned_at.get(sequence, []):
            apply_return(retirement)

    for index, row in enumerate(deliveries):
        apply_events(index)

        runs += row.total_runs
        legal_balls += 1 if row.is_legal_ball else 0
        wickets += 1 if row.is_wicket else 0
        last_bowler_id = row.bowler_id

        if row.is_wicket:
            if row.dismissed_player_id is not None:
                out_ids.add(row.dismissed_player_id)
            dismissed_non_striker = (
                row.dismissed_player_id is not None
                and row.dismissed_player_id == non_striker
            )
            if dismissed_non_striker:
                non_striker = None
            else:
                striker = None
            incoming = take_batter()
            if incoming is not None:
                if dismissed_non_striker:
                    non_striker = incoming
                else:
                    striker = incoming
            else:
                survivor = non_striker if dismissed_non_striker else striker
                if survivor is not None:
                    # One batter left: solo mode keeps them on strike, otherwise
                    # the innings waits for a retirement to be reversed.
                    striker, non_striker = survivor, None

        # In solo mode there is no partner to rotate with.
        if (
            (row.runs_off_bat + row.extra_runs) % 2 == 1
            and striker is not None
            and non_striker is not None
        ):
            striker, non_striker = non_striker, striker

        if row.is_legal_ball and legal_balls % rules.balls_per_over == 0:
            if striker is not None and non_striker is not None:
                striker, non_striker = non_striker, striker

        pending_free_hit = bool(
            rules.free_hit_enabled
            and (
                row.extra_type == "no_ball"
                or (row.is_free_hit and not row.is_legal_ball)
            )
        )

    apply_events(len(deliveries))

    wickets += retirement_wickets
    has_returnable = any(
        row.returned_at is None and row.retirement_type != "retired_out"
        for row in retirements
    )
    available = [
        player_id
        for player_id in order[next_index:]
        if player_id not in out_ids
        and player_id not in retired_active
        and player_id not in retired_out
        and player_id not in {striker, non_striker}
    ]
    solo_mode = bool(
        rules.solo_batting_enabled and striker is not None and non_striker is None
    )

    is_complete = _is_complete(
        rules=rules,
        has_events=bool(deliveries or retirements),
        legal_balls=legal_balls,
        wickets=wickets,
        runs=runs,
        striker=striker,
        non_striker=non_striker,
        target=innings.target,
        has_returnable=has_returnable,
        waiting=bool(returned_queue or available),
    )
    return LiveState(
        striker_id=striker,
        non_striker_id=non_striker,
        next_batter_index=next_index,
        pending_free_hit=pending_free_hit,
        legal_balls=legal_balls,
        wickets=wickets,
        runs=runs,
        is_complete=is_complete,
        target=innings.target,
        last_bowler_id=last_bowler_id,
        solo_mode=solo_mode,
        out_player_ids=tuple(sorted(out_ids)),
        retired_out_ids=tuple(sorted(retired_out)),
        retired_active_ids=tuple(sorted(retired_active)),
        returned_player_ids=tuple(row.player_id for row in retirements if row.returned_at),
        available_player_ids=tuple(available),
    )


def _is_complete(
    *,
    rules: RuleSet,
    has_events: bool,
    legal_balls: int,
    wickets: int,
    runs: int,
    striker: int | None,
    non_striker: int | None,
    target: int | None,
    has_returnable: bool,
    waiting: bool,
) -> bool:
    if not has_events:
        return False
    if legal_balls >= rules.total_balls:
        return True
    if wickets >= rules.max_wickets:
        return True
    if target is not None and runs >= target:
        return True
    if striker is None:
        # Nobody at the crease: the innings is only over if no retired batter
        # can return and no eligible batter is waiting.
        return not (has_returnable or waiting)
    if non_striker is None and not rules.solo_batting_enabled:
        # Solo batting is switched off, so one batter cannot continue alone.
        return not has_returnable
    return False


def current_state(innings: Innings) -> LiveState:
    rules = rules_for_match(get_match_for(innings))
    return replay(
        innings, rules, active_deliveries(innings), retirements_for(innings)
    )


# --- scoring --------------------------------------------------------------


def _lock_innings(innings: Innings) -> None:
    """Take a row lock in PostgreSQL; SQLite (tests) has no row locking."""
    if db.engine.dialect.name == "sqlite":
        return
    db.session.execute(
        select(Innings).where(Innings.id == innings.id).with_for_update()
    ).scalar_one()


def _require_bowler(innings: Innings, bowler_id: int) -> Player:
    bowler = db.session.get(Player, bowler_id)
    if bowler is None:
        raise ValidationError(
            "Bowler not found.", details={"field": "bowler_id", "bowler_id": bowler_id}
        )
    if bowler.team_id != innings.bowling_team_id:
        raise ValidationError(
            "The bowler must belong to the bowling team.",
            details={"field": "bowler_id", "bowler_id": bowler_id},
        )
    return bowler


def _validate_bowler_quota(
    deliveries: list[Delivery], bowler_id: int, rules: RuleSet
) -> None:
    if rules.max_overs_per_bowler is None:
        return
    balls_bowled = sum(
        1 for row in deliveries if row.bowler_id == bowler_id and row.is_legal_ball
    )
    limit = rules.max_overs_per_bowler * rules.balls_per_over
    if balls_bowled >= limit:
        raise ConflictError(
            f"This bowler has already bowled the maximum of {rules.max_overs_per_bowler} over(s).",
            code="bowler_over_limit",
            details={"bowler_id": bowler_id, "limit_overs": rules.max_overs_per_bowler},
        )


def _resolve_players(
    innings: Innings, state: LiveState, request: DeliveryRequest, rules: RuleSet
) -> tuple[int, int | None, int]:
    if state.striker_id is None:
        raise ConflictError(
            "There is no striker on the field. A retired batter may need to return.",
            code="no_striker",
        )
    if state.non_striker_id is None and not rules.solo_batting_enabled:
        raise ConflictError(
            "Only one batter remains and solo batting is disabled for this match.",
            code="solo_batting_disabled",
        )

    striker_id = request.striker_id if request.striker_id is not None else state.striker_id
    if striker_id != state.striker_id:
        raise ConflictError(
            "The striker changed. Refresh the scorecard and try again.",
            code="striker_mismatch",
            details={"expected": state.striker_id, "received": striker_id},
        )

    non_striker_id = (
        request.non_striker_id if request.non_striker_id is not None else state.non_striker_id
    )
    if non_striker_id != state.non_striker_id:
        raise ConflictError(
            "The non-striker changed. Refresh the scorecard and try again.",
            code="non_striker_mismatch",
            details={"expected": state.non_striker_id, "received": non_striker_id},
        )

    if request.bowler_id is None:
        raise ValidationError(
            "bowler_id is required to record a delivery.", details={"field": "bowler_id"}
        )
    _require_bowler(innings, request.bowler_id)
    return striker_id, non_striker_id, request.bowler_id


def _find_client_event(innings_id: int, client_event_id: str) -> Delivery | None:
    return db.session.execute(
        select(Delivery).where(
            Delivery.innings_id == innings_id,
            Delivery.client_event_id == client_event_id,
        )
    ).scalar_one_or_none()


def record_delivery(
    innings: Innings, payload: Mapping[str, Any], actor: str = "scorer"
) -> tuple[Delivery, LiveState, bool]:
    """Record one delivery exactly once, in a single transaction.

    The unique ``(innings_id, client_event_id)`` constraint is the source of
    truth for idempotency, not the pre-check: if two requests carrying the same
    event id race, the loser hits the constraint and the stored delivery is
    returned as a duplicate instead of scoring the ball twice. A lost response
    can therefore be retried safely.

    Returns ``(delivery, state, duplicate)``.
    """
    match = get_match_for(innings)
    rules = rules_for_match(match)
    request = parse_delivery_payload(payload)

    if request.client_event_id:
        existing = _find_client_event(innings.id, request.client_event_id)
        if existing is not None:
            return existing, current_state(innings), True

    if match.status != "live":
        raise ConflictError(
            "This match is not live.", code="match_not_live", details={"status": match.status}
        )
    if innings.status != "live":
        raise ConflictError(
            "This innings is not live.",
            code="innings_not_live",
            details={"status": innings.status},
        )

    last_integrity_error: IntegrityError | None = None
    # Two attempts: the second exists only to survive a sequence collision
    # between two different deliveries; a repeated event is resolved as a
    # duplicate on the first attempt.
    for attempt in range(2):
        try:
            _lock_innings(innings)
            db.session.refresh(innings)

            # Re-check under the lock: a concurrent request may have committed
            # this exact event after the fast path above.
            if request.client_event_id:
                existing = _find_client_event(innings.id, request.client_event_id)
                if existing is not None:
                    db.session.rollback()
                    return existing, current_state(innings), True

            if innings.status != "live":
                raise ConflictError(
                    "This innings is not live.",
                    code="innings_not_live",
                    details={"status": innings.status},
                )

            deliveries = active_deliveries(innings)
            state = replay(innings, rules, deliveries, retirements_for(innings))

            if (
                request.expected_revision is not None
                and request.expected_revision != innings.revision
            ):
                raise ConflictError(
                    "The score changed since this delivery was prepared.",
                    code="stale_revision",
                    details={"expected": request.expected_revision, "actual": innings.revision},
                )

            striker_id, non_striker_id, bowler_id = _resolve_players(
                innings, state, request, rules
            )
            outcome = compute_delivery(rules, state.snapshot(), request)
            _validate_bowler_quota(deliveries, bowler_id, rules)

            max_sequence = (
                db.session.execute(
                    select(func.max(Delivery.sequence)).where(Delivery.innings_id == innings.id)
                ).scalar()
                or 0
            )
            delivery = Delivery(
                innings_id=innings.id,
                sequence=max_sequence + 1,
                client_event_id=request.client_event_id,
                over_number=outcome.over_number,
                ball_in_over=outcome.ball_in_over,
                striker_id=striker_id,
                non_striker_id=non_striker_id,
                bowler_id=bowler_id,
                runs_off_bat=outcome.runs_off_bat,
                extra_type=request.extra_type,
                extra_runs=outcome.extra_runs,
                penalty_runs=outcome.penalty_runs,
                total_runs=outcome.total_runs,
                is_legal_ball=outcome.is_legal_ball,
                is_free_hit=outcome.is_free_hit,
                is_wicket=outcome.is_wicket,
                wicket_type=outcome.wicket_type,
                dismissed_player_id=(
                    non_striker_id
                    if outcome.dismissed_player == "non_striker"
                    else striker_id
                )
                if outcome.is_wicket
                else None,
                dismissed_role=outcome.dismissed_player,
            )
            db.session.add(delivery)
            db.session.flush()

            _recompute_innings(innings, match, rules)
            record_audit(
                match,
                innings.id,
                delivery.id,
                "delivery.recorded",
                {
                    "sequence": delivery.sequence,
                    "over": delivery.over_number,
                    "ball": delivery.ball_in_over,
                    "total_runs": delivery.total_runs,
                    "extra_type": delivery.extra_type,
                    "is_wicket": delivery.is_wicket,
                    "wicket_type": delivery.wicket_type,
                    "description": outcome.description,
                },
                actor,
            )
            db.session.commit()
            return delivery, current_state(innings), False
        except IntegrityError as exc:
            # Either this event committed elsewhere (return it), or another
            # delivery took the next sequence number (retry once).
            db.session.rollback()
            last_integrity_error = exc
            if request.client_event_id:
                existing = _find_client_event(innings.id, request.client_event_id)
                if existing is not None:
                    return existing, current_state(innings), True
            if attempt == 0:
                continue
            raise ConflictError(
                "Another delivery was saved at the same time. Reload the innings and try again.",
                code="delivery_conflict",
                details={"innings_id": innings.id},
            ) from exc
        except Exception:
            db.session.rollback()
            raise

    raise ConflictError(
        "Another delivery was saved at the same time. Reload the innings and try again.",
        code="delivery_conflict",
        details={"innings_id": innings.id},
    ) from last_integrity_error


def undo_last_delivery(
    innings: Innings, reason: str | None = None, actor: str = "scorer"
) -> tuple[Delivery, LiveState]:
    """Void the last active delivery and replay the innings.

    The delivery row stays in the database marked void so the audit trail and
    the original event are preserved.
    """
    match = get_match_for(innings)
    rules = rules_for_match(match)

    if innings.number == 1:
        second = _innings_by_number(match, 2)
        if second is not None and active_deliveries(second):
            raise ConflictError(
                "The second innings has started, so this delivery can no longer be undone.",
                code="later_innings_started",
            )

    try:
        _lock_innings(innings)
        deliveries = active_deliveries(innings)
        if not deliveries:
            raise ConflictError("There is no delivery to undo.", code="nothing_to_undo")

        last = deliveries[-1]
        last.is_voided = True
        last.voided_at = utcnow()
        last.void_reason = (reason or "Undo last delivery")[:200]
        db.session.flush()

        _recompute_innings(innings, match, rules)
        record_audit(
            match,
            innings.id,
            last.id,
            "delivery.voided",
            {
                "sequence": last.sequence,
                "reason": last.void_reason,
                "total_runs": last.total_runs,
                "is_wicket": last.is_wicket,
            },
            actor,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return last, current_state(innings)


# --- aggregates / lifecycle ----------------------------------------------


def _innings_by_number(match: Match, number: int) -> Innings | None:
    return db.session.execute(
        select(Innings).where(Innings.match_id == match.id, Innings.number == number)
    ).scalar_one_or_none()


def _recompute_innings(innings: Innings, match: Match, rules: RuleSet) -> None:
    """Recompute stored aggregates and move the match lifecycle forward."""
    state = replay(
        innings, rules, active_deliveries(innings), retirements_for(innings)
    )

    innings.total_runs = state.runs
    innings.wickets = state.wickets
    innings.legal_balls = state.legal_balls
    innings.status = "completed" if state.is_complete else "live"
    innings.revision = (innings.revision or 0) + 1
    match.revision = (match.revision or 0) + 1
    db.session.flush()

    if innings.number == 1 and innings.status == "completed":
        _activate_second_innings(match, innings)
    elif innings.number == 1 and innings.status == "live":
        _deactivate_second_innings(match, innings)
    elif innings.number == 2:
        if innings.status == "completed":
            _finalise_match(match, innings)
        elif match.status == "completed":
            # An undo reopened the chase.
            match.status = "live"
            match.result = None
            match.completed_at = None

    # Player statistics are a projection of the events, refreshed in the same
    # transaction. Imported lazily to avoid a circular import at module load.
    from .stats_manager import rebuild_player_match_stats

    rebuild_player_match_stats(match)


def _activate_second_innings(match: Match, first: Innings) -> None:
    second = _innings_by_number(match, 2)
    if second is None or second.status != "pending":
        return
    second.status = "live"
    second.target = first.total_runs + 1


def _deactivate_second_innings(match: Match, first: Innings) -> None:
    """If the first innings was reopened before the chase began, park it again."""
    second = _innings_by_number(match, 2)
    if second is None or second.status != "live":
        return
    if active_deliveries(second):
        return
    second.status = "pending"
    second.target = None


def _team_name(match: Match, team_id: int | None) -> str:
    if team_id is not None and match.team_a is not None and team_id == match.team_a.id:
        return match.team_a.name
    if team_id is not None and match.team_b is not None and team_id == match.team_b.id:
        return match.team_b.name
    return "Team"


def _finalise_match(match: Match, second: Innings) -> None:
    first = _innings_by_number(match, 1)
    if first is None or second.target is None:
        return
    rules = rules_for_match(match)

    if second.total_runs >= second.target:
        margin = rules.max_wickets - second.wickets
        winner_team_id = second.batting_team_id
        outcome = "wickets"
        summary = f"{_team_name(match, winner_team_id)} won by {margin} wicket(s)"
    elif second.total_runs == first.total_runs:
        margin = 0
        winner_team_id = None
        outcome = "tie"
        summary = "Match tied"
    else:
        margin = first.total_runs - second.total_runs
        winner_team_id = first.batting_team_id
        outcome = "runs"
        summary = f"{_team_name(match, winner_team_id)} won by {margin} run(s)"

    match.status = "completed"
    match.completed_at = utcnow()
    match.result = {
        "winner_team_id": winner_team_id,
        "outcome": outcome,
        "margin": margin,
        "summary": summary,
        "first_innings_runs": first.total_runs,
        "second_innings_runs": second.total_runs,
    }


def record_audit(
    match: Match,
    innings_id: int | None,
    delivery_id: int | None,
    event_type: str,
    payload: Mapping[str, Any] | None,
    actor: str = "scorer",
) -> MatchEvent:
    entry = MatchEvent(
        match_id=match.id,
        innings_id=innings_id,
        delivery_id=delivery_id,
        event_type=event_type,
        actor=(actor or "scorer")[:64],
        payload=dict(payload or {}),
    )
    db.session.add(entry)
    return entry
