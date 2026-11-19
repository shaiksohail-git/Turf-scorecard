"""Derived statistics.

Every number here is computed from delivery events and retirement events rather
than from stored running totals. After an undo or a retirement the scorecard is
rebuilt from those events, so historical cards stay correct.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .rules_engine import RuleSet

# Bowlers are credited with these dismissals; run outs and obstructions are not.
BOWLER_CREDIT_WICKETS = frozenset({"bowled", "caught", "lbw", "stumped", "hit_wicket"})

EXTRA_LABELS = {"wide": "wide", "no_ball": "no-ball", "bye": "bye", "leg_bye": "leg bye"}

RETIREMENT_LABELS = {
    "retired_not_out": "Retired not out",
    "retired_out": "Retired out",
    "retired_hurt": "Retired hurt",
}


def overs_label(legal_balls: int, balls_per_over: int = 6) -> str:
    """Render cricket's ``overs.balls`` notation."""
    if balls_per_over <= 0:
        return "0.0"
    return f"{legal_balls // balls_per_over}.{legal_balls % balls_per_over}"


def _dismissal_text(delivery, names: Mapping[int, str]) -> str:
    kind = (delivery.wicket_type or "out").replace("_", " ")
    return kind[:1].upper() + kind[1:]


def _batting_line(player_id: int, name: str, order: int) -> dict[str, Any]:
    return {
        "player_id": player_id,
        "name": name,
        "order": order,
        "runs": 0,
        "balls": 0,
        "fours": 0,
        "sixes": 0,
        "is_out": False,
        "dismissal": None,
        "retirement_type": None,
        "returned_to_bat": False,
        "strike_rate": 0.0,
    }


def _retirement_rows(retirements: Iterable) -> list:
    return sorted(
        retirements or (),
        key=lambda row: (row.retired_after_sequence, row.id or 0),
    )


def _commentary(active: list, names: Mapping[int, str]) -> list[dict[str, Any]]:
    lines = []
    for delivery in active:
        runs = delivery.total_runs
        parts = [f"{delivery.over_number}.{delivery.ball_in_over}"]
        parts.append(f"{names.get(delivery.bowler_id, 'Bowler')} to {names.get(delivery.striker_id, 'Batter')}")
        if delivery.extra_type:
            parts.append(EXTRA_LABELS.get(delivery.extra_type, delivery.extra_type))
        parts.append(f"{runs} run{'s' if runs != 1 else ''}" if runs else "dot ball")
        if delivery.is_wicket:
            kind = (delivery.wicket_type or "out").replace("_", " ")
            batter = names.get(delivery.dismissed_player_id, "Batter")
            parts.append(f"WICKET ({kind}, {batter})")
        lines.append(
            {
                "delivery_id": delivery.id,
                "over": f"{delivery.over_number}.{delivery.ball_in_over}",
                "striker_id": delivery.striker_id,
                "bowler_id": delivery.bowler_id,
                "runs": runs,
                "is_wicket": delivery.is_wicket,
                "extra_type": delivery.extra_type,
                "text": " — ".join(parts),
            }
        )
    return lines


def _fall_of_wickets(
    active: list, retirements: list, names: Mapping[int, str], rules: RuleSet
) -> list[dict[str, Any]]:
    retired_out_at: dict[int, list] = {}
    for row in retirements:
        if row.retirement_type == "retired_out":
            retired_out_at.setdefault(row.retired_after_sequence, []).append(row)

    fow: list[dict[str, Any]] = []
    runs = 0
    legal_balls = 0
    wickets = 0

    def add_retired(sequence: int) -> None:
        nonlocal wickets
        for row in retired_out_at.get(sequence, []):
            wickets += 1
            fow.append(
                {
                    "wicket": wickets,
                    "runs": runs,
                    "overs": overs_label(legal_balls, rules.balls_per_over),
                    "batter_id": row.player_id,
                    "batter_name": names.get(row.player_id, "Batter"),
                    "dismissal": "Retired out",
                }
            )

    for index, delivery in enumerate(active):
        add_retired(index)
        runs += delivery.total_runs
        legal_balls += 1 if delivery.is_legal_ball else 0
        if delivery.is_wicket:
            wickets += 1
            fow.append(
                {
                    "wicket": wickets,
                    "runs": runs,
                    "overs": overs_label(legal_balls, rules.balls_per_over),
                    "batter_id": delivery.dismissed_player_id,
                    "batter_name": names.get(delivery.dismissed_player_id, "Batter"),
                    "dismissal": _dismissal_text(delivery, names),
                }
            )
    add_retired(len(active))
    return fow


