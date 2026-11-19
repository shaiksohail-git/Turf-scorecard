"""Phase 4: series editing, dashboards, leaderboards, fantasy and awards."""

from __future__ import annotations

from app.services.series_stats import _award

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


def create_series(client, **overrides):
    payload = {
        "name": "Phase 4 League",
        "preset": "custom_match",
        "planned_matches": 3,
        "team_a": {"name": "Alpha", "players": ["A1", "A2"]},
        "team_b": {"name": "Bravo", "players": ["B1", "B2"]},
    }
    payload.update(overrides)
    response = client.post("/api/series", json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]


def series_detail(client, series_id: int) -> dict:
    response = client.get(f"/api/series/{series_id}")
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]


def complete_short_match(client, series_id: int, *, first_runs: int = 0) -> dict:
    """Complete a one-over Alpha/Bravo match with a controlled first innings."""
    match = create_and_start(client, short_payload(series_id=series_id))
    first = innings_id(match, 1)
    second = innings_id(match, 2)
    first_bowler = team_players(match, "b")[0]["id"]
    if first_runs == 6:
        score(client, first, first_bowler, runs_off_bat=6)
        for _ in range(5):
            score(client, first, first_bowler)
        # Bravo needs seven; six dots leave Alpha the winner.
        chase_bowler = team_players(match, "a")[0]["id"]
        for _ in range(6):
            score(client, second, chase_bowler)
    else:
        for _ in range(6):
            score(client, first, first_bowler)
        chase_bowler = team_players(match, "a")[0]["id"]
        score(client, second, chase_bowler, runs_off_bat=1)
    return match


def play_batting_match(client, series_id: int, score_to: int) -> dict:
    """Play a four-over, two-a-side match with A1 scoring a set total."""
    match = create_and_start(
        client,
        {
            "preset": "custom_match",
            "rules": {"overs": 4, "players_per_team": 2},
            "series_id": series_id,
            "team_a": {"name": "Alpha", "players": ["A1", "A2"]},
            "team_b": {"name": "Bravo", "players": ["B1", "B2"]},
            "toss": {"winner": "a", "decision": "bat"},
        },
    )
    first = innings_id(match, 1)
    second = innings_id(match, 2)
    bowler = team_players(match, "b")[0]["id"]

    if score_to == 100:
        # 31 runs each over while retaining strike, then a single and run out.
        for _ in range(3):
            for _ in range(5):
                score(client, first, bowler, runs_off_bat=6)
            score(client, first, bowler, runs_off_bat=1)
        score(client, first, bowler, runs_off_bat=6)
        score(client, first, bowler, runs_off_bat=1)
        score(
            client,
            first,
            bowler,
            is_wicket=True,
            wicket_type="run_out",
            dismissed_player="non_striker",
        )
    else:
        # 30 from sixes, a single at the over change, four fours and three,
        # then the striker is bowled for exactly 50.
        for _ in range(5):
            score(client, first, bowler, runs_off_bat=6)
        score(client, first, bowler, runs_off_bat=1)
        for _ in range(4):
            score(client, first, bowler, runs_off_bat=4)
        score(client, first, bowler, runs_off_bat=3)
        # The single/three sequence leaves A1 at the non-striker end.
        score(
            client,
            first,
            bowler,
            is_wicket=True,
            wicket_type="run_out",
            dismissed_player="non_striker",
        )

    # A single wicket ends the two-a-side chase under these rules.
    chase_bowler = team_players(match, "a")[0]["id"]
    score(client, second, chase_bowler, is_wicket=True, wicket_type="bowled")
    return match


# --- creation / editing --------------------------------------------------


