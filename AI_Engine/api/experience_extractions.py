"""직접 입력한 원문을 경험 초안으로 구조화하는 API."""

from __future__ import annotations

from functools import lru_cache
from copy import deepcopy
from hashlib import sha256
import logging
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from AI_Engine.attachment_service import attachment_service
from AI_Engine.auth.dependencies import get_current_user, require_csrf_user
from AI_Engine.privacy import guest_private_mode, redact_guest_text, redact_source_texts
from AI_Engine.blob_store import BlobStoreError
from AI_Engine.database.connection import get_database_session
from AI_Engine.database.models import (
    AnalysisRunRecord,
    Attachment,
    ExperienceProject,
    User,
    utc_now,
)
from AI_Engine.file_extraction import FileInputError, run_file_extraction
from AI_Engine.experience_ai import (
    ExperienceAI,
    ExperienceAIInputError,
    ExperienceAIOutputError,
)
from AI_Engine.experience_units import (
    EXPERIENCE_UNITS_SEGMENTER_VERSION,
    build_experience_units_proposal,
    organize_segmented_sources,
    recalculate_proposal_coverage,
    segment_sources,
    source_manifest,
    validate_proposal_invariants,
)
from AI_Engine.experience_unit_storage import (
    annotate_proposal_matches,
    save_experience_unit,
)
from AI_Engine.job_file_text import (
    MAX_JOB_FILE_BYTES,
    MAX_JOB_FILE_COUNT,
    MAX_JOB_FILES_TOTAL_BYTES,
)
from AI_Engine.knowledge_documents import (
    begin_analysis_run,
    complete_analysis_run,
    fail_analysis_run,
)
from AI_Engine.schemas import (
    EvidenceSource,
    EvidenceSourceType,
    ExperienceExtractionInputType,
    ExperienceExtractionRequest,
    ExperienceExtractionResult,
)
from AI_Engine.web_content import (
    WebContentError,
    merge_attachment_ids,
    web_content_service,
)


router = APIRouter(
    prefix="/api/v2/experience-extractions",
    tags=["experience-extractions"],
)
logger = logging.getLogger(__name__)


class DirectUnitsProposalUpdate(BaseModel):
    version: int = Field(ge=1)
    units: list[dict]
    coverage: dict
    status: Literal["edited", "rejected"] = "edited"


class DirectUnitApprove(BaseModel):
    version: int = Field(ge=1)
    unit_id: str = Field(min_length=1, max_length=100)


def _json_payload(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _json_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_payload(item) for item in value]
    if hasattr(value, "__dict__"):
        return {
            key: _json_payload(item)
            for key, item in vars(value).items()
            if not callable(item)
        }
    return value


def _run_value(run, key: str, default=""):
    if isinstance(run, dict):
        return run.get(key, default)
    return getattr(run, key, default)


def _persist_extraction_result(database: Session, analysis_record, result):
    result_payload = _json_payload(result)
    run = result.run
    run_status = _run_value(run, "status", "succeeded")
    sources = list(getattr(result, "sources", []) or [])
    drafts = list(getattr(result, "experience_drafts", []) or [])
    source_ids = [
        source.get("id") if isinstance(source, dict) else source.id
        for source in sources
    ]
    analyzed_ids = list(getattr(result, "analyzed_source_ids", source_ids) or [])
    complete_analysis_run(
        database,
        analysis_record,
        status=getattr(run_status, "value", run_status),
        output_payload=result_payload,
        external_run_id=_run_value(run, "id") or None,
        versions={
            "model": _run_value(run, "model_version"),
            "prompt": _run_value(run, "prompt_version"),
            "schema": _run_value(run, "schema_version"),
        },
        coverage_report={
            "source_count": len(source_ids),
            "analyzed_source_count": len(analyzed_ids),
            "draft_count": len(drafts),
            "rejected_draft_count": getattr(result, "rejected_draft_count", 0),
            "unprocessed_source_ids": [
                source_id for source_id in source_ids if source_id not in analyzed_ids
            ],
        },
        omitted_source_ids=[
            source_id for source_id in source_ids if source_id not in analyzed_ids
        ],
    )
    if hasattr(result, "model_copy"):
        return result.model_copy(update={"analysis_record_id": analysis_record.id})
    setattr(result, "analysis_record_id", analysis_record.id)
    return result


