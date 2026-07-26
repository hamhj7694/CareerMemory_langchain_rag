"""삭제되었거나 저장에 실패한 경험 초안의 사용자별 쓰레기통 API."""

from __future__ import annotations

import json
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from AI_Engine.auth.dependencies import get_current_user, require_csrf_user
from AI_Engine.database.connection import get_database_session
from AI_Engine.database.models import (
    ExperienceDraftTrash,
    ExperienceDraftTrashFile,
    User,
    utc_now,
)
from AI_Engine.job_file_text import (
    MAX_JOB_FILE_BYTES,
    MAX_JOB_FILE_COUNT,
    MAX_JOB_FILES_TOTAL_BYTES,
)


router = APIRouter(prefix="/api/v2/experience-draft-trash", tags=["experience-draft-trash"])


class TrashDraftCreate(BaseModel):
    status: Literal["deleted", "failed"]
    reason: str = ""
    draft: dict[str, Any] = Field(default_factory=dict)
    original_text: str = ""


class TrashDraftUpdate(BaseModel):
    draft: dict[str, Any]


class TrashDraftDelete(BaseModel):
    confirm: bool = False


def trash_id() -> str:
    return f"TRASH-{uuid4()}"


def item_dict(item: ExperienceDraftTrash) -> dict[str, Any]:
    return {
        "id": item.id,
        "status": item.status,
        "title": item.title,
        "reason": item.reason,
        "draft": item.draft,
        "original_text": item.original_text,
        "files": [
            {
                "id": file.id,
                "filename": file.filename,
                "mime_type": file.mime_type,
                "size_bytes": file.size_bytes,
            }
            for file in item.files
        ],
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def owned_item(item_id: str, user_id: str, database: Session) -> ExperienceDraftTrash:
    item = database.scalar(
        select(ExperienceDraftTrash).where(
            ExperienceDraftTrash.id == item_id,
            ExperienceDraftTrash.user_id == user_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="쓰레기통 초안을 찾을 수 없습니다.")
    return item


@router.get("")
def list_trash_drafts(
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
):
    items = list(
        database.scalars(
            select(ExperienceDraftTrash)
            .where(ExperienceDraftTrash.user_id == current_user.id)
            .order_by(ExperienceDraftTrash.created_at.desc())
        )
    )
    return {"items": [item_dict(item) for item in items], "total_count": len(items)}


@router.post("", status_code=201)
def create_trash_draft(
    request: TrashDraftCreate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    title = str(request.draft.get("title") or "").strip()
    if not title:
        title = "분석에 실패한 경험 원문" if request.status == "failed" else "제목 없는 초안"
    item = ExperienceDraftTrash(
        id=trash_id(),
        user_id=current_user.id,
        status=request.status,
        title=title,
        reason=request.reason.strip(),
        draft=request.draft,
        original_text=request.original_text,
    )
    database.add(item)
    database.commit()
    database.refresh(item)
    return item_dict(item)


@router.post("/with-files", status_code=201)
async def create_trash_draft_with_files(
    status_value: Literal["deleted", "failed"] = Form(alias="status"),
    reason: str = Form(""),
    draft_json: str = Form("{}"),
    original_text: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    """분석 실패 원문과 첨부파일을 함께 보관한다."""

    if len(files) > MAX_JOB_FILE_COUNT:
        raise HTTPException(status_code=422, detail=f"파일은 최대 {MAX_JOB_FILE_COUNT}개까지 보관할 수 있습니다.")
    try:
        draft = json.loads(draft_json)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=422, detail="초안 JSON 형식이 올바르지 않습니다.") from error
    if not isinstance(draft, dict):
        raise HTTPException(status_code=422, detail="초안은 객체 형식이어야 합니다.")

    stored_files: list[tuple[UploadFile, bytes]] = []
    total_bytes = 0
    for uploaded in files:
        content = await uploaded.read(MAX_JOB_FILE_BYTES + 1)
        if len(content) > MAX_JOB_FILE_BYTES:
            raise HTTPException(status_code=422, detail=f"{uploaded.filename} 파일이 10MB를 초과합니다.")
        total_bytes += len(content)
        if total_bytes > MAX_JOB_FILES_TOTAL_BYTES:
            raise HTTPException(status_code=422, detail="파일 전체 크기가 14MB를 초과합니다.")
        stored_files.append((uploaded, content))

    title = str(draft.get("title") or "").strip() or (
        "분석에 실패한 경험 원문" if status_value == "failed" else "제목 없는 초안"
    )
    item = ExperienceDraftTrash(
        id=trash_id(),
        user_id=current_user.id,
        status=status_value,
        title=title,
        reason=reason.strip(),
        draft=draft,
        original_text=original_text,
    )
    database.add(item)
    database.flush()
    for uploaded, content in stored_files:
        database.add(ExperienceDraftTrashFile(
            id=f"TRASH-FILE-{uuid4()}",
            trash_id=item.id,
            filename=uploaded.filename or "이름 없는 파일",
            mime_type=uploaded.content_type or "application/octet-stream",
            size_bytes=len(content),
            content=content,
        ))
        await uploaded.close()
    database.commit()
    database.refresh(item)
    return item_dict(item)


@router.get("/{item_id}/files/{file_id}")
def download_trash_file(
    item_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
):
    """현재 사용자가 보관한 쓰레기통 원본 파일을 다시 내려준다."""

    item = owned_item(item_id, current_user.id, database)
    stored = database.scalar(
        select(ExperienceDraftTrashFile).where(
            ExperienceDraftTrashFile.id == file_id,
            ExperienceDraftTrashFile.trash_id == item.id,
        )
    )
    if stored is None:
        raise HTTPException(status_code=404, detail="보관된 원본 파일을 찾을 수 없습니다.")
    return Response(
        content=stored.content,
        media_type=stored.mime_type,
    )


@router.patch("/{item_id}")
def update_trash_draft(
    item_id: str,
    request: TrashDraftUpdate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    item = owned_item(item_id, current_user.id, database)
    item.draft = request.draft
    item.title = str(request.draft.get("title") or item.title).strip() or item.title
    item.updated_at = utc_now()
    database.commit()
    database.refresh(item)
    return item_dict(item)


@router.delete("/{item_id}")
def permanently_delete_trash_draft(
    item_id: str,
    request: TrashDraftDelete,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    if not request.confirm:
        raise HTTPException(status_code=422, detail="완전 삭제 확인이 필요합니다.")
    item = owned_item(item_id, current_user.id, database)
    database.delete(item)
    database.commit()
    return {"deleted_id": item_id}


__all__ = ["router"]
