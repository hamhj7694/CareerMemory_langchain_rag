"""Career Memory 프론트엔드의 요청을 받는 FastAPI 서버 진입점."""

from __future__ import annotations

# 1. Python 서버 수명주기
# 서버가 시작할 때 DB 테이블을 준비하기 위해 비동기 context manager를 사용한다.
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

# 2. FastAPI 서버 기능
# FastAPI는 HTTP API를 만들고, CORSMiddleware는 브라우저의 로컬 개발 요청을 허용한다.
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from AI_Engine.api import (
    attachments_router,
    conversations_router,
    conversation_experiences_router,
    experience_extractions_router,
    experiences_router,
    experience_draft_trash_router,
    jobs_router,
)
from AI_Engine.auth import router as auth_router
from AI_Engine.api.errors import register_error_handlers
from AI_Engine.database import initialize_database


# 3. 로컬 개발 주소
# Vite 개발 서버는 기본적으로 5173 포트를 사용한다.
# localhost와 127.0.0.1은 브라우저에서 서로 다른 출처로 취급되므로 둘 다 허용한다.
LOCAL_FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


# 4. 서버 상태 응답 스키마
# 상태 확인 API의 반환 형태를 고정하면 프론트엔드와 테스트가 같은 필드를 사용할 수 있다.
class HealthResponse(BaseModel):
    status: str
    service: str


# 5. 서버 시작과 종료 처리
# 시작 시 SQLAlchemy 모델에 정의된 테이블이 없으면 생성한다.
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    initialize_database()
    yield


# 6. FastAPI 애플리케이션 생성
# 이 app 객체가 Uvicorn에서 실행할 실제 백엔드 서버다.
app = FastAPI(
    title="Career Memory AI API",
    version="0.1.0",
    description="Career Memory 프론트엔드와 AI 엔진을 연결하는 API",
    lifespan=lifespan,
)


# 7. 개발용 CORS 설정
# 프론트엔드와 백엔드의 포트가 다르므로 브라우저 요청을 명시적으로 허용해야 한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=LOCAL_FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 공개 API 오류를 프론트엔드 AppError 형식으로 통일한다.
register_error_handlers(app)


# 8. 기능별 API 라우터 연결
# 대화 관련 주소를 별도 파일에 두어 서버 진입점이 지나치게 커지지 않게 한다.
app.include_router(conversations_router)
app.include_router(attachments_router)
app.include_router(conversation_experiences_router)
app.include_router(experience_extractions_router)
app.include_router(experiences_router)
app.include_router(experience_draft_trash_router)
app.include_router(jobs_router)
app.include_router(auth_router)


# 9. 서버 상태 확인 API
# AI 모델을 호출하지 않고 Python 백엔드가 정상 실행 중인지 빠르게 확인한다.
@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["server"],
)
def get_health() -> HealthResponse:
    """백엔드 서버가 요청을 받을 수 있으면 정상 상태를 반환한다."""

    return HealthResponse(
        status="ok",
        service="career-memory-ai-api",
    )


__all__ = [
    "HealthResponse",
    "LOCAL_FRONTEND_ORIGINS",
    "app",
    "get_health",
    "lifespan",
]