def _attachment_sources(
    database: Session,
    *,
    user_id: str,
    attachment_ids: list[str],
) -> list[EvidenceSource]:
    if not attachment_ids:
        return []
    attachments = list(database.scalars(select(Attachment).where(
        Attachment.user_id == user_id,
        Attachment.id.in_(attachment_ids),
    )))
    by_id = {attachment.id: attachment for attachment in attachments}
    if any(attachment_id not in by_id for attachment_id in attachment_ids):
        raise FileInputError("열 수 없는 첨부 파일이 포함되어 있습니다.")
    sources: list[EvidenceSource] = []
    for attachment_id in attachment_ids:
        attachment = by_id[attachment_id]
        if attachment.parse_status not in {"ready", "partial"}:
            raise FileInputError(
                f"{attachment.filename}: 파일 처리가 완료되지 않았습니다."
            )
        sources.append(EvidenceSource(
            id=f"source-{attachment.id}",
            type=EvidenceSourceType.FILE,
            title=attachment.filename,
            attachment_id=attachment.id,
            filename=attachment.filename,
            mime_type=attachment.mime_type,
            content_hash=attachment.content_hash,
            text=attachment.extracted_text,
        ))
    return sources


def _manual_source(request: ExperienceExtractionRequest) -> EvidenceSource | None:
    if not request.text:
        return None
    manual_input_id = request.manual_input_id or request.client_request_id
    return EvidenceSource(
        id=f"source-{manual_input_id}",
        type=EvidenceSourceType.MANUAL_TEXT,
        title="사용자 직접 입력",
        manual_input_id=manual_input_id,
        text=request.text,
    )


def _store_direct_units_proposal(
    database: Session,
    analysis_record: AnalysisRunRecord,
    proposal: dict,
) -> None:
    coverage = proposal.get("coverage") or {}
    analysis_record.output_payload = {
        **(analysis_record.output_payload or {}),
        "proposal": proposal,
        "unit_ids": [unit["unit_id"] for unit in proposal.get("units", [])],
    }
    analysis_record.coverage_report = coverage
    analysis_record.versions = {
        **(analysis_record.versions or {}),
        "contract": "experience-units-v2",
        "segmenter": EXPERIENCE_UNITS_SEGMENTER_VERSION,
    }
    if coverage.get("processing_status") == "partial":
        analysis_record.status = "partial"
    analysis_record.updated_at = utc_now()
    database.commit()


def _apply_preferred_structure(
    database: Session,
    proposal: dict,
    *,
    request: ExperienceExtractionRequest,
    user_id: str,
) -> dict:
    if not request.preferred_project_id:
        return proposal
    project = database.scalar(
        select(ExperienceProject)
        .options(selectinload(ExperienceProject.domain))
        .where(
            ExperienceProject.id == request.preferred_project_id,
            ExperienceProject.user_id == user_id,
            ExperienceProject.deleted_at.is_(None),
        )
    )
    if project is None or (
        request.preferred_domain_id
        and project.domain_id != request.preferred_domain_id
    ):
        raise ExperienceAIInputError("선택한 경험 분류·프로젝트를 찾을 수 없습니다.")
    result = deepcopy(proposal)
    for unit in result.get("units", []):
        unit["project_id"] = project.id
        unit["domain"] = {"id": project.domain.id, "name": project.domain.name}
        unit["project"] = {
            "id": project.id,
            "name": project.name,
            "organization": project.organization,
        }
    return result


