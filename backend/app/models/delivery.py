"""Delivery model: one immutable row per scored ball.

Deliveries are the source of truth. Nothing is deleted: a mistake is undone by
marking the delivery void (with a reason) and replaying the innings, which keeps
the audit trail intact.
"""

from __future__ import annotations

from ..extensions import db
from .base import utcnow


class Delivery(db.Model):
    __tablename__ = "deliveries"

    id = db.Column(db.Integer, primary_key=True)
    innings_id = db.Column(
        db.Integer, db.ForeignKey("innings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence = db.Column(db.Integer, nullable=False)
    # Optional client supplied idempotency key; a double submit returns the
    # already recorded delivery instead of scoring the ball twice.
    client_event_id = db.Column(db.String(64))

    over_number = db.Column(db.Integer, nullable=False)
    ball_in_over = db.Column(db.Integer, nullable=False)

    striker_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False)
    non_striker_id = db.Column(db.Integer, db.ForeignKey("players.id"))
    bowler_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False)

    runs_off_bat = db.Column(db.Integer, nullable=False, default=0)
    extra_type = db.Column(db.String(16))
    extra_runs = db.Column(db.Integer, nullable=False, default=0)
    penalty_runs = db.Column(db.Integer, nullable=False, default=0)
    total_runs = db.Column(db.Integer, nullable=False, default=0)

    is_legal_ball = db.Column(db.Boolean, nullable=False, default=True)
    is_free_hit = db.Column(db.Boolean, nullable=False, default=False)

    is_wicket = db.Column(db.Boolean, nullable=False, default=False)
    wicket_type = db.Column(db.String(32))
    dismissed_player_id = db.Column(db.Integer, db.ForeignKey("players.id"))
    dismissed_role = db.Column(db.String(12))

    is_voided = db.Column(db.Boolean, nullable=False, default=False)
    voided_at = db.Column(db.DateTime(timezone=True))
    void_reason = db.Column(db.String(200))

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    innings = db.relationship("Innings", back_populates="deliveries")

    __table_args__ = (
        db.UniqueConstraint("innings_id", "sequence", name="uq_deliveries_innings_sequence"),
        db.UniqueConstraint(
            "innings_id", "client_event_id", name="uq_deliveries_innings_client_event"
        ),
        db.CheckConstraint(
            "runs_off_bat >= 0 AND extra_runs >= 0 AND penalty_runs >= 0 AND total_runs >= 0",
            name="ck_deliveries_runs",
        ),
        db.CheckConstraint("over_number >= 1 AND ball_in_over >= 1", name="ck_deliveries_position"),
        db.CheckConstraint(
            "extra_type IS NULL OR extra_type IN ('wide', 'no_ball', 'bye', 'leg_bye')",
            name="ck_deliveries_extra_type",
        ),
        db.CheckConstraint(
            "dismissed_role IS NULL OR dismissed_role IN ('striker', 'non_striker')",
            name="ck_deliveries_dismissed_role",
        ),
    )

    @property
    def runs_run(self) -> int:
        """Runs physically run (used for strike rotation)."""
        return self.runs_off_bat + self.extra_runs

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Delivery {self.id} innings={self.innings_id} seq={self.sequence} "
            f"{self.total_runs} runs>"
        )
