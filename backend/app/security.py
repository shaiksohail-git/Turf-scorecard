"""Application security middleware: auth guard, CSRF, headers and rate limits."""

from __future__ import annotations

import hmac
from typing import Callable

from flask import Flask, current_app, jsonify, redirect, request, session
from werkzeug.middleware.proxy_fix import ProxyFix

from .errors import ForbiddenError
from .services.auth_manager import check_csrf, current_user
from .utils.rate_limit import RateLimiter

PUBLIC_API_PATHS = {
    "/api/health",
    "/api/auth/session",
    "/api/auth/login",
    "/api/auth/register",
}
PUBLIC_PREFIXES = (
    "/css/",
    "/js/",
    "/components/",
    "/icons/",
    "/pages/login.html",
    "/manifest.webmanifest",
    "/sw.js",
    "/healthz",
)


def _is_public(path: str) -> bool:
    return path in PUBLIC_API_PATHS or path.startswith(PUBLIC_PREFIXES)


def _json_auth_error(message: str, code: str, status: int = 401):
    return jsonify({"error": {"code": code, "message": message, "details": {}}}), status


def require_match_access(match) -> None:
    """Reject cross-owner access when production authentication is enabled."""
    if not current_app.config.get("AUTH_REQUIRED", False):
        return
    user = current_user(optional=True)
    if user is not None and match.owner_id is not None and match.owner_id != user.id:
        raise ForbiddenError("You do not have access to this match.", code="forbidden")


def require_series_access(series) -> None:
    if not current_app.config.get("AUTH_REQUIRED", False):
        return
    user = current_user(optional=True)
    if user is not None and series.owner_id is not None and series.owner_id != user.id:
        raise ForbiddenError("You do not have access to this series.", code="forbidden")


def _rate_limit_for(path: str) -> tuple[int, int]:
    if path in {"/api/auth/login", "/api/auth/register"}:
        return (
            int(current_app.config.get("RATE_LIMIT_AUTH_REQUESTS", 10)),
            int(current_app.config.get("RATE_LIMIT_AUTH_WINDOW", 60)),
        )
    if "/deliveries" in path or "/retirements" in path:
        return (
            int(current_app.config.get("RATE_LIMIT_SCORING_REQUESTS", 300)),
            int(current_app.config.get("RATE_LIMIT_SCORING_WINDOW", 60)),
        )
    return (
        int(current_app.config.get("RATE_LIMIT_REQUESTS", 1000)),
        int(current_app.config.get("RATE_LIMIT_WINDOW", 60)),
    )


def install_security(app: Flask) -> None:
    """Install proxy handling, the auth/CSRF guard, rate limiting and headers."""
    if app.config.get("TRUST_PROXY"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_port=0)

    limiter = RateLimiter()
    app.extensions["gully_rate_limiter"] = limiter

    @app.before_request
    def _guard() -> object | None:
        path = request.path
        if request.method == "OPTIONS":
            return None

        if app.config.get("RATE_LIMIT_ENABLED", False) and path.startswith("/api/"):
            limit, window = _rate_limit_for(path)
            key = f"{request.remote_addr or 'unknown'}:{path if '/auth/' in path else 'api'}"
            decision = limiter.hit(key, limit, window)
            if not decision.allowed:
                response, status = _json_auth_error(
                    "Too many requests. Please slow down.",
                    "rate_limited",
                    429,
                )
                response.headers["Retry-After"] = str(decision.retry_after)
                response.headers["X-RateLimit-Remaining"] = "0"
                return response, status

        if not app.config.get("AUTH_REQUIRED", False):
            return None
        if _is_public(path):
            return None

        user = current_user(optional=True)
        if path.startswith("/api/"):
            if user is None:
                return _json_auth_error("Sign in is required.", "authentication_required")
            if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                supplied = request.headers.get("X-CSRF-Token")
                if not check_csrf(supplied):
                    return _json_auth_error(
                        "The security token is missing or invalid. Refresh and try again.",
                        "csrf_failed",
                        403,
                    )
            return None

        if path == "/" or path.startswith("/pages/"):
            if user is None:
                next_path = request.full_path.rstrip("?")
                return redirect(f"/pages/login.html?next={next_path}")
        return None

    @app.after_request
    def _headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; connect-src 'self' https:; "
            "manifest-src 'self'; worker-src 'self'",
        )
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        if request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.after_request
    def _auth_cookie(response):
        user = current_user(optional=True) if app.config.get("AUTH_REQUIRED") else None
        token = session.get("csrf_token") if user else None
        if user and token:
            response.set_cookie(
                "gully_csrf",
                token,
                httponly=False,
                secure=bool(app.config.get("SESSION_COOKIE_SECURE", False)),
                samesite=app.config.get("SESSION_COOKIE_SAMESITE", "Lax"),
                max_age=60 * 60 * 24 * 7,
            )
        return response
