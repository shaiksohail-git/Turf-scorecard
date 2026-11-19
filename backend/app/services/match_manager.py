"""Match lifecycle: creation with a frozen rules snapshot, and starting play."""

from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import func, select

from ..errors import ConflictError, NotFoundError, ValidationError
from ..extensions import db
from ..models import (
    Innings,
    Match,
    MatchRules,
    MatchTeam,
    Player,
    Series,
    SeriesMatch,
    Team,
    User,
    utcnow,
)
from .fantasy import FANTASY_CONFIGS, default_config_key
from .innings_manager import record_audit
from .rules_engine import PRESET_KEYS, RuleSet, build_ruleset
from .user_manager import get_default_user


def get_match(match_id: int) -> Match:
    match = db.session.get(Match, match_id)
    if match is None:
        raise NotFoundError("Match not found.", details={"match_id": match_id})
    return match


def _team_payload(raw: Any, field: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValidationError(
            f"{field} must be an object with a name and players.", details={"field": field}
        )
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValidationError(
            f"{field}.name is required.", details={"field": f"{field}.name"}
        )
    players_raw = raw.get("players")
    if not isinstance(players_raw, (list, tuple)) or not players_raw:
        raise ValidationError(
            f"{field}.players must be a non-empty list.",
            details={"field": f"{field}.players"},
        )

    players: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(players_raw):
        if isinstance(item, str):
            player_name = item.strip()
            role = "batter"
        elif isinstance(item, Mapping):
            player_name = str(item.get("name", "")).strip()
            role = str(item.get("role", "batter")).strip().lower() or "batter"
            if role not in Player.ROLES:
                raise ValidationError(
                    f"Unknown player role '{role}'.",
                    details={
                        "field": f"{field}.players[{index}].role",
                        "allowed": list(Player.ROLES),
                    },
                )
        else:
            raise ValidationError(
                "Each player must be a name or an object with a name.",
                details={"field": f"{field}.players[{index}]"},
            )
        if not player_name:
            raise ValidationError(
                "Every player needs a name.", details={"field": f"{field}.players[{index}].name"}
            )
        if player_name.lower() in seen:
            raise ValidationError(
                f"Duplicate player name '{player_name}' in {field}.",
                details={"field": f"{field}.players[{index}].name"},
            )
        seen.add(player_name.lower())
        players.append({"name": player_name, "role": role})

    short_name = raw.get("short_name")
    return {
        "name": name.strip(),
        "short_name": (str(short_name).strip()[:16] if short_name else None),
        "players": players,
    }


def _validate_squad(squad: dict[str, Any], rules: RuleSet, field: str) -> None:
    expected = rules.players_per_team
    if len(squad["players"]) != expected:
        raise ValidationError(
            f"{squad['name']} must have exactly {expected} players for this format.",
            details={
                "field": f"{field}.players",
                "expected": expected,
                "received": len(squad["players"]),
            },
        )


def _resolve_toss(
    payload: Mapping[str, Any], teams: list[Team]
) -> tuple[Team | None, str | None, Team]:
    """Return ``(toss_winner, toss_decision, batting_first_team)``."""
    toss = payload.get("toss")
    if toss is None:
        return None, None, teams[0]
    if not isinstance(toss, Mapping):
        raise ValidationError("toss must be an object.", details={"field": "toss"})

    winner_key = toss.get("winner")
    if winner_key not in ("a", "b"):
        raise ValidationError(
            "toss.winner must be 'a' or 'b'.", details={"field": "toss.winner"}
        )
    decision = toss.get("decision")
    if decision not in ("bat", "bowl"):
        raise ValidationError(
            "toss.decision must be 'bat' or 'bowl'.", details={"field": "toss.decision"}
        )

    winner = teams[0] if winner_key == "a" else teams[1]
    other = teams[1] if winner_key == "a" else teams[0]
    batting_first = winner if decision == "bat" else other
    return winner, decision, batting_first


def _resolve_owner(payload: Mapping[str, Any]) -> User:
    user_id = payload.get("user_id")
    if user_id is not None:
        user = db.session.get(User, user_id)
        if user is None:
            raise ValidationError(
                "User not found.", details={"field": "user_id", "user_id": user_id}
            )
        return user
    from flask import has_request_context

    from .auth_manager import current_user

    signed_in = current_user(optional=True) if has_request_context() else None
    if signed_in is not None:
        return signed_in
    owner = get_default_user()
    assert owner is not None  # created on demand
    return owner


def create_match(payload: Mapping[str, Any], actor: str = "scorer") -> Match:
    """Create a match atomically: every row is committed, or none is."""
    try:
        return _create_match_records(payload, actor=actor)
    except Exception:
        db.session.rollback()
        raise


def _create_match_records(payload: Mapping[str, Any], actor: str = "scorer") -> Match:
    if not isinstance(payload, Mapping):
        raise ValidationError("Request body must be a JSON object.", code="invalid_body")

    preset_key = payload.get("preset")
    if not preset_key:
        raise ValidationError(
            "A rules preset is required.",
            details={"field": "preset", "allowed": list(PRESET_KEYS)},
        )
    rules = build_ruleset(str(preset_key), payload.get("rules"))
    fantasy_config = payload.get("fantasy_config") or default_config_key(rules)
    if fantasy_config not in FANTASY_CONFIGS:
        raise ValidationError(
            "Unknown fantasy configuration.",
            details={
                "field": "fantasy_config",
                "allowed": sorted(FANTASY_CONFIGS),
            },
        )

    team_a_payload = _team_payload(payload.get("team_a"), "team_a")
    team_b_payload = _team_payload(payload.get("team_b"), "team_b")
    if team_a_payload["name"].lower() == team_b_payload["name"].lower():
        raise ValidationError(
            "The two teams must have different names.", details={"field": "team_b.name"}
        )
    _validate_squad(team_a_payload, rules, "team_a")
    _validate_squad(team_b_payload, rules, "team_b")

    series: Series | None = None
    series_id = payload.get("series_id")
    if series_id is not None:
        series = db.session.get(Series, series_id)
        if series is None:
            raise ValidationError(
                "Series not found.", details={"field": "series_id", "series_id": series_id}
            )

    owner = _resolve_owner(payload)

    teams: list[Team] = []
    for squad in (team_a_payload, team_b_payload):
        team = Team(name=squad["name"], short_name=squad["short_name"])
        db.session.add(team)
        db.session.flush()
        for order, player in enumerate(squad["players"], start=1):
            db.session.add(
                Player(
                    team_id=team.id,
                    name=player["name"],
                    role=player["role"],
                    batting_order=order,
                )
            )
        teams.append(team)
    db.session.flush()

    toss_winner, toss_decision, batting_first = _resolve_toss(payload, teams)

    match = Match(
        series_id=series.id if series else None,
        team_a_id=teams[0].id,
        team_b_id=teams[1].id,
        owner_id=owner.id,
        venue=(str(payload.get("venue")).strip()[:120] if payload.get("venue") else None),
        preset=rules.preset,
        rules=rules.to_dict(),
        rules_version=1,
        fantasy_config=fantasy_config,
        status="draft",
        toss_winner_id=toss_winner.id if toss_winner else None,
        toss_decision=toss_decision,
        batting_first_team_id=batting_first.id,
        revision=0,
    )
    db.session.add(match)
    db.session.flush()

    # Normalized rules record (same resolved values as the immutable JSON snapshot).
    db.session.add(
        MatchRules(
            match_id=match.id,
            preset=rules.preset,
            version=1,
            overs=rules.overs,
            balls_per_over=rules.balls_per_over,
            players_per_team=rules.players_per_team,
            wide_penalty=rules.wide_penalty,
            wide_counts_as_legal_ball=rules.wide_counts_as_legal_ball,
            no_ball_penalty=rules.no_ball_penalty,
            no_ball_counts_as_legal_ball=rules.no_ball_counts_as_legal_ball,
            free_hit_enabled=rules.free_hit_enabled,
            solo_batting_enabled=rules.solo_batting_enabled,
            allowed_runs=list(rules.allowed_runs),
            retired_player_option=rules.retired_player_option,
            retirement_types=list(rules.retirement_types),
            max_overs_per_bowler=rules.max_overs_per_bowler,
        )
    )

    # Normalized participation rows.
    for index, team in enumerate(teams):
        db.session.add(
            MatchTeam(
                match_id=match.id,
                team_id=team.id,
                side="a" if index == 0 else "b",
                is_toss_winner=bool(toss_winner is not None and toss_winner is team),
                bats_first=bool(batting_first is team),
            )
        )

    if series is not None:
        # Count existing links rather than the relationship: the match row is
        # already flushed, so ``series.matches`` would include it.
        existing_links = (
            db.session.scalar(
                select(func.count(SeriesMatch.id)).where(
                    SeriesMatch.series_id == series.id
                )
            )
            or 0
        )
        db.session.add(
            SeriesMatch(
                series_id=series.id,
                match_id=match.id,
                position=existing_links + 1,
            )
        )

    record_audit(
        match,
        None,
        None,
        "match.created",
        {
            "preset": rules.preset,
            "rules": rules.to_dict(),
            "fantasy_config": fantasy_config,
            "teams": [team.name for team in teams],
        },
        actor,
    )
    db.session.commit()
    return match


def start_match(match: Match, actor: str = "scorer") -> Match:
    """Create both innings and put the match live."""
    if match.status != "draft":
        raise ConflictError(
            "Only a draft match can be started.",
            code="invalid_match_state",
            details={"status": match.status},
        )

    rules = RuleSet.from_dict(match.rules)
    batting_first_id = match.batting_first_team_id or match.team_a_id
    bowling_first_id = (
        match.team_b_id if batting_first_id == match.team_a_id else match.team_a_id
    )

    squads: dict[int, list[int]] = {}
    for team_id in (batting_first_id, bowling_first_id):
        team = db.session.get(Team, team_id)
        if team is None:
            raise ValidationError("A team for this match no longer exists.")
        players = sorted(team.players, key=lambda player: player.batting_order)
        if len(players) != rules.players_per_team:
            raise ValidationError(
                f"{team.name} must have exactly {rules.players_per_team} players for this format.",
                details={
                    "team_id": team.id,
                    "expected": rules.players_per_team,
                    "received": len(players),
                },
            )
        squads[team_id] = [player.id for player in players]

    try:
        first = db.session.execute(
            select(Innings).where(Innings.match_id == match.id, Innings.number == 1)
        ).scalar_one_or_none()
        if first is None:
            first = Innings(
                match_id=match.id,
                number=1,
                batting_team_id=batting_first_id,
                bowling_team_id=bowling_first_id,
                status="live",
                batting_order=squads[batting_first_id],
            )
            db.session.add(first)
            db.session.flush()

        second = db.session.execute(
            select(Innings).where(Innings.match_id == match.id, Innings.number == 2)
        ).scalar_one_or_none()
        if second is None:
            db.session.add(
                Innings(
                    match_id=match.id,
                    number=2,
                    batting_team_id=bowling_first_id,
                    bowling_team_id=batting_first_id,
                    status="pending",
                    batting_order=squads[bowling_first_id],
                )
            )

        # Keep the normalized participation rows in step with the toss.
        for row in match.match_teams:
            row.bats_first = row.team_id == batting_first_id
            row.is_toss_winner = (
                match.toss_winner_id is not None and row.team_id == match.toss_winner_id
            )

        match.status = "live"
        match.started_at = match.started_at or utcnow()
        match.revision = (match.revision or 0) + 1

        record_audit(
            match,
            first.id,
            None,
            "match.started",
            {"batting_first_team_id": batting_first_id, "innings_id": first.id},
            actor,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return match
