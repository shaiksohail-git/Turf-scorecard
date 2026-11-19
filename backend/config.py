"""Application configuration.

All runtime settings come from environment variables, optionally loaded from a
``.env`` file at the project root (see ``.env.example``).

PostgreSQL is the production target. The automated test suite overrides
``SQLALCHEMY_DATABASE_URI`` with a throwaway SQLite database so the tests need
no external service; the schema and the scoring code only use portable SQL
features so both dialects behave identically.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

FRONTEND_DIR = PROJECT_ROOT / "frontend"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable using common truthy spellings."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    """Default (development/production) configuration."""

    APP_NAME = "GullyScore"
    APP_VERSION = "0.2.0"

    SECRET_KEY = os.getenv("GULLY_SECRET_KEY", "dev-secret-change-me")

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://gully:gully@localhost:5432/gullyscore"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 300}

    FRONTEND_DIR = FRONTEND_DIR
    MIGRATIONS_DIR = MIGRATIONS_DIR
    CORS_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]
    CORS_SUPPORTS_CREDENTIALS = True

    # Production authentication. The first account can always register; later
    # registrations require ALLOW_REGISTRATION=true.
    AUTH_REQUIRED = env_bool("AUTH_REQUIRED", False)
    ALLOW_REGISTRATION = env_bool("ALLOW_REGISTRATION", False)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = timedelta(days=int(os.getenv("SESSION_DAYS", "7")))
    TRUST_PROXY = env_bool("TRUST_PROXY", False)

    # Process-local fixed-window limits; use a shared limiter if running more
    # than one backend process.
    RATE_LIMIT_ENABLED = env_bool("RATE_LIMIT_ENABLED", True)
    RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "1000"))
    RATE_LIMIT_SCORING_REQUESTS = int(os.getenv("RATE_LIMIT_SCORING_REQUESTS", "300"))
    RATE_LIMIT_AUTH_REQUESTS = int(os.getenv("RATE_LIMIT_AUTH_REQUESTS", "10"))
    RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
    RATE_LIMIT_SCORING_WINDOW = int(os.getenv("RATE_LIMIT_SCORING_WINDOW", "60"))
    RATE_LIMIT_AUTH_WINDOW = int(os.getenv("RATE_LIMIT_AUTH_WINDOW", "60"))

    MAX_CONTENT_LENGTH = 1024 * 1024
    DEBUG = env_bool("FLASK_DEBUG", False)