def test_series_creation_captures_roster_and_planned_length(client):
    series = create_series(
        client,
        name="Sunday Turf Cup",
        preset="custom_turf",
        format="custom_turf",
        planned_matches=6,
        team_a={"name": "Green Caps", "players": ["Arun", "Bilal"]},
        team_b={"name": "Night Riders", "players": ["Farid", "Gopal"]},
        notes="Home and away",
    )

    assert series["name"] == "Sunday Turf Cup"
    assert series["preset"] == "custom_turf"
    assert series["format"] == "custom_turf"
    assert series["planned_matches"] == 6
    assert series["matches_played"] == 0
    assert series["matches_remaining"] == 6
    assert series["team_a"] == {"name": "Green Caps", "players": ["Arun", "Bilal"]}
    assert series["team_b"] == {"name": "Night Riders", "players": ["Farid", "Gopal"]}
    assert len(series["teams"]) == 2


def test_series_edit_never_deletes_matches_or_rewrites_rules_snapshot(client):
    series = create_series(client, planned_matches=5)
    completed = complete_short_match(client, series["id"])
    draft = create_match(client, turf_payload(series_id=series["id"]))
    assert draft["rules"]["overs"] == 6

    response = client.patch(
        f"/api/series/{series['id']}",
        json={
            "name": "Renamed Series",
            "planned_matches": 1,
            "notes": "Shortened after the first result",
            "team_a": {"name": "Alpha", "players": ["A1", "A2"]},
            "team_b": {"name": "Bravo", "players": ["B1", "B2"]},
        },
    )
    assert response.status_code == 200, response.get_json()
    edited = response.get_json()["data"]
    assert edited["name"] == "Renamed Series"
    assert edited["planned_matches"] == 1
    assert edited["matches_played"] == 1
    assert edited["matches_remaining"] == 0
    assert edited["match_count"] == 2
    assert {match["id"] for match in edited["matches"]} == {completed["id"], draft["id"]}

    unchanged = client.get(f"/api/matches/{draft['id']}").get_json()["data"]
    assert unchanged["rules"]["overs"] == 6
    assert unchanged["preset"] == "custom_turf"

    too_short = client.patch(
        f"/api/series/{series['id']}", json={"planned_matches": 0}
    )
    assert too_short.status_code == 422
    assert too_short.get_json()["error"]["details"]["minimum"] == 1
    assert series_detail(client, series["id"])["match_count"] == 2


def test_series_plan_can_increase_again_without_touching_results(client):
    series = create_series(client, planned_matches=1)
    match = complete_short_match(client, series["id"])
    response = client.patch(
        f"/api/series/{series['id']}", json={"planned_matches": 4}
    )
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["matches_remaining"] == 3
    assert data["matches_played"] == 1
    assert data["matches"][0]["id"] == match["id"]
    completed = client.get(f"/api/matches/{match['id']}").get_json()["data"]
    assert data["matches"][0]["result"] == completed["result"]


# --- dashboard -----------------------------------------------------------


def test_series_dashboard_standings_recent_results_and_no_double_counting(client):
    series = create_series(client, planned_matches=4)
    first = complete_short_match(client, series["id"], first_runs=0)  # Bravo wins
    second = complete_short_match(client, series["id"], first_runs=6)  # Alpha wins

    dashboard = series_detail(client, series["id"])
    assert dashboard["matches_played"] == 2
    assert dashboard["matches_remaining"] == 2
    assert dashboard["match_count"] == 2
    assert {row["match_id"] for row in dashboard["recent_results"]} == {
        first["id"],
        second["id"],
    }
    assert len(dashboard["recent_results"]) == 2

    standings = {row["team_name"]: row for row in dashboard["standings"]}
    assert standings["Alpha"]["wins"] == 1
    assert standings["Alpha"]["losses"] == 1
    assert standings["Bravo"]["wins"] == 1
    assert standings["Bravo"]["losses"] == 1
    assert standings["Alpha"]["points"] == 2
    assert standings["Bravo"]["points"] == 2
    assert [row["played"] for row in dashboard["standings"]] == [2, 2]

    # Reading the dashboard is idempotent and never adds phantom match rows.
    again = series_detail(client, series["id"])
    assert again["matches_played"] == 2
    assert len(again["match_fantasy"]) == 2
    assert len({row["match_id"] for row in again["match_fantasy"]}) == 2


