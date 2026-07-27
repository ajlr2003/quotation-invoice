# =============================================================================
# app/models/activity_log.py
# -----------------------------------------------------------------------------
# Generic activity timeline entry ("who did what, when") attached to any
# business entity via the entity_id / entity_type pattern already used by
# Document and Approval. Read-only from the API's perspective — entries are
# only ever written by service-layer code as a side effect of a real action
# (create, status change, approval, deactivation, …), never edited or deleted.
# =============================================================================

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin
from app.models.enums import ActivityEntityType

if TYPE_CHECKING:
    from app.models.user import User


class ActivityLog(AuditMixin, Base):
    """A single timeline entry for an entity ("Abdulrahman sent RFQ to 3 suppliers").

    Table: ``activity_logs``

    ``created_at`` (from ``AuditMixin``) is the entry's timestamp — entries
    are immutable, so ``updated_at`` is unused but kept for schema
    consistency with every other model in this codebase.
    """

    __tablename__ = "activity_logs"

    # ── Generic entity reference ─────────────────────────────────────────────
    entity_type: Mapped[ActivityEntityType] = mapped_column(
        Enum(ActivityEntityType, name="activity_entity_type"),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)

    # ── Who & what ────────────────────────────────────────────────────────────
    # Short machine-readable action key (e.g. "created", "status_changed",
    # "approved", "deactivated") plus a human-readable message for display.
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[user_id], lazy="noload")

    # Requires ``user`` to be eagerly loaded (selectinload) by the caller —
    # same convention as SalesQuotation.created_by_name.
    @property
    def user_name(self) -> Optional[str]:
        return self.user.full_name if self.user else None

    def __repr__(self) -> str:
        return (
            f"<ActivityLog entity={self.entity_type}:{self.entity_id} "
            f"action={self.action!r}>"
        )
