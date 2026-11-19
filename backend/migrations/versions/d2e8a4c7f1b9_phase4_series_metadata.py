"""Phase 4 series metadata

Revision ID: d2e8a4c7f1b9
Revises: b7d1e4c9a2f0
Create Date: 2026-11-09 22:30:00.000000

Series gain a planned match count and a selected two-team roster. Existing
series keep every linked match; the planned count is backfilled from the
matches that already belong to the series, so no historical match disappears.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d2e8a4c7f1b9"
down_revision = "b7d1e4c9a2f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("series") as batch:
        batch.add_column(
            sa.Column(
                "planned_matches",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(sa.Column("team_a_name", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("team_b_name", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("team_a_players", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("team_b_players", sa.JSON(), nullable=True))

    op.execute(
        sa.text(
            "UPDATE series SET planned_matches = ("
            "SELECT COUNT(*) FROM matches WHERE matches.series_id = series.id"
            ")"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("series") as batch:
        batch.drop_column("team_b_players")
        batch.drop_column("team_a_players")
        batch.drop_column("team_b_name")
        batch.drop_column("team_a_name")
        batch.drop_column("planned_matches")
