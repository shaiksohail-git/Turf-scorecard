"""Security and administrative audit entries.

Match scoring already has its own ``match_events`` trail. This table records
security-relevant actions that are not tied to a match, such as sign-in,
registration, logout and profile changes.
"""

from __future__ import annotations

from ..extensions import db
from .base import utcnow


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(64), nullable=False, index=True)
    actor = db.Column(db.String(64), nullable=False, default="anonymous")
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(255))
    details = db.Column(db.JSON)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AuditLog {self.id} {self.action} user={self.user_id}>"
