"""Authentication endpoints for the optional production sign-in flow."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request, session

from ..errors import ValidationError
from ..extensions import db
from ..services.auth_manager import (
    authenticate,
    begin_session,
    create_account,
    current_user,
    end_session,
    record_security_event,
    registration_allowed,
)
from ..utils.payload import json_body
from ..utils.serializers import user_dict

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _session_payload(user=None) -> dict:
    return {
        "authenticated": user is not None,
        "auth_required": bool(current_app.config.get("AUTH_REQUIRED", False)),
        "registration_open": registration_allowed(),
        "user": user_dict(user) if user is not None else None,
    }


def _csrf_cookie(response, token: str):
    response.set_cookie(
        "gully_csrf",
        token,
        httponly=False,
        secure=bool(current_app.config.get("SESSION_COOKIE_SECURE", False)),
        samesite=current_app.config.get("SESSION_COOKIE_SAMESITE", "Lax"),
        max_age=60 * 60 * 24 * 7,
    )
    return response


@bp.get("/session")
def session_info():
    user = current_user(optional=True)
    response = jsonify({"data": _session_payload(user)})
    if user and session.get("csrf_token"):
        _csrf_cookie(response, session["csrf_token"])
    return response


@bp.post("/login")
def login():
    payload = json_body()
    user = authenticate(payload.get("email"), payload.get("password"))
    if user is None:
        record_security_event(
            "auth.login_failed",
            actor=str(payload.get("email") or "anonymous")[:64],
            details={"reason": "invalid_credentials"},
        )
        db.session.commit()
        from ..errors import ApiError

        raise ApiError(
            "Email or password is incorrect.",
            status_code=401,
            code="invalid_credentials",
        )
    token = begin_session(user)
    record_security_event(
        "auth.login", actor=user.display_name, user_id=user.id, details={"email": user.email}
    )
    db.session.commit()
    response = jsonify({"data": {**_session_payload(user), "csrf_token": token}})
    return _csrf_cookie(response, token)


@bp.post("/register")
def register():
    user = create_account(json_body())
    token = begin_session(user)
    record_security_event(
        "auth.login", actor=user.display_name, user_id=user.id, details={"first_login": True}
    )
    db.session.commit()
    response = jsonify({"data": {**_session_payload(user), "csrf_token": token}})
    response.status_code = 201
    return _csrf_cookie(response, token)


@bp.post("/logout")
def logout():
    user = current_user(optional=True)
    if user is not None:
        record_security_event(
            "auth.logout", actor=user.display_name, user_id=user.id, details={}
        )
        db.session.commit()
    end_session()
    response = jsonify({"data": {"authenticated": False}})
    response.delete_cookie("gully_csrf")
    return response


@bp.patch("/password")
def change_password():
    from werkzeug.security import generate_password_hash

    from ..services.auth_manager import validate_password

    user = current_user()
    payload = json_body()
    if not user.password_hash:
        raise ValidationError("This account has no password set.", code="password_not_set")
    from werkzeug.security import check_password_hash

    if not check_password_hash(user.password_hash, str(payload.get("current_password") or "")):
        raise ValidationError(
            "Current password is incorrect.", details={"field": "current_password"}
        )
    user.password_hash = generate_password_hash(validate_password(payload.get("new_password")))
    record_security_event(
        "auth.password_changed", actor=user.display_name, user_id=user.id, details={}
    )
    db.session.commit()
    return jsonify({"data": {"changed": True}})
