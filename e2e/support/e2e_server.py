"""격리 DB에서 결정론적 챗봇을 사용하는 Playwright 전용 서버."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from AI_Engine.api.conversation_jobs import get_conversation_job_discovery_ai
from AI_Engine.api.conversations import get_chatbot_ai
from AI_Engine.api.experience_extractions import get_experience_ai
from AI_Engine.router import app
from AI_Engine.schemas import (
    EvidenceCitation,
    ExperienceClassificationDraft,
    ExperienceDraft,
    ExperienceExtractionResult,
    ExtractionRun,
    ExtractionRunStatus,
    ProjectActivityDraft,
)


class E2EChatbot:
    """외부 모델 비용 없이 실제 SSE·DB 저장 경로를 검증한다."""

    @staticmethod
    def _answer(content: str) -> str:
        if "안녕 나는 함" in content and "형준이야." in content:
            return "통합 프롬프트 확인: 안녕 나는 함형준이야."
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
        if "안녕 나는 함" in request.content and "형준이야." not in request.content:
            # Keep the first response in-flight long enough for Playwright to
            # deterministically submit the follow-up and exercise cancellation.
            time.sleep(3)
        yield SimpleNamespace(type="token", text_delta=answer[midpoint:])
        yield SimpleNamespace(type="completed")


class E2EExperienceAI:
    """Return a cited draft so browser tests exercise the real analysis API and DB."""

    model_version = "e2e-stub"

    def organize(self, request, *, sources, **_kwargs):
        matching = [source for source in sources if source.text and "E2E 경험 분석" in source.text]
        drafts = []
        stress_matching = [
            source
            for source in sources
            if source.text and "E2E 혼합 스트레스" in source.text and "[경험]" in source.text
        ]
        for source in stress_matching:
            quote = next(
                line.strip().removeprefix("- ")
                for line in source.text.splitlines()
                if "[경험]" in line
            )
            drafts.append(ExperienceDraft(
                draft_id=f"DRAFT-E2E-STRESS-{uuid4()}",
                domain=ExperienceClassificationDraft(name="개발 경험"),
                project=ProjectActivityDraft(name="혼합 입력 검증"),
                title=quote,
                summary=quote,
                actions=[quote],
                results=[],
                facts=[],
                source_ref_ids=[source.id],
                field_citations={"actions.0": [EvidenceCitation(
                    source_ref_id=source.id,
                    quote=quote,
                )]},
            ))
        if matching:
            quote = "처리 시간을 20% 줄였습니다."
            source = next(
                (item for item in matching if quote in (item.text or "")),
                matching[0],
            )
            drafts.append(ExperienceDraft(
                draft_id=f"DRAFT-E2E-{uuid4()}",
                domain=ExperienceClassificationDraft(name="개인 프로젝트"),
                project=ProjectActivityDraft(name="Career Memory"),
                title="FastAPI 처리 시간 개선",
                summary="FastAPI API를 구현하고 처리 시간을 20% 줄였습니다.",
                actions=["FastAPI API를 구현했습니다."],
                results=[quote],
                facts=[quote],
                source_ref_ids=[item.id for item in matching],
                field_citations={"facts.0": [EvidenceCitation(source_ref_id=source.id, quote=quote)]},
            ))
        return ExperienceExtractionResult(
            run=ExtractionRun(
                id=f"EXTRACT-E2E-{uuid4()}",
                client_request_id=request.client_request_id,
                input_type=request.input_type,
                status=ExtractionRunStatus.SUCCEEDED,
                conversation_id=request.conversation_id,
                model_version=self.model_version,
                prompt_version="e2e-prompt",
                schema_version="e2e-schema",
            ),
            experience_drafts=drafts,
            sources=sources,
            analyzed_source_ids=[source.id for source in sources],
        )


if os.getenv("E2E_AI_MODE", "stub").lower() != "live":
    app.dependency_overrides[get_chatbot_ai] = E2EChatbot
    app.dependency_overrides[get_conversation_job_discovery_ai] = lambda: SimpleNamespace(
        discover=lambda _sources: [], model_version="e2e-stub"
    )
    app.dependency_overrides[get_experience_ai] = E2EExperienceAI


__all__ = ["E2EChatbot", "app"]
