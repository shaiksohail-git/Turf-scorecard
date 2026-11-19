"""Phase 3 retirements, fantasy ledger and extended player statistics

Revision ID: b7d1e4c9a2f0
Revises: c1543d14e253
Create Date: 2026-11-09 18:00:00.000000

Retirements are innings events anchored to the number of active deliveries at
the moment they happened. The fantasy ledger is a rebuildable projection with a
unique source key per award. Existing matches keep working: the new columns are
backfilled, retirements are empty and the ledger is rebuilt on the next scoring
action (or by the stats rebuild).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b7d1e4c9a2f0"
down_revision = "c1543d14e253"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("matches") as batch:
        batch.add_column(
            sa.Column(
                "fantasy_config",
                sa.String(length=16),
                nullable=False,
                server_default="short",
            )
        )

    op.execute(
        sa.text(
            "UPDATE matches SET fantasy_config = 't20' "
            "WHERE preset IN ('full_t20', 'custom_match')"
        )
    )

    with op.batch_alter_table("player_match_statistics") as batch:
        batch.add_column(
            sa.Column("highest_score", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("not_outs", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column(
                "best_bowling_wickets", sa.Integer(), nullable=False, server_default="0"
            )
        )
        batch.add_column(
            sa.Column(
                "best_bowling_runs", sa.Integer(), nullable=False, server_default="0"
            )
        )
        batch.add_column(
            sa.Column(
                "fantasy_points", sa.Integer(), nullable=False, server_default="0"
            )
        )

    op.create_table(
        "retirements",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "innings_id",
            sa.Integer(),
            sa.ForeignKey("innings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "player_id",
            sa.Integer(),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("retirement_type", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.String(length=200)),
        sa.Column(
            "replacement_player_id",
            sa.Integer(),
            sa.ForeignKey("players.id"),
        ),
        sa.Column(
            "retired_after_sequence",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("returned_after_sequence", sa.Integer()),
        sa.Column("returned_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "innings_id",
            "player_id",
            "retired_after_sequence",
            name="uq_retirements_innings_player_sequence",
        ),
        sa.CheckConstraint(
            "retirement_type IN ('retired_not_out', 'retired_out', 'retired_hurt')",
            name="ck_retirements_type",
        ),
        sa.CheckConstraint(
            "retired_after_sequence >= 0", name="ck_retirements_sequence"
        ),
    )
    op.create_index(
        "ix_retirements_innings_id", "retirements", ["innings_id"], unique=False
    )
    op.create_index(
        "ix_retirements_player_id", "retirements", ["player_id"], unique=False
    )

    op.create_table(
        "fantasy_points",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "match_id",
            sa.Integer(),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "innings_id",
            sa.Integer(),
            sa.ForeignKey("innings.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "player_id",
            sa.Integer(),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "delivery_id",
            sa.Integer(),
            sa.ForeignKey("deliveries.id", ondelete="SET NULL"),
        ),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=120), nullable=False),
        sa.Column("detail", sa.String(length=160)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("match_id", "source_key", name="uq_fantasy_points_source"),
    )
    op.create_index("ix_fantasy_points_match_id", "fantasy_points", ["match_id"])
    op.create_index("ix_fantasy_points_player_id", "fantasy_points", ["player_id"])


def downgrade() -> None:
    op.drop_index("ix_fantasy_points_player_id", table_name="fantasy_points")
    op.drop_index("ix_fantasy_points_match_id", table_name="fantasy_points")
    op.drop_table("fantasy_points")

    op.drop_index("ix_retirements_player_id", table_name="retirements")
    op.drop_index("ix_retirements_innings_id", table_name="retirements")
    op.drop_table("retirements")

    with op.batch_alter_table("player_match_statistics") as batch:
        batch.drop_column("fantasy_points")
        batch.drop_column("best_bowling_runs")
        batch.drop_column("best_bowling_wickets")
        batch.drop_column("not_outs")
        batch.drop_column("highest_score")

    with op.batch_alter_table("matches") as batch:
        batch.drop_column("fantasy_config")
