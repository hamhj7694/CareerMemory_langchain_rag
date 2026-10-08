"""격리 DB에서 결정론적 챗봇을 사용하는 Playwright 전용 서버."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from types import SimpleNamespace

from AI_Engine.api.conversations import get_chatbot_ai
from AI_Engine.router import app


class E2EChatbot:
    """외부 모델 비용 없이 실제 SSE·DB 저장 경로를 검증한다."""

    @staticmethod
    def _answer(content: str) -> str:
        if "첨부 문서" in content or "FastAPI" in content:
            return "FastAPI 기반 API의 응답 시간을 50% 줄였습니다."
        return "채팅 응답 정상"

    def invoke(self, request):
        answer = self._answer(request.content)
        return SimpleNamespace(
            message=SimpleNamespace(
                id="MSG-E2E",
                content=answer,
                created_at=datetime.now(timezone.utc),
            ),
            citations=[],
            suggested_actions=[],
        )

    def stream(self, request):
        answer = self._answer(request.content)
        midpoint = max(1, len(answer) // 2)
        yield SimpleNamespace(type="started")
        yield SimpleNamespace(type="token", text_delta=answer[:midpoint])
        yield SimpleNamespace(type="token", text_delta=answer[midpoint:])
        yield SimpleNamespace(type="completed")


if os.getenv("E2E_AI_MODE", "stub").lower() != "live":
    app.dependency_overrides[get_chatbot_ai] = E2EChatbot


__all__ = ["E2EChatbot", "app"]