def test_series_dashboard_recalculates_after_an_undo(client):
    series = create_series(client, planned_matches=2)
    match = complete_short_match(client, series["id"], first_runs=0)
    assert series_detail(client, series["id"])["matches_played"] == 1

    second = innings_id(match, 2)
    undone = undo_delivery(client, second, reason="Chase score was wrong")
    assert undone.status_code == 200, undone.get_json()

    corrected = series_detail(client, series["id"])
    assert corrected["matches_played"] == 0
    assert corrected["recent_results"] == []
    assert corrected["mvp_leaderboard"] == []
    assert corrected["awards"]["player_of_series"]["winners"] == []

    # Re-enter the corrected chase; the dashboard comes back immediately.
    chase_bowler = team_players(match, "a")[0]["id"]
    score(client, second, chase_bowler, runs_off_bat=1)
    restored = series_detail(client, series["id"])
    assert restored["matches_played"] == 1
    assert len(restored["recent_results"]) == 1


# --- batting leaderboards ------------------------------------------------


def test_all_batting_leaderboards_and_qualification_thresholds(client):
    series = create_series(client, planned_matches=2)
    play_batting_match(client, series["id"], 100)
    play_batting_match(client, series["id"], 50)

    dashboard = series_detail(client, series["id"])
    batting = dashboard["batting_leaderboards"]
    assert batting["runs"]["rows"][0]["player_name"] == "A1"
    top = batting["runs"]["rows"][0]
    assert top["runs"] == 150
    assert top["highest_score"] == 100
    assert top["fifties"] == 1
    assert top["centuries"] == 1
    assert top["fours"] == 4
    assert top["sixes"] == 21
    assert top["batting_average"] == 75.0
    assert top["strike_rate"] == 483.87
    assert top["qualified"]["batting_average"] is True
    assert top["qualified"]["batting_strike_rate"] is True
    assert batting["highest_score"]["rows"][0]["player_id"] == top["player_id"]
    assert batting["average"]["rows"][0]["player_id"] == top["player_id"]
    assert batting["strike_rate"]["rows"][0]["player_id"] == top["player_id"]
    assert batting["fours"]["rows"][0]["fours"] == 4
    assert batting["sixes"]["rows"][0]["sixes"] == 21
    assert batting["fifties"]["rows"][0]["fifties"] == 1
    assert batting["centuries"]["rows"][0]["centuries"] == 1


# --- bowling leaderboards ------------------------------------------------


def test_all_bowling_leaderboards(client):
    series = create_series(
        client,
        preset="custom_turf",
        planned_matches=1,
        team_a={"name": "Green Caps", "players": list(turf_payload()["team_a"]["players"])},
        team_b={"name": "Night Riders", "players": list(turf_payload()["team_b"]["players"])},
    )
    match = create_and_start(client, turf_payload(series_id=series["id"]))
    first = innings_id(match, 1)
    second = innings_id(match, 2)
    bowler = team_players(match, "b")[0]["id"]

    # Eight dots then four wickets: both overs are maidens, the bowler
    # finishes with 4/0 and reaches the 12-ball economy threshold.
    for _ in range(8):
        score(client, first, bowler)
    for _ in range(4):
        score(client, first, bowler, is_wicket=True, wicket_type="bowled")

    chase_bowler = team_players(match, "a")[0]["id"]
    score(client, second, chase_bowler, runs_off_bat=1)

    dashboard = series_detail(client, series["id"])
    bowling = dashboard["bowling_leaderboards"]
    top = bowling["wickets"]["rows"][0]
    assert top["player_name"] == "Farid"
    assert top["wickets"] == 4
    assert top["best_bowling"] == "4/0"
    assert top["economy"] == 0.0
    assert top["bowling_average"] == 0.0
    assert top["bowling_strike_rate"] == 3.0
    assert top["maidens"] == 2
    assert top["dot_balls"] == 12
    assert top["qualified"]["bowling_economy"] is True
    assert top["qualified"]["bowling_average"] is True
    assert top["qualified"]["bowling_strike_rate"] is True
    assert bowling["economy"]["rows"][0]["player_id"] == top["player_id"]
    assert bowling["best_figures"]["rows"][0]["player_id"] == top["player_id"]
    assert bowling["average"]["rows"][0]["player_id"] == top["player_id"]
    assert bowling["strike_rate"]["rows"][0]["player_id"] == top["player_id"]
    assert bowling["maidens"]["rows"][0]["maidens"] == 2
    assert bowling["dot_balls"]["rows"][0]["dot_balls"] == 12
    assert dashboard["awards"]["best_bowler"]["winners"][0]["player_name"] == "Farid"


