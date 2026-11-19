"""Tests for the normalized Phase 1 schema, profile, events and stats APIs."""

from __future__ import annotations

from sqlalchemy import select

from app.models import (
    MatchRules,
    MatchTeam,
    PlayerMatchStatistics,
    SeriesMatch,
    User,
)
from helpers import (
    TURF_TEAM_B,
    create_match,
    innings_id,
    post_delivery,
    team_players,
    turf_payload,
    undo_delivery,
)


def test_default_local_user_owns_every_match(client, session):
    first = create_match(client, turf_payload())
    second = create_match(client, turf_payload())

    users = session.execute(select(User)).scalars().all()
    assert [user.display_name for user in users] == ["Local Scorer"]
    assert first["owner_id"] == users[0].id
    assert second["owner_id"] == users[0].id


def test_profile_can_be_read_and_updated(client):
    me = client.get("/api/users/me").get_json()["data"]
    assert me["display_name"] == "Local Scorer"
    assert me["is_active"] is True

    updated = client.patch("/api/users/me", json={"display_name": "Ayesha"})
    assert updated.status_code == 200
    assert updated.get_json()["data"]["display_name"] == "Ayesha"
    assert client.get("/api/users/me").get_json()["data"]["display_name"] == "Ayesha"

    invalid = client.patch("/api/users/me", json={"display_name": "x"})
    assert invalid.status_code == 422
    assert invalid.get_json()["error"]["details"]["field"] == "display_name"


def test_match_team_rows_mirror_the_toss(client, session, turf_match):
    rows = (
        session.execute(
            select(MatchTeam)
            .where(MatchTeam.match_id == turf_match["id"])
            .order_by(MatchTeam.side)
        )
        .scalars()
        .all()
    )
    assert [(row.side, row.team_id) for row in rows] == [
        ("a", turf_match["team_a"]["id"]),
        ("b", turf_match["team_b"]["id"]),
    ]
    assert rows[0].is_toss_winner is True
    assert rows[0].bats_first is True
    assert rows[1].is_toss_winner is False
    assert rows[1].bats_first is False


def test_match_rules_row_matches_the_frozen_snapshot(client, session, turf_match):
    row = session.execute(
        select(MatchRules).where(MatchRules.match_id == turf_match["id"])
    ).scalar_one()

    assert row.preset == "custom_turf"
    assert row.to_dict() == {
        key: turf_match["rules"][key] for key in row.to_dict()
    }
    assert row.to_ruleset().total_balls == 36


def test_series_match_link_records_position(client, session):
    series = client.post(
        "/api/series", json={"name": "Turf League", "preset": "custom_turf"}
    ).get_json()["data"]

    first = create_match(client, turf_payload(series_id=series["id"]))
    second = create_match(client, turf_payload(series_id=series["id"]))

    links = (
        session.execute(
            select(SeriesMatch)
            .where(SeriesMatch.series_id == series["id"])
            .order_by(SeriesMatch.position)
        )
        .scalars()
        .all()
    )
    assert [(link.match_id, link.position) for link in links] == [
        (first["id"], 1),
        (second["id"], 2),
    ]


