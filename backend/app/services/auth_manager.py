"""Session authentication, password hashing and security audit helpers.

Authentication is optional for local single-scorekeeper development and is
enabled in production with ``AUTH_REQUIRED=true``. Passwords use Werkzeug's
salted PBKDF2 hashing; sessions are signed Flask cookies and mutations require a
CSRF token when authentication is required.
"""

from __future__ import annotations

import hmac
import secrets
from typing import Any, Mapping

from flask import current_app, request, session
from sqlalchemy import func, select
from werkzeug.security import check_password_hash, generate_password_hash

from ..errors import ForbiddenError, ValidationError
from ..extensions import db
from ..models import AuditLog, User, utcnow

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 256


def normalize_email(value: Any) -> str:
    if not isinstance(value, str):
        raise ValidationError("email is required.", details={"field": "email"})
    email = value.strip().lower()
    if len(email) < 3 or len(email) > 160 or "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValidationError("Enter a valid email address.", details={"field": "email"})
    return email


def validate_password(value: Any, field: str = "password") -> str:
    if not isinstance(value, str):
        raise ValidationError("A password is required.", details={"field": field})
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
            details={"field": field, "minimum": MIN_PASSWORD_LENGTH},
        )
    if len(value) > MAX_PASSWORD_LENGTH:
        raise ValidationError(
            "Password is too long.", details={"field": field, "maximum": MAX_PASSWORD_LENGTH}
        )
    return value


def validate_display_name(value: Any) -> str:
    if not isinstance(value, str) or not 2 <= len(value.strip()) <= 60:
        raise ValidationError(
            "display_name must be between 2 and 60 characters.",
            details={"field": "display_name"},
        )
    return value.strip()


def _auth_enabled() -> bool:
    return bool(current_app.config.get("AUTH_REQUIRED", False))


def user_count() -> int:
    return int(db.session.scalar(select(func.count(User.id))) or 0)


def registration_allowed() -> bool:
    """The first account is always allowed so a deployment can be bootstrapped."""
    if not _auth_enabled():
        return False
    return user_count() == 0 or bool(current_app.config.get("ALLOW_REGISTRATION", False))


def current_user(*, optional: bool = False) -> User | None:
    """Return the signed-in user, or raise when authentication is required."""
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if isinstance(user_id, int) else None
    if user is not None and not user.is_active:
        session.clear()
        user = None
    if user is None and _auth_enabled() and not optional:
        raise ForbiddenError(
            "Sign in is required to use this API.",
            code="authentication_required",
        )
    return user


def create_account(payload: Mapping[str, Any]) -> User:
    if not isinstance(payload, Mapping):
        raise ValidationError("Request body must be a JSON object.", code="invalid_body")
    if not registration_allowed():
        raise ForbiddenError(
            "Registration is not open on this deployment.",
            code="registration_disabled",
        )

    display_name = validate_display_name(payload.get("display_name"))
    email = normalize_email(payload.get("email"))
    password = validate_password(payload.get("password"))
    if db.session.scalar(select(User).where(User.email == email)) is not None:
        raise ValidationError(
            "An account with that email already exists.", details={"field": "email"}
        )

    user = User(
        display_name=display_name,
        email=email,
        password_hash=generate_password_hash(password),
        is_active=True,
    )
    db.session.add(user)
    db.session.flush()
    record_security_event(
        "auth.register",
        actor=user.display_name,
        user_id=user.id,
        details={"email": email},
    )
    db.session.commit()
    return user


def authenticate(email: Any, password: Any) -> User | None:
    clean_email = normalize_email(email)
    if not isinstance(password, str) or not password:
        return None
    user = db.session.scalar(select(User).where(User.email == clean_email))
    if (
        user is None
        or not user.is_active
        or not user.password_hash
        or not check_password_hash(user.password_hash, password)
    ):
        return None
    user.last_login_at = utcnow()
    return user


def begin_session(user: User) -> str:
    session.clear()
    session.permanent = True
    session["user_id"] = user.id
    csrf_token = secrets.token_urlsafe(32)
    session["csrf_token"] = csrf_token
    return csrf_token


def end_session() -> None:
    session.clear()


def csrf_token() -> str | None:
    token = session.get("csrf_token")
    return token if isinstance(token, str) else None


def check_csrf(token: str | None) -> bool:
    expected = csrf_token()
    return bool(expected and token and hmac.compare_digest(expected, token))


def record_security_event(
    action: str,
    *,
    actor: str = "anonymous",
    user_id: int | None = None,
    details: Mapping[str, Any] | None = None,
) -> AuditLog:
    """Persist a security event without letting audit failure break auth."""
    forwarded = request.headers.get("X-Forwarded-For", "") if current_app.config.get("TRUST_PROXY") else ""
    ip_address = (forwarded.split(",")[0].strip() if forwarded else request.remote_addr) or None
    try:
        row = AuditLog(
            action=action[:64],
            actor=(actor or "anonymous")[:64],
            user_id=user_id,
            ip_address=(ip_address or "")[:64] or None,
            user_agent=(request.user_agent.string or "")[:255] or None,
            details=dict(details or {}),
        )
        db.session.add(row)
        db.session.flush()
        return row
    except Exception:  # pragma: no cover - depends on DB/audit table availability
        db.session.rollback()
        current_app.logger.exception("Could not write security audit event %s", action)
        raise
