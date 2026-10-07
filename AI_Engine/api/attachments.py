"""사용자별 채팅 첨부 파일의 중복 확인·저장·본문 추출 API."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from AI_Engine.attachment_service import attachment_service, normalized_filename
from AI_Engine.auth.dependencies import get_current_user, require_csrf_user
from AI_Engine.blob_store import BlobStoreError
from AI_Engine.database.connection import get_database_session
from AI_Engine.database.models import Attachment, FileProcessingJob, TranscriptionSegment, User
from AI_Engine.file_extraction import FileInputError, run_file_extraction
from AI_Engine.job_file_text import (
    MAX_JOB_FILE_BYTES,
)


router = APIRouter(prefix="/api/v2/attachments", tags=["attachments"])


class AttachmentDescriptor(BaseModel):
    client_id: str
    filename: str
    mime_type: str = ""
    size_bytes: int = Field(ge=0)
    content_hash: str = Field(min_length=64, max_length=64)


class AttachmentPreflightRequest(BaseModel):
    items: list[AttachmentDescriptor] = Field(max_length=10)


class AttachmentResponse(BaseModel):
    id: str
    filename: str
    mime_type: str
    size_bytes: int
    content_hash: str
    status: str
    extracted_text_available: bool
    parse_error: str | None = None
    parser_version: str
    quality_score: float | None = None
    warnings: list[str] = Field(default_factory=list)
    media_kind: str = "document"
    duration_ms: int | None = None
    storage_backend: str = "database"
    processing_job_id: str | None = None
    processing_job_status: str | None = None
    original_attachment_id: str | None = None
    created_at: datetime
    reused: bool = False


class AttachmentPreflightItem(BaseModel):
    client_id: str
    status: Literal[
        "new_file",
        "exact_duplicate",
        "same_name_different_content",
    ]
    existing_attachment: AttachmentResponse | None = None


def _attachment_response(
    attachment: Attachment,
    database: Session,
    *,
    reused: bool = False,
) -> AttachmentResponse:
    job = attachment_service.latest_job(database, attachment.id)
    metadata = attachment.extraction_metadata or {}
    return AttachmentResponse(
        id=attachment.id,
        filename=attachment.filename,
        mime_type=attachment.mime_type,
        size_bytes=attachment.size_bytes,
        content_hash=attachment.content_hash,
        status=attachment.parse_status,
        extracted_text_available=bool(attachment.extracted_text.strip()),
        parse_error=attachment.parse_error,
        parser_version=attachment.parser_version,
        quality_score=metadata.get("quality_score"),
        warnings=list(metadata.get("warnings", [])),
        media_kind=attachment.media_kind,
        duration_ms=attachment.duration_ms,
        storage_backend=attachment.storage_backend,
        processing_job_id=job.id if job is not None else None,
        processing_job_status=job.status if job is not None else None,
        original_attachment_id=attachment.original_attachment_id,
        created_at=attachment.created_at,
        reused=reused,
    )


def _owned_attachment(
    attachment_id: str,
    user_id: str,
    database: Session,
) -> Attachment:
    attachment = database.scalar(
        select(Attachment).where(
            Attachment.id == attachment_id,
            Attachment.user_id == user_id,
        )
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="첨부 파일을 찾을 수 없습니다.")
    return attachment


@router.post("/preflight")
def preflight_attachments(
    request: AttachmentPreflightRequest,
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
) -> dict[str, list[AttachmentPreflightItem]]:
    """클라이언트 해시를 사용자 소유 파일과 비교해 업로드 전에 중복을 알려준다."""

    results: list[AttachmentPreflightItem] = []
    for descriptor in request.items:
        exact = database.scalar(
            select(Attachment).where(
                Attachment.user_id == current_user.id,
                Attachment.content_hash == descriptor.content_hash.lower(),
            )
        )
        if exact is not None:
            results.append(AttachmentPreflightItem(
                client_id=descriptor.client_id,
                status="exact_duplicate",
                existing_attachment=_attachment_response(exact, database, reused=True),
            ))
            continue

        same_name = database.scalar(
            select(Attachment)
            .where(
                Attachment.user_id == current_user.id,
                Attachment.normalized_filename
                == normalized_filename(descriptor.filename),
            )
            .order_by(Attachment.created_at.desc())
        )
        results.append(AttachmentPreflightItem(
            client_id=descriptor.client_id,
            status=(
                "same_name_different_content"
                if same_name is not None
                else "new_file"
            ),
            existing_attachment=(
                _attachment_response(same_name, database)
                if same_name is not None
                else None
            ),
        ))
    return {"items": results}


@router.post("", response_model=AttachmentResponse, status_code=201)
async def upload_attachment(
    file: UploadFile = File(...),
    content_hash: str = Form(""),
    original_attachment_id: str = Form(""),
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> AttachmentResponse:
    """원본 바이트와 추출 본문을 저장하고 동일 해시는 기존 파일을 재사용한다."""

    content = await file.read(MAX_JOB_FILE_BYTES + 1)
    await file.close()
    if len(content) > MAX_JOB_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"{file.filename or '첨부 파일'}은 파일당 허용 크기를 초과합니다.",
        )

    server_hash = hashlib.sha256(content).hexdigest()
    if content_hash and content_hash.lower() != server_hash:
        raise HTTPException(
            status_code=422,
            detail="브라우저에서 계산한 파일 해시와 서버의 파일 해시가 다릅니다.",
        )

    exact = database.scalar(
        select(Attachment).where(
            Attachment.user_id == current_user.id,
            Attachment.content_hash == server_hash,
        )
    )
    if exact is not None:
        return _attachment_response(exact, database, reused=True)

    filename = (file.filename or "이름 없는 파일").strip()
    mime_type = (file.content_type or "application/octet-stream").lower()
    previous_id = original_attachment_id.strip() or None
    if previous_id is not None:
        _owned_attachment(previous_id, current_user.id, database)
    else:
        same_name = database.scalar(
            select(Attachment)
            .where(
                Attachment.user_id == current_user.id,
                Attachment.normalized_filename == normalized_filename(filename),
            )
            .order_by(Attachment.created_at.desc())
        )
        previous_id = same_name.id if same_name is not None else None

    try:
        ingested = attachment_service.ingest(
            database,
            user_id=current_user.id,
            filename=filename,
            mime_type=mime_type,
            content=content,
            original_attachment_id=previous_id,
        )
    except (FileInputError, BlobStoreError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except IntegrityError:
        database.rollback()
        exact = database.scalar(
            select(Attachment).where(
                Attachment.user_id == current_user.id,
                Attachment.content_hash == server_hash,
            )
        )
        if exact is not None:
            return _attachment_response(exact, database, reused=True)
        raise
    if ingested.job is not None and ingested.job.status == "queued":
        await run_file_extraction(
            attachment_service.process_job,
            database,
            ingested.job.id,
        )
    database.refresh(ingested.attachment)
    return _attachment_response(
        ingested.attachment,
        database,
        reused=ingested.reused,
    )


@router.post("/{attachment_id}/process", response_model=AttachmentResponse)
async def process_attachment(
    attachment_id: str,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> AttachmentResponse:
    """실패·중단된 첨부 원본을 현재 파서 버전으로 다시 처리한다."""

    attachment = _owned_attachment(attachment_id, current_user.id, database)
    job = attachment_service.retry(database, attachment)
    if job.status == "queued":
        await run_file_extraction(
            attachment_service.process_job,
            database,
            job.id,
        )
    database.refresh(attachment)
    return _attachment_response(attachment, database, reused=True)


@router.get("/{attachment_id}", response_model=AttachmentResponse)
def get_attachment(
    attachment_id: str,
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
) -> AttachmentResponse:
    return _attachment_response(
        _owned_attachment(attachment_id, current_user.id, database),
        database,
    )


@router.delete("/{attachment_id}")
def delete_attachment(
    attachment_id: str,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> dict[str, str]:
    attachment = _owned_attachment(attachment_id, current_user.id, database)
    storage_backend = attachment.storage_backend
    storage_key = attachment.storage_key
    database.execute(delete(TranscriptionSegment).where(
        TranscriptionSegment.attachment_id == attachment.id,
    ))
    database.execute(delete(FileProcessingJob).where(
        FileProcessingJob.attachment_id == attachment.id,
    ))
    database.delete(attachment)
    database.commit()
    if storage_backend == "local" and storage_key:
        try:
            attachment_service.delete_blob(attachment)
        except BlobStoreError:
            # DB 삭제는 완료되었으므로 고아 blob 정리는 유지보수 작업에서 재시도한다.
            pass
    return {"deleted_id": attachment_id}


__all__ = ["router"]
