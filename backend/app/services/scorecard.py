"""Read-only scorecard composition for one match."""

from __future__ import annotations

from ..models import Match
from ..utils.serializers import innings_state_dict, match_summary
from .innings_manager import active_deliveries, replay, retirements_for, rules_for_match
from .statistics import build_innings_scorecard


def build_match_scorecard(match: Match) -> dict:
    rules = rules_for_match(match)

    names: dict[int, str] = {}
    for team in (match.team_a, match.team_b):
        for player in team.players:
            names[player.id] = player.name

    innings_cards = []
    for innings in match.innings:
        deliveries = active_deliveries(innings)
        retirements = retirements_for(innings)
        state = replay(innings, rules, deliveries, retirements)
        card = build_innings_scorecard(innings, deliveries, names, rules, retirements)
        card["state"] = innings_state_dict(innings, state, rules)
        innings_cards.append(card)

    return {
        "match": match_summary(match),
        "rules": rules.to_public(),
        "innings": innings_cards,
    }
