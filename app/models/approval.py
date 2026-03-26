"""
Approval — multi-level approval record attached to a Quotation (or Invoice).
Uses a generic entity_id / entity_type pattern to stay extensible.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin
from app.models.enums import ApprovalStatus, ApprovalEntityType

if TYPE_CHECKING:
    from app.models.user import User


class Approval(AuditMixin, Base):
    """
    A single approval step for a Quotation or Invoice.

    Multi-level approval is modelled via `level`:
      level 1 → team lead, level 2 → manager, level 3 → director, etc.
    All levels must be APPROVED before the entity moves forward.
    Any REJECTED approval immediately blocks the workflow.
    """

    __tablename__ = "approvals"

    # ── Generic entity reference ──────────────────────────────────────────
    entity_type: Mapped[ApprovalEntityType] = mapped_column(
        Enum(ApprovalEntityType, name="approval_entity_type"),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False, index=True
    )

    # ── Approval meta ─────────────────────────────────────────────────────
    level: Mapped[int]    = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="approval_status"),
        nullable=False,
        default=ApprovalStatus.PENDING,
    )

    # ── Who & when ───────────────────────────────────────────────────────
    approver_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actioned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    comments: Mapped[Optional[str]]         = mapped_column(Text)

    # ── Delegation support ────────────────────────────────────────────────
    delegated_to_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    # ── Relationships ─────────────────────────────────────────────────────
    approver: Mapped["User"] = relationship(
        "User", back_populates="approvals", foreign_keys=[approver_id]
    )
    delegated_to: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[delegated_to_id]
    )

    def approve(self, approver_id: uuid.UUID, comments: str = "") -> None:
        self.status = ApprovalStatus.APPROVED
        self.approver_id = approver_id
        self.actioned_at = datetime.utcnow()
        self.comments = comments

    def reject(self, approver_id: uuid.UUID, comments: str) -> None:
        self.status = ApprovalStatus.REJECTED
        self.approver_id = approver_id
        self.actioned_at = datetime.utcnow()
        self.comments = comments

    def __repr__(self) -> str:
        return (
            f"<Approval id={self.id} entity={self.entity_type}:{self.entity_id} "
            f"level={self.level} status={self.status}>"
        )