def _partnerships(
    active: list,
    retirements: list,
    names: Mapping[int, str],
    rules: RuleSet,
    batting_order: list[int],
) -> list[dict[str, Any]]:
    retired_out_at: dict[int, list] = {}
    for row in retirements:
        if row.retirement_type == "retired_out":
            retired_out_at.setdefault(row.retired_after_sequence, []).append(row)

    runs = 0
    legal_balls = 0
    wickets = 0
    pair: frozenset[int] | None = None
    start_runs = 0
    start_balls = 0
    result: list[dict[str, Any]] = []

    def close(unbeaten: bool) -> None:
        nonlocal pair
        if pair is None:
            return
        result.append(
            {
                "wicket": None if unbeaten else wickets,
                "batters": [player_id for player_id in pair if player_id is not None],
                "batter_names": [
                    names.get(player_id, "Batter") for player_id in pair if player_id is not None
                ],
                "runs": runs - start_runs,
                "balls": legal_balls - start_balls,
                "unbeaten": unbeaten,
            }
        )
        pair = None

    def open_with(delivery) -> None:
        nonlocal pair, start_runs, start_balls
        # Compare as a set: a single swaps ends without changing the pair.
        candidate = frozenset(
            player_id
            for player_id in (delivery.striker_id, delivery.non_striker_id)
            if player_id is not None
        )
        if candidate != pair:
            pair = candidate
            start_runs = runs
            start_balls = legal_balls

    def retire_out(sequence: int) -> None:
        nonlocal wickets
        for _ in retired_out_at.get(sequence, []):
            wickets += 1
            close(unbeaten=False)

    for index, delivery in enumerate(active):
        retire_out(index)
        open_with(delivery)
        runs += delivery.total_runs
        legal_balls += 1 if delivery.is_legal_ball else 0
        if delivery.is_wicket:
            wickets += 1
            close(unbeaten=False)
    retire_out(len(active))
    if pair is not None:
        close(unbeaten=True)
    return result


