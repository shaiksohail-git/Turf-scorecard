"""Statistics endpoints backing the Stats screen."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..services.auth_manager import current_user
from ..services.stats_manager import player_stats, stats_overview, team_stats
from ..utils.payload import int_arg

bp = Blueprint("stats", __name__, url_prefix="/api")


@bp.get("/stats/overview")
def overview():
    limit = int_arg("limit", default=5, minimum=1, maximum=20)
    user = current_user(optional=True)
    return jsonify({"data": stats_overview(limit, owner_id=user.id if user else None)})


@bp.get("/stats/players")
def players():
    limit = int_arg("limit", default=50, minimum=1, maximum=200)
    user = current_user(optional=True)
    return jsonify({"data": player_stats(limit, owner_id=user.id if user else None)})


@bp.get("/stats/teams")
def teams():
    user = current_user(optional=True)
    return jsonify({"data": team_stats(owner_id=user.id if user else None)})