def test_player_match_statistics_rebuild_on_every_ball(client, session, turf_match):
    striker = team_players(turf_match, "a")[0]
    bowler = team_players(turf_match, "b")[0]
    innings = innings_id(turf_match)

    post_delivery(client, innings, runs_off_bat=4, bowler_id=bowler["id"])
    post_delivery(client, innings, runs_off_bat=6, bowler_id=bowler["id"])

    rows = (
        session.execute(
            select(PlayerMatchStatistics).where(
                PlayerMatchStatistics.match_id == turf_match["id"]
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 10

    batter = next(row for row in rows if row.player_id == striker["id"])
    assert (
        batter.runs,
        batter.balls_faced,
        batter.fours,
        batter.sixes,
        batter.batting_innings,
    ) == (10, 2, 1, 1, 1)

    bowler_row = next(row for row in rows if row.player_id == bowler["id"])
    assert (
        bowler_row.balls_bowled,
        bowler_row.runs_conceded,
        bowler_row.bowling_innings,
    ) == (2, 10, 1)

    undo_delivery(client, innings)
    session.expire_all()
    batter = session.execute(
        select(PlayerMatchStatistics).where(
            PlayerMatchStatistics.match_id == turf_match["id"],
            PlayerMatchStatistics.player_id == striker["id"],
        )
    ).scalar_one()
    assert (batter.runs, batter.balls_faced, batter.sixes) == (4, 1, 0)


def test_stats_overview_reports_totals_and_leaderboards(client, turf_match):
    striker = team_players(turf_match, "a")[0]
    bowler = team_players(turf_match, "b")[0]
    post_delivery(
        client, innings_id(turf_match), runs_off_bat=4, bowler_id=bowler["id"]
    )

    data = client.get("/api/stats/overview").get_json()["data"]
    totals = data["totals"]
    assert totals["matches"] == 1
    assert totals["matches_live"] == 1
    assert totals["players"] == 10
    assert totals["teams"] == 2
    assert totals["runs"] == 4
    assert totals["legal_balls"] == 1

    assert data["top_run_scorers"][0]["player_name"] == striker["name"]
    assert data["top_run_scorers"][0]["runs"] == 4
    assert data["top_wicket_takers"] == []


def test_events_endpoint_exposes_the_audit_trail(client, turf_match):
    innings = innings_id(turf_match)
    post_delivery(
        client,
        innings,
        runs_off_bat=2,
        bowler_id=team_players(turf_match, "b")[0]["id"],
    )
    undo_delivery(client, innings, reason="mis-tap")

    events = client.get(
        f"/api/matches/{turf_match['id']}/events"
    ).get_json()["data"]
    assert [event["event_type"] for event in events] == [
        "delivery.voided",
        "delivery.recorded",
        "match.started",
        "match.created",
    ]
    assert all(event["actor"] for event in events)
    assert events[0]["payload"]["reason"] == "mis-tap"


def test_scorecard_payload_supports_the_scorecard_screen(client, turf_match):
    innings = innings_id(turf_match)
    bowler = team_players(turf_match, "b")[0]
    post_delivery(client, innings, runs_off_bat=4, bowler_id=bowler["id"])
    post_delivery(client, innings, extra_type="wide", bowler_id=bowler["id"])

    data = client.get(
        f"/api/matches/{turf_match['id']}/scorecard"
    ).get_json()["data"]
    assert {"match", "rules", "innings"} <= set(data)
    assert data["match"]["status"] == "live"

    card = data["innings"][0]
    assert card["overs"] == "0.1"
    assert card["extras"]["total"] == 1

    batter = card["batting"][0]
    for key in (
        "name",
        "runs",
        "balls",
        "fours",
        "sixes",
        "strike_rate",
        "is_out",
        "dismissal",
    ):
        assert key in batter
    assert batter["runs"] == 4
    assert batter["strike_rate"] == 400.0

    bowling_line = card["bowling"][0]
    for key in ("name", "overs", "runs", "wickets", "economy"):
        assert key in bowling_line
    assert card["state"]["runs"] == 5
    assert card["state"]["legal_balls"] == 1


def test_match_detail_exposes_the_live_pad_inputs(client, turf_match):
    detail = client.get(f"/api/matches/{turf_match['id']}").get_json()["data"]

    assert detail["rules"]["allowed_runs"] == [0, 1, 2, 3, 4, 5, 6]
    assert [player["name"] for player in detail["team_b"]["players"]] == list(
        TURF_TEAM_B
    )
    assert detail["innings"][0]["bowling_team_id"] == detail["team_b"]["id"]
    assert detail["owner_id"] is not None
    assert [row["side"] for row in detail["match_teams"]] == ["a", "b"]
