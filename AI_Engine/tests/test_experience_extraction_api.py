"""직접 입력 경험정리 API 계약 테스트."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from AI_Engine.api.experience_extractions import get_experience_ai
from AI_Engine.auth.dependencies import require_csrf_user
from AI_Engine.router import app
from AI_Engine.schemas import (
    EvidenceSource,
    ExperienceClassificationDraft,
    ExperienceDraft,
    ExperienceExtractionResult,
    ExtractionRun,
    ProjectActivityDraft,
)


class FakeExperienceAI:
    """외부 모델 호출 없이 하나의 검증된 경험 초안을 반환한다."""

    def __init__(self) -> None:
        self.requests = []

    def organize(self, request):
        self.requests.append(request)
        source_id = f"source-{request.manual_input_id}"
        now = datetime.now(timezone.utc)
        return ExperienceExtractionResult(
            run=ExtractionRun(
                id="RUN-test",
                client_request_id=request.client_request_id,
                input_type="direct_input",
                status="succeeded",
                model_version="fake-model",
                prompt_version="test-prompt",
                schema_version="test-schema",
                started_at=now,
                completed_at=now,
            ),
            experience_drafts=[
                ExperienceDraft(
                    draft_id="DRAFT-test",
                    domain=ExperienceClassificationDraft(name="직장 경험"),
                    project=ProjectActivityDraft(name="서비스 개선"),
                    title="전환율 개선",
                    summary="사용자 전환율을 개선한 경험",
                    source_ref_ids=[source_id],
                )
            ],
            sources=[
                EvidenceSource(
                    id=source_id,
                    type="manual_text",
                    title="사용자 직접 입력",
                    manual_input_id=request.manual_input_id,
                    text=request.text,
                )
            ],
            analyzed_source_ids=[source_id],
        )


class ExperienceExtractionApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fake_ai = FakeExperienceAI()
        app.dependency_overrides[get_experience_ai] = lambda: cls.fake_ai
        app.dependency_overrides[require_csrf_user] = lambda: SimpleNamespace(
            id="USER-test"
        )
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.pop(get_experience_ai, None)
        app.dependency_overrides.pop(require_csrf_user, None)

    def setUp(self) -> None:
        self.fake_ai.requests.clear()

    def test_direct_text_returns_experience_draft(self) -> None:
        request_id = str(uuid4())
        response = self.client.post(
            "/api/v2/experience-extractions/direct-input",
            json={
                "client_request_id": request_id,
                "input_type": "direct_input",
                "manual_input_id": "MANUAL-test",
                "text": "사용자 전환율을 개선했습니다.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["experience_drafts"][0]["title"],
            "전환율 개선",
        )
        self.assertEqual(len(self.fake_ai.requests), 1)

    def test_file_input_is_rejected_until_parser_is_connected(self) -> None:
        response = self.client.post(
            "/api/v2/experience-extractions/direct-input",
            json={
                "client_request_id": str(uuid4()),
                "input_type": "direct_input",
                "attachment_ids": ["ATT-test"],
            },
        )

        self.assertEqual(response.status_code, 501)
        self.assertEqual(
            response.json()["error"]["message"],
            "파일을 이용한 경험 정리는 아직 제공되지 않아요!",
        )


if __name__ == "__main__":
    unittest.main()
