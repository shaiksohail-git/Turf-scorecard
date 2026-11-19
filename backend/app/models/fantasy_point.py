"""Itemized fantasy-point ledger.

Rows are rebuilt from delivery events after every innings recompute, so the
ledger is a projection. ``source_key`` is unique per match and names the exact
award (for example ``innings:3:player:12:milestone:50``) which is what prevents
duplicate milestone, haul or maiden awards.
"""

from __future__ import annotations

from ..extensions import db
from .base import TimestampMixin


class FantasyPoint(TimestampMixin, db.Model):
    __tablename__ = "fantasy_points"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(
        db.Integer, db.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    innings_id = db.Column(db.Integer, db.ForeignKey("innings.id", ondelete="CASCADE"))
    player_id = db.Column(
        db.Integer, db.ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    delivery_id = db.Column(db.Integer, db.ForeignKey("deliveries.id", ondelete="SET NULL"))

    category = db.Column(db.String(32), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    source_key = db.Column(db.String(120), nullable=False)
    detail = db.Column(db.String(160))

    __table_args__ = (
        db.UniqueConstraint("match_id", "source_key", name="uq_fantasy_points_source"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<FantasyPoint {self.id} match={self.match_id} player={self.player_id} "
            f"{self.category}={self.points}>"
        )
