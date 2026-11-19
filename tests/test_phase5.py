"""Phase 5 security, authorization and pagination regressions."""

from __future__ import annotations

from sqlalchemy import select

from app.extensions import db
from app.models import AuditLog, Match, User
from helpers import short_payload


def enable_auth(app, **overrides):
    app.config.update(
        AUTH_REQUIRED=True,
        ALLOW_REGISTRATION=True,
        RATE_LIMIT_ENABLED=False,
        SESSION_COOKIE_SECURE=False,
    )
    app.config.update(overrides)
    return app


def register(client, email="a@example.com", name="Scorer A"):
    response = client.post(
        "/api/auth/register",
        json={"display_name": name, "email": email, "password": "correct horse battery"},
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["csrf_token"]


def login(client, email, password="correct horse battery"):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]["csrf_token"]


def create_match(client, token=None):
    headers = {"X-CSRF-Token": token} if token else {}
    response = client.post("/api/matches", json=short_payload(), headers=headers)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]


def test_auth_is_required_and_first_registration_is_allowed(app, client):
    enable_auth(app)

    assert client.get("/api/matches").status_code == 401
    session = client.get("/api/auth/session").get_json()["data"]
    assert session["auth_required"] is True
    assert session["registration_open"] is True

    token = register(client)
    assert token
    session = client.get("/api/auth/session").get_json()["data"]
    assert session["authenticated"] is True
    assert session["user"]["email"] == "a@example.com"


def test_csrf_is_required_for_authenticated_mutations(app, client):
    enable_auth(app)
    token = register(client)

    missing = client.post("/api/matches", json=short_payload())
    assert missing.status_code == 403
    assert missing.get_json()["error"]["code"] == "csrf_failed"

    created = create_match(client, token)
    assert created["status"] == "draft"


def test_password_is_hashed_and_login_is_audited(app, client, session):
    enable_auth(app)
    register(client)
    user = session.scalar(select(User).where(User.email == "a@example.com"))
    assert user is not None
    assert user.password_hash
    assert "correct horse battery" not in user.password_hash
    assert user.password_hash.startswith(("scrypt:", "pbkdf2:"))

    client.post("/api/auth/logout")
    assert client.post(
        "/api/auth/login",
        json={"email": "a@example.com", "password": "wrong password"},
    ).status_code == 401
    actions = session.scalars(select(AuditLog.action)).all()
    assert "auth.register" in actions
    assert "auth.login_failed" in actions


def test_users_cannot_read_each_others_matches(app, client, session):
    enable_auth(app)
    token_a = register(client, "a@example.com", "Scorer A")
    match = create_match(client, token_a)
    owner_id = session.get(Match, match["id"]).owner_id
    assert owner_id is not None

    client.post("/api/auth/logout")
    register(client, "b@example.com", "Scorer B")
    assert client.get(f"/api/matches/{match['id']}").status_code == 403
    listed = client.get("/api/matches").get_json()["data"]
    assert all(item["id"] != match["id"] for item in listed)


def test_stats_are_scoped_to_the_signed_in_owner(app, client):
    enable_auth(app)
    token_a = register(client, "a@example.com", "Scorer A")
    create_match(client, token_a)
    client.post("/api/auth/logout", headers={"X-CSRF-Token": token_a})
    register(client, "b@example.com", "Scorer B")

    teams = client.get("/api/stats/teams").get_json()["data"]
    overview = client.get("/api/stats/overview").get_json()["data"]
    assert teams == []
    assert overview["totals"]["matches"] == 0
    assert overview["totals"]["teams"] == 0
    assert overview["totals"]["players"] == 0
    assert overview["teams"] == []


def test_logout_clears_the_session(app, client):
    enable_auth(app)
    token = register(client)
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": token}).status_code == 200
    assert client.get("/api/matches").status_code == 401


def test_owner_sees_own_match_after_switching_accounts(app, client):
    enable_auth(app)
    token_a = register(client, "a@example.com", "Scorer A")
    match = create_match(client, token_a)
    client.post("/api/auth/logout")
    login(client, "a@example.com")
    response = client.get(f"/api/matches/{match['id']}")
    assert response.status_code == 200
    assert response.get_json()["data"]["id"] == match["id"]


def test_auth_rate_limit_returns_retry_after(app, client):
    enable_auth(app, RATE_LIMIT_ENABLED=True, RATE_LIMIT_AUTH_REQUESTS=2)
    for _ in range(2):
        assert client.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": "bad"}
        ).status_code == 401
    response = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "bad"}
    )
    assert response.status_code == 429
    assert response.headers["Retry-After"]
    assert response.get_json()["error"]["code"] == "rate_limited"


def test_paginated_match_history_meta(app, client):
    for _ in range(3):
        create_match(client)
    first = client.get("/api/matches?page=1&per_page=2").get_json()
    assert len(first["data"]) == 2
    assert first["meta"] == {"page": 1, "per_page": 2, "total": 3, "has_more": True}

    second = client.get("/api/matches?page=2&per_page=2").get_json()
    assert len(second["data"]) == 1
    assert second["meta"]["has_more"] is False


def test_security_headers_and_pwa_assets(app, client):
    response = client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in response.headers
    assert response.headers["Cache-Control"] == "no-store"

    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert b"GullyScore" in manifest.data
    assert client.get("/sw.js").status_code == 200
    assert client.get("/icons/icon.svg").status_code == 200


def test_protected_pages_redirect_to_login_but_login_page_loads(app, client):
    enable_auth(app)
    response = client.get("/pages/matches.html")
    assert response.status_code == 302
    assert "login.html" in response.headers["Location"]
    assert client.get("/pages/login.html").status_code == 200
