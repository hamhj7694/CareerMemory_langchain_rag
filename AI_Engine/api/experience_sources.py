"""원본 근거 편집과 현재 근거 기반 경험 재정리 API."""

from __future__ import annotations

from copy import deepcopy
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from AI_Engine.api.experience_extractions import (
    _json_payload,
    _persist_extraction_result,
    get_experience_ai,
)
from AI_Engine.api.experiences import experience_dict, owned_experience
from AI_Engine.auth.dependencies import get_current_user, require_csrf_user
from AI_Engine.blob_store import read_attachment_bytes
from AI_Engine.database.connection import get_database_session
from AI_Engine.database.models import (
    Attachment,
    Conversation,
    Experience,
    Message,
    User,
    utc_now,
)
from AI_Engine.evidence_repository import sync_experience_evidence
from AI_Engine.knowledge_documents import (
    begin_analysis_run,
    content_document_dict,
    experience_content_blocks,
    fail_analysis_run,
    upsert_content_document,
)
from AI_Engine.experience_ai import (
    ExperienceAI,
    ExperienceAIInputError,
    ExperienceAIOutputError,
)
from AI_Engine.schemas import (
    EvidenceSource,
    EvidenceSourceType,
    ExperienceExtractionInputType,
    ExperienceExtractionRequest,
)


router = APIRouter(prefix="/api/v2", tags=["experience-sources"])


class TextSourceCreate(BaseModel):
    title: str = Field(default="", max_length=200)
    text: str = Field(min_length=1)
    client_request_id: str


class FileSourcesAttach(BaseModel):
    attachment_ids: list[str] = Field(min_length=1, max_length=10)
    client_request_id: str


class TextSourceUpdate(BaseModel):
    changes: dict
    client_request_id: str


class SourceMutation(BaseModel):
    client_request_id: str


def _source_id(source: object) -> str:
    if isinstance(source, str):
        return source
    if isinstance(source, dict):
        return str(
            source.get("id")
            or source.get("source_id")
            or source.get("sourceId")
            or ""
        )
    return ""


def _source_refs(experience: Experience) -> list[dict]:
    refs: list[dict] = []
    by_id: set[str] = set()
    for source in experience.source_refs or []:
        normalized = {"id": source} if isinstance(source, str) else deepcopy(source)
        source_id = _source_id(normalized)
        if not source_id or source_id in by_id:
            continue
        normalized["id"] = source_id
        refs.append(normalized)
        by_id.add(source_id)
    for source_id in experience.source_ids or []:
        if source_id not in by_id:
            refs.append({
                "id": source_id,
                "type": "unknown",
                "title": "원본 정보 없음",
                "unavailable": True,
            })
            by_id.add(source_id)
    return refs


def _source_payload(experience: Experience) -> dict:
    return {
        "experience_id": experience.id,
        "sources": _source_refs(experience),
    }


def _find_source(experience: Experience, source_id: str) -> dict:
    source = next(
        (item for item in _source_refs(experience) if _source_id(item) == source_id),
        None,
    )
    if source is None:
        raise HTTPException(
            status_code=404,
            detail="현재 경험에 연결된 원본 근거를 찾을 수 없습니다.",
        )
    return source


def _owned_attachment(
    attachment_id: str,
    user_id: str,
    database: Session,
) -> Attachment:
    attachment = database.scalar(select(Attachment).where(
        Attachment.id == attachment_id,
        Attachment.user_id == user_id,
    ))
    if attachment is None:
        raise HTTPException(status_code=404, detail="첨부 파일을 찾을 수 없습니다.")
    return attachment


def _attachment_id(source: dict) -> str:
    direct = str(
        source.get("attachment_id")
        or source.get("attachmentId")
        or ""
    ).strip()
    if direct:
        return direct
    source_id = _source_id(source)
    if source_id.startswith("source-ATT-"):
        return source_id.removeprefix("source-")
    if source_id.startswith("ATT-"):
        return source_id
    return ""