def _analyze_direct_units(
    database: Session,
    *,
    request: ExperienceExtractionRequest,
    sources: list[EvidenceSource],
    current_user: User,
    experience_ai: ExperienceAI,
) -> dict:
    original_sources = list(sources)
    manual = _manual_source(request)
    if manual is not None:
        original_sources.insert(0, manual)
    original_sources = redact_source_texts(
        original_sources,
        guest=guest_private_mode(current_user),
    )
    if not original_sources:
        raise ExperienceAIInputError("분석 가능한 원본 텍스트가 없습니다.")
    segmented = segment_sources(
        original_sources,
        privacy_policy="guest_redacted" if guest_private_mode(current_user) else "registered_full",
    )
    analysis_record = begin_analysis_run(
        database,
        user_id=current_user.id,
        client_request_id=request.client_request_id,
        target_type="experience_extraction",
        input_type=str(ExperienceExtractionInputType.DIRECT_INPUT.value),
        input_payload={
            **request.model_dump(mode="json"),
            "source_manifest": source_manifest(segmented),
            "segmenter_version": EXPERIENCE_UNITS_SEGMENTER_VERSION,
        },
        source_ids=[source.id for source in original_sources],
    )
    stored_payload = analysis_record.output_payload or {}
    stored_proposal = stored_payload.get("proposal")
    if (
        analysis_record.status in {"succeeded", "partial"}
        and isinstance(stored_proposal, dict)
        and stored_proposal.get("contract_version") == "experience-units-v2"
    ):
        # client_request_id is the idempotency key. A browser retry must replay
        # the durable proposal instead of spending another model call or
        # replacing edits/approvals already made against this analysis run.
        return {
            **deepcopy(stored_payload),
            "analysis_record_id": analysis_record.id,
            "proposal": deepcopy(stored_proposal),
        }
    try:
        result = organize_segmented_sources(experience_ai, request, segmented)
        result = _persist_extraction_result(database, analysis_record, result)
        proposal = build_experience_units_proposal(
            result, segmented, analysis_run_id=analysis_record.id,
        )
        proposal = _apply_preferred_structure(
            database, proposal, request=request, user_id=current_user.id,
        )
        proposal = annotate_proposal_matches(
            database, proposal, user_id=current_user.id,
        )
        _store_direct_units_proposal(database, analysis_record, proposal)
        payload = _json_payload(result)
        payload["analysis_record_id"] = analysis_record.id
        payload["proposal"] = proposal
        return payload
    except ExperienceAIInputError as error:
        fail_analysis_run(database, analysis_record, code="invalid_input", message=str(error))
        raise
    except ExperienceAIOutputError as error:
        fail_analysis_run(database, analysis_record, code="invalid_ai_output", message=str(error))
        raise


def _direct_run_or_404(
    database: Session,
    *,
    analysis_run_id: str,
    user_id: str,
) -> AnalysisRunRecord:
    item = database.scalar(select(AnalysisRunRecord).where(
        AnalysisRunRecord.id == analysis_run_id,
        AnalysisRunRecord.user_id == user_id,
        AnalysisRunRecord.target_type == "experience_extraction",
    ))
    if item is None or not isinstance((item.output_payload or {}).get("proposal"), dict):
        raise HTTPException(status_code=404, detail="경험 단위 분석 결과를 찾을 수 없습니다.")
    return item


def _direct_source_text(
    database: Session,
    *,
    analysis_record: AnalysisRunRecord,
    snapshot: dict,
    current_user: User,
) -> str:
    attachment_id = snapshot.get("attachment_id")
    if attachment_id:
        attachment = database.get(Attachment, attachment_id)
        if attachment is None or attachment.user_id != current_user.id:
            raise HTTPException(status_code=422, detail="원문 첨부 연결이 유효하지 않습니다.")
        value = attachment.extracted_text
    elif snapshot.get("manual_input_id"):
        value = str((analysis_record.input_payload or {}).get("text") or "")
    else:
        raise HTTPException(status_code=422, detail="직접 입력 원문 연결이 유효하지 않습니다.")
    return redact_guest_text(value) if guest_private_mode(current_user) else value


def _hydrate_direct_source_refs(
    database: Session,
    *,
    analysis_record: AnalysisRunRecord,
    unit: dict,
    current_user: User,
) -> list[dict]:
    snapshots = {
        snapshot.get("source_id"): snapshot
        for snapshot in (analysis_record.output_payload or {}).get("proposal", {}).get("source_snapshots", [])
    }
    values: list[dict] = []
    for source in unit.get("source_refs") or []:
        item = dict(source)
        snapshot = snapshots.get(item.get("id")) or {}
        item["text"] = _direct_source_text(
            database, analysis_record=analysis_record,
            snapshot={**snapshot, **item}, current_user=current_user,
        )
        item["type"] = "file" if item.get("attachment_id") else "manual_text"
        values.append(item)
    return values


@lru_cache(maxsize=1)
def get_experience_ai() -> ExperienceAI:
    """환경 변수로 선택한 Gemini 또는 OpenAI 경험정리 AI를 재사용한다."""

    return ExperienceAI()


