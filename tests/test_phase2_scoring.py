"""Phase 2 scoring guarantees.

Covers the requirements the scoring core must keep: one transaction per ball,
validation of every delivery, integer legal-ball counts, exactly-once recording,
all three presets, the two-innings workflow, match results and safe corrections.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import Delivery, Innings, Match, Team
from helpers import (
    create_and_start,
    create_match,
    error_code,
    innings_id,
    post_delivery,
    short_payload,
    team_players,
    turf_payload,
    undo_delivery,
)


def score(client, innings: int, bowler_id: int, **payload):
    response = post_delivery(client, innings, bowler_id=bowler_id, **payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["state"]


def player_id(match: dict, key: str, index: int) -> int:
    return team_players(match, key)[index]["id"]


# --- integer legal-ball counting -----------------------------------------


def test_legal_balls_are_an_integer_and_exclude_illegal_deliveries(client, turf_match):
    innings = innings_id(turf_match)
    bowler = player_id(turf_match, "b", 0)

    assert score(client, innings, bowler, extra_type="wide")["legal_balls"] == 0
    assert score(client, innings, bowler, extra_type="no_ball")["legal_balls"] == 0
    assert score(client, innings, bowler, extra_type="bye", extra_runs=1)["legal_balls"] == 1
    state = score(client, innings, bowler, runs_off_bat=1)

    assert state["legal_balls"] == 2
    assert isinstance(state["legal_balls"], int)
    assert state["overs"] == "0.2"


def test_seven_legal_balls_render_as_one_point_one_overs(client, turf_match):
    innings = innings_id(turf_match)
    bowler = player_id(turf_match, "b", 0)

    for _ in range(7):
        state = score(client, innings, bowler, runs_off_bat=1)

    assert state["legal_balls"] == 7
    assert state["overs"] == "1.1"
    assert state["balls_remaining"] == 29


# --- exactly once --------------------------------------------------------


def test_retry_with_the_same_event_id_returns_the_original_delivery(client, turf_match):
    innings = innings_id(turf_match)
    bowler = player_id(turf_match, "b", 0)

    first = post_delivery(
        client, innings, runs_off_bat=2, bowler_id=bowler, client_event_id="evt-retry"
    )
    retry = post_delivery(
        client, innings, runs_off_bat=2, bowler_id=bowler, client_event_id="evt-retry"
    )

    assert retry.status_code == 200
    body = retry.get_json()["data"]
    assert body["duplicate"] is True
    assert body["delivery"]["id"] == first.get_json()["data"]["delivery"]["id"]
    assert body["state"]["revision"] == first.get_json()["data"]["state"]["revision"]

    stored = client.get(f"/api/innings/{innings}/deliveries").get_json()["data"]
    assert len(stored) == 1
    assert stored[0]["total_runs"] == 2


def test_database_constraints_reject_a_duplicate_event_and_sequence(client, session, turf_match):
    innings = innings_id(turf_match)
    bowler = player_id(turf_match, "b", 0)
    striker = player_id(turf_match, "a", 0)
    score(client, innings, bowler, runs_off_bat=1, client_event_id="evt-db")

    session.expire_all()
    row = session.execute(select(Delivery)).scalar_one()

    session.add(
        Delivery(
            innings_id=innings,
            sequence=row.sequence + 1,
            client_event_id="evt-db",
            over_number=1,
            ball_in_over=2,
            striker_id=striker,
            bowler_id=bowler,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()

    session.expire_all()
    row = session.execute(select(Delivery)).scalar_one()
    session.add(
        Delivery(
            innings_id=innings,
            sequence=row.sequence,
            client_event_id=None,
            over_number=1,
            ball_in_over=2,
            striker_id=striker,
            bowler_id=bowler,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


# --- atomic writes -------------------------------------------------------


def test_rejected_delivery_writes_nothing(client, session, turf_match):
    innings = innings_id(turf_match)
    bowler = player_id(turf_match, "b", 0)
    before = session.get(Innings, innings).revision

    response = post_delivery(client, innings, runs_off_bat=9, bowler_id=bowler)
    assert response.status_code == 422
    assert error_code(response) == "runs_not_allowed"

    session.expire_all()
    assert session.get(Innings, innings).revision == before
    assert session.execute(select(func.count(Delivery.id))).scalar() == 0


def test_invalid_match_creation_leaves_no_partial_rows(client, session):
    payload = turf_payload()
    payload["team_b"]["players"] = ["Only One"]

    response = client.post("/api/matches", json=payload)
    assert response.status_code == 422

    assert session.execute(select(func.count(Match.id))).scalar() == 0
    assert session.execute(select(func.count(Team.id))).scalar() == 0


# --- per-delivery validation --------------------------------------------


def test_conflicting_run_aliases_are_rejected(client, turf_match):
    response = post_delivery(
        client,
        innings_id(turf_match),
        runs=1,
        runs_off_bat=2,
        bowler_id=player_id(turf_match, "b", 0),
    )
    assert response.status_code == 422
    assert error_code(response) == "conflicting_fields"


def test_conflicting_extra_aliases_are_rejected(client, turf_match):
    response = post_delivery(
        client,
        innings_id(turf_match),
        extra="wide",
        extra_type="no_ball",
        bowler_id=player_id(turf_match, "b", 0),
    )
    assert response.status_code == 422
    assert error_code(response) == "conflicting_fields"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"runs_off_bat": -1}, "invalid_runs"),
        ({"runs_off_bat": 7}, "runs_not_allowed"),
        ({"extra_runs": 1}, "invalid_extra_runs"),
        ({"is_wicket": True}, "invalid_wicket_type"),
        ({"wicket_type": "bowled"}, "wicket_type_without_wicket"),
        ({"is_wicket": True, "wicket_type": "caught", "runs_off_bat": 1}, "wicket_runs_conflict"),
        ({"extra_type": "wide", "runs_off_bat": 2}, "invalid_runs"),
        ({"extra_type": "leg_bye", "extra_runs": 0}, "invalid_extra_runs"),
        ({"shot": "cover drive"}, "unknown_fields"),
    ],
)
def test_every_malformed_delivery_is_rejected(client, turf_match, payload, code):
    response = post_delivery(
        client,
        innings_id(turf_match),
        bowler_id=player_id(turf_match, "b", 0),
        **payload,
    )
    assert response.status_code == 422
    assert error_code(response) == code


# --- presets -------------------------------------------------------------


@pytest.mark.parametrize(
    ("preset", "overs", "players", "solo"),
    [
        ("full_t20", 20, 11, False),
        ("custom_match", 20, 11, False),
        ("custom_turf", 6, 5, True),
    ],
)
def test_all_three_presets_create_and_start(client, preset, overs, players, solo):
    payload = {
        "preset": preset,
        "team_a": {"name": f"{preset} A", "players": [f"A{i}" for i in range(players)]},
        "team_b": {"name": f"{preset} B", "players": [f"B{i}" for i in range(players)]},
        "toss": {"winner": "a", "decision": "bat"},
    }

    match = create_and_start(client, payload)

    assert match["status"] == "live"
    assert match["rules"]["overs"] == overs
    assert match["rules"]["players_per_team"] == players
    assert match["rules"]["solo_batting_enabled"] is solo
    assert match["innings"][0]["status"] == "live"
    assert match["innings"][1]["status"] == "pending"
    assert match["innings"][0]["target"] is None


# --- two innings and results --------------------------------------------


def test_first_innings_completion_opens_the_chase(client, short_match):
    first = innings_id(short_match, 1)
    second = innings_id(short_match, 2)
    bowler = player_id(short_match, "b", 0)

    score(client, first, bowler, runs_off_bat=2)
    score(client, first, bowler, is_wicket=True, wicket_type="bowled")

    match = client.get(f"/api/matches/{short_match['id']}").get_json()["data"]
    assert match["innings"][0]["status"] == "completed"
    assert match["innings"][0]["runs"] == 2
    assert match["innings"][1]["status"] == "live"
    assert match["innings"][1]["target"] == 3

    chase_state = client.get(f"/api/innings/{second}").get_json()["data"]
    assert chase_state["runs_needed"] == 3
    assert chase_state["target"] == 3


def test_match_can_end_as_a_tie(client, short_match):
    first = innings_id(short_match, 1)
    second = innings_id(short_match, 2)

    score(client, first, player_id(short_match, "b", 0), runs_off_bat=1)
    score(
        client,
        first,
        player_id(short_match, "b", 0),
        is_wicket=True,
        wicket_type="bowled",
    )
    score(client, second, player_id(short_match, "a", 0), runs_off_bat=1)
    score(
        client,
        second,
        player_id(short_match, "a", 0),
        is_wicket=True,
        wicket_type="bowled",
    )

    match = client.get(f"/api/matches/{short_match['id']}").get_json()["data"]
    assert match["status"] == "completed"
    assert match["result"]["outcome"] == "tie"
    assert match["result"]["winner_team_id"] is None
    assert match["result"]["margin"] == 0
    assert match["result"]["summary"] == "Match tied"


def test_team_defending_a_total_wins_by_runs(client, short_match):
    first = innings_id(short_match, 1)
    second = innings_id(short_match, 2)

    score(client, first, player_id(short_match, "b", 0), runs_off_bat=4)
    score(
        client,
        first,
        player_id(short_match, "b", 0),
        is_wicket=True,
        wicket_type="bowled",
    )
    score(client, second, player_id(short_match, "a", 0), runs_off_bat=0)
    score(
        client,
        second,
        player_id(short_match, "a", 0),
        is_wicket=True,
        wicket_type="bowled",
    )

    match = client.get(f"/api/matches/{short_match['id']}").get_json()["data"]
    assert match["result"]["outcome"] == "runs"
    assert match["result"]["winner_team_id"] == match["team_a"]["id"]
    assert match["result"]["margin"] == 4
    assert "won by 4 run" in match["result"]["summary"]


# --- corrections ---------------------------------------------------------


def test_undo_reopens_a_completed_chase_and_can_be_rescored(client, short_match):
    first = innings_id(short_match, 1)
    second = innings_id(short_match, 2)

    for _ in range(6):
        score(client, first, player_id(short_match, "b", 0), runs_off_bat=0)
    score(client, second, player_id(short_match, "a", 0), runs_off_bat=1)

    finished = client.get(f"/api/matches/{short_match['id']}").get_json()["data"]
    assert finished["status"] == "completed"

    response = undo_delivery(client, second, reason="wrong batter")
    assert response.status_code == 200

    reopened = client.get(f"/api/matches/{short_match['id']}").get_json()["data"]
    assert reopened["status"] == "live"
    assert reopened["result"] is None
    assert reopened["innings"][1]["status"] == "live"
    assert reopened["innings"][1]["runs"] == 0
    assert reopened["innings"][1]["target"] == 1

    score(client, second, player_id(short_match, "a", 0), runs_off_bat=1)
    corrected = client.get(f"/api/matches/{short_match['id']}").get_json()["data"]
    assert corrected["status"] == "completed"
    assert corrected["result"]["outcome"] == "wickets"

    events = client.get(f"/api/matches/{short_match['id']}/events").get_json()["data"]
    assert any(event["event_type"] == "delivery.voided" for event in events)


def test_first_innings_cannot_be_undone_after_the_chase_starts(client, short_match):
    first = innings_id(short_match, 1)
    second = innings_id(short_match, 2)
    bowler = player_id(short_match, "b", 0)

    for _ in range(6):
        score(client, first, bowler, runs_off_bat=0)
    score(client, second, player_id(short_match, "a", 0), runs_off_bat=0)

    response = undo_delivery(client, first)
    assert response.status_code == 409
    assert error_code(response) == "later_innings_started"


# --- complete scorecard --------------------------------------------------


def test_scorecard_accounts_for_extras_and_bowler_credits(client, session, turf_match):
    innings = innings_id(turf_match)
    bowler = player_id(turf_match, "b", 0)

    score(client, innings, bowler, extra_type="no_ball", runs_off_bat=4)
    score(client, innings, bowler, extra_type="wide", extra_runs=1)
    score(client, innings, bowler, extra_type="bye", extra_runs=2)
    score(client, innings, bowler, extra_type="leg_bye", extra_runs=1)
    score(client, innings, bowler, runs_off_bat=4)
    score(client, innings, bowler, runs_off_bat=6)
    score(
        client,
        innings,
        bowler,
        is_wicket=True,
        wicket_type="run_out",
        dismissed_player="non_striker",
    )

    card = client.get(f"/api/matches/{turf_match['id']}/scorecard").get_json()["data"]
    first = card["innings"][0]

    assert first["total_runs"] == 20
    assert first["batting_runs"] == 14
    assert first["extras"] == {"wide": 2, "no_ball": 1, "bye": 2, "leg_bye": 1, "total": 6}
    assert first["wickets"] == 1

    assert sum(line["runs"] for line in first["batting"]) == 14
    assert sum(line["fours"] for line in first["batting"]) == 2
    assert sum(line["sixes"] for line in first["batting"]) == 1

    figures = first["bowling"][0]
    assert figures["runs"] == 17  # byes and leg byes are not charged to the bowler
    assert figures["wickets"] == 0  # a run out is not a bowler wicket
    assert figures["legal_balls"] == 5
    assert figures["overs"] == "0.5"
    assert figures["economy"] == 20.4

    session.expire_all()
    stored = session.get(Innings, innings)
    assert stored.legal_balls == 5
    assert isinstance(stored.legal_balls, int)
    assert stored.total_runs == 20
