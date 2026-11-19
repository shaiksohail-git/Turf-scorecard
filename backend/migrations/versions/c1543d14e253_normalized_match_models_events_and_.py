"""normalized match models, match events and player statistics

Revision ID: c1543d14e253
Revises: ef8a7c709082
Create Date: 2026-11-09 00:11:06.428698

This revision adds the normalized tables introduced for Phase 1 and rewrites
the old ``scoring_audit`` table as ``match_events``. Audit rows are copied, not
dropped, and existing match rows are backfilled into ``match_teams``,
``match_rules`` and ``series_matches`` so the normalized tables agree with the
denormalized columns kept for fast lookups.

``player_match_statistics`` is a derived projection. It is rebuilt from delivery
events on every innings recompute, so this migration leaves it empty rather than
duplicating the scoring engine in a migration script.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c1543d14e253"
down_revision = "ef8a7c709082"
branch_labels = None
depends_on = None

MATCH_RULES = sa.table(
    "match_rules",
    sa.column("match_id", sa.Integer),
    sa.column("preset", sa.String),
    sa.column("version", sa.Integer),
    sa.column("overs", sa.Integer),
    sa.column("balls_per_over", sa.Integer),
    sa.column("players_per_team", sa.Integer),
    sa.column("wide_penalty", sa.Integer),
    sa.column("wide_counts_as_legal_ball", sa.Boolean),
    sa.column("no_ball_penalty", sa.Integer),
    sa.column("no_ball_counts_as_legal_ball", sa.Boolean),
    sa.column("free_hit_enabled", sa.Boolean),
    sa.column("solo_batting_enabled", sa.Boolean),
    sa.column("allowed_runs", sa.JSON),
    sa.column("retired_player_option", sa.Boolean),
    sa.column("retirement_types", sa.JSON),
    sa.column("max_overs_per_bowler", sa.Integer),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _json_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, (str, bytes)):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _copy_audit_rows() -> None:
    """Move ``scoring_audit`` rows into the new ``match_events`` table."""
    if not _has_table("scoring_audit"):
        return
    op.execute(
        sa.text(
            """
            INSERT INTO match_events
                (id, match_id, innings_id, delivery_id, event_type, actor, payload, created_at)
            SELECT id, match_id, innings_id, delivery_id, action, actor, payload, created_at
            FROM scoring_audit
            ORDER BY id
            """
        )
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                SELECT setval(
                    pg_get_serial_sequence('match_events', 'id'),
                    COALESCE((SELECT MAX(id) FROM match_events), 1),
                    (SELECT COUNT(*) > 0 FROM match_events)
                )
                """
            )
        )


