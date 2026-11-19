"""Configurable fantasy points with an itemized, rebuildable ledger.

T20 and short-format matches use separate configurations. Awards are derived
only from deliveries and retirements; the ledger is deleted and rebuilt inside
the scoring transaction, and ``(match_id, source_key)`` is unique so a milestone,
maiden or haul can never be awarded twice.

Fielding and captaincy points are deliberately not modelled.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import delete, select

from ..extensions import db
from ..models import FantasyPoint, Innings
from .innings_manager import active_deliveries, retirements_for, rules_for_match
from .rules_engine import RuleSet
from .statistics import build_innings_scorecard


@dataclass(frozen=True)
class FantasyConfig:
    key: str
    label: str
    run_points: int = 1
    four_points: int = 4
    six_points: int = 6
    milestone_25: int = 4
    milestone_50: int = 8
    milestone_100: int = 16
    duck_points: int = -2
    wicket_points: int = 25
    bowled_lbw_points: int = 8
    maiden_points: int = 12
    haul_3: int = 4
    haul_4: int = 8
    haul_5: int = 16
    min_balls_for_rate: int = 6
    # (threshold, points) evaluated from the highest threshold down.
    strike_rate_bands: tuple[tuple[float, int], ...] = (
        (170, 6),
        (150, 4),
        (130, 2),
        (60, -2),
        (0, -6),
    )
    # (maximum economy, points) evaluated from the lowest maximum up; anything
    # above the last band gets ``economy_penalty``.
    economy_bands: tuple[tuple[float, int], ...] = (
        (6, 6),
        (7.5, 4),
        (9, 2),
        (11, 0),
    )
    economy_penalty: int = -6


FANTASY_T20 = FantasyConfig(
    key="t20",
    label="T20 fantasy",
    strike_rate_bands=((170, 6), (150, 4), (130, 2), (60, -2), (0, -6)),
    economy_bands=((6, 6), (7.5, 4), (9, 2), (11, 0)),
    economy_penalty=-6,
)

FANTASY_SHORT = FantasyConfig(
    key="short",
    label="Short-format fantasy",
    strike_rate_bands=((200, 6), (150, 4), (100, 2), (50, -4), (0, -6)),
    economy_bands=((7, 6), (9, 4), (11, 2), (14, 0)),
    economy_penalty=-6,
)

FANTASY_CONFIGS = {config.key: config for config in (FANTASY_T20, FANTASY_SHORT)}


def config_for(key: str | None) -> FantasyConfig:
    return FANTASY_CONFIGS.get(key or "short", FANTASY_SHORT)


def default_config_key(rules: RuleSet) -> str:
    if rules.preset == "custom_turf":
        return "short"
    return "t20" if rules.overs >= 10 else "short"


def _band_points(bands: Iterable[tuple[float, int]], value: float) -> int:
    for threshold, points in bands:
        if value >= threshold:
            return points
    return 0


def _economy_points(config: FantasyConfig, economy: float) -> int:
    for maximum, points in config.economy_bands:
        if economy <= maximum:
            return points
    return config.economy_penalty


def _maidens(deliveries, bowler_id: int, rules: RuleSet) -> list[int]:
    overs: dict[int, dict[str, int]] = {}
    for delivery in deliveries:
        if delivery.bowler_id != bowler_id:
            continue
        entry = overs.setdefault(delivery.over_number, {"legal": 0, "runs": 0})
        if delivery.is_legal_ball:
            entry["legal"] += 1
        if delivery.extra_type not in {"bye", "leg_bye"}:
            entry["runs"] += delivery.total_runs
    return [
        over
        for over, entry in overs.items()
        if entry["legal"] >= rules.balls_per_over and entry["runs"] == 0
    ]


def _innings_awards(
    innings: Innings,
    rules: RuleSet,
    config: FantasyConfig,
    names: dict[int, str],
    deliveries: list,
) -> dict[str, dict]:
    card = build_innings_scorecard(
        innings, deliveries, names, rules, retirements_for(innings)
    )
    awards: dict[str, dict] = {}

    def add(
        player_id: int,
        suffix: str,
        category: str,
        points: int,
        detail: str,
        delivery_id: int | None = None,
    ) -> None:
        if points == 0:
            return
        key = f"innings:{innings.id}:player:{player_id}:{suffix}"
        awards[key] = {
            "player_id": player_id,
            "innings_id": innings.id,
            "delivery_id": delivery_id,
            "category": category,
            "points": points,
            "detail": detail,
            "source_key": key,
        }

    for line in card["batting"]:
        player_id = line["player_id"]
        prefix = ""
        add(player_id, "runs", "runs", line["runs"] * config.run_points, f"{line['runs']} runs")
        add(player_id, "fours", "boundary_four", line["fours"] * config.four_points, f"{line['fours']} fours")
        add(player_id, "sixes", "boundary_six", line["sixes"] * config.six_points, f"{line['sixes']} sixes")

        for threshold, points in (
            (25, config.milestone_25),
            (50, config.milestone_50),
            (100, config.milestone_100),
        ):
            if line["runs"] >= threshold:
                add(
                    player_id,
                    f"milestone:{threshold}",
                    f"milestone_{threshold}",
                    points,
                    f"Reached {threshold} runs",
                )

        if (
            line["is_out"]
            and line["runs"] == 0
            and line["balls"] >= 1
            and line["retirement_type"] != "retired_out"
        ):
            add(player_id, "duck", "duck", config.duck_points, "Duck")

        if line["balls"] >= config.min_balls_for_rate:
            strike_rate = line["runs"] / line["balls"] * 100
            add(
                player_id,
                "strike_rate",
                "strike_rate",
                _band_points(config.strike_rate_bands, strike_rate),
                f"Strike rate {strike_rate:.1f}",
            )

    for line in card["bowling"]:
        player_id = line["player_id"]
        wickets = line["wickets"]
        add(
            player_id,
            "wickets",
            "wicket",
            wickets * config.wicket_points,
            f"{wickets} wickets",
        )
        bowled_lbw = sum(
            1
            for delivery in deliveries
            if delivery.bowler_id == player_id
            and delivery.is_wicket
            and delivery.wicket_type in {"bowled", "lbw"}
        )
        add(
            player_id,
            "bowled_lbw",
            "bowled_lbw",
            bowled_lbw * config.bowled_lbw_points,
            f"{bowled_lbw} bowled/LBW",
        )

        for over in _maidens(deliveries, player_id, rules):
            add(
                player_id,
                f"maiden:{over}",
                "maiden",
                config.maiden_points,
                f"Maiden over {over}",
            )

        for threshold in (3, 4, 5):
            if wickets >= threshold:
                points = {3: config.haul_3, 4: config.haul_4, 5: config.haul_5}[threshold]
                add(
                    player_id,
                    f"haul:{threshold}",
                    f"haul_{threshold}",
                    points,
                    f"{threshold}-wicket haul",
                )

        if line["legal_balls"] >= config.min_balls_for_rate:
            add(
                player_id,
                "economy",
                "economy",
                _economy_points(config, line["economy"]),
                f"Economy {line['economy']:.2f}",
            )

    return awards


def rebuild_fantasy_ledger(match) -> dict[int, int]:
    """Rebuild every fantasy award for a match and return per-player totals."""
    config = config_for(getattr(match, "fantasy_config", None))
    rules = rules_for_match(match)
    names: dict[int, str] = {}
    for team in (match.team_a, match.team_b):
        for player in team.players:
            names[player.id] = player.name

    db.session.execute(delete(FantasyPoint).where(FantasyPoint.match_id == match.id))

    totals: dict[int, int] = defaultdict(int)
    for innings in match.innings:
        deliveries = active_deliveries(innings)
        awards = _innings_awards(innings, rules, config, names, deliveries)
        for award in awards.values():
            db.session.add(
                FantasyPoint(
                    match_id=match.id,
                    innings_id=award["innings_id"],
                    player_id=award["player_id"],
                    delivery_id=award["delivery_id"],
                    category=award["category"],
                    points=award["points"],
                    source_key=award["source_key"],
                    detail=award["detail"],
                )
            )
            totals[award["player_id"]] += award["points"]

    db.session.flush()
    return dict(totals)


def fantasy_ledger(match_id: int, player_id: int | None = None) -> list[FantasyPoint]:
    query = (
        select(FantasyPoint)
        .where(FantasyPoint.match_id == match_id)
        .order_by(FantasyPoint.id)
    )
    if player_id is not None:
        query = query.where(FantasyPoint.player_id == player_id)
    return list(db.session.execute(query).scalars())
