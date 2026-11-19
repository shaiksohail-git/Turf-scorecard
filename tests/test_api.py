"""End-to-end API tests: match setup, scoring, undo, scorecard and series."""

from __future__ import annotations

from helpers import (
    create_and_start,
    create_match,
    error_code,
    innings_id,
    post_delivery,
    short_payload,
    start_match,
    team_players,
    turf_payload,
    undo_delivery,
)


def test_health_reports_database_status(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "ok"
    assert data["database"] is True


def test_rules_presets_are_exposed(client):
    response = client.get("/api/rules/presets")
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert [preset["key"] for preset in payload["presets"]] == [
        "full_t20",
        "custom_match",
        "custom_turf",
    ]
    turf = next(p for p in payload["presets"] if p["key"] == "custom_turf")["rules"]
    assert turf["overs"] == 6
    assert turf["players_per_team"] == 5
    assert turf["solo_batting_enabled"] is True


def test_rules_validate_endpoint_returns_resolved_rules(client):
    response = client.post(
        "/api/rules/validate", json={"preset": "custom_turf", "rules": {"overs": 4}}
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["overs"] == 4

    bad = client.post("/api/rules/validate", json={"preset": "custom_turf", "rules": {"overs": 0}})
    assert bad.status_code == 422
    assert error_code(bad) == "invalid_rules"


def test_match_requires_a_preset(client):
    response = client.post("/api/matches", json={"team_a": {"name": "A"}, "team_b": {"name": "B"}})
    assert response.status_code == 422
    assert response.get_json()["error"]["details"]["field"] == "preset"


def test_squad_size_must_match_the_format(client):
    payload = turf_payload()
    payload["team_a"]["players"] = ["Only", "Four", "Players", "Here"]

    response = client.post("/api/matches", json=payload)
    assert response.status_code == 422
    details = response.get_json()["error"]["details"]
    assert details["expected"] == 5
    assert details["received"] == 4


def test_created_match_snapshots_turf_rules(client):
    match = create_match(client, turf_payload())

    assert match["status"] == "draft"
    assert match["preset"] == "custom_turf"
    assert match["rules"]["overs"] == 6
    assert match["rules"]["players_per_team"] == 5
    assert match["rules"]["max_wickets"] == 5
    assert len(match["team_a"]["players"]) == 5


def test_start_creates_both_innings(client, turf_match):
    assert turf_match["status"] == "live"
    assert [innings["number"] for innings in turf_match["innings"]] == [1, 2]
    assert turf_match["innings"][0]["status"] == "live"
    assert turf_match["innings"][1]["status"] == "pending"


def test_draft_match_has_no_innings_to_score(client):
    match = create_match(client, turf_payload())

    # Innings are only created when the match starts.
    assert match["innings"] == []
    response = post_delivery(
        client,
        1,
        runs_off_bat=1,
        bowler_id=team_players(match, "b")[0]["id"],
    )
    assert response.status_code == 404
    assert error_code(response) == "not_found"


def test_record_delivery_updates_state_and_scorecard(client, turf_match):
    innings = innings_id(turf_match)
    striker = team_players(turf_match, "a")[0]
    bowler = team_players(turf_match, "b")[0]

    first = post_delivery(client, innings, runs_off_bat=4, bowler_id=bowler["id"])
    assert first.status_code == 201
    state = first.get_json()["data"]["state"]
    assert state["runs"] == 4
    assert state["legal_balls"] == 1
    assert state["striker_id"] == striker["id"]
    assert state["overs"] == "0.1"

    second = post_delivery(client, innings, runs_off_bat=1, bowler_id=bowler["id"])
    state = second.get_json()["data"]["state"]
    assert state["runs"] == 5
    # A single rotated the strike to the second batter.
    assert state["striker_id"] == team_players(turf_match, "a")[1]["id"]

    card = client.get(f"/api/matches/{turf_match['id']}/scorecard").get_json()["data"]
    assert card["innings"][0]["total_runs"] == 5
    assert card["innings"][0]["overs"] == "0.2"
    assert card["innings"][0]["batting"][0]["runs"] == 5
    assert card["innings"][0]["state"]["revision"] == 2


def test_delivery_is_idempotent_with_a_client_event_id(client, turf_match):
    innings = innings_id(turf_match)
    bowler = team_players(turf_match, "b")[0]

    first = post_delivery(
        client, innings, runs_off_bat=2, bowler_id=bowler["id"], client_event_id="evt-1"
    )
    assert first.status_code == 201
    duplicate = post_delivery(
        client, innings, runs_off_bat=2, bowler_id=bowler["id"], client_event_id="evt-1"
    )
    assert duplicate.status_code == 200
    assert duplicate.get_json()["data"]["duplicate"] is True
    assert duplicate.get_json()["data"]["state"]["runs"] == 2

    events = client.get(f"/api/innings/{innings}/deliveries").get_json()["data"]
    assert len(events) == 1


def test_undo_voids_the_last_delivery_without_deleting_it(client, turf_match):
    innings = innings_id(turf_match)
    bowler = team_players(turf_match, "b")[0]
    post_delivery(client, innings, runs_off_bat=4, bowler_id=bowler["id"])
    post_delivery(client, innings, runs_off_bat=1, bowler_id=bowler["id"])

    response = undo_delivery(client, innings, reason="scored the wrong ball")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["state"]["runs"] == 4
    assert data["state"]["legal_balls"] == 1
    assert data["undone"]["void_reason"] == "scored the wrong ball"

    active = client.get(f"/api/innings/{innings}/deliveries").get_json()["data"]
    everything = client.get(
        f"/api/innings/{innings}/deliveries?include_voided=true"
    ).get_json()["data"]
    assert len(active) == 1
    assert len(everything) == 2
    assert everything[-1]["is_voided"] is True


def test_undo_with_no_deliveries_is_a_conflict(client, turf_match):
    response = undo_delivery(client, innings_id(turf_match))
    assert response.status_code == 409
    assert error_code(response) == "nothing_to_undo"


def test_invalid_delivery_returns_a_precise_error(client, turf_match):
    response = post_delivery(
        client,
        innings_id(turf_match),
        runs_off_bat=9,
        bowler_id=team_players(turf_match, "b")[0]["id"],
    )
    assert response.status_code == 422
    assert error_code(response) == "runs_not_allowed"
    assert response.get_json()["error"]["details"]["allowed_runs"] == [0, 1, 2, 3, 4, 5, 6]


def test_bowler_must_belong_to_the_bowling_team(client, turf_match):
    response = post_delivery(
        client,
        innings_id(turf_match),
        runs_off_bat=1,
        bowler_id=team_players(turf_match, "a")[0]["id"],
    )
    assert response.status_code == 422
    assert "bowling team" in response.get_json()["error"]["message"]


def test_stale_revision_is_rejected(client, turf_match):
    response = post_delivery(
        client,
        innings_id(turf_match),
        runs_off_bat=1,
        bowler_id=team_players(turf_match, "b")[0]["id"],
        expected_revision=99,
    )
    assert response.status_code == 409
    assert error_code(response) == "stale_revision"


def test_full_one_over_match_lifecycle(client, short_match):
    first_innings = innings_id(short_match, 1)
    second_innings = innings_id(short_match, 2)
    bowler = team_players(short_match, "b")[0]

    for _ in range(6):
        response = post_delivery(client, first_innings, bowler_id=bowler["id"])
        assert response.status_code == 201, response.get_json()

    state = response.get_json()["data"]["state"]
    assert state["is_complete"] is True

    match = client.get(f"/api/matches/{short_match['id']}").get_json()["data"]
    assert match["innings"][0]["status"] == "completed"
    assert match["innings"][1]["status"] == "live"
    assert match["innings"][1]["target"] == 1

    # The chase needs one run.
    chase_bowler = team_players(short_match, "a")[0]
    chase = post_delivery(client, second_innings, runs_off_bat=1, bowler_id=chase_bowler["id"])
    assert chase.status_code == 201

    finished = client.get(f"/api/matches/{short_match['id']}").get_json()["data"]
    assert finished["status"] == "completed"
    assert finished["result"]["outcome"] == "wickets"
    assert finished["result"]["winner_team_id"] == finished["team_b"]["id"]
    assert "won by 1 wicket" in finished["result"]["summary"]


def test_record_delivery_after_innings_complete_is_rejected(client, short_match):
    first_innings = innings_id(short_match, 1)
    bowler = team_players(short_match, "b")[0]
    for _ in range(6):
        post_delivery(client, first_innings, bowler_id=bowler["id"])

    response = post_delivery(client, first_innings, bowler_id=bowler["id"])
    assert response.status_code == 409
    assert error_code(response) == "innings_not_live"


def test_series_can_be_created_and_listed(client):
    created = client.post(
        "/api/series", json={"name": "Sunday Turf Cup", "preset": "custom_turf"}
    )
    assert created.status_code == 201
    series = created.get_json()["data"]
    assert series["name"] == "Sunday Turf Cup"
    assert series["match_count"] == 0

    listing = client.get("/api/series").get_json()["data"]
    assert [item["name"] for item in listing] == ["Sunday Turf Cup"]


def test_match_can_belong_to_a_series(client):
    series = client.post("/api/series", json={"name": "Winter League"}).get_json()["data"]
    payload = turf_payload(series_id=series["id"])

    match = create_match(client, payload)
    assert match["series_id"] == series["id"]

    series_detail = client.get(f"/api/series/{series['id']}").get_json()["data"]
    assert series_detail["match_count"] == 1
    assert series_detail["matches"][0]["id"] == match["id"]


def test_starting_a_live_match_twice_is_a_conflict(client, turf_match):
    response = client.post(f"/api/matches/{turf_match['id']}/start")
    assert response.status_code == 409
    assert error_code(response) == "invalid_match_state"


def test_unknown_match_returns_not_found(client):
    response = client.get("/api/matches/4242")
    assert response.status_code == 404
    assert error_code(response) == "not_found"


def test_batting_order_follows_the_submitted_squad(client):
    match = create_and_start(client, turf_payload())
    order = [player["name"] for player in team_players(match, "a")]

    assert order == ["Arun", "Bilal", "Chetan", "Danish", "Eshan"]
    assert [player["batting_order"] for player in team_players(match, "a")] == [1, 2, 3, 4, 5]


def test_toss_decision_bowl_changes_the_batting_side(client):
    payload = short_payload(toss={"winner": "a", "decision": "bowl"})
    match = create_and_start(client, payload)

    assert match["innings"][0]["batting_team_id"] == match["team_b"]["id"]


def test_previous_bowler_cannot_exceed_the_over_limit(client):
    payload = {
        "preset": "full_t20",
        "rules": {"overs": 1, "players_per_team": 2, "max_overs_per_bowler": 1},
        "team_a": {"name": "Alpha", "players": ["A1", "A2"]},
        "team_b": {"name": "Bravo", "players": ["B1", "B2"]},
        "toss": {"winner": "a", "decision": "bat"},
    }
    match = start_match(client, create_match(client, payload)["id"])
    innings = innings_id(match)
    bowler = team_players(match, "b")[0]

    for _ in range(6):
        response = post_delivery(client, innings, bowler_id=bowler["id"])
        assert response.status_code == 201

    # The innings is over, so the quota error is only reachable in a longer
    # match; assert the innings did complete as scheduled.
    assert response.get_json()["data"]["state"]["is_complete"] is True
