"""Phase 5 authentication, security audit and query indexes

Revision ID: f4a9c2d6b8e1
Revises: d2e8a4c7f1b9
Create Date: 2026-11-10 10:00:00.000000

Adds optional production authentication fields, series ownership, a security
audit table and composite indexes used by paginated history and detail reads.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f4a9c2d6b8e1"
down_revision = "d2e8a4c7f1b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("password_hash", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("series") as batch:
        batch.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
        batch.create_index("ix_series_owner_id", ["owner_id"])
        batch.create_foreign_key(
            "fk_series_owner_id_users", "users", ["owner_id"], ["id"], ondelete="SET NULL"
        )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False, server_default="anonymous"),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.create_index("ix_matches_status_id", "matches", ["status", "id"])
    op.create_index("ix_matches_series_id_id", "matches", ["series_id", "id"])
    op.create_index("ix_matches_owner_id_id", "matches", ["owner_id", "id"])
    op.create_index("ix_series_owner_id_id", "series", ["owner_id", "id"])
    op.create_index("ix_match_events_match_id_id", "match_events", ["match_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_match_events_match_id_id", table_name="match_events")
    op.drop_index("ix_series_owner_id_id", table_name="series")
    op.drop_index("ix_matches_owner_id_id", table_name="matches")
    op.drop_index("ix_matches_series_id_id", table_name="matches")
    op.drop_index("ix_matches_status_id", table_name="matches")

    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_table("audit_logs")

    with op.batch_alter_table("series") as batch:
        batch.drop_constraint("fk_series_owner_id_users", type_="foreignkey")
        batch.drop_index("ix_series_owner_id")
        batch.drop_column("owner_id")

    with op.batch_alter_table("users") as batch:
        batch.drop_column("last_login_at")
        batch.drop_column("password_hash")