# --- fantasy and awards --------------------------------------------------


def test_series_fantasy_leaderboard_and_awards_are_deterministic(client):
    series = create_series(client, planned_matches=2)
    complete_short_match(client, series["id"], first_runs=0)
    complete_short_match(client, series["id"], first_runs=6)

    dashboard = series_detail(client, series["id"])
    assert dashboard["fantasy_leaderboard"] == dashboard["mvp_leaderboard"]
    assert len(dashboard["fantasy_leaderboard"]) > 0
    assert len(dashboard["match_fantasy"]) == 2
    for row in dashboard["fantasy_leaderboard"]:
        assert row["fantasy_points"] == row["batting_points"] + row["bowling_points"]
        assert all(
            item["match_id"] in {match["id"] for match in dashboard["matches"]}
            for item in row["match_points"]
        )

    top = dashboard["fantasy_leaderboard"][0]
    series_award = dashboard["awards"]["player_of_series"]
    assert series_award["value"] == top["fantasy_points"]
    assert series_award["winners"][0]["player_name"] == top["player_name"]
    assert dashboard["awards"]["best_batter"]["winners"]
    assert dashboard["awards"]["best_bowler"]["winners"]
    assert len(dashboard["awards"]["player_of_match"]) == 2

    keys = []
    for award in dashboard["awards"]["player_of_match"]:
        keys.extend(winner["award_key"] for winner in award["winners"])
    assert len(keys) == len(set(keys))

    first_read = [
        (award["match_id"], [winner["player_name"] for winner in award["winners"]])
        for award in dashboard["awards"]["player_of_match"]
    ]
    second = series_detail(client, series["id"])
    second_read = [
        (award["match_id"], [winner["player_name"] for winner in award["winners"]])
        for award in second["awards"]["player_of_match"]
    ]
    assert first_read == second_read


def test_award_ties_keep_every_winner_and_use_a_stable_order():
    rows = [
        {
            "player_id": 2,
            "player_name": "Zed",
            "team_name": "Bravo",
            "fantasy_points": 20,
            "batting_points": 20,
            "bowling_points": 0,
            "runs": 40,
            "highest_score": 40,
            "wickets": 0,
            "matches": 2,
        },
        {
            "player_id": 1,
            "player_name": "Amy",
            "team_name": "Alpha",
            "fantasy_points": 20,
            "batting_points": 20,
            "bowling_points": 0,
            "runs": 40,
            "highest_score": 40,
            "wickets": 0,
            "matches": 2,
        },
    ]
    award = _award(
        rows,
        key="best_batter",
        label="Best Batter",
        metric="batting_points",
        eligible=lambda row: True,
        tie_break=lambda row: (-row["runs"], -row["highest_score"]),
    )
    assert award["tied"] is True
    assert [winner["player_name"] for winner in award["winners"]] == ["Amy", "Zed"]
    assert len({winner["award_key"] for winner in award["winners"]}) == 2


# --- validation ----------------------------------------------------------


def test_series_validation_rejects_unknown_preset_and_bad_plan(client):
    bad_preset = client.post(
        "/api/series", json={"name": "Bad", "preset": "mystery"}
    )
    assert bad_preset.status_code == 422
    assert error_code(bad_preset) == "validation_error"

    bad_plan = client.post(
        "/api/series", json={"name": "Bad", "planned_matches": -1}
    )
    assert bad_plan.status_code == 422
    assert bad_plan.get_json()["error"]["details"]["field"] == "planned_matches"
