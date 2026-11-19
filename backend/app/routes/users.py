"""User profile endpoints.

Phase 1 has no authentication; these operate on the single local scorer account
so the Settings screen has a real, persisted profile.
"""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..extensions import db
from ..services.auth_manager import current_user
from ..services.user_manager import get_default_user, update_profile
from ..utils.payload import json_body
from ..utils.serializers import user_dict

bp = Blueprint("users", __name__, url_prefix="/api")


@bp.get("/users/me")
def me():
    user = current_user(optional=True) or get_default_user()
    db.session.commit()
    return jsonify({"data": user_dict(user)})


@bp.patch("/users/me")
def update_me():
    user = current_user(optional=True) or get_default_user()
    updated = update_profile(user, json_body())
    return jsonify({"data": user_dict(updated)})
