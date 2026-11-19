"""API error types and JSON error handlers.

Every failure path returns the same envelope so the frontend can render errors
uniformly::

    {"error": {"code": "validation_error", "message": "...", "details": {...}}}
"""

from __future__ import annotations

from typing import Any, Mapping

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from .extensions import db


class ApiError(Exception):
    """Base class for expected, client-facing failures."""

    status_code = 400
    code = "api_error"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class ValidationError(ApiError):
    status_code = 422
    code = "validation_error"


class NotFoundError(ApiError):
    status_code = 404
    code = "not_found"


class ConflictError(ApiError):
    status_code = 409
    code = "conflict"


class ForbiddenError(ApiError):
    status_code = 403
    code = "forbidden"


class RateLimitError(ApiError):
    status_code = 429
    code = "rate_limited"


class DeliveryValidationError(ValueError):
    """Raised by the scoring engine for a delivery that breaks the rules.

    It is a plain ``ValueError`` so the engine stays testable without Flask,
    and it is translated to a 422 response by the handler below.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "invalid_delivery",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _handle_api_error(error: ApiError):
        db.session.rollback()
        return jsonify({"error": error.to_dict()}), error.status_code

    @app.errorhandler(DeliveryValidationError)
    def _handle_delivery_error(error: DeliveryValidationError):
        db.session.rollback()
        return jsonify({"error": error.to_dict()}), 422

    @app.errorhandler(HTTPException)
    def _handle_http_error(error: HTTPException):
        db.session.rollback()
        payload = {
            "code": (error.name or "http_error").lower().replace(" ", "_"),
            "message": error.description or "Request failed",
            "details": {},
        }
        return jsonify({"error": payload}), error.code or 500

    @app.errorhandler(Exception)
    def _handle_unexpected_error(error: Exception):
        db.session.rollback()
        app.logger.exception("Unhandled exception while serving request")
        if app.config.get("TESTING"):
            raise error
        payload = {
            "code": "internal_error",
            "message": "Something went wrong on the server.",
            "details": {},
        }
        return jsonify({"error": payload}), 500
