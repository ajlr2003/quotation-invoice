from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.document import DocumentKPIs, DocumentListResponse, DocumentResponse
from app.services import document_service

router = APIRouter()

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.get("/kpis", response_model=DocumentKPIs)
async def kpis(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await document_service.get_kpis(db)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    doc_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await document_service.list_documents(db, doc_type=doc_type, search=search)


@router.post("/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile,
    description: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large — maximum 50 MB")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    mime = file.content_type or "application/octet-stream"
    return await document_service.upload_document(
        db,
        file_bytes=file_bytes,
        original_filename=file.filename,
        mime_type=mime,
        description=description,
        user_id=current_user.id,
    )


@router.get("/{doc_id}/download")
async def download_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        path, doc = await document_service.get_file_path(db, doc_id)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))

    return FileResponse(
        path=str(path),
        media_type=doc.mime_type,
        filename=doc.original_filename,
    )


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        await document_service.delete_document(db, doc_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
