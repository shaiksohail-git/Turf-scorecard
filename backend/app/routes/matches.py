"""Match endpoints: create, list, start, scorecard and timeline."""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import func, select

from ..errors import ValidationError
from ..extensions import db
from ..models import MATCH_STATUSES, Match, MatchEvent
from ..security import require_match_access
from ..services.auth_manager import current_user
from ..services.fantasy import fantasy_ledger
from ..services.match_manager import create_match, get_match, start_match
from ..services.scorecard import build_match_scorecard
from ..utils.payload import current_actor, int_arg, json_body
from ..utils.serializers import (
    event_dict,
    fantasy_point_dict,
    match_detail,
    match_summary,
)

bp = Blueprint("matches", __name__, url_prefix="/api")


@bp.get("/matches")
def list_matches():
    status = request.args.get("status")
    if status is not None and status not in MATCH_STATUSES:
        raise ValidationError(
            "Unknown match status.",
            details={"field": "status", "allowed": list(MATCH_STATUSES)},
        )
    series_id = request.args.get("series_id", type=int)
    page = int_arg("page", default=1, minimum=1, maximum=100000)
    if request.args.get("per_page") is not None:
        per_page = int_arg("per_page", default=20, minimum=1, maximum=100)
    else:
        # ``limit`` remains supported for the home screen and older clients.
        per_page = int_arg("limit", default=20, minimum=1, maximum=100)
    offset = (page - 1) * per_page

    conditions = []
    if status:
        conditions.append(Match.status == status)
    if series_id is not None:
        conditions.append(Match.series_id == series_id)
    signed_in = current_user(optional=True)
    if signed_in is not None:
        conditions.append((Match.owner_id == signed_in.id) | (Match.owner_id.is_(None)))

    count_query = select(func.count(Match.id))
    if conditions:
        count_query = count_query.where(*conditions)
    total = int(db.session.scalar(count_query) or 0)

    query = select(Match)
    if conditions:
        query = query.where(*conditions)
    matches = db.session.execute(
        query.order_by(Match.id.desc()).offset(offset).limit(per_page)
    ).scalars()
    return jsonify(
        {
            "data": [match_summary(match) for match in matches],
            "meta": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "has_more": offset + per_page < total,
            },
        }
    )


@bp.post("/matches")
def create():
    payload = json_body()
    match = create_match(payload, actor=current_actor())
    return jsonify({"data": match_detail(match)}), 201


@bp.get("/matches/<int:match_id>")
def read(match_id: int):
    match = get_match(match_id)
    require_match_access(match)
    return jsonify({"data": match_detail(match)})


@bp.post("/matches/<int:match_id>/start")
def start(match_id: int):
    match = get_match(match_id)
    require_match_access(match)
    match = start_match(match, actor=current_actor())
    return jsonify({"data": match_detail(match)})


@bp.get("/matches/<int:match_id>/scorecard")
def scorecard(match_id: int):
    match = get_match(match_id)
    require_match_access(match)
    return jsonify({"data": build_match_scorecard(match)})


@bp.get("/matches/<int:match_id>/events")
def events(match_id: int):
    match = get_match(match_id)
    require_match_access(match)
    limit = int_arg("limit", default=50, minimum=1, maximum=200)
    rows = db.session.execute(
        select(MatchEvent)
        .where(MatchEvent.match_id == match.id)
        .order_by(MatchEvent.id.desc())
        .limit(limit)
    ).scalars()
    return jsonify({"data": [event_dict(row) for row in rows]})


@bp.get("/matches/<int:match_id>/fantasy")
def fantasy(match_id: int):
    match = get_match(match_id)
    require_match_access(match)
    player_id = request.args.get("player_id", type=int)
    rows = fantasy_ledger(match.id, player_id)
    totals: dict[int, int] = {}
    for row in rows:
        totals[row.player_id] = totals.get(row.player_id, 0) + row.points
    return jsonify(
        {
            "data": {
                "config": match.fantasy_config,
                "totals": [
                    {"player_id": key, "points": value}
                    for key, value in sorted(totals.items())
                ],
                "ledger": [fantasy_point_dict(row) for row in rows],
            }
        }
    )
