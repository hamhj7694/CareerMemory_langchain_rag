"""프론트엔드 공개 API를 기능별로 나누는 FastAPI 라우터 패키지."""

from AI_Engine.api.attachments import router as attachments_router
from AI_Engine.api.conversations import router as conversations_router
from AI_Engine.api.experience_extractions import (
    router as experience_extractions_router,
)
from AI_Engine.api.experiences import router as experiences_router
from AI_Engine.api.experience_sources import router as experience_sources_router
from AI_Engine.api.experience_draft_trash import router as experience_draft_trash_router
from AI_Engine.api.conversation_experiences import router as conversation_experiences_router
from AI_Engine.api.jobs import router as jobs_router

__all__ = [
    "attachments_router",
    "conversations_router",
    "experience_extractions_router",
    "experiences_router",
    "experience_sources_router",
    "experience_draft_trash_router",
    "conversation_experiences_router",
    "jobs_router",
]
