"""무손실 AI 실행 기록과 자유 형식 콘텐츠 블록을 관리한다."""

from __future__ import annotations

from typing import Any, Iterable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from AI_Engine.database.models import (
    AnalysisRunRecord,
    ContentBlock,
    ContentDocument,
    utc_now,
)


CONTENT_SCHEMA_VERSION = "content-blocks-v1"


def resource_id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def begin_analysis_run(
    database: Session,
    *,
    user_id: str,
    client_request_id: str,
    target_type: str,
    input_type: str,
    input_payload: dict[str, Any],
    source_ids: Iterable[str] = (),
) -> AnalysisRunRecord:
    """LLM 호출 전에 원문 입력을 커밋해 브라우저 이탈과 호출 실패에도 남긴다."""

    existing = database.scalar(select(AnalysisRunRecord).where(
        AnalysisRunRecord.user_id == user_id,
        AnalysisRunRecord.client_request_id == client_request_id,
        AnalysisRunRecord.target_type == target_type,
    ))
    if existing is not None:
        return existing
    item = AnalysisRunRecord(
        id=resource_id("ANALYSIS"),
        user_id=user_id,
        client_request_id=client_request_id,
        target_type=target_type,
        input_type=input_type,
        input_payload=input_payload,
        source_ids=list(dict.fromkeys(source_ids)),
        status="processing",
    )
    database.add(item)
    database.commit()
    database.refresh(item)
    return item


def complete_analysis_run(
    database: Session,
    item: AnalysisRunRecord,
    *,
    output_payload: dict[str, Any],
    external_run_id: str | None = None,
    target_id: str | None = None,
    versions: dict[str, Any] | None = None,
    token_usage: dict[str, Any] | None = None,
    coverage_report: dict[str, Any] | None = None,
    omitted_source_ids: Iterable[str] = (),
) -> AnalysisRunRecord:
    item.external_run_id = external_run_id
    item.target_id = target_id or item.target_id
    item.output_payload = output_payload
    item.versions = versions or {}
    item.token_usage = token_usage or {}
    item.coverage_report = coverage_report or {}
    item.omitted_source_ids = list(dict.fromkeys(omitted_source_ids))
    item.status = "succeeded"
    item.error = None
    item.completed_at = utc_now()
    item.updated_at = utc_now()
    database.commit()
    database.refresh(item)
    return item


def fail_analysis_run(
    database: Session,
    item: AnalysisRunRecord,
    *,
    code: str,
    message: str,
) -> None:
    item.status = "failed"
    item.error = {"code": code, "message": message}
    item.completed_at = utc_now()
    item.updated_at = utc_now()
    database.commit()


def analysis_run_dict(item: AnalysisRunRecord | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "id": item.id,
        "external_run_id": item.external_run_id,
        "target_type": item.target_type,
        "target_id": item.target_id,
        "input_type": item.input_type,
        "status": item.status,
        "versions": item.versions,
        "token_usage": item.token_usage,
        "coverage_report": item.coverage_report,
        "omitted_source_ids": item.omitted_source_ids,
        "error": item.error,
        "started_at": item.started_at,
        "completed_at": item.completed_at,
    }


def _citation_list(field_citations: dict[str, Any], key: str) -> list[dict[str, Any]]:
    if not isinstance(field_citations, dict):
        return []
    values: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for field_key, citations in field_citations.items():
        if field_key != key and not str(field_key).startswith(f"{key}."):
            continue
        for citation in citations if isinstance(citations, list) else []:
            if not isinstance(citation, dict):
                continue
            identity = (
                str(citation.get("source_ref_id") or citation.get("sourceRefId") or ""),
                str(citation.get("quote") or ""),
                str(citation.get("locator") or ""),
            )
            if identity in seen:
                continue
            seen.add(identity)
            values.append(citation)
    return values


def experience_content_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """정형 필드를 동일한 데이터의 표시용 projection으로 만든다."""

    field_citations = payload.get("field_citations") or {}
    confidence = payload.get("confidence")
    blocks: list[dict[str, Any]] = []

    def add(block_type: str, key: str, data: dict[str, Any]) -> None:
        if not any(value not in (None, "", [], {}) for value in data.values()):
            return
        blocks.append({
            "id": f"core-{key}",
            "type": block_type,
            "data": data,
            "citations": _citation_list(field_citations, key),
            "origin": "system_projection",
            "review_status": "confirmed",
            "confidence": confidence,
            "visibility": "visible",
            "schema_version": 1,
        })

    add("summary", "summary", {"title": "요약", "text": payload.get("summary", "")})
    add("situation", "situation", {"title": "상황", "text": payload.get("situation", "")})
    add("list", "actions", {"title": "행동", "items": payload.get("actions") or []})
    add("list", "results", {"title": "결과", "items": payload.get("results") or []})
    add("role", "role", {"title": "직군·직업 및 역할", "text": payload.get("role", "")})
    add("skills", "skills", {
        "title": "역량",
        "items": payload.get("skills") or [],
        "mentions": payload.get("skill_mentions") or [],
        "groups": payload.get("skill_groups") or [],
    })
    add("facts", "facts", {
        "title": "근거에서 확인된 내용",
        "items": payload.get("facts") or [],
        "evidence_status": payload.get("fact_evidence_status") or {},
    })
    add("metrics", "metrics", {
        "title": "수치 성과",
        "items": payload.get("metrics") or [],
    })
    add("period", "period", {"title": "기간", "value": payload.get("period") or {}})
    add("callout", "missing_information", {
        "title": "확인이 필요한 정보",
        "items": payload.get("missing_information") or [],
        "tone": "warning",
    })
    add("properties", "extensions", {
        "title": "추가 정보",
        "value": payload.get("extensions") or {},
    })
    return blocks


