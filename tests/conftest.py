"""Pytest fixtures.

The suite runs against a throwaway in-memory SQLite database so no external
service is needed. Set ``TEST_DATABASE_URL`` to run the same tests against
PostgreSQL as well.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app import create_app  # noqa: E402
from app.extensions import db as _db  # noqa: E402
from helpers import create_and_start, short_payload, turf_payload  # noqa: E402

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret"
    APP_NAME = "GullyScore"
    APP_VERSION = "test"
    FRONTEND_DIR = PROJECT_ROOT / "frontend"
    CORS_ORIGINS = ["*"]
    MAX_CONTENT_LENGTH = 1024 * 1024
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = TEST_DATABASE_URL or "sqlite+pysqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = (
        {}
        if TEST_DATABASE_URL
        else {
            "poolclass": StaticPool,
            "connect_args": {"check_same_thread": False},
        }
    )


@pytest.fixture()
def app():
    application = create_app(TestConfig)
    with application.app_context():
        _db.create_all()
        try:
            yield application
        finally:
            _db.session.remove()
            _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def session(app):
    return _db.session


@pytest.fixture()
def turf_match(client):
    """A started Custom Turf match (6 overs, 5 a side) with Team A batting."""
    return create_and_start(client, turf_payload())


@pytest.fixture()
def short_match(client):
    """A started one over, two-a-side match with Team A batting."""
    return create_and_start(client, short_payload())
