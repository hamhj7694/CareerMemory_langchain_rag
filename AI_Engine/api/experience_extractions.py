"""직접 입력한 원문을 경험 초안으로 구조화하는 API."""

from __future__ import annotations

from functools import lru_cache
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from AI_Engine.attachment_service import attachment_service
from AI_Engine.auth.dependencies import require_csrf_user
from AI_Engine.blob_store import BlobStoreError
from AI_Engine.database.connection import get_database_session
from AI_Engine.database.models import Attachment, User
from AI_Engine.file_extraction import FileInputError, run_file_extraction
from AI_Engine.experience_ai import (
    ExperienceAI,
    ExperienceAIInputError,
    ExperienceAIOutputError,
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


__all__ = ["get_experience_ai", "router"]
