"""Innings model: aggregates that are always derived from delivery events."""

from __future__ import annotations

from ..extensions import db
from .base import TimestampMixin

INNINGS_STATUSES = ("pending", "live", "completed")


class Innings(TimestampMixin, db.Model):
    __tablename__ = "innings"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(
        db.Integer, db.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number = db.Column(db.Integer, nullable=False)
    batting_team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    bowling_team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)

    status = db.Column(db.String(16), nullable=False, default="pending")
    # Ordered list of player ids for the batting side. Fixed when the innings
    # starts so replaying events always yields the same result.
    batting_order = db.Column(db.JSON, nullable=False, default=list)

    total_runs = db.Column(db.Integer, nullable=False, default=0)
    wickets = db.Column(db.Integer, nullable=False, default=0)
    legal_balls = db.Column(db.Integer, nullable=False, default=0)
    target = db.Column(db.Integer)
    revision = db.Column(db.Integer, nullable=False, default=0)

    match = db.relationship("Match", back_populates="innings")
    batting_team = db.relationship("Team", foreign_keys=[batting_team_id])
    bowling_team = db.relationship("Team", foreign_keys=[bowling_team_id])
    deliveries = db.relationship(
        "Delivery",
        back_populates="innings",
        cascade="all, delete-orphan",
        order_by="Delivery.sequence",
    )
    retirements = db.relationship(
        "Retirement",
        back_populates="innings",
        cascade="all, delete-orphan",
        order_by="Retirement.retired_after_sequence, Retirement.id",
    )

    __table_args__ = (
        db.UniqueConstraint("match_id", "number", name="uq_innings_match_number"),
        db.CheckConstraint(
            "status IN ('pending', 'live', 'completed')", name="ck_innings_status"
        ),
        db.CheckConstraint("number >= 1", name="ck_innings_number"),
        db.CheckConstraint(
            "total_runs >= 0 AND wickets >= 0 AND legal_balls >= 0", name="ck_innings_totals"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Innings {self.id} match={self.match_id} #{self.number} {self.status}>"
