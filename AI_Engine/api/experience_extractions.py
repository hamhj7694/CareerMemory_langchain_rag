"""직접 입력한 원문을 경험 초안으로 구조화하는 API."""

from __future__ import annotations

from functools import lru_cache
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from AI_Engine.auth.dependencies import require_csrf_user
from AI_Engine.database.models import User
from AI_Engine.experience_file_text import extract_experience_file_texts
from AI_Engine.experience_ai import (
    ExperienceAI,
    ExperienceAIInputError,
    ExperienceAIOutputError,
)
from AI_Engine.job_file_text import (
    JobFile,
    JobFileExtractionError,
    JobFileInputError,
    MAX_JOB_FILE_BYTES,
)
from AI_Engine.schemas import (
    EvidenceSource,
    EvidenceSourceType,
    ExperienceExtractionInputType,
    ExperienceExtractionRequest,
    ExperienceExtractionResult,
)


router = APIRouter(
    prefix="/api/v2/experience-extractions",
    tags=["experience-extractions"],
)
logger = logging.getLogger(__name__)


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
    _current_user: User = Depends(require_csrf_user),
    experience_ai: ExperienceAI = Depends(get_experience_ai),
) -> ExperienceExtractionResult:
    """사용자가 직접 작성한 텍스트를 검토 가능한 경험 초안으로 변환한다."""

    if request.input_type != ExperienceExtractionInputType.DIRECT_INPUT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="직접 입력 경험정리는 input_type이 direct_input이어야 합니다.",
        )
    if request.attachment_ids:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="파일을 이용한 경험 정리는 아직 제공되지 않아요!",
        )

    try:
        return experience_ai.organize(request)
    except ExperienceAIInputError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except ExperienceAIOutputError as error:
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
    _current_user: User = Depends(require_csrf_user),
    experience_ai: ExperienceAI = Depends(get_experience_ai),
) -> ExperienceExtractionResult:
    """직접 입력과 첨부 파일 원문을 한 번의 경험 분석 근거로 묶는다."""

    uploaded_files: list[JobFile] = []
    for uploaded in files:
        content = await uploaded.read(MAX_JOB_FILE_BYTES + 1)
        uploaded_files.append(JobFile(
            filename=uploaded.filename or "이름 없는 파일",
            mime_type=(uploaded.content_type or "").lower(),
            content=content,
        ))
        await uploaded.close()

    try:
        extracted_files = extract_experience_file_texts(uploaded_files)
        sources: list[EvidenceSource] = []
        attachment_ids: list[str] = []
        for extracted in extracted_files:
            attachment_id = f"experience-attachment-{uuid4()}"
            attachment_ids.append(attachment_id)
            sources.append(EvidenceSource(
                id=f"source-{attachment_id}",
                type=EvidenceSourceType.FILE,
                title=extracted.filename,
                attachment_id=attachment_id,
                filename=extracted.filename,
                mime_type=extracted.mime_type,
                text=extracted.text,
            ))
        request = ExperienceExtractionRequest(
            client_request_id=client_request_id,
            input_type=ExperienceExtractionInputType.DIRECT_INPUT,
            text=text.strip() or None,
            attachment_ids=attachment_ids,
        )
        return experience_ai.organize(request, sources=sources)
    except (JobFileInputError, ValueError, ExperienceAIInputError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except JobFileExtractionError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error
    except ExperienceAIOutputError as error:
        logger.exception("파일 포함 경험정리 AI 구조화 출력 검증 실패")
        raise HTTPException(
            status_code=502,
            detail="AI가 만든 경험 초안 형식을 확인하지 못했습니다. 다시 시도해 주세요.",
        ) from error


__all__ = ["get_experience_ai", "router"]