def job_content_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [{
        "id": "core-posting-content",
        "type": "source_text",
        "data": {"title": "채용공고 원문", "text": payload.get("posting_content", "")},
        "source_refs": [
            {"attachment_id": value}
            for value in payload.get("source_attachment_ids") or []
        ],
        "origin": "user",
        "review_status": "confirmed",
        "visibility": "visible",
        "schema_version": 1,
    }]
    for index, requirement in enumerate(payload.get("requirements") or []):
        if not isinstance(requirement, dict):
            continue
        quote = requirement.get("source_excerpt") or ""
        blocks.append({
            "id": f"core-requirement-{requirement.get('id') or index}",
            "type": "job_requirement",
            "data": requirement,
            "citations": ([{
                "quote": quote,
                "locator": requirement.get("source_locator"),
            }] if quote else []),
            "origin": "llm",
            "review_status": "needs_review" if (
                requirement.get("confidence") is not None
                and float(requirement["confidence"]) < 0.5
            ) else "confirmed",
            "confidence": requirement.get("confidence"),
            "visibility": "visible",
            "schema_version": 1,
        })
    return blocks


def merge_projected_blocks(
    projected: list[dict[str, Any]],
    supplied: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """핵심 projection을 유지하면서 사용자/미래 버전 블록을 덧붙인다."""

    extra = [block for block in (supplied or []) if isinstance(block, dict)]
    if not extra:
        return projected
    if any(block.get("origin") == "system_projection" for block in extra):
        return extra
    return projected + extra


def _normalized_block(value: dict[str, Any], position: int) -> dict[str, Any]:
    known = {
        "id", "type", "block_type", "position", "data", "source_refs",
        "citations", "origin", "review_status", "confidence", "visibility",
        "schema_version",
    }
    data = value.get("data") if isinstance(value.get("data"), dict) else {
        "value": value.get("data")
    }
    extensions = {key: item for key, item in value.items() if key not in known}
    if extensions:
        data = {**data, "extensions": {
            **(data.get("extensions") or {}),
            **extensions,
        }}
    return {
        "id": str(value.get("id") or resource_id("BLOCK")),
        "block_type": str(value.get("type") or value.get("block_type") or "custom"),
        "position": position,
        "data": data,
        "source_refs": list(value.get("source_refs") or []),
        "citations": list(value.get("citations") or []),
        "origin": str(value.get("origin") or "user"),
        "review_status": str(value.get("review_status") or "confirmed"),
        "confidence": value.get("confidence"),
        "visibility": str(value.get("visibility") or "visible"),
        "schema_version": int(value.get("schema_version") or 1),
    }


def upsert_content_document(
    database: Session,
    *,
    user_id: str,
    owner_type: str,
    owner_id: str,
    title: str,
    blocks: list[dict[str, Any]],
    extensions: dict[str, Any] | None = None,
    document_id: str | None = None,
) -> ContentDocument:
    document = None
    if document_id:
        document = database.get(ContentDocument, document_id)
    if document is None:
        document = database.scalar(select(ContentDocument).where(
            ContentDocument.user_id == user_id,
            ContentDocument.owner_type == owner_type,
            ContentDocument.owner_id == owner_id,
        ))
    if document is None:
        document = ContentDocument(
            id=resource_id("DOC"),
            user_id=user_id,
            owner_type=owner_type,
            owner_id=owner_id,
            title=title,
            schema_version=CONTENT_SCHEMA_VERSION,
            extensions=extensions or {},
        )
        database.add(document)
        database.flush()
    else:
        document.title = title
        document.extensions = extensions or {}
        document.version += 1
        document.updated_at = utc_now()
        document.blocks.clear()
        database.flush()

    used_block_ids: set[str] = set()
    for position, value in enumerate(blocks):
        normalized = _normalized_block(value, position)
        block_id = normalized["id"]
        if not block_id.startswith(f"{document.id}:"):
            block_id = f"{document.id}:{block_id}"
        if block_id in used_block_ids:
            block_id = f"{block_id}:{position}"
        used_block_ids.add(block_id)
        document.blocks.append(ContentBlock(
            id=block_id,
            document_id=document.id,
            **{key: item for key, item in normalized.items() if key != "id"},
        ))
    database.flush()
    return document


def content_document_dict(document: ContentDocument | None) -> dict[str, Any] | None:
    if document is None:
        return None
    return {
        "id": document.id,
        "owner_type": document.owner_type,
        "owner_id": document.owner_id,
        "title": document.title,
        "schema_version": document.schema_version,
        "extensions": document.extensions,
        "version": document.version,
        "blocks": [
            {
                "id": block.id,
                "type": block.block_type,
                "position": block.position,
                "data": block.data,
                "source_refs": block.source_refs,
                "citations": block.citations,
                "origin": block.origin,
                "review_status": block.review_status,
                "confidence": block.confidence,
                "visibility": block.visibility,
                "schema_version": block.schema_version,
            }
            for block in document.blocks
        ],
    }


__all__ = [
    "analysis_run_dict",
    "begin_analysis_run",
    "complete_analysis_run",
    "content_document_dict",
    "experience_content_blocks",
    "fail_analysis_run",
    "job_content_blocks",
    "merge_projected_blocks",
    "upsert_content_document",
]
