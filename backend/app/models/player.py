"""Player model."""

from __future__ import annotations

from ..extensions import db
from .base import TimestampMixin


class Player(TimestampMixin, db.Model):
    __tablename__ = "players"

    ROLES = ("batter", "bowler", "all_rounder", "wicketkeeper")

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(
        db.Integer, db.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(24), nullable=False, default="batter")
    batting_order = db.Column(db.Integer, nullable=False, default=0)

    team = db.relationship("Team", back_populates="players")

    __table_args__ = (
        db.CheckConstraint(
            "role IN ('batter', 'bowler', 'all_rounder', 'wicketkeeper')",
            name="ck_players_role",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Player {self.id} {self.name!r} team={self.team_id}>"
