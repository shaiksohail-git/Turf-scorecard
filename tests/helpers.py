"""Shared helpers for the API-level tests."""

from __future__ import annotations

TURF_TEAM_A = ("Arun", "Bilal", "Chetan", "Danish", "Eshan")
TURF_TEAM_B = ("Farid", "Gopal", "Harish", "Imran", "Jatin")


def turf_payload(**overrides) -> dict:
    payload = {
        "preset": "custom_turf",
        "venue": "Test turf",
        "team_a": {"name": "Green Caps", "players": list(TURF_TEAM_A)},
        "team_b": {"name": "Night Riders", "players": list(TURF_TEAM_B)},
        "toss": {"winner": "a", "decision": "bat"},
    }
    payload.update(overrides)
    return payload


def short_payload(**overrides) -> dict:
    """A one over, two-a-side match for lifecycle tests."""
    payload = {
        "preset": "custom_match",
        "rules": {"overs": 1, "players_per_team": 2},
        "team_a": {"name": "Alpha", "players": ["A1", "A2"]},
        "team_b": {"name": "Bravo", "players": ["B1", "B2"]},
        "toss": {"winner": "a", "decision": "bat"},
    }
    payload.update(overrides)
    return payload


def create_match(client, payload: dict) -> dict:
    response = client.post("/api/matches", json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]


def start_match(client, match_id: int) -> dict:
    response = client.post(f"/api/matches/{match_id}/start")
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]


def create_and_start(client, payload: dict) -> dict:
    match = create_match(client, payload)
    return start_match(client, match["id"])


def team_players(match: dict, key: str = "a") -> list[dict]:
    return match[f"team_{key}"]["players"]


def innings_id(match: dict, number: int = 1) -> int:
    for innings in match["innings"]:
        if innings["number"] == number:
            return innings["innings_id"]
    raise AssertionError(f"innings {number} is missing from the match payload")


def post_delivery(client, innings: int, **payload):
    return client.post(f"/api/innings/{innings}/deliveries", json=payload)


def undo_delivery(client, innings: int, reason: str | None = None):
    body = {} if reason is None else {"reason": reason}
    return client.post(f"/api/innings/{innings}/deliveries/undo", json=body)


def error_code(response) -> str:
    return response.get_json()["error"]["code"]
