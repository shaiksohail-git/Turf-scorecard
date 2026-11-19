"""Retirement events for one innings.

A retirement is recorded between deliveries; ``retired_after_sequence`` is the
number of active deliveries at the moment it happened, which lets replay place
the event exactly where it occurred. Retirement is not a dismissal except for
``retired_out``, which counts as a wicket and cannot be reversed.
"""

from __future__ import annotations

from ..extensions import db
from .base import TimestampMixin

RETIREMENT_TYPES = ("retired_not_out", "retired_out", "retired_hurt")


class Retirement(TimestampMixin, db.Model):
    __tablename__ = "retirements"

    id = db.Column(db.Integer, primary_key=True)
    innings_id = db.Column(
        db.Integer, db.ForeignKey("innings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_id = db.Column(
        db.Integer, db.ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    retirement_type = db.Column(db.String(24), nullable=False)
    reason = db.Column(db.String(200))
    replacement_player_id = db.Column(db.Integer, db.ForeignKey("players.id"))

    retired_after_sequence = db.Column(db.Integer, nullable=False, default=0)
    retired_at = db.Column(db.DateTime(timezone=True), nullable=False)
    returned_after_sequence = db.Column(db.Integer)
    returned_at = db.Column(db.DateTime(timezone=True))

    innings = db.relationship("Innings", back_populates="retirements")
    player = db.relationship("Player", foreign_keys=[player_id])
    replacement = db.relationship("Player", foreign_keys=[replacement_player_id])

    __table_args__ = (
        db.UniqueConstraint(
            "innings_id",
            "player_id",
            "retired_after_sequence",
            name="uq_retirements_innings_player_sequence",
        ),
        db.CheckConstraint(
            "retirement_type IN ('retired_not_out', 'retired_out', 'retired_hurt')",
            name="ck_retirements_type",
        ),
        db.CheckConstraint(
            "retired_after_sequence >= 0", name="ck_retirements_sequence"
        ),
    )

    @property
    def can_return(self) -> bool:
        return self.retirement_type != "retired_out" and self.returned_at is None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Retirement {self.id} innings={self.innings_id} "
            f"player={self.player_id} {self.retirement_type}>"
        )