@router.post(
    "/direct-input",
    response_model=ExperienceExtractionResult,
)
def extract_direct_input(
    request: ExperienceExtractionRequest,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
    experience_ai: ExperienceAI = Depends(get_experience_ai),
) -> ExperienceExtractionResult:
    """사용자가 직접 작성한 텍스트를 검토 가능한 경험 초안으로 변환한다."""

    if request.input_type != ExperienceExtractionInputType.DIRECT_INPUT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="직접 입력 경험정리는 input_type이 direct_input이어야 합니다.",
        )
    if guest_private_mode(current_user):
        request = request.model_copy(update={
            "text": redact_guest_text(request.text),
        })
    analysis_record = begin_analysis_run(
        database,
        user_id=current_user.id,
        client_request_id=request.client_request_id,
        target_type="experience_extraction",
        input_type=str(request.input_type),
        input_payload=request.model_dump(mode="json"),
        source_ids=request.attachment_ids,
    )
    try:
        web_sources = web_content_service.ingest(
            database,
            user_id=current_user.id,
            texts=(request.text,),
            existing_attachment_ids=request.attachment_ids,
        )
        resolved_request = request.model_copy(update={
            "attachment_ids": merge_attachment_ids(
                request.attachment_ids,
                web_sources.attachment_ids,
            ),
        })
        analysis_record.input_payload = resolved_request.model_dump(mode="json")
        analysis_record.source_ids = resolved_request.attachment_ids
        database.commit()
        sources = _attachment_sources(
            database,
            user_id=current_user.id,
            attachment_ids=resolved_request.attachment_ids,
        )
        sources = redact_source_texts(sources, guest=guest_private_mode(current_user))
        result = experience_ai.organize(resolved_request, sources=sources)
        return _persist_extraction_result(database, analysis_record, result)
    except (FileInputError, WebContentError, ExperienceAIInputError) as error:
        fail_analysis_run(
            database, analysis_record, code="invalid_input", message=str(error)
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except ExperienceAIOutputError as error:
        fail_analysis_run(
            database, analysis_record, code="invalid_ai_output", message=str(error)
        )
        # 사용자에게는 내부 스키마를 노출하지 않되, 개발 중에는 어떤 필드가
        # 잘못되었는지 서버 로그에서 바로 확인할 수 있게 원인을 남긴다.
        logger.exception("경험정리 AI 구조화 출력 검증 실패")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI가 만든 경험 초안 형식을 확인하지 못했습니다. 다시 시도해 주세요.",
        ) from error


