"""사용자별 채팅 첨부 파일의 중복 확인·저장·본문 추출 API."""

from __future__ import annotations

import hashlib
import unicodedata
from datetime import datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from AI_Engine.auth.dependencies import get_current_user, require_csrf_user
from AI_Engine.database.connection import get_database_session
from AI_Engine.database.models import Attachment, User
from AI_Engine.experience_file_text import extract_experience_file_texts
from AI_Engine.job_file_text import (
    JobFile,
    JobFileExtractionError,
    JobFileInputError,
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
    items: list[AttachmentDescriptor] = Field(max_length=5)


class AttachmentResponse(BaseModel):
    id: str
    filename: str
    mime_type: str
    size_bytes: int
    content_hash: str
    status: str
    extracted_text_available: bool
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


def _normalized_filename(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _attachment_response(
    attachment: Attachment,
    *,
    reused: bool = False,
) -> AttachmentResponse:
    return AttachmentResponse(
        id=attachment.id,
        filename=attachment.filename,
        mime_type=attachment.mime_type,
        size_bytes=attachment.size_bytes,
        content_hash=attachment.content_hash,
        status=attachment.parse_status,
        extracted_text_available=bool(attachment.extracted_text.strip()),
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
                existing_attachment=_attachment_response(exact, reused=True),
            ))
            continue

        same_name = database.scalar(
            select(Attachment)
            .where(
                Attachment.user_id == current_user.id,
                Attachment.normalized_filename
                == _normalized_filename(descriptor.filename),
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
                _attachment_response(same_name)
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
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
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
        return _attachment_response(exact, reused=True)

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
                Attachment.normalized_filename == _normalized_filename(filename),
            )
            .order_by(Attachment.created_at.desc())
        )
        previous_id = same_name.id if same_name is not None else None

    try:
        extracted = extract_experience_file_texts([
            JobFile(filename=filename, mime_type=mime_type, content=content)
        ])[0]
    except (JobFileInputError, JobFileExtractionError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    attachment = Attachment(
        id=f"ATT-{uuid4()}",
        user_id=current_user.id,
        filename=filename,
        normalized_filename=_normalized_filename(filename),
        mime_type=mime_type,
        size_bytes=len(content),
        content_hash=server_hash,
        content=content,
        extracted_text=extracted.text,
        parse_status="ready",
        original_attachment_id=previous_id,
    )
    database.add(attachment)
    try:
        database.commit()
    except IntegrityError:
        database.rollback()
        exact = database.scalar(
            select(Attachment).where(
                Attachment.user_id == current_user.id,
                Attachment.content_hash == server_hash,
            )
        )
        if exact is not None:
            return _attachment_response(exact, reused=True)
        raise
    database.refresh(attachment)
    return _attachment_response(attachment)


@router.get("/{attachment_id}", response_model=AttachmentResponse)
def get_attachment(
    attachment_id: str,
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
) -> AttachmentResponse:
    return _attachment_response(
        _owned_attachment(attachment_id, current_user.id, database)
    )


@router.delete("/{attachment_id}")
def delete_attachment(
    attachment_id: str,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> dict[str, str]:
    attachment = _owned_attachment(attachment_id, current_user.id, database)
    database.delete(attachment)
    database.commit()
    return {"deleted_id": attachment_id}


__all__ = ["router"]