def build_innings_scorecard(
    innings,
    deliveries: Iterable,
    names: Mapping[int, str],
    rules: RuleSet,
    retirements: Iterable | None = None,
) -> dict[str, Any]:
    """Build a batting/bowling/partnership card for one innings from events."""
    active = [delivery for delivery in deliveries if not delivery.is_voided]
    retirement_rows = _retirement_rows(retirements)
    retirement_by_player: dict[int, Any] = {}
    retired_out_ids: set[int] = set()
    for row in retirement_rows:
        retirement_by_player[row.player_id] = row
        if row.retirement_type == "retired_out":
            retired_out_ids.add(row.player_id)

    batting: dict[int, dict[str, Any]] = {}
    for index, player_id in enumerate(innings.batting_order or [], start=1):
        batting[player_id] = _batting_line(player_id, names.get(player_id, f"Player {player_id}"), index)

    bowling: dict[int, dict[str, Any]] = {}
    extras = {key: 0 for key in EXTRA_LABELS}
    total_runs = 0
    wickets = 0
    legal_balls = 0
    bat_runs = 0

    for delivery in active:
        total_runs += delivery.total_runs
        if delivery.is_legal_ball:
            legal_balls += 1
        if delivery.is_wicket:
            wickets += 1
        bat_runs += delivery.runs_off_bat

        if delivery.striker_id not in batting:
            batting[delivery.striker_id] = _batting_line(
                delivery.striker_id,
                names.get(delivery.striker_id, f"Player {delivery.striker_id}"),
                len(batting) + 1,
            )
        if delivery.non_striker_id is not None and delivery.non_striker_id not in batting:
            batting[delivery.non_striker_id] = _batting_line(
                delivery.non_striker_id,
                names.get(delivery.non_striker_id, f"Player {delivery.non_striker_id}"),
                len(batting) + 1,
            )

        striker = batting[delivery.striker_id]
        striker["runs"] += delivery.runs_off_bat
        # A batter faces every legal ball and every no-ball, but not a wide.
        if delivery.is_legal_ball or delivery.extra_type == "no_ball":
            striker["balls"] += 1
        if delivery.runs_off_bat == 4:
            striker["fours"] += 1
        elif delivery.runs_off_bat == 6:
            striker["sixes"] += 1

        if delivery.extra_type in extras:
            extras[delivery.extra_type] += delivery.total_runs - delivery.runs_off_bat

        if delivery.is_wicket and delivery.dismissed_player_id is not None:
            dismissed = batting.setdefault(
                delivery.dismissed_player_id,
                _batting_line(
                    delivery.dismissed_player_id,
                    names.get(delivery.dismissed_player_id, f"Player {delivery.dismissed_player_id}"),
                    len(batting) + 1,
                ),
            )
            dismissed["is_out"] = True
            dismissed["dismissal"] = _dismissal_text(delivery, names)

        if delivery.bowler_id not in bowling:
            bowling[delivery.bowler_id] = {
                "player_id": delivery.bowler_id,
                "name": names.get(delivery.bowler_id, f"Player {delivery.bowler_id}"),
                "legal_balls": 0,
                "runs": 0,
                "wickets": 0,
                "wides": 0,
                "no_balls": 0,
                "overs": "0.0",
                "economy": 0.0,
            }
        bowler = bowling[delivery.bowler_id]
        if delivery.is_legal_ball:
            bowler["legal_balls"] += 1
        if delivery.extra_type == "wide":
            bowler["wides"] += 1
        if delivery.extra_type == "no_ball":
            bowler["no_balls"] += 1
        # Byes and leg byes are not charged to the bowler.
        if delivery.extra_type not in {"bye", "leg_bye"}:
            bowler["runs"] += delivery.total_runs
        if delivery.is_wicket and delivery.wicket_type in BOWLER_CREDIT_WICKETS:
            bowler["wickets"] += 1

    # Retirements appear on the card even when the batter never faced a ball.
    for player_id, row in retirement_by_player.items():
        line = batting.setdefault(
            player_id,
            _batting_line(
                player_id,
                names.get(player_id, f"Player {player_id}"),
                len(batting) + 1,
            ),
        )
        if row.returned_at is not None:
            # The batter came back: history stays in ``retirements``, but the
            # card shows their final innings rather than a stale retirement.
            line["returned_to_bat"] = True
            if not line["is_out"]:
                line["dismissal"] = None
        else:
            line["retirement_type"] = row.retirement_type
            if row.retirement_type == "retired_out":
                line["is_out"] = True
                line["dismissal"] = "Retired out"
            elif not line["is_out"]:
                line["dismissal"] = RETIREMENT_LABELS[row.retirement_type]

    wickets += len(retired_out_ids)

    batting_lines = []
    for line in batting.values():
        if (
            line["balls"]
            or line["runs"]
            or line["is_out"]
            or line["retirement_type"]
            or line["returned_to_bat"]
        ):
            line["strike_rate"] = (
                round(line["runs"] / line["balls"] * 100, 2) if line["balls"] else 0.0
            )
            batting_lines.append(line)

    bowling_lines = list(bowling.values())
    for line in bowling_lines:
        line["overs"] = overs_label(line["legal_balls"], rules.balls_per_over)
        overs_bowled = line["legal_balls"] / rules.balls_per_over if rules.balls_per_over else 0
        line["economy"] = round(line["runs"] / overs_bowled, 2) if overs_bowled else 0.0

    overs_bowled = legal_balls / rules.balls_per_over if rules.balls_per_over else 0
    return {
        "innings_id": innings.id,
        "number": innings.number,
        "status": innings.status,
        "batting_team_id": innings.batting_team_id,
        "bowling_team_id": innings.bowling_team_id,
        "total_runs": total_runs,
        "wickets": wickets,
        "legal_balls": legal_balls,
        "overs": overs_label(legal_balls, rules.balls_per_over),
        "run_rate": round(total_runs / overs_bowled, 2) if overs_bowled else 0.0,
        "batting_runs": bat_runs,
        "extras": {**extras, "total": sum(extras.values())},
        "batting": batting_lines,
        "bowling": bowling_lines,
        "fall_of_wickets": _fall_of_wickets(active, retirement_rows, names, rules),
        "partnerships": _partnerships(
            active,
            retirement_rows,
            names,
            rules,
            list(innings.batting_order or []),
        ),
        "commentary": _commentary(active, names),
        "retirements": [
            {
                "id": row.id,
                "player_id": row.player_id,
                "player_name": names.get(row.player_id, "Batter"),
                "retirement_type": row.retirement_type,
                "reason": row.reason,
                "replacement_player_id": row.replacement_player_id,
                "retired_after_sequence": row.retired_after_sequence,
                "retired_at": row.retired_at.isoformat() if row.retired_at else None,
                "returned_after_sequence": row.returned_after_sequence,
                "returned_at": row.returned_at.isoformat() if row.returned_at else None,
            }
            for row in retirement_rows
        ],
        "target": innings.target,
    }
