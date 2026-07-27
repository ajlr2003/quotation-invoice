from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.enums import DocumentType
from app.schemas.document import DocumentKPIs, DocumentListResponse, DocumentResponse

UPLOAD_DIR = Path("uploads/documents")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_MIME_TO_TYPE = {
    "application/pdf": DocumentType.PDF,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": DocumentType.EXCEL,
    "application/vnd.ms-excel": DocumentType.EXCEL,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocumentType.WORD,
    "application/msword": DocumentType.WORD,
    "image/png": DocumentType.IMAGE,
    "image/jpeg": DocumentType.IMAGE,
    "image/gif": DocumentType.IMAGE,
    "image/webp": DocumentType.IMAGE,
}


def _doc_type_from_mime(mime: str) -> DocumentType:
    return _MIME_TO_TYPE.get(mime, DocumentType.OTHER)


def _to_response(d: Document) -> DocumentResponse:
    return DocumentResponse(
        id=d.id,
        filename=d.filename,
        original_filename=d.original_filename,
        mime_type=d.mime_type,
        file_size_bytes=d.file_size_bytes,
        document_type=d.document_type.value,
        description=d.description,
        entity_type=d.entity_type.value if d.entity_type else None,
        entity_id=d.entity_id,
        version=d.version,
        uploaded_by_id=d.uploaded_by_id,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


async def list_documents(
    db: AsyncSession,
    doc_type: Optional[str] = None,
    search: Optional[str] = None,
) -> DocumentListResponse:
    q = select(Document).order_by(Document.created_at.desc())
    if doc_type and doc_type != "all":
        q = q.where(Document.document_type == doc_type)
    if search:
        q = q.where(Document.original_filename.ilike(f"%{search}%"))
    result = await db.execute(q)
    docs = list(result.scalars().all())
    return DocumentListResponse(items=[_to_response(d) for d in docs], total=len(docs))


async def upload_document(
    db: AsyncSession,
    file_bytes: bytes,
    original_filename: str,
    mime_type: str,
    description: Optional[str],
    user_id: uuid.UUID,
) -> DocumentResponse:
    doc_type = _doc_type_from_mime(mime_type)
    unique_name = f"{uuid.uuid4()}_{original_filename}"
    dest = UPLOAD_DIR / unique_name
    dest.write_bytes(file_bytes)

    doc = Document(
        filename=unique_name,
        original_filename=original_filename,
        mime_type=mime_type,
        file_size_bytes=len(file_bytes),
        document_type=doc_type,
        storage_key=str(dest),
        description=description,
        version=1,
        is_latest=True,
        uploaded_by_id=user_id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return _to_response(doc)


async def get_file_path(db: AsyncSession, doc_id: uuid.UUID) -> tuple[Path, Document]:
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise ValueError(f"Document {doc_id} not found")
    path = Path(doc.storage_key)
    if not path.exists():
        raise FileNotFoundError(f"File for document {doc_id} not found on disk")
    return path, doc


async def delete_document(db: AsyncSession, doc_id: uuid.UUID) -> None:
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise ValueError(f"Document {doc_id} not found")
    path = Path(doc.storage_key)
    if path.exists():
        path.unlink()
    await db.delete(doc)
    await db.commit()


async def get_kpis(db: AsyncSession) -> DocumentKPIs:
    total = (await db.execute(select(func.count()).select_from(Document))).scalar_one()
    size_row = await db.execute(select(func.sum(Document.file_size_bytes)))
    total_size = int(size_row.scalar() or 0)

    type_rows = await db.execute(
        select(Document.document_type, func.count()).group_by(Document.document_type)
    )
    by_type = {row[0].value: row[1] for row in type_rows.all()}

    return DocumentKPIs(total_documents=total, total_size_bytes=total_size, by_type=by_type)
