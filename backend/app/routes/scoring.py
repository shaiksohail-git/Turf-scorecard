"""Scoring endpoints: innings state, delivery events and undo."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..errors import ValidationError
from ..security import require_match_access
from ..services.retirement_manager import (
    list_retirements,
    record_retirement,
    return_to_batting,
)
from ..services.innings_manager import (
    all_deliveries,
    current_state,
    get_innings,
    get_match_for,
    record_delivery,
    rules_for_match,
    undo_last_delivery,
)
from ..utils.payload import current_actor, json_body
from ..utils.serializers import delivery_event, innings_state_dict, retirement_dict

bp = Blueprint("scoring", __name__, url_prefix="/api")


def _state_payload(innings):
    rules = rules_for_match(get_match_for(innings))
    return innings_state_dict(innings, current_state(innings), rules)


def _accessible_innings(innings_id: int):
    innings = get_innings(innings_id)
    require_match_access(get_match_for(innings))
    return innings


@bp.get("/innings/<int:innings_id>")
def innings_state(innings_id: int):
    innings = _accessible_innings(innings_id)
    return jsonify({"data": _state_payload(innings)})


@bp.get("/innings/<int:innings_id>/deliveries")
def list_deliveries(innings_id: int):
    innings = _accessible_innings(innings_id)
    include_voided = request.args.get("include_voided", "false").lower() in {"1", "true", "yes"}
    rows = all_deliveries(innings)
    events = [
        delivery_event(row) for row in rows if include_voided or not row.is_voided
    ]
    return jsonify({"data": events})


@bp.post("/innings/<int:innings_id>/deliveries")
def create_delivery(innings_id: int):
    innings = _accessible_innings(innings_id)
    payload = json_body()
    delivery, state, duplicate = record_delivery(
        innings, payload, actor=current_actor()
    )
    rules = rules_for_match(get_match_for(innings))
    return (
        jsonify(
            {
                "data": {
                    "delivery": delivery_event(delivery),
                    "state": innings_state_dict(innings, state, rules),
                    "duplicate": duplicate,
                }
            }
        ),
        200 if duplicate else 201,
    )


@bp.get("/innings/<int:innings_id>/retirements")
def retirements(innings_id: int):
    innings = _accessible_innings(innings_id)
    return jsonify({"data": [retirement_dict(row) for row in list_retirements(innings)]})


@bp.post("/innings/<int:innings_id>/retirements")
def create_retirement(innings_id: int):
    innings = _accessible_innings(innings_id)
    event = record_retirement(innings, json_body(), actor=current_actor())
    rules = rules_for_match(get_match_for(innings))
    return (
        jsonify(
            {
                "data": {
                    "retirement": retirement_dict(event),
                    "state": innings_state_dict(innings, current_state(innings), rules),
                }
            }
        ),
        201,
    )


@bp.post("/innings/<int:innings_id>/retirements/<int:retirement_id>/return")
def return_batter(innings_id: int, retirement_id: int):
    innings = _accessible_innings(innings_id)
    event = return_to_batting(innings, retirement_id, actor=current_actor())
    rules = rules_for_match(get_match_for(innings))
    return jsonify(
        {
            "data": {
                "retirement": retirement_dict(event),
                "state": innings_state_dict(innings, current_state(innings), rules),
            }
        }
    )


@bp.post("/innings/<int:innings_id>/deliveries/undo")
def undo_delivery(innings_id: int):
    innings = _accessible_innings(innings_id)
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        raise ValidationError("The JSON body must be an object.", code="invalid_body")
    reason = payload.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise ValidationError("reason must be a string.", details={"field": "reason"})

    delivery, state = undo_last_delivery(innings, reason=reason, actor=current_actor())
    rules = rules_for_match(get_match_for(innings))
    return jsonify(
        {
            "data": {
                "undone": delivery_event(delivery),
                "state": innings_state_dict(innings, state, rules),
            }
        }
    )
