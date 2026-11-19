"""Local user profile handling until authentication exists."""

from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import select

from ..errors import ValidationError
from ..extensions import db
from ..models import User

DEFAULT_DISPLAY_NAME = "Local Scorer"


def get_default_user(create: bool = True) -> User | None:
    """Return the local scorer account, creating it on first use."""
    user = db.session.execute(select(User).order_by(User.id)).scalars().first()
    if user is None and create:
        user = User(display_name=DEFAULT_DISPLAY_NAME)
        db.session.add(user)
        db.session.flush()
    return user


def update_profile(user: User, payload: Mapping[str, Any]) -> User:
    if not isinstance(payload, Mapping):
        raise ValidationError("Request body must be a JSON object.", code="invalid_body")

    display_name = payload.get("display_name", user.display_name)
    if not isinstance(display_name, str) or not 2 <= len(display_name.strip()) <= 60:
        raise ValidationError(
            "display_name must be between 2 and 60 characters.",
            details={"field": "display_name"},
        )
    user.display_name = display_name.strip()

    if "email" in payload:
        email = payload.get("email")
        if email in (None, ""):
            user.email = None
        elif isinstance(email, str) and "@" in email and len(email) <= 160:
            user.email = email.strip().lower()
        else:
            raise ValidationError(
                "email must be a valid address.", details={"field": "email"}
            )

    db.session.commit()
    return user