@router.post(
    "/direct-input-files",
    response_model=ExperienceExtractionResult,
)
async def extract_direct_input_files(
    client_request_id: str = Form(...),
    text: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
    experience_ai: ExperienceAI = Depends(get_experience_ai),
) -> ExperienceExtractionResult:
    """직접 입력과 첨부 파일 원문을 한 번의 경험 분석 근거로 묶는다."""

    if guest_private_mode(current_user):
        text = redact_guest_text(text)
    if len(files) > MAX_JOB_FILE_COUNT:
        raise HTTPException(status_code=422, detail=f"파일은 최대 {MAX_JOB_FILE_COUNT}개까지 선택할 수 있습니다.")
    uploaded_files: list[tuple[str, str, bytes]] = []
    total_bytes = 0
    for uploaded in files:
        content = await uploaded.read(MAX_JOB_FILE_BYTES + 1)
        await uploaded.close()
        total_bytes += len(content)
        uploaded_files.append((
            uploaded.filename or "이름 없는 파일",
            (uploaded.content_type or "").lower(),
            content,
        ))
    if total_bytes > MAX_JOB_FILES_TOTAL_BYTES:
        raise HTTPException(status_code=413, detail="첨부 파일 전체 크기가 허용 범위를 초과합니다.")

    analysis_record = begin_analysis_run(
        database,
        user_id=current_user.id,
        client_request_id=client_request_id,
        target_type="experience_extraction",
        input_type=str(ExperienceExtractionInputType.DIRECT_INPUT.value),
        input_payload={
            "client_request_id": client_request_id,
            "input_type": ExperienceExtractionInputType.DIRECT_INPUT.value,
            "text": text,
            "files": [
                {"filename": filename, "mime_type": mime_type, "size_bytes": len(content)}
                for filename, mime_type, content in uploaded_files
            ],
        },
    )
    try:
        attachment_ids: list[str] = []
        for filename, mime_type, content in uploaded_files:
            ingested = attachment_service.ingest(
                database,
                user_id=current_user.id,
                filename=filename,
                mime_type=mime_type,
                content=content,
            )
            if ingested.job is not None and ingested.job.status == "queued":
                await run_file_extraction(
                    attachment_service.process_job,
                    database,
                    ingested.job.id,
                )
            database.refresh(ingested.attachment)
            if ingested.attachment.parse_status not in {"ready", "partial"}:
                raise FileInputError(
                    ingested.attachment.parse_error
                    or f"{filename}: 파일 처리에 실패했습니다."
                )
            attachment_ids.append(ingested.attachment.id)
        web_sources = web_content_service.ingest(
            database,
            user_id=current_user.id,
            texts=(text,),
            existing_attachment_ids=attachment_ids,
        )
        attachment_ids = merge_attachment_ids(
            attachment_ids,
            web_sources.attachment_ids,
        )
        sources = _attachment_sources(
            database,
            user_id=current_user.id,
            attachment_ids=attachment_ids,
        )
        sources = redact_source_texts(sources, guest=guest_private_mode(current_user))
        request = ExperienceExtractionRequest(
            client_request_id=client_request_id,
            input_type=ExperienceExtractionInputType.DIRECT_INPUT,
            text=text.strip() or None,
            attachment_ids=attachment_ids,
        )
        analysis_record.input_payload = request.model_dump(mode="json")
        analysis_record.source_ids = attachment_ids
        database.commit()
        result = experience_ai.organize(request, sources=sources)
        return _persist_extraction_result(database, analysis_record, result)
    except (
        FileInputError,
        BlobStoreError,
        WebContentError,
        ValueError,
        ExperienceAIInputError,
    ) as error:
        if "analysis_record" in locals():
            fail_analysis_run(
                database, analysis_record, code="invalid_input", message=str(error)
            )
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ExperienceAIOutputError as error:
        if "analysis_record" in locals():
            fail_analysis_run(
                database, analysis_record, code="invalid_ai_output", message=str(error)
            )
        logger.exception("파일 포함 경험정리 AI 구조화 출력 검증 실패")
        raise HTTPException(
            status_code=502,
            detail="AI가 만든 경험 초안 형식을 확인하지 못했습니다. 다시 시도해 주세요.",
        ) from error


