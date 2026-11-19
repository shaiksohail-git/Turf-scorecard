"""JSON serialisers shared by the API routes."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ..models import (
    Delivery,
    FantasyPoint,
    Innings,
    Match,
    MatchEvent,
    Player,
    Retirement,
    Series,
    Team,
    User,
)
from ..services.rules_engine import RuleSet
from ..services.statistics import overs_label


def iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value is not None else None


def player_dict(player: Player) -> dict[str, Any]:
    return {
        "id": player.id,
        "team_id": player.team_id,
        "name": player.name,
        "role": player.role,
        "batting_order": player.batting_order,
    }


def team_dict(team: Team, include_players: bool = False) -> dict[str, Any]:
    data = {
        "id": team.id,
        "name": team.name,
        "short_name": team.short_name,
    }
    if include_players:
        data["players"] = [
            player_dict(player)
            for player in sorted(team.players, key=lambda player: player.batting_order)
        ]
    return data


def user_dict(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "display_name": user.display_name,
        "email": user.email,
        "is_active": user.is_active,
        "created_at": iso(user.created_at),
    }


def innings_state_dict(innings: Innings, state, rules: RuleSet) -> dict[str, Any]:
    runs_needed = None
    if innings.target is not None:
        runs_needed = max(innings.target - state.runs, 0)
    return {
        "innings_id": innings.id,
        "number": innings.number,
        "status": innings.status,
        "batting_team_id": innings.batting_team_id,
        "bowling_team_id": innings.bowling_team_id,
        "runs": state.runs,
        "wickets": state.wickets,
        "legal_balls": state.legal_balls,
        "overs": overs_label(state.legal_balls, rules.balls_per_over),
        "striker_id": state.striker_id,
        "non_striker_id": state.non_striker_id,
        "last_bowler_id": state.last_bowler_id,
        "pending_free_hit": state.pending_free_hit,
        "target": innings.target,
        "runs_needed": runs_needed,
        "balls_remaining": max(rules.total_balls - state.legal_balls, 0),
        "max_wickets": rules.max_wickets,
        "is_complete": state.is_complete,
        "solo_mode": getattr(state, "solo_mode", False),
        "can_score": state.striker_id is not None and not state.is_complete,
        "retired_active_ids": list(getattr(state, "retired_active_ids", ())),
        "retired_out_ids": list(getattr(state, "retired_out_ids", ())),
        "available_player_ids": list(getattr(state, "available_player_ids", ())),
        "revision": innings.revision,
    }


def delivery_event(delivery: Delivery) -> dict[str, Any]:
    return {
        "id": delivery.id,
        "sequence": delivery.sequence,
        "over_number": delivery.over_number,
        "ball_in_over": delivery.ball_in_over,
        "striker_id": delivery.striker_id,
        "non_striker_id": delivery.non_striker_id,
        "bowler_id": delivery.bowler_id,
        "runs_off_bat": delivery.runs_off_bat,
        "extra_type": delivery.extra_type,
        "extra_runs": delivery.extra_runs,
        "penalty_runs": delivery.penalty_runs,
        "total_runs": delivery.total_runs,
        "is_legal_ball": delivery.is_legal_ball,
        "is_free_hit": delivery.is_free_hit,
        "is_wicket": delivery.is_wicket,
        "wicket_type": delivery.wicket_type,
        "dismissed_player_id": delivery.dismissed_player_id,
        "dismissed_role": delivery.dismissed_role,
        "is_voided": delivery.is_voided,
        "void_reason": delivery.void_reason,
        "client_event_id": delivery.client_event_id,
        "created_at": iso(delivery.created_at),
    }


def retirement_dict(retirement: Retirement) -> dict[str, Any]:
    return {
        "id": retirement.id,
        "innings_id": retirement.innings_id,
        "player_id": retirement.player_id,
        "player_name": retirement.player.name if retirement.player else None,
        "retirement_type": retirement.retirement_type,
        "reason": retirement.reason,
        "replacement_player_id": retirement.replacement_player_id,
        "retired_after_sequence": retirement.retired_after_sequence,
        "retired_at": iso(retirement.retired_at),
        "returned_after_sequence": retirement.returned_after_sequence,
        "returned_at": iso(retirement.returned_at),
        "can_return": retirement.returned_at is None
        and retirement.retirement_type != "retired_out",
    }


def fantasy_point_dict(point: FantasyPoint) -> dict[str, Any]:
    return {
        "id": point.id,
        "match_id": point.match_id,
        "innings_id": point.innings_id,
        "player_id": point.player_id,
        "delivery_id": point.delivery_id,
        "category": point.category,
        "points": point.points,
        "detail": point.detail,
        "source_key": point.source_key,
        "created_at": iso(point.created_at),
    }


def event_dict(event: MatchEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "match_id": event.match_id,
        "innings_id": event.innings_id,
        "delivery_id": event.delivery_id,
        "event_type": event.event_type,
        "actor": event.actor,
        "payload": event.payload,
        "created_at": iso(event.created_at),
    }


def match_summary(match: Match) -> dict[str, Any]:
    rules = RuleSet.from_dict(match.rules)
    date_value = match.started_at or match.created_at
    return {
        "id": match.id,
        "preset": match.preset,
        "status": match.status,
        "fantasy_config": match.fantasy_config,
        "series_id": match.series_id,
        "owner_id": match.owner_id,
        "venue": match.venue,
        "date": iso(date_value),
        "overs": rules.overs,
        "balls_per_over": rules.balls_per_over,
        "players_per_team": rules.players_per_team,
        "teams": [team_dict(match.team_a), team_dict(match.team_b)],
        "batting_first_team_id": match.batting_first_team_id,
        "innings": [
            {
                "innings_id": innings.id,
                "number": innings.number,
                "batting_team_id": innings.batting_team_id,
                "bowling_team_id": innings.bowling_team_id,
                "runs": innings.total_runs,
                "wickets": innings.wickets,
                "legal_balls": innings.legal_balls,
                "overs": overs_label(innings.legal_balls, rules.balls_per_over),
                "status": innings.status,
                "target": innings.target,
            }
            for innings in match.innings
        ],
        "result": match.result,
        "result_summary": (match.result or {}).get("summary"),
        "revision": match.revision,
        "created_at": iso(match.created_at),
        "started_at": iso(match.started_at),
        "completed_at": iso(match.completed_at),
    }


def match_detail(match: Match) -> dict[str, Any]:
    rules = RuleSet.from_dict(match.rules)
    data = match_summary(match)
    data["rules"] = rules.to_public()
    data["rules_version"] = match.rules_version
    data["toss"] = {
        "winner_team_id": match.toss_winner_id,
        "decision": match.toss_decision,
    }
    data["team_a"] = team_dict(match.team_a, include_players=True)
    data["team_b"] = team_dict(match.team_b, include_players=True)
    data["match_teams"] = [
        {
            "team_id": row.team_id,
            "side": row.side,
            "is_toss_winner": row.is_toss_winner,
            "bats_first": row.bats_first,
        }
        for row in match.match_teams
    ]
    return data


def series_dict(series: Series, include_matches: bool = False) -> dict[str, Any]:
    planned = getattr(series, "planned_matches", 0) or 0
    completed = sum(1 for match in series.matches if match.status == "completed")
    team_a_players = list(getattr(series, "team_a_players", None) or [])
    team_b_players = list(getattr(series, "team_b_players", None) or [])
    team_a_name = getattr(series, "team_a_name", None)
    team_b_name = getattr(series, "team_b_name", None)
    data = {
        "id": series.id,
        "name": series.name,
        "format": series.format,
        "preset": series.preset,
        "planned_matches": planned,
        "team_a": {"name": team_a_name, "players": team_a_players},
        "team_b": {"name": team_b_name, "players": team_b_players},
        "teams": [
            {"name": name, "players": players}
            for name, players in (
                (team_a_name, team_a_players),
                (team_b_name, team_b_players),
            )
            if name
        ],
        "start_date": iso(series.start_date),
        "end_date": iso(series.end_date),
        "notes": series.notes,
        "created_at": iso(series.created_at),
        "updated_at": iso(series.updated_at),
        "match_count": len(series.matches),
        "matches_played": completed,
        "matches_remaining": max(planned - completed, 0),
    }
    if include_matches:
        data["matches"] = [match_summary(match) for match in series.matches]
    return data
