"""Team model."""

from __future__ import annotations

from ..extensions import db
from .base import TimestampMixin


class Team(TimestampMixin, db.Model):
    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, index=True)
    short_name = db.Column(db.String(16))

    players = db.relationship(
        "Player",
        back_populates="team",
        order_by="Player.batting_order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Team {self.id} {self.name!r}>"