def _backfill_matches() -> None:
    bind = op.get_bind()

    # Owner: existing matches belong to the local scorer until sign-in exists.
    if bind.execute(sa.text("SELECT COUNT(*) FROM matches")).scalar():
        bind.execute(
            sa.text(
                """
                INSERT INTO users (display_name, email, is_active, created_at, updated_at)
                SELECT 'Local Scorer', NULL, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                WHERE NOT EXISTS (SELECT 1 FROM users)
                """
            )
        )
        bind.execute(
            sa.text(
                """
                UPDATE matches
                SET owner_id = (SELECT MIN(id) FROM users)
                WHERE owner_id IS NULL
                """
            )
        )

    bind.execute(
        sa.text(
            """
            INSERT INTO match_teams
                (match_id, team_id, side, is_toss_winner, bats_first, created_at, updated_at)
            SELECT
                m.id,
                m.team_a_id,
                'a',
                COALESCE(m.toss_winner_id = m.team_a_id, FALSE),
                COALESCE(m.batting_first_team_id = m.team_a_id, FALSE),
                m.created_at,
                m.updated_at
            FROM matches m
            WHERE NOT EXISTS (
                SELECT 1 FROM match_teams mt WHERE mt.match_id = m.id AND mt.side = 'a'
            )
            """
        )
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO match_teams
                (match_id, team_id, side, is_toss_winner, bats_first, created_at, updated_at)
            SELECT
                m.id,
                m.team_b_id,
                'b',
                COALESCE(m.toss_winner_id = m.team_b_id, FALSE),
                COALESCE(m.batting_first_team_id = m.team_b_id, FALSE),
                m.created_at,
                m.updated_at
            FROM matches m
            WHERE NOT EXISTS (
                SELECT 1 FROM match_teams mt WHERE mt.match_id = m.id AND mt.side = 'b'
            )
            """
        )
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO series_matches (series_id, match_id, position, created_at)
            SELECT
                m.series_id,
                m.id,
                ROW_NUMBER() OVER (
                    PARTITION BY m.series_id ORDER BY m.created_at, m.id
                ),
                m.created_at
            FROM matches m
            WHERE m.series_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM series_matches sm WHERE sm.match_id = m.id
              )
            """
        )
    )

    # Rules snapshot: the JSON column is the source of truth, so parse it in
    # Python instead of relying on JSON operators that differ per dialect.
    now = datetime.now(timezone.utc)
    rows = []
    for match_id, raw_rules in bind.execute(sa.text("SELECT id, rules FROM matches")).all():
        rules = _json_dict(raw_rules)
        if not rules.get("overs"):
            continue
        rows.append(
            {
                "match_id": match_id,
                "preset": str(rules.get("preset") or "custom_match"),
                "version": int(rules.get("version") or 1),
                "overs": int(rules["overs"]),
                "balls_per_over": int(rules.get("balls_per_over") or 6),
                "players_per_team": int(rules.get("players_per_team") or 2),
                "wide_penalty": int(rules.get("wide_penalty") or 0),
                "wide_counts_as_legal_ball": bool(
                    rules.get("wide_counts_as_legal_ball", False)
                ),
                "no_ball_penalty": int(rules.get("no_ball_penalty") or 0),
                "no_ball_counts_as_legal_ball": bool(
                    rules.get("no_ball_counts_as_legal_ball", False)
                ),
                "free_hit_enabled": bool(rules.get("free_hit_enabled", False)),
                "solo_batting_enabled": bool(rules.get("solo_batting_enabled", False)),
                "allowed_runs": list(rules.get("allowed_runs") or []),
                "retired_player_option": bool(rules.get("retired_player_option", False)),
                "retirement_types": list(rules.get("retirement_types") or []),
                "max_overs_per_bowler": rules.get("max_overs_per_bowler"),
                "created_at": now,
                "updated_at": now,
            }
        )
    if rows:
        existing = {
            row[0] for row in bind.execute(sa.text("SELECT match_id FROM match_rules")).all()
        }
        rows = [row for row in rows if row["match_id"] not in existing]
        if rows:
            op.bulk_insert(MATCH_RULES, rows)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=60), nullable=False),
        sa.Column("email", sa.String(length=160), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "match_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("preset", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("overs", sa.Integer(), nullable=False),
        sa.Column("balls_per_over", sa.Integer(), nullable=False),
        sa.Column("players_per_team", sa.Integer(), nullable=False),
        sa.Column("wide_penalty", sa.Integer(), nullable=False),
        sa.Column("wide_counts_as_legal_ball", sa.Boolean(), nullable=False),
        sa.Column("no_ball_penalty", sa.Integer(), nullable=False),
        sa.Column("no_ball_counts_as_legal_ball", sa.Boolean(), nullable=False),
        sa.Column("free_hit_enabled", sa.Boolean(), nullable=False),
        sa.Column("solo_batting_enabled", sa.Boolean(), nullable=False),
        sa.Column("allowed_runs", sa.JSON(), nullable=False),
        sa.Column("retired_player_option", sa.Boolean(), nullable=False),
        sa.Column("retirement_types", sa.JSON(), nullable=False),
        sa.Column("max_overs_per_bowler", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "overs >= 1 AND balls_per_over >= 1", name="ck_match_rules_overs"
        ),
        sa.CheckConstraint(
            "players_per_team >= 2 AND players_per_team <= 11",
            name="ck_match_rules_players",
        ),
        sa.CheckConstraint("version >= 1", name="ck_match_rules_version"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_match_rules_match_id"), "match_rules", ["match_id"], unique=True
    )

    op.create_table(
        "match_teams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("side", sa.String(length=1), nullable=False),
        sa.Column("is_toss_winner", sa.Boolean(), nullable=False),
        sa.Column("bats_first", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("side IN ('a', 'b')", name="ck_match_teams_side"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "side", name="uq_match_teams_match_side"),
        sa.UniqueConstraint("match_id", "team_id", name="uq_match_teams_match_team"),
    )
    op.create_index(
        op.f("ix_match_teams_match_id"), "match_teams", ["match_id"], unique=False
    )
    op.create_index(
        op.f("ix_match_teams_team_id"), "match_teams", ["team_id"], unique=False
    )

    op.create_table(
        "player_match_statistics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("batting_innings", sa.Integer(), nullable=False),
        sa.Column("runs", sa.Integer(), nullable=False),
        sa.Column("balls_faced", sa.Integer(), nullable=False),
        sa.Column("fours", sa.Integer(), nullable=False),
        sa.Column("sixes", sa.Integer(), nullable=False),
        sa.Column("is_out", sa.Boolean(), nullable=False),
        sa.Column("dismissal", sa.String(length=64), nullable=True),
        sa.Column("bowling_innings", sa.Integer(), nullable=False),
        sa.Column("balls_bowled", sa.Integer(), nullable=False),
        sa.Column("runs_conceded", sa.Integer(), nullable=False),
        sa.Column("wickets", sa.Integer(), nullable=False),
        sa.Column("wides", sa.Integer(), nullable=False),
        sa.Column("no_balls", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "runs >= 0 AND balls_faced >= 0 AND wickets >= 0 AND runs_conceded >= 0",
            name="ck_player_match_statistics_values",
        ),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "match_id", "player_id", name="uq_player_match_statistics"
        ),
    )
    op.create_index(
        op.f("ix_player_match_statistics_match_id"),
        "player_match_statistics",
        ["match_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_player_match_statistics_player_id"),
        "player_match_statistics",
        ["player_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_player_match_statistics_team_id"),
        "player_match_statistics",
        ["team_id"],
        unique=False,
    )

    op.create_table(
        "series_matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series_id", "match_id", name="uq_series_matches_pair"),
    )
    op.create_index(
        op.f("ix_series_matches_match_id"), "series_matches", ["match_id"], unique=False
    )
    op.create_index(
        op.f("ix_series_matches_series_id"),
        "series_matches",
        ["series_id"],
        unique=False,
    )

    op.create_table(
        "match_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("innings_id", sa.Integer(), nullable=True),
        sa.Column("delivery_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["delivery_id"], ["deliveries.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["innings_id"], ["innings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_match_events_event_type"), "match_events", ["event_type"], unique=False
    )
    op.create_index(
        op.f("ix_match_events_match_id"), "match_events", ["match_id"], unique=False
    )

    # Preserve the audit trail before removing the old table.
    _copy_audit_rows()
    if _has_table("scoring_audit"):
        op.drop_table("scoring_audit")

    with op.batch_alter_table("matches") as batch:
        batch.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
        batch.create_index(op.f("ix_matches_owner_id"), ["owner_id"], unique=False)
        batch.create_foreign_key(
            "fk_matches_owner_id_users",
            "users",
            ["owner_id"],
            ["id"],
            ondelete="SET NULL",
        )

    _backfill_matches()


def downgrade() -> None:
    op.create_table(
        "scoring_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("innings_id", sa.Integer(), nullable=True),
        sa.Column("delivery_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["delivery_id"], ["deliveries.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["innings_id"], ["innings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_scoring_audit_action"), "scoring_audit", ["action"], unique=False
    )
    op.create_index(
        op.f("ix_scoring_audit_match_id"), "scoring_audit", ["match_id"], unique=False
    )
    op.execute(
        sa.text(
            """
            INSERT INTO scoring_audit
                (id, match_id, innings_id, delivery_id, action, actor, payload, created_at)
            SELECT id, match_id, innings_id, delivery_id, event_type, actor, payload, created_at
            FROM match_events
            ORDER BY id
            """
        )
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                SELECT setval(
                    pg_get_serial_sequence('scoring_audit', 'id'),
                    COALESCE((SELECT MAX(id) FROM scoring_audit), 1),
                    (SELECT COUNT(*) > 0 FROM scoring_audit)
                )
                """
            )
        )

    op.drop_index(op.f("ix_match_events_match_id"), table_name="match_events")
    op.drop_index(op.f("ix_match_events_event_type"), table_name="match_events")
    op.drop_table("match_events")

    op.drop_index(op.f("ix_series_matches_series_id"), table_name="series_matches")
    op.drop_index(op.f("ix_series_matches_match_id"), table_name="series_matches")
    op.drop_table("series_matches")

    op.drop_index(
        op.f("ix_player_match_statistics_team_id"),
        table_name="player_match_statistics",
    )
    op.drop_index(
        op.f("ix_player_match_statistics_player_id"),
        table_name="player_match_statistics",
    )
    op.drop_index(
        op.f("ix_player_match_statistics_match_id"),
        table_name="player_match_statistics",
    )
    op.drop_table("player_match_statistics")

    op.drop_index(op.f("ix_match_teams_team_id"), table_name="match_teams")
    op.drop_index(op.f("ix_match_teams_match_id"), table_name="match_teams")
    op.drop_table("match_teams")

    op.drop_index(op.f("ix_match_rules_match_id"), table_name="match_rules")
    op.drop_table("match_rules")

    with op.batch_alter_table("matches") as batch:
        batch.drop_constraint("fk_matches_owner_id_users", type_="foreignkey")
        batch.drop_index(op.f("ix_matches_owner_id"))
        batch.drop_column("owner_id")

    op.drop_table("users")