def _touch_sources(experience: Experience, refs: list[dict]) -> None:
    experience.source_refs = refs
    experience.source_ids = [_source_id(source) for source in refs]
    experience.version += 1
    experience.updated_at = utc_now()


def _invalidate_source_claims(
    experience: Experience,
    source_id: str,
    *,
    remove_citations: bool,
) -> list[str]:
    """원문 변경·연결 해제가 영향을 준 사실을 stale/needs_evidence로 표시한다."""

    field_citations = deepcopy(experience.field_citations or {})
    statuses = dict(experience.fact_evidence_status or {})
    unsupported: list[str] = []
    for index, fact in enumerate(experience.facts or []):
        key = f"facts.{index}"
        citations = [
            citation for citation in field_citations.get(key, [])
            if isinstance(citation, dict)
        ]
        references_source = any(
            str(citation.get("source_ref_id") or citation.get("sourceRefId") or "")
            == source_id
            for citation in citations
        )
        if not references_source:
            statuses.setdefault(fact, "supported" if citations else "needs_evidence")
            continue
        if remove_citations:
            citations = [
                citation for citation in citations
                if str(citation.get("source_ref_id") or citation.get("sourceRefId") or "")
                != source_id
            ]
            if citations:
                field_citations[key] = citations
            else:
                field_citations.pop(key, None)
            statuses[fact] = "supported" if citations else "needs_evidence"
            if not citations:
                unsupported.append(fact)
        else:
            statuses[fact] = "stale"
            unsupported.append(fact)
    experience.field_citations = field_citations
    experience.fact_evidence_status = statuses
    return unsupported


def _sync_content_document(database: Session, experience: Experience) -> None:
    existing = (
        content_document_dict(experience.content_document) or {"blocks": []}
    )["blocks"]
    custom = [
        block for block in existing
        if block.get("origin") != "system_projection"
    ]
    document = upsert_content_document(
        database,
        user_id=experience.user_id,
        owner_type="experience",
        owner_id=experience.id,
        title=experience.title,
        blocks=experience_content_blocks({
            "summary": experience.summary,
            "situation": experience.situation,
            "actions": experience.actions,
            "results": experience.results,
            "role": experience.role,
            "skills": experience.skills,
            "skill_mentions": experience.skill_mentions,
            "skill_groups": experience.skill_groups,
            "facts": experience.facts,
            "fact_evidence_status": experience.fact_evidence_status,
            "metrics": experience.metrics,
            "period": experience.period,
            "missing_information": experience.missing_information,
            "field_citations": experience.field_citations,
            "confidence": experience.confidence,
            "extensions": experience.extensions,
        }) + custom,
        extensions=experience.extensions,
        document_id=experience.content_document_id,
    )
    experience.content_document_id = document.id


