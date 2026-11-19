"""Rules preset endpoints.

These let the frontend show the exact defaults and validate an edited
configuration before a match is created.
"""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..errors import ValidationError
from ..services.rules_engine import (
    EXTRA_TYPES,
    PRESET_KEYS,
    RETIREMENT_TYPES,
    WICKET_TYPES,
    build_ruleset,
    preset_catalog,
    validate_ruleset,
)
from ..utils.payload import json_body

bp = Blueprint("rules", __name__, url_prefix="/api")


@bp.get("/rules/presets")
def list_presets():
    return jsonify(
        {
            "data": {
                "presets": preset_catalog(),
                "preset_keys": list(PRESET_KEYS),
                "extra_types": list(EXTRA_TYPES),
                "wicket_types": list(WICKET_TYPES),
                "retirement_types": list(RETIREMENT_TYPES),
            }
        }
    )


@bp.post("/rules/validate")
def validate_rules():
    payload = json_body()
    preset_key = payload.get("preset")
    if not preset_key:
        raise ValidationError(
            "A preset key is required.",
            details={"field": "preset", "allowed": list(PRESET_KEYS)},
        )
    rules = build_ruleset(str(preset_key), payload.get("rules"))
    validate_ruleset(rules)
    return jsonify({"data": rules.to_public()})
