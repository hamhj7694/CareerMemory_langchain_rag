"""직접 입력한 원문을 경험 초안으로 구조화하는 API."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status

from AI_Engine.auth.dependencies import require_csrf_user
from AI_Engine.database.models import User
from AI_Engine.experience_ai import (
    ExperienceAI,
    ExperienceAIInputError,
    ExperienceAIOutputError,
)
from AI_Engine.schemas import (
    ExperienceExtractionInputType,
    ExperienceExtractionRequest,
    ExperienceExtractionResult,
)


router = APIRouter(
    prefix="/api/v2/experience-extractions",
    tags=["experience-extractions"],
)


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
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI가 만든 경험 초안 형식을 확인하지 못했습니다. 다시 시도해 주세요.",
        ) from error


__all__ = ["get_experience_ai", "router"]