def _ai_source(
    source: dict,
    *,
    user_id: str,
    database: Session,
) -> EvidenceSource:
    source_id = _source_id(source)
    raw_type = str(
        source.get("type")
        or source.get("source_type")
        or source.get("sourceType")
        or ""
    )
    title = str(source.get("title") or source.get("filename") or "").strip()
    text = str(
        source.get("text")
        or source.get("original_text")
        or source.get("originalText")
        or ""
    )

    attachment_id = _attachment_id(source)
    if raw_type == EvidenceSourceType.FILE.value or attachment_id:
        if not attachment_id:
            raise HTTPException(
                status_code=422,
                detail=f"파일 근거의 원본 첨부 정보를 찾을 수 없습니다: {source_id}",
            )
        attachment = _owned_attachment(attachment_id, user_id, database)
        return EvidenceSource(
            id=source_id,
            type=EvidenceSourceType.FILE,
            title=title or attachment.filename,
            attachment_id=attachment.id,
            filename=attachment.filename,
            mime_type=attachment.mime_type,
            uploaded_at=attachment.created_at,
            content_hash=attachment.content_hash,
            text=attachment.extracted_text,
        )

    if raw_type in {
        EvidenceSourceType.MESSAGE_TEXT.value,
        "conversation",
        "conversation_message",
        "message",
    }:
        message_id = str(
            source.get("message_id")
            or source.get("messageId")
            or source_id.removeprefix("source-")
        )
        if not text.strip():
            message = database.scalar(
                select(Message)
                .join(
                    Conversation,
                    Conversation.id == Message.conversation_id,
                )
                .where(
                    Message.id == message_id,
                    Conversation.user_id == user_id,
                )
            )
            text = message.content if message is not None else ""
        if not text.strip():
            raise HTTPException(
                status_code=422,
                detail=f"대화 근거의 원문을 찾을 수 없습니다: {source_id}",
            )
        return EvidenceSource(
            id=source_id,
            type=EvidenceSourceType.MESSAGE_TEXT,
            title=title or "대화 원문",
            message_id=message_id,
            text=text,
        )

    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail=f"분석할 수 있는 원문이 없는 근거입니다: {source_id}",
        )
    manual_input_id = str(
        source.get("manual_input_id")
        or source.get("manualInputId")
        or source_id.removeprefix("source-")
    )
    return EvidenceSource(
        id=source_id,
        type=EvidenceSourceType.MANUAL_TEXT,
        title=title or "사용자 직접 입력",
        manual_input_id=manual_input_id,
        text=text,
    )


@router.post("/experiences/{experience_id}/sources/text", status_code=201)
def add_text_source(
    experience_id: str,
    request: TextSourceCreate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> dict:
    experience = owned_experience(experience_id, current_user.id, database)
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="원본 텍스트를 입력해 주세요.")
    manual_input_id = f"MANUAL-{uuid4()}"
    source = {
        "id": f"source-{manual_input_id}",
        "type": EvidenceSourceType.MANUAL_TEXT.value,
        "title": request.title.strip() or "사용자 직접 입력",
        "manual_input_id": manual_input_id,
        "text": text,
        "created_at": utc_now().isoformat(),
    }
    refs = _source_refs(experience)
    refs.append(source)
    _touch_sources(experience, refs)
    _sync_content_document(database, experience)
    sync_experience_evidence(database, experience)
    database.commit()
    return {
        **_source_payload(experience),
        "experience": experience_dict(experience),
        "added_source_ids": [source["id"]],
    }


