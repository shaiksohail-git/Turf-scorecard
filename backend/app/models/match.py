"""Match model.

``Match.rules`` is an immutable snapshot of the rule preset taken when the
match is created. Nothing in the application rewrites it, so historical
matches keep scoring under the rules they started with even if presets change
later.
"""

from __future__ import annotations

from ..extensions import db
from .base import TimestampMixin

MATCH_STATUSES = ("draft", "live", "completed", "abandoned")
TOSS_DECISIONS = ("bat", "bowl")


class Match(TimestampMixin, db.Model):
    __tablename__ = "matches"

    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(
        db.Integer, db.ForeignKey("series.id", ondelete="SET NULL"), index=True, nullable=True
    )

    team_a_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False, index=True)
    team_b_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False, index=True)
    owner_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )

    venue = db.Column(db.String(120))
    preset = db.Column(db.String(32), nullable=False)
    rules = db.Column(db.JSON, nullable=False)
    rules_version = db.Column(db.Integer, nullable=False, default=1)

    status = db.Column(db.String(16), nullable=False, default="draft", index=True)
    # Fantasy rules differ between T20 and short formats; the match pins the
    # configuration it was created with so historical ledgers stay reproducible.
    fantasy_config = db.Column(db.String(16), nullable=False, default="short")
    toss_winner_id = db.Column(db.Integer, db.ForeignKey("teams.id"))
    toss_decision = db.Column(db.String(8))
    batting_first_team_id = db.Column(db.Integer, db.ForeignKey("teams.id"))

    result = db.Column(db.JSON)
    started_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))
    revision = db.Column(db.Integer, nullable=False, default=0)

    series = db.relationship("Series", back_populates="matches")
    owner = db.relationship("User", back_populates="matches")
    team_a = db.relationship("Team", foreign_keys=[team_a_id])
    team_b = db.relationship("Team", foreign_keys=[team_b_id])
    match_teams = db.relationship(
        "MatchTeam",
        back_populates="match",
        cascade="all, delete-orphan",
        order_by="MatchTeam.side",
    )
    rules_row = db.relationship(
        "MatchRules", back_populates="match", uselist=False, cascade="all, delete-orphan"
    )
    series_links = db.relationship(
        "SeriesMatch", back_populates="match", cascade="all, delete-orphan"
    )
    innings = db.relationship(
        "Innings",
        back_populates="match",
        cascade="all, delete-orphan",
        order_by="Innings.number",
    )

    __table_args__ = (
        db.CheckConstraint("team_a_id <> team_b_id", name="ck_matches_distinct_teams"),
        db.CheckConstraint(
            "status IN ('draft', 'live', 'completed', 'abandoned')", name="ck_matches_status"
        ),
        db.CheckConstraint(
            "toss_decision IS NULL OR toss_decision IN ('bat', 'bowl')",
            name="ck_matches_toss_decision",
        ),
        db.CheckConstraint("rules_version >= 1", name="ck_matches_rules_version"),
        db.CheckConstraint(
            "fantasy_config IN ('t20', 'short')", name="ck_matches_fantasy_config"
        ),
        db.Index("ix_matches_status_id", "status", "id"),
        db.Index("ix_matches_series_id_id", "series_id", "id"),
        db.Index("ix_matches_owner_id_id", "owner_id", "id"),
    )

    @property
    def teams(self) -> tuple:
        return (self.team_a, self.team_b)

    def team_by_key(self, key: str):
        return self.team_a if key == "a" else self.team_b

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Match {self.id} {self.preset} {self.status}>"
