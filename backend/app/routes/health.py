"""Health and readiness endpoints."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models import utcnow

bp = Blueprint("health", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    database_ok = True
    database_error = None
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:  # pragma: no cover - depends on environment
        database_ok = False
        database_error = str(exc)
        current_app.logger.warning("Health check database failure: %s", exc)

    payload = {
        "status": "ok" if database_ok else "degraded",
        "app": current_app.config["APP_NAME"],
        "version": current_app.config["APP_VERSION"],
        "database": database_ok,
        "time": utcnow().isoformat(),
    }
    if database_error:
        payload["database_error"] = database_error
    return jsonify({"data": payload}), 200 if database_ok else 503