@router.post("/experiences/{experience_id}/sources/files")
def attach_file_sources(
    experience_id: str,
    request: FileSourcesAttach,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> dict:
    experience = owned_experience(experience_id, current_user.id, database)
    refs = _source_refs(experience)
    existing_attachment_ids = {
        _attachment_id(source) for source in refs if _attachment_id(source)
    }
    added_source_ids: list[str] = []
    for attachment_id in dict.fromkeys(request.attachment_ids):
        attachment = _owned_attachment(attachment_id, current_user.id, database)
        if attachment.id in existing_attachment_ids:
            continue
        source_id = f"source-{attachment.id}"
        refs.append({
            "id": source_id,
            "type": EvidenceSourceType.FILE.value,
            "title": attachment.filename,
            "attachment_id": attachment.id,
            "filename": attachment.filename,
            "mime_type": attachment.mime_type,
            "size_bytes": attachment.size_bytes,
            "uploaded_at": attachment.created_at.isoformat(),
            "content_hash": attachment.content_hash,
        })
        existing_attachment_ids.add(attachment.id)
        added_source_ids.append(source_id)
    if added_source_ids:
        _touch_sources(experience, refs)
        sync_experience_evidence(database, experience)
        database.commit()
    return {
        **_source_payload(experience),
        "experience": experience_dict(experience),
        "added_source_ids": added_source_ids,
    }


@router.patch("/experiences/{experience_id}/sources/{source_id}")
def update_text_source(
    experience_id: str,
    source_id: str,
    request: TextSourceUpdate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> dict:
    experience = owned_experience(experience_id, current_user.id, database)
    refs = _source_refs(experience)
    source = next(
        (item for item in refs if _source_id(item) == source_id),
        None,
    )
    if source is None:
        raise HTTPException(status_code=404, detail="수정할 원본 근거를 찾을 수 없습니다.")
    if _attachment_id(source) or str(source.get("type")) == "message_text":
        raise HTTPException(
            status_code=422,
            detail="직접 작성한 텍스트 근거만 수정할 수 있습니다.",
        )
    text = str(request.changes.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="원본 텍스트를 입력해 주세요.")
    source["text"] = text
    source["updated_at"] = utc_now().isoformat()
    unsupported_facts = _invalidate_source_claims(
        experience, source_id, remove_citations=False
    )
    _touch_sources(experience, refs)
    _sync_content_document(database, experience)
    sync_experience_evidence(database, experience)
    database.commit()
    return {
        **source,
        "experiences": [experience_dict(experience)],
        "unsupported_facts": unsupported_facts,
    }


@router.delete("/experiences/{experience_id}/sources/{source_id}")
def unlink_source(
    experience_id: str,
    source_id: str,
    _request: SourceMutation,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> dict:
    experience = owned_experience(experience_id, current_user.id, database)
    refs = _source_refs(experience)
    remaining = [
        source for source in refs if _source_id(source) != source_id
    ]
    if len(remaining) == len(refs):
        raise HTTPException(
            status_code=404,
            detail="현재 경험에 연결된 원본 근거가 아닙니다.",
        )
    unsupported_facts = _invalidate_source_claims(
        experience, source_id, remove_citations=True
    )
    _touch_sources(experience, remaining)
    _sync_content_document(database, experience)
    sync_experience_evidence(database, experience)
    database.commit()
    return {
        **_source_payload(experience),
        "experience": experience_dict(experience),
        "unlinked_source_id": source_id,
        "source_deleted": False,
        "unsupported_facts": unsupported_facts,
    }


@router.get("/experiences/{experience_id}/sources/{source_id}/download")
def download_source(
    experience_id: str,
    source_id: str,
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
) -> Response:
    experience = owned_experience(experience_id, current_user.id, database)
    source = _find_source(experience, source_id)
    attachment_id = _attachment_id(source)
    if not attachment_id:
        raise HTTPException(status_code=422, detail="파일 근거가 아닙니다.")
    attachment = _owned_attachment(attachment_id, current_user.id, database)
    encoded_filename = quote(attachment.filename)
    return Response(
        content=read_attachment_bytes(attachment),
        media_type=attachment.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{encoded_filename}"
            )
        },
    )


@router.post("/experiences/{experience_id}/reorganize-from-sources")
def reorganize_from_sources(
    experience_id: str,
    request: SourceMutation,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
    experience_ai: ExperienceAI = Depends(get_experience_ai),
) -> dict:
    source_experience = owned_experience(
        experience_id,
        current_user.id,
        database,
    )
    refs = _source_refs(source_experience)
    if not refs:
        raise HTTPException(status_code=422, detail="다시 정리할 원본 근거가 없습니다.")
    sources = [
        _ai_source(source, user_id=current_user.id, database=database)
        for source in refs
    ]
    extraction_request = ExperienceExtractionRequest(
        client_request_id=request.client_request_id,
        input_type=ExperienceExtractionInputType.EVIDENCE_REORGANIZATION,
        source_ref_ids=[source.id for source in sources],
        attachment_ids=[
            source.attachment_id for source in sources if source.attachment_id
        ],
    )
    analysis_record = begin_analysis_run(
        database,
        user_id=current_user.id,
        client_request_id=request.client_request_id,
        target_type="experience_reorganization",
        input_type=str(ExperienceExtractionInputType.EVIDENCE_REORGANIZATION.value),
        input_payload={
            **extraction_request.model_dump(mode="json"),
            "source_experience_id": source_experience.id,
            "sources": refs,
        },
        source_ids=[source.id for source in sources],
    )
    try:
        result = experience_ai.organize(extraction_request, sources=sources)
        result = _persist_extraction_result(database, analysis_record, result)
    except ExperienceAIInputError as error:
        fail_analysis_run(database, analysis_record, code="invalid_input", message=str(error))
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ExperienceAIOutputError as error:
        fail_analysis_run(database, analysis_record, code="invalid_ai_output", message=str(error))
        raise HTTPException(
            status_code=502,
            detail="현재 근거로 경험 상세내용을 다시 정리하지 못했습니다.",
        ) from error
    if not result.experience_drafts:
        raise HTTPException(
            status_code=422,
            detail="현재 근거에서 정리할 경험 내용을 찾지 못했습니다.",
        )

    title_base = source_experience.title.strip() or "제목 없는 경험"
    while title_base.endswith(" - 새 정리본"):
        title_base = title_base.removesuffix(" - 새 정리본").rstrip()
    created_items: list[Experience] = []
    for index, draft in enumerate(result.experience_drafts):
        draft_payload = _json_payload(draft)
        project_payload = draft_payload.get("project") or {}
        project_period = project_payload.get("period") or deepcopy(source_experience.period)
        field_citations = dict(draft_payload.get("field_citations") or {})
        facts = list(draft_payload.get("facts") or [])
        draft_title = str(draft_payload.get("title") or "").strip()
        title = (
            f"{title_base} - 새 정리본"
            if len(result.experience_drafts) == 1
            else draft_title or f"{title_base} - 새 정리본 {index + 1}"
        )
        extensions = {
            "reorganized_from_experience_id": source_experience.id,
            "ai_domain": draft_payload.get("domain") or {},
            "ai_project": project_payload,
        }
        created = Experience(
            id=f"EXP-{uuid4()}",
            user_id=current_user.id,
            project_id=source_experience.project_id,
            title=title,
            summary=str(draft_payload.get("summary") or ""),
            situation=str(draft_payload.get("situation") or ""),
            actions=list(draft_payload.get("actions") or []),
            results=list(draft_payload.get("results") or []),
            role=str(draft_payload.get("role") or ""),
            skills=list(draft_payload.get("skills") or []),
            skill_mentions=list(draft_payload.get("skill_mentions") or []),
            skill_groups=list(draft_payload.get("skill_groups") or []),
            facts=facts,
            fact_evidence_status={
                fact: (
                    "supported" if field_citations.get(f"facts.{fact_index}")
                    else "needs_evidence"
                )
                for fact_index, fact in enumerate(facts)
            },
            metrics=list(draft_payload.get("metrics") or []),
            period=project_period or {},
            missing_information=list(draft_payload.get("missing_information") or []),
            source_ids=[_source_id(source) for source in refs],
            source_refs=refs,
            draft_id=draft_payload.get("draft_id"),
            field_citations=field_citations,
            confidence=draft_payload.get("confidence"),
            extensions=extensions,
            analysis_run_id=analysis_record.id,
            status="confirmed",
        )
        created.project = source_experience.project
        database.add(created)
        database.flush()
        document = upsert_content_document(
            database,
            user_id=current_user.id,
            owner_type="experience",
            owner_id=created.id,
            title=created.title,
            blocks=experience_content_blocks({
                **draft_payload,
                "fact_evidence_status": created.fact_evidence_status,
                "extensions": extensions,
            }),
            extensions=extensions,
        )
        created.content_document_id = document.id
        sync_experience_evidence(database, created)
        created_items.append(created)
    analysis_record.target_id = created_items[0].id
    database.commit()
    for created in created_items:
        database.refresh(created)
    return {
        "experience": experience_dict(created_items[0]),
        "experiences": [experience_dict(item) for item in created_items],
        "source_experience_id": source_experience.id,
        "sources": refs,
        "extraction_run": _json_payload(result.run),
    }


__all__ = ["router"]
