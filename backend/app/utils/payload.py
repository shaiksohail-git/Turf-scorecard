"""Small helpers shared by the API routes."""

from __future__ import annotations

from flask import request

from ..errors import ValidationError


def json_body() -> dict:
    """Return the request JSON object or raise a validation error."""
    payload = request.get_json(silent=True)
    if payload is None:
        raise ValidationError("A JSON body is required.", code="invalid_body")
    if not isinstance(payload, dict):
        raise ValidationError("The JSON body must be an object.", code="invalid_body")
    return payload


def current_actor() -> str:
    """Identify who is scoring, for the audit trail."""
    actor = (request.headers.get("X-Actor") or "scorer").strip()
    return actor[:64] or "scorer"


def int_arg(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"{name} must be an integer.", details={"field": name}
        ) from exc
    return max(minimum, min(maximum, value))
