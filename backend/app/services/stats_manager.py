"""Derived player/team statistics and aggregate reporting.

``rebuild_player_match_stats`` runs inside the scoring transaction after every
innings recompute, so player rows always match the delivery and retirement
events. The dashboard endpoints aggregate those rows by player and team name,
because squads are created per match rather than as global registries.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import distinct, func, or_, select

from ..extensions import db
from ..models import Innings, Match, Player, PlayerMatchStatistics, Team
from .fantasy import rebuild_fantasy_ledger
from .innings_manager import active_deliveries, retirements_for, rules_for_match
from .statistics import build_innings_scorecard

ZERO_TOTALS: dict[str, Any] = {
    "batting_innings": 0,
    "runs": 0,
    "highest_score": 0,
    "balls_faced": 0,
    "fours": 0,
    "sixes": 0,
    "is_out": False,
    "not_outs": 0,
    "dismissal": None,
    "bowling_innings": 0,
    "balls_bowled": 0,
    "runs_conceded": 0,
    "wickets": 0,
    "best_bowling_wickets": 0,
    "best_bowling_runs": 0,
    "wides": 0,
    "no_balls": 0,
    "fantasy_points": 0,
}


def _squad(match: Match) -> dict[int, Player]:
    players: dict[int, Player] = {}
    for team in (match.team_a, match.team_b):
        if team is None:
            continue
        for player in team.players:
            players[player.id] = player
    return players


def rebuild_player_match_stats(match: Match) -> None:
    rules = rules_for_match(match)
    squad = _squad(match)
    names = {player_id: player.name for player_id, player in squad.items()}

    totals: dict[int, dict[str, Any]] = defaultdict(lambda: dict(ZERO_TOTALS))

    for innings in match.innings:
        retirements = retirements_for(innings)
        card = build_innings_scorecard(
            innings, active_deliveries(innings), names, rules, retirements
        )
        for line in card["batting"]:
            entry = totals[line["player_id"]]
            entry["batting_innings"] += 1
            entry["runs"] += line["runs"]
            entry["highest_score"] = max(entry["highest_score"], line["runs"])
            entry["balls_faced"] += line["balls"]
            entry["fours"] += line["fours"]
            entry["sixes"] += line["sixes"]
            if line["is_out"]:
                entry["is_out"] = True
                entry["dismissal"] = line["dismissal"]
            else:
                entry["not_outs"] += 1
        for line in card["bowling"]:
            entry = totals[line["player_id"]]
            entry["bowling_innings"] += 1
            entry["balls_bowled"] += line["legal_balls"]
            entry["runs_conceded"] += line["runs"]
            entry["wickets"] += line["wickets"]
            entry["wides"] += line["wides"]
            entry["no_balls"] += line["no_balls"]
            best = (entry["best_bowling_wickets"], -entry["best_bowling_runs"])
            candidate = (line["wickets"], -line["runs"])
            if candidate > best:
                entry["best_bowling_wickets"] = line["wickets"]
                entry["best_bowling_runs"] = line["runs"]

    fantasy_totals = rebuild_fantasy_ledger(match)
    for player_id, entry in totals.items():
        entry["fantasy_points"] = fantasy_totals.get(player_id, 0)

    existing = {
        row.player_id: row
        for row in db.session.execute(
            select(PlayerMatchStatistics).where(PlayerMatchStatistics.match_id == match.id)
        ).scalars()
    }

    for player_id, player in squad.items():
        row = existing.get(player_id)
        if row is None:
            row = PlayerMatchStatistics(
                match_id=match.id, player_id=player_id, team_id=player.team_id
            )
            db.session.add(row)
        data = totals.get(player_id, dict(ZERO_TOTALS))
        for field, value in data.items():
            setattr(row, field, value)

    db.session.flush()


def _average(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 2) if denominator else None


def _owner_conditions(owner_id: int | None) -> list:
    if owner_id is None:
        return []
    return [(Match.owner_id == owner_id) | (Match.owner_id.is_(None))]


def _player_aggregates(owner_id: int | None = None) -> list[dict[str, Any]]:
    query = (
        select(PlayerMatchStatistics, Player.name, Team.name)
        .join(Player, Player.id == PlayerMatchStatistics.player_id)
        .join(Team, Team.id == PlayerMatchStatistics.team_id)
    )
    if owner_id is not None:
        query = query.join(Match, Match.id == PlayerMatchStatistics.match_id).where(
            *_owner_conditions(owner_id)
        )
    rows = db.session.execute(query.order_by(PlayerMatchStatistics.id)).all()

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row, player_name, team_name in rows:
        key = (player_name, team_name)
        entry = grouped.setdefault(
            key,
            {
                "player_id": row.player_id,
                "player_name": player_name,
                "team_name": team_name,
                "matches": set(),
                "innings": 0,
                "runs": 0,
                "highest_score": 0,
                "balls_faced": 0,
                "fours": 0,
                "sixes": 0,
                "dismissals": 0,
                "not_outs": 0,
                "wickets": 0,
                "balls_bowled": 0,
                "runs_conceded": 0,
                "best_wickets": 0,
                "best_runs": 0,
                "fantasy_points": 0,
            },
        )
        entry["matches"].add(row.match_id)
        entry["innings"] += row.batting_innings
        entry["runs"] += row.runs
        entry["highest_score"] = max(entry["highest_score"], row.highest_score)
        entry["balls_faced"] += row.balls_faced
        entry["fours"] += row.fours
        entry["sixes"] += row.sixes
        entry["dismissals"] += 1 if row.is_out else 0
        entry["not_outs"] += row.not_outs
        entry["wickets"] += row.wickets
        entry["balls_bowled"] += row.balls_bowled
        entry["runs_conceded"] += row.runs_conceded
        entry["fantasy_points"] += row.fantasy_points
        if (row.best_bowling_wickets, -row.best_bowling_runs) > (
            entry["best_wickets"],
            -entry["best_runs"],
        ):
            entry["best_wickets"] = row.best_bowling_wickets
            entry["best_runs"] = row.best_bowling_runs

    result = []
    for entry in grouped.values():
        overs = entry["balls_bowled"] / 6 if entry["balls_bowled"] else 0
        result.append(
            {
                "player_id": entry["player_id"],
                "player_name": entry["player_name"],
                "team_name": entry["team_name"],
                "matches": len(entry["matches"]),
                "innings": entry["innings"],
                "runs": entry["runs"],
                "highest_score": entry["highest_score"],
                "batting_average": _average(entry["runs"], entry["dismissals"]),
                "strike_rate": round(entry["runs"] / entry["balls_faced"] * 100, 2)
                if entry["balls_faced"]
                else 0.0,
                "fours": entry["fours"],
                "sixes": entry["sixes"],
                "not_outs": entry["not_outs"],
                "wickets": entry["wickets"],
                "bowling_average": _average(entry["runs_conceded"], entry["wickets"]),
                "economy": round(entry["runs_conceded"] / overs, 2) if overs else None,
                "best_bowling": f"{entry['best_wickets']}/{entry['best_runs']}",
                "best_bowling_wickets": entry["best_wickets"],
                "best_bowling_runs": entry["best_runs"],
                "fantasy_points": entry["fantasy_points"],
            }
        )
    result.sort(key=lambda row: (-row["runs"], -row["wickets"], row["player_name"]))
    return result


def player_stats(limit: int | None = None, owner_id: int | None = None) -> list[dict[str, Any]]:
    rows = _player_aggregates(owner_id)
    return rows[:limit] if limit else rows


def team_stats(owner_id: int | None = None) -> list[dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    query = select(Match)
    conditions = _owner_conditions(owner_id)
    if conditions:
        query = query.where(*conditions)
    matches = db.session.execute(query.order_by(Match.id)).scalars().all()

    for match in matches:
        for team in (match.team_a, match.team_b):
            entry = entries.setdefault(
                team.name,
                {
                    "team_id": team.id,
                    "team_name": team.name,
                    "matches": 0,
                    "completed": 0,
                    "wins": 0,
                    "losses": 0,
                    "ties": 0,
                    "highest_score": None,
                    "lowest_score": None,
                    "win_percentage": 0.0,
                },
            )
            entry["matches"] += 1
            scores = [
                innings.total_runs
                for innings in match.innings
                if innings.batting_team_id == team.id and innings.status != "pending"
            ]
            if scores:
                high = max(scores)
                low = min(scores)
                entry["highest_score"] = high if entry["highest_score"] is None else max(entry["highest_score"], high)
                entry["lowest_score"] = low if entry["lowest_score"] is None else min(entry["lowest_score"], low)

            if match.status == "completed" and match.result:
                entry["completed"] += 1
                winner = match.result.get("winner_team_id")
                if winner == team.id:
                    entry["wins"] += 1
                elif winner is None:
                    entry["ties"] += 1
                else:
                    entry["losses"] += 1

    result = list(entries.values())
    for entry in result:
        entry["win_percentage"] = (
            round(entry["wins"] / entry["completed"] * 100, 2)
            if entry["completed"]
            else 0.0
        )
    result.sort(key=lambda row: (-row["wins"], -row["matches"], row["team_name"]))
    return result


def stats_overview(limit: int = 5, owner_id: int | None = None) -> dict[str, Any]:
    """Aggregate totals and leaderboards for the Stats screen."""
    conditions = _owner_conditions(owner_id)
    match_total = db.session.scalar(select(func.count(Match.id)).where(*conditions)) or 0
    live_total = (
        db.session.scalar(
            select(func.count(Match.id)).where(Match.status == "live", *conditions)
        )
        or 0
    )
    completed_total = (
        db.session.scalar(
            select(func.count(Match.id)).where(Match.status == "completed", *conditions)
        )
        or 0
    )
    team_total = (
        db.session.scalar(
            select(func.count(distinct(Team.id)))
            .join(Match, or_(Match.team_a_id == Team.id, Match.team_b_id == Team.id))
            .where(*conditions)
        )
        or 0
    )
    player_total = (
        db.session.scalar(
            select(func.count(distinct(Player.id)))
            .join(Team, Team.id == Player.team_id)
            .join(Match, or_(Match.team_a_id == Team.id, Match.team_b_id == Team.id))
            .where(*conditions)
        )
        or 0
    )

    innings_query = select(
        func.coalesce(func.sum(Innings.total_runs), 0),
        func.coalesce(func.sum(Innings.wickets), 0),
        func.coalesce(func.sum(Innings.legal_balls), 0),
    )
    if conditions:
        innings_query = innings_query.join(Match, Match.id == Innings.match_id).where(*conditions)
    innings_totals = db.session.execute(innings_query).one()
    runs_scored, wickets_taken, balls_bowled = innings_totals

    players = _player_aggregates(owner_id)

    def board(rows, label):
        return [
            {
                "player_id": row["player_id"],
                "player_name": row["player_name"],
                "team_name": row["team_name"],
                "runs": row["runs"],
                "wickets": row["wickets"],
                "fantasy_points": row["fantasy_points"],
                "matches": row["matches"],
                "label": label,
            }
            for row in rows
            if row[label] > 0
        ]

    run_rows = sorted(players, key=lambda row: -row["runs"])[:limit]
    wicket_rows = sorted(players, key=lambda row: -row["wickets"])[:limit]
    fantasy_rows = sorted(players, key=lambda row: -row["fantasy_points"])[:limit]

    return {
        "totals": {
            "matches": match_total,
            "matches_live": live_total,
            "matches_completed": completed_total,
            "teams": team_total,
            "players": player_total,
            "runs": int(runs_scored or 0),
            "wickets": int(wickets_taken or 0),
            "legal_balls": int(balls_bowled or 0),
        },
        "top_run_scorers": board(run_rows, "runs"),
        "top_wicket_takers": board(wicket_rows, "wickets"),
        "top_fantasy_scorers": board(fantasy_rows, "fantasy_points"),
        "teams": team_stats(owner_id),
        "players": players[:20],
    }
