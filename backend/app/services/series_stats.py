"""Derived, correction-safe series statistics.

The dashboard is a projection over completed matches. It never stores or
rewrites match statistics: batting and bowling boards are rebuilt from delivery
and retirement events, and fantasy totals come from the per-match fantasy
ledger. Undoing a delivery, or completing a correction, therefore changes the
next dashboard response without double-counting the match.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Iterable

from sqlalchemy import select

from ..extensions import db
from ..models import FantasyPoint, Match, Series
from .innings_manager import active_deliveries, retirements_for, rules_for_match
from .statistics import build_innings_scorecard

MIN_BATTING_INNINGS = 2
MIN_BALLS_FACED = 30
MIN_BALLS_BOWLED = 12
MIN_WICKETS = 2

QUALIFICATION = {
    "batting_average": f"Minimum {MIN_BATTING_INNINGS} innings and one dismissal.",
    "batting_strike_rate": f"Minimum {MIN_BALLS_FACED} balls faced.",
    "bowling_economy": f"Minimum {MIN_BALLS_BOWLED} legal balls bowled.",
    "bowling_average": f"Minimum {MIN_WICKETS} wickets.",
    "bowling_strike_rate": f"Minimum {MIN_WICKETS} wickets.",
}

# Fielding and captaincy are deliberately absent from these sets.
BATTING_CATEGORIES = frozenset(
    {
        "runs",
        "boundary_four",
        "boundary_six",
        "milestone_25",
        "milestone_50",
        "milestone_100",
        "duck",
        "strike_rate",
    }
)
BOWLING_CATEGORIES = frozenset(
    {
        "wicket",
        "bowled_lbw",
        "maiden",
        "haul_3",
        "haul_4",
        "haul_5",
        "economy",
    }
)


def _round(value: float | None, places: int = 2) -> float | None:
    return round(value, places) if value is not None else None


def _name_key(row: dict[str, Any]) -> tuple[str, str]:
    return (row["player_name"].casefold(), row["team_name"].casefold())


def _player_key(name: str, team: str) -> tuple[str, str]:
    return (name.strip().casefold(), team.strip().casefold())


def _player_maps(match: Match) -> tuple[dict[int, str], dict[int, str]]:
    names: dict[int, str] = {}
    teams: dict[int, str] = {}
    for team in (match.team_a, match.team_b):
        if team is None:
            continue
        for player in team.players:
            names[player.id] = player.name
            teams[player.id] = team.name
    return names, teams


def _new_entry(player_id: int, name: str, team: str) -> dict[str, Any]:
    return {
        "player_id": player_id,
        "player_ids": {player_id},
        "player_name": name,
        "team_name": team,
        "matches": set(),
        "batting_innings": 0,
        "runs": 0,
        "balls": 0,
        "fours": 0,
        "sixes": 0,
        "dismissals": 0,
        "not_outs": 0,
        "highest_score": 0,
        "fifties": 0,
        "centuries": 0,
        "bowling_innings": 0,
        "bowling_balls": 0,
        "bowling_overs": 0.0,
        "runs_conceded": 0,
        "wickets": 0,
        "best_wickets": 0,
        "best_runs": 0,
        "maidens": 0,
        "dot_balls": 0,
        "fantasy_points": 0,
        "batting_points": 0,
        "bowling_points": 0,
        "match_points": {},
    }


def _entry(
    entries: dict[tuple[str, str], dict[str, Any]],
    player_id: int,
    names: dict[int, str],
    teams: dict[int, str],
) -> dict[str, Any]:
    name = names.get(player_id, f"Player {player_id}")
    team = teams.get(player_id, "Team")
    key = _player_key(name, team)
    row = entries.get(key)
    if row is None:
        row = _new_entry(player_id, name, team)
        entries[key] = row
    else:
        row["player_ids"].add(player_id)
    return row


def _finalise(entry: dict[str, Any]) -> dict[str, Any]:
    dismissals = entry["dismissals"]
    balls = entry["balls"]
    wickets = entry["wickets"]
    bowling_overs = entry["bowling_overs"]
    row = {
        "player_id": entry["player_id"],
        "player_ids": sorted(entry["player_ids"]),
        "player_name": entry["player_name"],
        "team_name": entry["team_name"],
        "matches": len(entry["matches"]),
        "batting_innings": entry["batting_innings"],
        "runs": entry["runs"],
        "balls": balls,
        "fours": entry["fours"],
        "sixes": entry["sixes"],
        "dismissals": dismissals,
        "not_outs": entry["not_outs"],
        "highest_score": entry["highest_score"],
        "fifties": entry["fifties"],
        "centuries": entry["centuries"],
        "batting_average": _round(entry["runs"] / dismissals, 2) if dismissals else None,
        "strike_rate": _round(entry["runs"] / balls * 100, 2) if balls else 0.0,
        "bowling_innings": entry["bowling_innings"],
        "bowling_balls": entry["bowling_balls"],
        "bowling_overs": _round(bowling_overs, 2),
        "runs_conceded": entry["runs_conceded"],
        "wickets": wickets,
        "best_wickets": entry["best_wickets"],
        "best_runs": entry["best_runs"],
        "best_bowling": (
            f"{entry['best_wickets']}/{entry['best_runs']}"
            if entry["bowling_innings"]
            else None
        ),
        "maidens": entry["maidens"],
        "dot_balls": entry["dot_balls"],
        "economy": _round(entry["runs_conceded"] / bowling_overs, 2)
        if bowling_overs
        else 0.0,
        "bowling_average": _round(entry["runs_conceded"] / wickets, 2)
        if wickets
        else None,
        "bowling_strike_rate": _round(entry["bowling_balls"] / wickets, 2)
        if wickets
        else None,
        "fantasy_points": entry["fantasy_points"],
        "batting_points": entry["batting_points"],
        "bowling_points": entry["bowling_points"],
        "match_points": [
            {"match_id": match_id, "points": points}
            for match_id, points in sorted(entry["match_points"].items())
        ],
        "qualified": {
            "batting_average": entry["batting_innings"] >= MIN_BATTING_INNINGS
            and dismissals > 0,
            "batting_strike_rate": balls >= MIN_BALLS_FACED,
            "bowling_economy": entry["bowling_balls"] >= MIN_BALLS_BOWLED,
            "bowling_average": wickets >= MIN_WICKETS,
            "bowling_strike_rate": wickets >= MIN_WICKETS,
        },
    }
    return row


def _collect_players(series: Series) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]], list[Match]]:
    completed = sorted(
        (match for match in series.matches if match.status == "completed"),
        key=lambda match: match.id,
    )
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    match_points: dict[int, dict[tuple[str, str], dict[str, Any]]] = defaultdict(dict)

    for match in completed:
        names, teams = _player_maps(match)
        rules = rules_for_match(match)
        for innings in match.innings:
            deliveries = active_deliveries(innings)
            card = build_innings_scorecard(
                innings,
                deliveries,
                names,
                rules,
                retirements_for(innings),
            )
            for line in card["batting"]:
                row = _entry(entries, line["player_id"], names, teams)
                row["matches"].add(match.id)
                row["batting_innings"] += 1
                runs = line["runs"]
                row["runs"] += runs
                row["balls"] += line["balls"]
                row["fours"] += line["fours"]
                row["sixes"] += line["sixes"]
                row["highest_score"] = max(row["highest_score"], runs)
                if runs >= 100:
                    row["centuries"] += 1
                elif runs >= 50:
                    row["fifties"] += 1
                if line["is_out"]:
                    row["dismissals"] += 1
                else:
                    row["not_outs"] += 1

            for line in card["bowling"]:
                row = _entry(entries, line["player_id"], names, teams)
                row["matches"].add(match.id)
                row["bowling_innings"] += 1
                row["bowling_balls"] += line["legal_balls"]
                row["bowling_overs"] += (
                    line["legal_balls"] / rules.balls_per_over
                    if rules.balls_per_over
                    else 0.0
                )
                row["runs_conceded"] += line["runs"]
                row["wickets"] += line["wickets"]
                if (
                    line["wickets"] > row["best_wickets"]
                    or (
                        line["wickets"] == row["best_wickets"]
                        and line["runs"] < row["best_runs"]
                    )
                ):
                    row["best_wickets"] = line["wickets"]
                    row["best_runs"] = line["runs"]

            # Dot balls and maidens are not part of the batting scorecard.
            overs: dict[tuple[int, int], dict[str, int]] = {}
            for delivery in deliveries:
                row = _entry(entries, delivery.bowler_id, names, teams)
                row["matches"].add(match.id)
                if delivery.is_legal_ball and delivery.total_runs == 0:
                    row["dot_balls"] += 1
                over = overs.setdefault(
                    (delivery.bowler_id, delivery.over_number),
                    {"legal": 0, "runs": 0},
                )
                if delivery.is_legal_ball:
                    over["legal"] += 1
                if delivery.extra_type not in {"bye", "leg_bye"}:
                    over["runs"] += delivery.total_runs
            for (bowler_id, _over_number), over in overs.items():
                if over["legal"] >= rules.balls_per_over and over["runs"] == 0:
                    row = _entry(entries, bowler_id, names, teams)
                    row["maidens"] += 1

        # The fantasy ledger is rebuilt inside every scoring transaction. It is
        # the authoritative source for the two fantasy award categories.
        ledger = db.session.execute(
            select(FantasyPoint).where(FantasyPoint.match_id == match.id)
        ).scalars()
        for point in ledger:
            row = _entry(entries, point.player_id, names, teams)
            row["matches"].add(match.id)
            row["fantasy_points"] += point.points
            if point.category in BATTING_CATEGORIES:
                row["batting_points"] += point.points
            if point.category in BOWLING_CATEGORIES:
                row["bowling_points"] += point.points
            row["match_points"][match.id] = (
                row["match_points"].get(match.id, 0) + point.points
            )
            match_entry = match_points[match.id].setdefault(
                _player_key(row["player_name"], row["team_name"]),
                {
                    "player_id": row["player_id"],
                    "player_name": row["player_name"],
                    "team_name": row["team_name"],
                    "total_points": 0,
                    "batting_points": 0,
                    "bowling_points": 0,
                },
            )
            match_entry["total_points"] += point.points
            if point.category in BATTING_CATEGORIES:
                match_entry["batting_points"] += point.points
            if point.category in BOWLING_CATEGORIES:
                match_entry["bowling_points"] += point.points

    rows = [_finalise(entry) for entry in entries.values()]
    return rows, match_points, completed


def _batting_board(
    label: str, rows: Iterable[dict[str, Any]], qualification: str | None = None
) -> dict[str, Any]:
    return {"label": label, "rows": list(rows), "qualification": qualification}


def _standing_rows(series: Series, completed: list[Match]) -> list[dict[str, Any]]:
    names: list[str] = []
    for name in (getattr(series, "team_a_name", None), getattr(series, "team_b_name", None)):
        if name and name not in names:
            names.append(name)
    for match in completed:
        for team in (match.team_a, match.team_b):
            if team and team.name not in names:
                names.append(team.name)

    table: dict[str, dict[str, Any]] = {
        name: {
            "team_name": name,
            "played": 0,
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "points": 0,
        }
        for name in names
    }

    for match in completed:
        a_name = match.team_a.name if match.team_a else "Team A"
        b_name = match.team_b.name if match.team_b else "Team B"
        for name in (a_name, b_name):
            table.setdefault(
                name,
                {
                    "team_name": name,
                    "played": 0,
                    "wins": 0,
                    "losses": 0,
                    "ties": 0,
                    "points": 0,
                },
            )
        table[a_name]["played"] += 1
        table[b_name]["played"] += 1

        result = match.result or {}
        winner_id = result.get("winner_team_id")
        if result.get("outcome") == "tie":
            table[a_name]["ties"] += 1
            table[b_name]["ties"] += 1
        elif winner_id is not None:
            if match.team_a and winner_id == match.team_a.id:
                winner_name, loser_name = a_name, b_name
            elif match.team_b and winner_id == match.team_b.id:
                winner_name, loser_name = b_name, a_name
            else:
                winner_name = loser_name = None
            if winner_name and loser_name:
                table[winner_name]["wins"] += 1
                table[loser_name]["losses"] += 1

    rows = []
    for entry in table.values():
        played = entry["played"]
        entry["points"] = entry["wins"] * 2 + entry["ties"]
        entry["win_percentage"] = (
            round(entry["wins"] / played * 100, 2) if played else 0.0
        )
        rows.append(entry)
    rows.sort(
        key=lambda row: (
            -row["points"],
            -row["wins"],
            row["losses"],
            row["team_name"].casefold(),
        )
    )
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def _match_label(match: Match) -> str:
    a_name = match.team_a.name if match.team_a else "Team A"
    b_name = match.team_b.name if match.team_b else "Team B"
    return f"{a_name} vs {b_name}"


def _team_name(match: Match, team_id: int | None) -> str | None:
    if team_id is not None and match.team_a and team_id == match.team_a.id:
        return match.team_a.name
    if team_id is not None and match.team_b and team_id == match.team_b.id:
        return match.team_b.name
    return None


def _recent_results(completed: list[Match], limit: int = 5) -> list[dict[str, Any]]:
    ordered = sorted(
        completed,
        key=lambda match: (
            match.completed_at.isoformat() if match.completed_at else "",
            match.id,
        ),
        reverse=True,
    )[:limit]
    results = []
    for match in ordered:
        result = match.result or {}
        results.append(
            {
                "match_id": match.id,
                "label": _match_label(match),
                "completed_at": (
                    match.completed_at.isoformat() if match.completed_at else None
                ),
                "result_summary": result.get("summary"),
                "winner_team_id": result.get("winner_team_id"),
                "winner_team_name": _team_name(
                    match, result.get("winner_team_id")
                ),
                "innings": [
                    {
                        "number": innings.number,
                        "team_name": _team_name(match, innings.batting_team_id),
                        "runs": innings.total_runs,
                        "wickets": innings.wickets,
                        "overs": (
                            f"{innings.legal_balls // rules_for_match(match).balls_per_over}."
                            f"{innings.legal_balls % rules_for_match(match).balls_per_over}"
                        ),
                    }
                    for innings in match.innings
                ],
            }
        )
    return results


def _award(
    rows: list[dict[str, Any]],
    *,
    key: str,
    label: str,
    metric: str,
    eligible: Callable[[dict[str, Any]], bool],
    tie_break: Callable[[dict[str, Any]], tuple],
) -> dict[str, Any]:
    candidates = [row for row in rows if eligible(row)]
    if not candidates:
        return {
            "key": key,
            "label": label,
            "metric": metric,
            "value": None,
            "tied": False,
            "winners": [],
        }
    best = max(row[metric] for row in candidates)
    winners = [row for row in candidates if row[metric] == best]
    winners.sort(key=lambda row: (*tie_break(row), *_name_key(row)))
    return {
        "key": key,
        "label": label,
        "metric": metric,
        "value": best,
        "tied": len(winners) > 1,
        "winners": [
            {
                "award_key": f"{key}:{_player_key(row['player_name'], row['team_name'])[0]}:"
                f"{_player_key(row['player_name'], row['team_name'])[1]}",
                "player_id": row["player_id"],
                "player_name": row["player_name"],
                "team_name": row["team_name"],
                "matches": row["matches"],
                "points": row["fantasy_points"],
                "batting_points": row["batting_points"],
                "bowling_points": row["bowling_points"],
                "runs": row["runs"],
                "wickets": row["wickets"],
            }
            for row in winners
        ],
    }


def _player_of_match_awards(
    completed: list[Match], match_points: dict[int, dict[tuple[str, str], dict[str, Any]]]
) -> list[dict[str, Any]]:
    awards: list[dict[str, Any]] = []
    for match in sorted(completed, key=lambda item: item.id, reverse=True):
        players = list(match_points.get(match.id, {}).values())
        if not players:
            continue
        best = max(player["total_points"] for player in players)
        winners = [player for player in players if player["total_points"] == best]
        winners.sort(
            key=lambda player: (
                -player["batting_points"],
                -player["bowling_points"],
                player["player_name"].casefold(),
                player["team_name"].casefold(),
            )
        )
        awards.append(
            {
                "match_id": match.id,
                "match_label": _match_label(match),
                "metric": "total_points",
                "value": best,
                "tied": len(winners) > 1,
                "winners": [
                    {
                        "award_key": f"player_of_match:{match.id}:"
                        f"{player['player_name'].casefold()}:{player['team_name'].casefold()}",
                        "player_id": player["player_id"],
                        "player_name": player["player_name"],
                        "team_name": player["team_name"],
                        "points": player["total_points"],
                        "batting_points": player["batting_points"],
                        "bowling_points": player["bowling_points"],
                    }
                    for player in winners
                ],
            }
        )
    return awards


def series_dashboard(series: Series) -> dict[str, Any]:
    """Build the complete series dashboard from completed match events."""
    rows, match_points, completed = _collect_players(series)

    batting_rows = [row for row in rows if row["batting_innings"]]
    bowling_rows = [row for row in rows if row["bowling_innings"]]

    batting_by_runs = sorted(
        batting_rows,
        key=lambda row: (-row["runs"], -row["highest_score"], *_name_key(row)),
    )
    batting_by_highest = sorted(
        batting_rows,
        key=lambda row: (-row["highest_score"], -row["runs"], *_name_key(row)),
    )
    batting_by_average = sorted(
        (
            row
            for row in batting_rows
            if row["qualified"]["batting_average"]
        ),
        key=lambda row: (-row["batting_average"], -row["runs"], *_name_key(row)),
    )
    batting_by_strike_rate = sorted(
        (
            row
            for row in batting_rows
            if row["qualified"]["batting_strike_rate"]
        ),
        key=lambda row: (-row["strike_rate"], -row["runs"], *_name_key(row)),
    )
    batting_by_fours = sorted(
        batting_rows, key=lambda row: (-row["fours"], -row["runs"], *_name_key(row))
    )
    batting_by_sixes = sorted(
        batting_rows, key=lambda row: (-row["sixes"], -row["runs"], *_name_key(row))
    )
    batting_by_fifties = sorted(
        batting_rows,
        key=lambda row: (-row["fifties"], -row["runs"], *_name_key(row)),
    )
    batting_by_centuries = sorted(
        batting_rows,
        key=lambda row: (-row["centuries"], -row["runs"], *_name_key(row)),
    )

    qualified_economy = [row for row in bowling_rows if row["qualified"]["bowling_economy"]]
    qualified_average = [row for row in bowling_rows if row["qualified"]["bowling_average"]]
    qualified_strike_rate = [
        row for row in bowling_rows if row["qualified"]["bowling_strike_rate"]
    ]
    bowling_by_wickets = sorted(
        bowling_rows,
        key=lambda row: (-row["wickets"], row["economy"], *_name_key(row)),
    )
    bowling_by_economy = sorted(
        qualified_economy,
        key=lambda row: (row["economy"], -row["wickets"], *_name_key(row)),
    )
    bowling_by_figures = sorted(
        bowling_rows,
        key=lambda row: (-row["best_wickets"], row["best_runs"], *_name_key(row)),
    )
    bowling_by_average = sorted(
        qualified_average,
        key=lambda row: (
            row["bowling_average"],
            -row["wickets"],
            *_name_key(row),
        ),
    )
    bowling_by_strike_rate = sorted(
        qualified_strike_rate,
        key=lambda row: (
            row["bowling_strike_rate"],
            -row["wickets"],
            *_name_key(row),
        ),
    )
    bowling_by_maidens = sorted(
        bowling_rows,
        key=lambda row: (-row["maidens"], -row["wickets"], *_name_key(row)),
    )
    bowling_by_dots = sorted(
        bowling_rows,
        key=lambda row: (-row["dot_balls"], -row["wickets"], *_name_key(row)),
    )

    mvp = sorted(
        rows,
        key=lambda row: (
            -row["fantasy_points"],
            -row["batting_points"],
            -row["bowling_points"],
            *_name_key(row),
        ),
    )
    for index, row in enumerate(mvp, start=1):
        row["rank"] = index

    match_fantasy = []
    for match in completed:
        players = list(match_points.get(match.id, {}).values())
        if not players:
            continue
        players.sort(
            key=lambda player: (
                -player["total_points"],
                -player["batting_points"],
                -player["bowling_points"],
                player["player_name"].casefold(),
                player["team_name"].casefold(),
            )
        )
        match_fantasy.append(
            {
                "match_id": match.id,
                "match_label": _match_label(match),
                "completed_at": (
                    match.completed_at.isoformat() if match.completed_at else None
                ),
                "players": players,
            }
        )

    awards = {
        "player_of_match": _player_of_match_awards(completed, match_points),
        "best_batter": _award(
            batting_rows,
            key="best_batter",
            label="Best Batter",
            metric="batting_points",
            eligible=lambda row: row["batting_innings"] > 0,
            tie_break=lambda row: (-row["runs"], -row["highest_score"]),
        ),
        "best_bowler": _award(
            bowling_rows,
            key="best_bowler",
            label="Best Bowler",
            metric="bowling_points",
            eligible=lambda row: row["bowling_innings"] > 0,
            tie_break=lambda row: (
                -row["wickets"],
                row["bowling_average"]
                if row["bowling_average"] is not None
                else float("inf"),
            ),
        ),
        "player_of_series": _award(
            rows,
            key="player_of_series",
            label="Player of the Series",
            metric="fantasy_points",
            eligible=lambda row: row["matches"] > 0,
            tie_break=lambda row: (-row["runs"], -row["wickets"]),
        ),
    }

    played = len(completed)
    planned = series.planned_matches or 0
    return {
        "series_id": series.id,
        "matches_played": played,
        "matches_remaining": max(planned - played, 0),
        "match_count": len(series.matches),
        "live_matches": sum(1 for match in series.matches if match.status == "live"),
        "draft_matches": sum(1 for match in series.matches if match.status == "draft"),
        "standings": _standing_rows(series, completed),
        "mvp_leaderboard": mvp,
        "fantasy_leaderboard": mvp,
        "match_fantasy": match_fantasy,
        "batting_leaderboards": {
            "runs": _batting_board("Most runs", batting_by_runs),
            "highest_score": _batting_board("Highest score", batting_by_highest),
            "average": _batting_board(
                "Best batting average", batting_by_average, QUALIFICATION["batting_average"]
            ),
            "strike_rate": _batting_board(
                "Best strike rate",
                batting_by_strike_rate,
                QUALIFICATION["batting_strike_rate"],
            ),
            "fours": _batting_board("Most fours", batting_by_fours),
            "sixes": _batting_board("Most sixes", batting_by_sixes),
            "fifties": _batting_board("Most fifties", batting_by_fifties),
            "centuries": _batting_board("Most centuries", batting_by_centuries),
        },
        "bowling_leaderboards": {
            "wickets": _batting_board("Most wickets", bowling_by_wickets),
            "economy": _batting_board(
                "Best economy",
                bowling_by_economy,
                QUALIFICATION["bowling_economy"],
            ),
            "best_figures": _batting_board("Best bowling figures", bowling_by_figures),
            "average": _batting_board(
                "Best bowling average",
                bowling_by_average,
                QUALIFICATION["bowling_average"],
            ),
            "strike_rate": _batting_board(
                "Best bowling strike rate",
                bowling_by_strike_rate,
                QUALIFICATION["bowling_strike_rate"],
            ),
            "maidens": _batting_board("Most maiden overs", bowling_by_maidens),
            "dot_balls": _batting_board("Most dot balls", bowling_by_dots),
        },
        "recent_results": _recent_results(completed),
        "awards": awards,
        "qualification": QUALIFICATION,
    }
