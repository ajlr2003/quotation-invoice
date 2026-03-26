"""
Document — file attachments for any entity (RFQ, Quotation, Invoice, SupplierQuote).
Stores metadata only; actual files live in object storage (S3 / GCS / Azure Blob).
"""
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AuditMixin
from app.models.enums import DocumentEntityType, DocumentType

if TYPE_CHECKING:
    from app.models.user import User


class Document(AuditMixin, Base):
    """
    Metadata record for a file attachment.

    The actual binary is stored externally (e.g. S3).
    `storage_key` is the object-store key / path used to build a pre-signed URL.
    """

    __tablename__ = "documents"

    # ── Generic entity reference ──────────────────────────────────────────
    entity_type: Mapped[DocumentEntityType] = mapped_column(
        Enum(DocumentEntityType, name="document_entity_type"),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)

    # ── File metadata ─────────────────────────────────────────────────────
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type"),
        nullable=False,
        default=DocumentType.OTHER,
    )
    filename: Mapped[str]              = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str]     = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str]             = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)

    # ── Storage ───────────────────────────────────────────────────────────
    storage_key: Mapped[str]           = mapped_column(String(512), nullable=False)
    storage_bucket: Mapped[Optional[str]] = mapped_column(String(255))

    # ── Contextual ────────────────────────────────────────────────────────
    description: Mapped[Optional[str]] = mapped_column(Text)
    version: Mapped[int]               = mapped_column(default=1, nullable=False)
    is_latest: Mapped[bool]            = mapped_column(default=True, nullable=False)

    # ── Ownership ─────────────────────────────────────────────────────────
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # ── Relationships ─────────────────────────────────────────────────────
    uploaded_by: Mapped["User"] = relationship("User", foreign_keys=[uploaded_by_id])

    def __repr__(self) -> str:
        return (
            f"<Document id={self.id} entity={self.entity_type}:{self.entity_id} "
            f"file={self.original_filename}>"
        )
