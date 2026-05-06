# =============================================================================
# app/models/user.py
# -----------------------------------------------------------------------------
# ORM model for system user accounts. Users authenticate via JWT and are
# assigned a role that controls access to protected endpoints. The User model
# is referenced by RFQ, Quotation, and Approval models through foreign keys.
# =============================================================================

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.rfq import RFQ
    from app.models.quotation import Quotation
    from app.models.approval import Approval


class User(AuditMixin, Base):
    """System user account — purchasers, managers, finance officers, or admins.

    Table: ``users``

    Key relationships:
    - ``rfqs``      — RFQs created by this user.
    - ``quotations`` — Quotations authored by this user.
    - ``approvals``  — Approval records where this user is the approver.
    """

    __tablename__ = "users"

    # ── Identity ──────────────────────────────────────────────────────────────
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # ── Role & status ─────────────────────────────────────────────────────────
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"),
        nullable=False,
        default=UserRole.PURCHASER,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ── Contact ───────────────────────────────────────────────────────────────
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    department: Mapped[Optional[str]] = mapped_column(String(100))

    # ── Relationships ─────────────────────────────────────────────────────────
    rfqs: Mapped[List["RFQ"]] = relationship(
        "RFQ", back_populates="created_by", foreign_keys="RFQ.created_by_id"
    )
    quotations: Mapped[List["Quotation"]] = relationship(
        "Quotation", back_populates="created_by", foreign_keys="Quotation.created_by_id"
    )
    approvals: Mapped[List["Approval"]] = relationship(
        "Approval", back_populates="approver", foreign_keys="[Approval.approver_id]"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"
