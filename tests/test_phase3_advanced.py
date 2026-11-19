"""Phase 3: solo batting, retirements, advanced cards, statistics and fantasy."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from app.models import FantasyPoint, PlayerMatchStatistics
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


def pid(match: dict, key: str, index: int) -> int:
    return team_players(match, key)[index]["id"]


def retire(client, innings: int, **payload):
    return client.post(f"/api/innings/{innings}/retirements", json=payload)


def return_batter(client, innings: int, retirement_id: int):
    return client.post(f"/api/innings/{innings}/retirements/{retirement_id}/return")


def to_solo(client, match: dict) -> tuple[int, int]:
    """Dismiss four Turf batters so only the last batter (A5) remains."""
    first = innings_id(match)
    bowler = pid(match, "b", 0)
    score(client, first, bowler, is_wicket=True, wicket_type="bowled")  # A1
    score(client, first, bowler, is_wicket=True, wicket_type="bowled")  # A3
    score(client, first, bowler, is_wicket=True, wicket_type="bowled")  # A4
    score(
        client,
        first,
        bowler,
        is_wicket=True,
        wicket_type="run_out",
        dismissed_player="non_striker",
    )  # A2, leaving A5 alone
    return first, bowler


# --- solo batting --------------------------------------------------------


def test_solo_batting_keeps_the_last_batter_on_strike(client):
    match = create_and_start(client, turf_payload())
    first, bowler = to_solo(client, match)

    state = client.get(f"/api/innings/{first}").get_json()["data"]
    assert state["wickets"] == 4
    assert state["solo_mode"] is True
    assert state["striker_id"] == pid(match, "a", 4)
    assert state["non_striker_id"] is None
    assert state["is_complete"] is False

    after_single = score(client, first, bowler, runs_off_bat=1)
    assert after_single["striker_id"] == pid(match, "a", 4)
    assert after_single["runs"] == 1

    after_four = score(client, first, bowler, runs_off_bat=4)
    assert after_four["striker_id"] == pid(match, "a", 4)
    assert after_four["runs"] == 5

    finished = score(
        client, first, bowler, is_wicket=True, wicket_type="bowled"
    )
    assert finished["is_complete"] is True
    assert finished["wickets"] == 5

    detail = client.get(f"/api/matches/{match['id']}").get_json()["data"]
    assert detail["innings"][0]["status"] == "completed"
    assert detail["innings"][1]["status"] == "live"
    assert detail["innings"][1]["target"] == 6

    card = client.get(f"/api/matches/{match['id']}/scorecard").get_json()["data"]
    last = next(
        line
        for line in card["innings"][0]["batting"]
        if line["player_id"] == pid(match, "a", 4)
    )
    # The run-out ball, the single, the four and the wicket ball were all faced.
    assert (last["runs"], last["balls"], last["fours"]) == (5, 4, 1)
    assert last["strike_rate"] == 125.0
    assert last["is_out"] is True


def test_solo_completion_by_target_still_works(client):
    match = create_and_start(client, turf_payload())
    first, bowler = to_solo(client, match)
    for _ in range(5):
        score(client, first, bowler, runs_off_bat=6)
    # Even in solo mode the scheduled overs end the innings: four wickets plus
    # nine balls have been bowled, so 27 more complete the six overs.
    for _ in range(27):
        state = score(client, first, bowler, runs_off_bat=0)
    assert state["is_complete"] is True


# --- retirements ---------------------------------------------------------


def test_retired_hurt_adds_no_wicket_and_can_return(client):
    match = create_and_start(client, turf_payload())
    first = innings_id(match)
    striker = pid(match, "a", 0)
    replacement = pid(match, "a", 2)

    response = retire(
        client,
        first,
        player_id=striker,
        retirement_type="retired_hurt",
        reason="Cramp",
    )
    assert response.status_code == 201, response.get_json()
    data = response.get_json()["data"]
    assert data["state"]["wickets"] == 0
    assert data["state"]["striker_id"] == replacement
    assert data["state"]["striker_id"] != striker
    assert data["retirement"]["reason"] == "Cramp"
    assert data["retirement"]["retired_at"] is not None
    assert data["retirement"]["can_return"] is True

    history = client.get(f"/api/innings/{first}/retirements").get_json()["data"]
    assert [(row["player_id"], row["retirement_type"]) for row in history] == [
        (striker, "retired_hurt")
    ]

    score(client, first, pid(match, "b", 0), runs_off_bat=1)
    returned = return_batter(client, first, history[0]["id"])
    assert returned.status_code == 200, returned.get_json()
    assert returned.get_json()["data"]["retirement"]["returned_at"] is not None

    # The returning batter is next in, so a wicket brings them back.
    score(
        client, first, pid(match, "b", 0), is_wicket=True, wicket_type="bowled"
    )
    state = client.get(f"/api/innings/{first}").get_json()["data"]
    assert state["striker_id"] == striker

    score(client, first, pid(match, "b", 0), runs_off_bat=4)
    card = client.get(f"/api/matches/{match['id']}/scorecard").get_json()["data"]
    line = next(
        row for row in card["innings"][0]["batting"] if row["player_id"] == striker
    )
    assert (line["runs"], line["is_out"], line["returned_to_bat"]) == (4, False, True)
    assert line["retirement_type"] is None
    assert line["dismissal"] is None


def test_retired_out_counts_as_a_wicket_and_cannot_return(client):
    match = create_and_start(client, turf_payload())
    first = innings_id(match)
    striker = pid(match, "a", 0)

    response = retire(
        client, first, player_id=striker, retirement_type="retired_out", reason="Walked"
    )
    assert response.status_code == 201, response.get_json()
    data = response.get_json()["data"]
    assert data["state"]["wickets"] == 1
    assert data["retirement"]["can_return"] is False

    blocked = return_batter(client, first, data["retirement"]["id"])
    assert blocked.status_code == 409
    assert error_code(blocked) == "retired_out_cannot_return"

    card = client.get(f"/api/matches/{match['id']}/scorecard").get_json()["data"]
    first_card = card["innings"][0]
    assert first_card["wickets"] == 1
    assert first_card["bowling"] == []
    line = next(
        row for row in first_card["batting"] if row["player_id"] == striker
    )
    assert line["is_out"] is True
    assert line["dismissal"] == "Retired out"


def test_last_batter_non_dismissal_retirement_pauses_without_ending(client):
    match = create_and_start(client, turf_payload())
    first, _ = to_solo(client, match)
    last = pid(match, "a", 4)

    response = retire(
        client, first, player_id=last, retirement_type="retired_not_out", reason="Rest"
    )
    assert response.status_code == 201, response.get_json()
    data = response.get_json()["data"]
    assert data["state"]["wickets"] == 4
    assert data["state"]["striker_id"] is None
    assert data["state"]["is_complete"] is False
    assert data["state"]["can_score"] is False

    blocked = post_delivery(
        client, first, runs_off_bat=1, bowler_id=pid(match, "b", 0)
    )
    assert blocked.status_code == 409
    assert error_code(blocked) == "no_striker"

    returned = return_batter(client, first, data["retirement"]["id"])
    assert returned.status_code == 200, returned.get_json()
    state = returned.get_json()["data"]["state"]
    assert state["striker_id"] == last
    assert state["solo_mode"] is True
    assert state["can_score"] is True

    after_run = score(client, first, pid(match, "b", 0), runs_off_bat=2)
    assert after_run["runs"] == 2
    assert after_run["striker_id"] == last


def test_last_batter_retired_out_ends_the_innings(client):
    match = create_and_start(client, turf_payload())
    first, _ = to_solo(client, match)
    last = pid(match, "a", 4)

    response = retire(
        client, first, player_id=last, retirement_type="retired_out", reason="Retired"
    )
    assert response.status_code == 201, response.get_json()
    state = response.get_json()["data"]["state"]
    assert state["wickets"] == 5
    assert state["is_complete"] is True

    detail = client.get(f"/api/matches/{match['id']}").get_json()["data"]
    assert detail["innings"][0]["status"] == "completed"
    assert detail["innings"][1]["status"] == "live"


def test_retirement_notation_for_all_three_types(client):
    match = create_and_start(client, turf_payload())
    first = innings_id(match)

    retire(client, first, player_id=pid(match, "a", 0), retirement_type="retired_hurt")
    retire(
        client, first, player_id=pid(match, "a", 1), retirement_type="retired_not_out"
    )
    response = retire(
        client, first, player_id=pid(match, "a", 2), retirement_type="retired_out"
    )
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["data"]["state"]["wickets"] == 1

    card = client.get(f"/api/matches/{match['id']}/scorecard").get_json()["data"]
    lines = {line["player_id"]: line for line in card["innings"][0]["batting"]}
    assert lines[pid(match, "a", 0)]["dismissal"] == "Retired hurt"
    assert lines[pid(match, "a", 0)]["is_out"] is False
    assert lines[pid(match, "a", 1)]["dismissal"] == "Retired not out"
    assert lines[pid(match, "a", 2)]["dismissal"] == "Retired out"
    assert lines[pid(match, "a", 2)]["is_out"] is True
    assert len(card["innings"][0]["retirements"]) == 3
    assert len(card["innings"][0]["fall_of_wickets"]) == 1


def test_retirement_eligibility_is_validated(client):
    match = create_and_start(client, turf_payload())
    first = innings_id(match)

    not_at_crease = retire(
        client, first, player_id=pid(match, "a", 4), retirement_type="retired_hurt"
    )
    assert not_at_crease.status_code == 422
    assert error_code(not_at_crease) == "validation_error"

    same_player = retire(
        client,
        first,
        player_id=pid(match, "a", 0),
        retirement_type="retired_hurt",
        replacement_player_id=pid(match, "a", 0),
    )
    assert same_player.status_code == 422

    at_crease = retire(
        client,
        first,
        player_id=pid(match, "a", 0),
        retirement_type="retired_hurt",
        replacement_player_id=pid(match, "a", 1),
    )
    assert at_crease.status_code == 422

    disabled = create_and_start(
        client, turf_payload(rules={"retired_player_option": False})
    )
    response = retire(
        client,
        innings_id(disabled),
        player_id=pid(disabled, "a", 0),
        retirement_type="retired_hurt",
    )
    assert response.status_code == 409
    assert error_code(response) == "retirements_disabled"

    restricted = create_and_start(
        client, turf_payload(rules={"retirement_types": ["retired_hurt"]})
    )
    response = retire(
        client,
        innings_id(restricted),
        player_id=pid(restricted, "a", 0),
        retirement_type="retired_out",
    )
    assert response.status_code == 422
    assert "retired_out" not in response.get_json()["error"]["details"]["allowed"]


def test_retirement_and_return_are_audited(client):
    match = create_and_start(client, turf_payload())
    first = innings_id(match)
    created = retire(
        client,
        first,
        player_id=pid(match, "a", 0),
        retirement_type="retired_hurt",
        reason="Heat",
    ).get_json()["data"]
    return_batter(client, first, created["retirement"]["id"])

    events = client.get(f"/api/matches/{match['id']}/events").get_json()["data"]
    types = [event["event_type"] for event in events]
    assert "player.retired" in types
    assert "player.returned" in types

    history = client.get(f"/api/innings/{first}/retirements").get_json()["data"]
    assert history[0]["returned_at"] is not None
    assert history[0]["reason"] == "Heat"


# --- advanced scorecard --------------------------------------------------


def test_scorecard_has_fall_of_wickets_partnerships_and_commentary(client):
    match = create_and_start(client, turf_payload())
    first = innings_id(match)
    bowler = pid(match, "b", 0)
    score(client, first, bowler, runs_off_bat=4)
    score(client, first, bowler, runs_off_bat=1)
    score(client, first, bowler, is_wicket=True, wicket_type="bowled")

    card = client.get(f"/api/matches/{match['id']}/scorecard").get_json()["data"]
    innings = card["innings"][0]

    assert len(innings["commentary"]) == 3
    assert "4 runs" in innings["commentary"][0]["text"]
    assert "WICKET" in innings["commentary"][2]["text"]

    assert innings["fall_of_wickets"] == [
        {
            "wicket": 1,
            "runs": 5,
            "overs": "0.3",
            "batter_id": pid(match, "a", 1),
            "batter_name": "Bilal",
            "dismissal": "Bowled",
        }
    ]

    assert len(innings["partnerships"]) == 1
    assert innings["partnerships"][0]["runs"] == 5
    assert innings["partnerships"][0]["balls"] == 3
    assert innings["partnerships"][0]["wicket"] == 1
    assert innings["partnerships"][0]["unbeaten"] is False


# --- fantasy -------------------------------------------------------------


def fantasy_payload(client, match_id: int) -> dict:
    return client.get(f"/api/matches/{match_id}/fantasy").get_json()["data"]


def category_totals(payload: dict) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for row in payload["ledger"]:
        totals[row["category"]] += row["points"]
    return dict(totals)


def test_fantasy_run_boundary_and_milestone_awards_are_not_duplicated(client):
    match = create_and_start(client, turf_payload())
    first = innings_id(match)
    bowler = pid(match, "b", 0)
    # Five sixes, then a single on the last ball of the over to keep the same
    # batter on strike after the change of ends, then four more sixes.
    for _ in range(5):
        score(client, first, bowler, runs_off_bat=6)
    score(client, first, bowler, runs_off_bat=1)
    for _ in range(4):
        score(client, first, bowler, runs_off_bat=6)

    payload = fantasy_payload(client, match["id"])
    totals = category_totals(payload)
    assert totals["runs"] == 55
    assert totals["boundary_six"] == 54
    assert totals["milestone_25"] == 4
    assert totals["milestone_50"] == 8
    assert "milestone_100" not in totals

    keys = [row["source_key"] for row in payload["ledger"]]
    assert len(keys) == len(set(keys))

    striker_total = next(
        row["points"]
        for row in payload["totals"]
        if row["player_id"] == pid(match, "a", 0)
    )
    assert striker_total == 127  # includes the short-format strike-rate bonus

    players = client.get("/api/stats/players").get_json()["data"]
    striker = next(row for row in players if row["player_name"] == "Arun")
    assert striker["runs"] == 55
    assert striker["highest_score"] == 55
    assert striker["fantasy_points"] == 127

    undo_delivery(client, first)
    corrected = fantasy_payload(client, match["id"])
    corrected_totals = category_totals(corrected)
    assert corrected_totals["runs"] == 49
    assert "milestone_50" not in corrected_totals
    assert corrected_totals["milestone_25"] == 4


def test_fantasy_duck_and_bowling_awards(client, short_match):
    first = innings_id(short_match)
    bowler = pid(short_match, "b", 0)
    score(client, first, bowler, runs_off_bat=0)
    score(client, first, bowler, is_wicket=True, wicket_type="bowled")

    payload = fantasy_payload(client, short_match["id"])
    totals = category_totals(payload)
    assert totals["duck"] == -2
    assert totals["wicket"] == 25
    assert totals["bowled_lbw"] == 8

    striker_total = next(
        row["points"]
        for row in payload["totals"]
        if row["player_id"] == pid(short_match, "a", 0)
    )
    assert striker_total == -2
    bowler_total = next(
        row["points"]
        for row in payload["totals"]
        if row["player_id"] == bowler
    )
    assert bowler_total == 33


def test_fantasy_maiden_and_three_wicket_haul(client):
    match = create_and_start(client, turf_payload())
    first = innings_id(match)
    bowler = pid(match, "b", 0)

    for _ in range(6):
        score(client, first, bowler, runs_off_bat=0)
    for _ in range(3):
        score(client, first, bowler, is_wicket=True, wicket_type="bowled")

    payload = fantasy_payload(client, match["id"])
    totals = category_totals(payload)
    assert totals["maiden"] == 12
    assert totals["wicket"] == 75
    assert totals["bowled_lbw"] == 24
    assert totals["haul_3"] == 4
    assert totals["economy"] == 6

    bowlers = [row for row in payload["ledger"] if row["category"] == "maiden"]
    assert len(bowlers) == 1


def test_t20_and_short_formats_use_different_fantasy_configs(client):
    turf = create_and_start(client, turf_payload(fantasy_config="short"))
    t20_turf = create_and_start(client, turf_payload(fantasy_config="t20"))

    assert client.get(f"/api/matches/{turf['id']}").get_json()["data"]["fantasy_config"] == "short"
    assert client.get(f"/api/matches/{t20_turf['id']}").get_json()["data"]["fantasy_config"] == "t20"

    # 10 runs off 8 balls is a strike rate of 125.
    for match in (turf, t20_turf):
        first = innings_id(match)
        bowler = pid(match, "b", 0)
        # 10 runs off 8 balls: 4,0,0,0,0,1 then 4,1. The single on the sixth
        # ball swaps ends, so the over change keeps the same batter on strike.
        for _ in range(4):
            score(client, first, bowler, runs_off_bat=0)
        score(client, first, bowler, runs_off_bat=4)
        score(client, first, bowler, runs_off_bat=1)
        score(client, first, bowler, runs_off_bat=4)
        score(client, first, bowler, runs_off_bat=1)

    short_points = category_totals(fantasy_payload(client, turf["id"]))["strike_rate"]
    t20_points = category_totals(fantasy_payload(client, t20_turf["id"]))["strike_rate"]
    assert short_points == 2
    assert t20_points == -2

    full = create_match(
        client,
        {
            "preset": "full_t20",
            "team_a": {"name": "T20 A", "players": [f"A{i}" for i in range(11)]},
            "team_b": {"name": "T20 B", "players": [f"B{i}" for i in range(11)]},
        },
    )
    assert full["fantasy_config"] == "t20"

    invalid = client.post(
        "/api/matches", json=turf_payload(fantasy_config="mystery")
    )
    assert invalid.status_code == 422


# --- player and team statistics -----------------------------------------


def test_player_and_team_statistics_after_a_completed_match(client, session, short_match):
    first = innings_id(short_match, 1)
    second = innings_id(short_match, 2)
    score(client, first, pid(short_match, "b", 0), runs_off_bat=4)
    score(
        client,
        first,
        pid(short_match, "b", 0),
        is_wicket=True,
        wicket_type="bowled",
    )
    score(client, second, pid(short_match, "a", 0), runs_off_bat=0)
    score(
        client,
        second,
        pid(short_match, "a", 0),
        is_wicket=True,
        wicket_type="bowled",
    )

    players = client.get("/api/stats/players").get_json()["data"]
    batter = next(row for row in players if row["player_name"] == "A1")
    assert batter["runs"] == 4
    assert batter["highest_score"] == 4
    assert batter["batting_average"] == 4.0
    assert batter["strike_rate"] == 200.0
    assert batter["fours"] == 1
    assert batter["matches"] == 1

    bowler = next(row for row in players if row["player_name"] == "B1")
    assert bowler["wickets"] == 1
    assert bowler["best_bowling"] == "1/4"
    assert bowler["bowling_average"] == 4.0
    assert bowler["economy"] == 12.0

    teams = client.get("/api/stats/teams").get_json()["data"]
    alpha = next(row for row in teams if row["team_name"] == "Alpha")
    bravo = next(row for row in teams if row["team_name"] == "Bravo")
    assert (alpha["matches"], alpha["wins"], alpha["losses"]) == (1, 1, 0)
    assert (alpha["highest_score"], alpha["lowest_score"]) == (4, 4)
    assert alpha["win_percentage"] == 100.0
    assert (bravo["wins"], bravo["losses"]) == (0, 1)

    overview = client.get("/api/stats/overview").get_json()["data"]
    assert overview["top_fantasy_scorers"]
    assert overview["teams"]

    rows = (
        session.execute(
            select(PlayerMatchStatistics).where(
                PlayerMatchStatistics.match_id == short_match["id"]
            )
        )
        .scalars()
        .all()
    )
    assert all(row.fantasy_points == 0 or isinstance(row.fantasy_points, int) for row in rows)
    ledger = session.execute(
        select(FantasyPoint).where(FantasyPoint.match_id == short_match["id"])
    ).scalars().all()
    assert ledger