@router.post("/direct-input-v2")
def extract_direct_input_v2(
    request: ExperienceExtractionRequest,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
    experience_ai: ExperienceAI = Depends(get_experience_ai),
):
    """Analyze direct text with the same lossless V2 unit contract as chat."""

    if request.input_type != ExperienceExtractionInputType.DIRECT_INPUT:
        raise HTTPException(status_code=422, detail="직접 입력은 input_type이 direct_input이어야 합니다.")
    if guest_private_mode(current_user):
        request = request.model_copy(update={"text": redact_guest_text(request.text)})
    try:
        web_sources = web_content_service.ingest(
            database,
            user_id=current_user.id,
            texts=(request.text,),
            existing_attachment_ids=request.attachment_ids,
        )
        resolved_request = request.model_copy(update={
            "manual_input_id": request.manual_input_id or request.client_request_id,
            "attachment_ids": merge_attachment_ids(
                request.attachment_ids, web_sources.attachment_ids,
            ),
        })
        sources = _attachment_sources(
            database,
            user_id=current_user.id,
            attachment_ids=resolved_request.attachment_ids,
        )
        return _analyze_direct_units(
            database, request=resolved_request, sources=sources,
            current_user=current_user, experience_ai=experience_ai,
        )
    except (FileInputError, WebContentError, ExperienceAIInputError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ExperienceAIOutputError as error:
        logger.exception("V2 경험정리 AI 구조화 출력 검증 실패")
        raise HTTPException(
            status_code=502,
            detail="AI가 만든 경험 단위 형식을 확인하지 못했습니다. 다시 시도해 주세요.",
        ) from error


@router.post("/direct-input-files-v2")
async def extract_direct_input_files_v2(
    client_request_id: str = Form(...),
    text: str = Form(""),
    preferred_domain_id: str | None = Form(None),
    preferred_project_id: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
    experience_ai: ExperienceAI = Depends(get_experience_ai),
):
    """Analyze direct text and files through lossless V2 segmentation and batching."""

    if guest_private_mode(current_user):
        text = redact_guest_text(text)
    if len(files) > MAX_JOB_FILE_COUNT:
        raise HTTPException(status_code=422, detail=f"파일은 최대 {MAX_JOB_FILE_COUNT}개까지 선택할 수 있습니다.")
    uploaded_files: list[tuple[str, str, bytes]] = []
    total_bytes = 0
    for uploaded in files:
        content = await uploaded.read(MAX_JOB_FILE_BYTES + 1)
        await uploaded.close()
        total_bytes += len(content)
        uploaded_files.append((
            uploaded.filename or "이름 없는 파일",
            (uploaded.content_type or "").lower(),
            content,
        ))
    if total_bytes > MAX_JOB_FILES_TOTAL_BYTES:
        raise HTTPException(status_code=413, detail="첨부 파일 전체 크기가 허용 범위를 초과합니다.")
    try:
        attachment_ids: list[str] = []
        for filename, mime_type, content in uploaded_files:
            ingested = attachment_service.ingest(
                database,
                user_id=current_user.id,
                filename=filename,
                mime_type=mime_type,
                content=content,
            )
            if ingested.job is not None and ingested.job.status == "queued":
                await run_file_extraction(
                    attachment_service.process_job,
                    database,
                    ingested.job.id,
                )
            database.refresh(ingested.attachment)
            if ingested.attachment.parse_status not in {"ready", "partial"}:
                raise FileInputError(
                    ingested.attachment.parse_error or f"{filename}: 파일 처리에 실패했습니다."
                )
            attachment_ids.append(ingested.attachment.id)
        web_sources = web_content_service.ingest(
            database,
            user_id=current_user.id,
            texts=(text,),
            existing_attachment_ids=attachment_ids,
        )
        attachment_ids = merge_attachment_ids(attachment_ids, web_sources.attachment_ids)
        request = ExperienceExtractionRequest(
            client_request_id=client_request_id,
            input_type=ExperienceExtractionInputType.DIRECT_INPUT,
            text=text.strip() or None,
            manual_input_id=client_request_id,
            attachment_ids=attachment_ids,
            preferred_domain_id=preferred_domain_id,
            preferred_project_id=preferred_project_id,
        )
        sources = _attachment_sources(
            database, user_id=current_user.id, attachment_ids=attachment_ids,
        )
        return _analyze_direct_units(
            database, request=request, sources=sources,
            current_user=current_user, experience_ai=experience_ai,
        )
    except (
        FileInputError, BlobStoreError, WebContentError, ValueError,
        ExperienceAIInputError,
    ) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ExperienceAIOutputError as error:
        logger.exception("파일 포함 V2 경험정리 AI 구조화 출력 검증 실패")
        raise HTTPException(
            status_code=502,
            detail="AI가 만든 경험 단위 형식을 확인하지 못했습니다. 다시 시도해 주세요.",
        ) from error


@router.patch("/{analysis_run_id}/experience-units-proposal")
def update_direct_units_proposal(
    analysis_run_id: str,
    request: DirectUnitsProposalUpdate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    item = _direct_run_or_404(
        database, analysis_run_id=analysis_run_id, user_id=current_user.id,
    )
    current = item.output_payload["proposal"]
    if current.get("version") != request.version:
        raise HTTPException(status_code=409, detail="경험 제안이 변경되었습니다. 새로고침해 주세요.")
    current_by_id = {unit.get("unit_id"): unit for unit in current.get("units", [])}
    for unit in request.units:
        stored = current_by_id.get(unit.get("unit_id"))
        if stored is None:
            raise HTTPException(status_code=422, detail="새 경험 단위 ID를 임의로 추가할 수 없습니다.")
        for key in (
            "analysis_run_id", "source_ref_ids", "source_refs", "primary_span_ids",
            "context_span_ids", "field_span_ids", "saved_experience_id", "saved_at",
            "fact_ids",
        ):
            if unit.get(key) != stored.get(key):
                raise HTTPException(status_code=422, detail=f"{key} 추적 정보는 수정할 수 없습니다.")
    incoming_ids = {unit.get("unit_id") for unit in request.units}
    if any(
        unit.get("saved_experience_id") and unit.get("unit_id") not in incoming_ids
        for unit in current.get("units", [])
    ):
        raise HTTPException(status_code=409, detail="이미 저장된 경험 단위는 삭제할 수 없습니다.")
    proposal = {
        **current,
        "version": request.version + 1,
        "units": request.units,
        "coverage": recalculate_proposal_coverage({
            **current, "units": request.units, "coverage": request.coverage,
        }),
        "status": request.status,
    }
    proposal = annotate_proposal_matches(
        database, proposal, user_id=current_user.id,
    )
    for updated in proposal.get("units", []):
        stored = current_by_id.get(updated.get("unit_id")) or {}
        if stored.get("saved_experience_id"):
            updated["save_strategy"] = stored.get("save_strategy", {"operation": "create"})
    validate_proposal_invariants(proposal)
    _store_direct_units_proposal(database, item, proposal)
    return {"proposal": proposal}


@router.get("/{analysis_run_id}/experience-units-proposal/spans")
def get_direct_unit_spans(
    analysis_run_id: str,
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
):
    item = _direct_run_or_404(
        database, analysis_run_id=analysis_run_id, user_id=current_user.id,
    )
    proposal = item.output_payload["proposal"]
    span_status = (proposal.get("coverage") or {}).get("span_status") or {}
    values: list[dict] = []
    for snapshot in proposal.get("source_snapshots") or []:
        source_text = _direct_source_text(
            database, analysis_record=item,
            snapshot=snapshot, current_user=current_user,
        )
        if snapshot.get("text_hash") and sha256(source_text.encode("utf-8")).hexdigest() != snapshot["text_hash"]:
            raise HTTPException(status_code=409, detail="원문이 분석 이후 변경되어 근거 구간을 표시할 수 없습니다.")
        for span in snapshot.get("spans") or []:
            start = int(span.get("char_start") or 0)
            end = int(span.get("char_end") or start)
            values.append({
                "id": span.get("id"), "source_id": snapshot.get("source_id"),
                "source_title": snapshot.get("title") or "원문",
                "category": span_status.get(span.get("id"), span.get("category")),
                "char_start": start, "char_end": end,
                "text": source_text[start:end],
            })
    return {"items": values, "total_count": len(values)}


@router.post("/{analysis_run_id}/experience-units-proposal/approve")
def approve_direct_experience_unit(
    analysis_run_id: str,
    request: DirectUnitApprove,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    item = _direct_run_or_404(
        database, analysis_run_id=analysis_run_id, user_id=current_user.id,
    )
    current = item.output_payload["proposal"]
    validate_proposal_invariants(current)
    unit = next(
        (value for value in current.get("units", []) if value.get("unit_id") == request.unit_id),
        None,
    )
    if unit is None:
        raise HTTPException(status_code=404, detail="저장할 경험 단위를 찾을 수 없습니다.")
    if unit.get("saved_experience_id"):
        return {
            "proposal": current,
            "created": {"experience_id": unit["saved_experience_id"]},
            "operation": unit.get("save_operation") or "replayed",
            "replayed": True,
        }
    if current.get("version") != request.version:
        raise HTTPException(status_code=409, detail="경험 제안이 변경되었습니다. 새로고침해 주세요.")
    source_refs = _hydrate_direct_source_refs(
        database, analysis_record=item, unit=unit, current_user=current_user,
    )
    experience, operation = save_experience_unit(
        database, unit=unit, source_refs=source_refs, current_user=current_user,
    )
    units = deepcopy(current.get("units", []))
    saved_unit = next(value for value in units if value.get("unit_id") == request.unit_id)
    saved_unit.update({
        "saved_experience_id": experience.id,
        "saved_at": utc_now().isoformat(),
        "save_operation": operation,
        "status": "approved",
    })
    all_approved = all(value.get("saved_experience_id") for value in units)
    proposal = {
        **current,
        "version": request.version + 1,
        "units": units,
        "status": "approved" if all_approved else "edited",
        "coverage": {
            **current.get("coverage", {}),
            "review_status": "approved" if all_approved else "partial",
        },
    }
    _store_direct_units_proposal(database, item, proposal)
    return {
        "proposal": proposal,
        "created": {"experience_id": experience.id},
        "operation": operation,
        "replayed": False,
    }


__all__ = [
    "approve_direct_experience_unit",
    "get_experience_ai",
    "get_direct_unit_spans",
    "router",
    "update_direct_units_proposal",
]
