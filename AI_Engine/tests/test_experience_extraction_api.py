"""직접 입력 경험정리 API 계약 테스트."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
import hashlib
import os
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from AI_Engine.api.experience_extractions import get_experience_ai
from AI_Engine.auth.dependencies import get_current_user, require_csrf_user
from AI_Engine.blob_store import clear_blob_store_cache
from AI_Engine.database import models  # noqa: F401
from AI_Engine.database.connection import Base, get_database_session
from AI_Engine.database.models import Attachment, Experience
from AI_Engine.router import app
from AI_Engine.schemas import (
    EvidenceSource,
    ExperienceClassificationDraft,
    ExperienceDraft,
    ExperienceExtractionResult,
    ExtractionRun,
    ProjectActivityDraft,
)
from AI_Engine.web_content import WebIngestionResult


class FakeExperienceAI:
    """외부 모델 호출 없이 하나의 검증된 경험 초안을 반환한다."""

    def __init__(self) -> None:
        self.requests = []

    def organize(self, request, *, sources=()):
        self.requests.append(request)
        manual_source_id = f"source-{request.manual_input_id or request.client_request_id}"
        registered_sources = list(sources)
        if request.text:
            registered_sources.insert(
                0,
                EvidenceSource(
                    id=manual_source_id,
                    type="manual_text",
                    title="사용자 직접 입력",
                    manual_input_id=request.manual_input_id or request.client_request_id,
                    text=request.text,
                ),
            )
        source_ids = [source.id for source in registered_sources]
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
                    source_ref_ids=source_ids,
                )
            ],
            sources=registered_sources,
            analyzed_source_ids=source_ids,
        )


class ExperienceExtractionApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.attachment_storage = TemporaryDirectory()
        cls.storage_environment = patch.dict(
            os.environ,
            {"ATTACHMENT_STORAGE_ROOT": cls.attachment_storage.name},
        )
        cls.storage_environment.start()
        clear_blob_store_cache()
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.session_factory = sessionmaker(
            bind=cls.engine,
            expire_on_commit=False,
        )
        Base.metadata.create_all(bind=cls.engine)

        def get_test_session():
            database = cls.session_factory()
            try:
                yield database
            finally:
                database.close()

        cls.fake_ai = FakeExperienceAI()
        app.dependency_overrides[get_experience_ai] = lambda: cls.fake_ai
        app.dependency_overrides[get_database_session] = get_test_session
        app.dependency_overrides[require_csrf_user] = lambda: SimpleNamespace(
            id="USER-test"
        )
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id="USER-test"
        )
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.pop(get_experience_ai, None)
        app.dependency_overrides.pop(require_csrf_user, None)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_database_session, None)
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()
        clear_blob_store_cache()
        cls.storage_environment.stop()
        cls.attachment_storage.cleanup()

    def setUp(self) -> None:
        self.fake_ai.requests.clear()
        with self.session_factory() as database:
            for table in reversed(Base.metadata.sorted_tables):
                database.execute(table.delete())
            database.commit()

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

        analysis_record_id = response.json()["analysis_record_id"]
        recoverable = self.client.get(
            "/api/v2/analysis-runs",
            params={"target_type": "experience_extraction", "unclaimed_only": True},
        )
        self.assertEqual(recoverable.status_code, 200)
        self.assertEqual(recoverable.json()["items"][0]["id"], analysis_record_id)
        self.assertEqual(
            recoverable.json()["items"][0]["input_payload"]["text"],
            "사용자 전환율을 개선했습니다.",
        )
        self.assertEqual(
            recoverable.json()["items"][0]["output_payload"]["experience_drafts"][0]["title"],
            "전환율 개선",
        )

        discarded = self.client.post(f"/api/v2/analysis-runs/{analysis_record_id}/discard")
        self.assertEqual(discarded.status_code, 200)
        after_discard = self.client.get(
            "/api/v2/analysis-runs",
            params={"target_type": "experience_extraction", "unclaimed_only": True},
        )
        self.assertEqual(after_discard.json()["items"], [])

    def test_direct_v2_reuses_existing_experience_and_same_unit_contract(self) -> None:
        first = self.client.post(
            "/api/v2/experience-extractions/direct-input-v2",
            json={
                "client_request_id": str(uuid4()),
                "input_type": "direct_input",
                "text": "사용자 전환율을 개선했습니다.",
            },
        )
        self.assertEqual(first.status_code, 200, first.text)
        first_payload = first.json()
        first_proposal = first_payload["proposal"]
        self.assertEqual(first_proposal["contract_version"], "experience-units-v2")
        self.assertEqual(first_proposal["units"][0]["save_strategy"]["operation"], "create")

        spans = self.client.get(
            f"/api/v2/experience-extractions/{first_payload['analysis_record_id']}"
            "/experience-units-proposal/spans"
        )
        self.assertEqual(spans.status_code, 200, spans.text)
        self.assertIn("사용자 전환율", spans.json()["items"][0]["text"])

        first_saved = self.client.post(
            f"/api/v2/experience-extractions/{first_payload['analysis_record_id']}"
            "/experience-units-proposal/approve",
            json={
                "version": first_proposal["version"],
                "unit_id": first_proposal["units"][0]["unit_id"],
            },
        )
        self.assertEqual(first_saved.status_code, 200, first_saved.text)
        self.assertEqual(first_saved.json()["operation"], "created")
        experience_id = first_saved.json()["created"]["experience_id"]

        second = self.client.post(
            "/api/v2/experience-extractions/direct-input-v2",
            json={
                "client_request_id": str(uuid4()),
                "input_type": "direct_input",
                "text": "사용자 전환율을 개선했습니다.",
            },
        )
        self.assertEqual(second.status_code, 200, second.text)
        second_payload = second.json()
        second_proposal = second_payload["proposal"]
        strategy = second_proposal["units"][0]["save_strategy"]
        self.assertEqual(strategy["operation"], "update")
        self.assertEqual(strategy["experience_id"], experience_id)

        second_saved = self.client.post(
            f"/api/v2/experience-extractions/{second_payload['analysis_record_id']}"
            "/experience-units-proposal/approve",
            json={
                "version": second_proposal["version"],
                "unit_id": second_proposal["units"][0]["unit_id"],
            },
        )
        self.assertEqual(second_saved.status_code, 200, second_saved.text)
        self.assertEqual(second_saved.json()["operation"], "updated")
        self.assertEqual(second_saved.json()["created"]["experience_id"], experience_id)
        with self.session_factory() as database:
            self.assertEqual(database.query(Experience).count(), 1)
            stored = database.get(Experience, experience_id)
            self.assertEqual(len(stored.source_ids), 2)

    def test_direct_v2_replays_same_client_request_without_reanalysis(self) -> None:
        request_id = str(uuid4())
        body = {
            "client_request_id": request_id,
            "input_type": "direct_input",
            "text": "같은 요청은 한 번만 분석해야 합니다.",
        }

        first = self.client.post(
            "/api/v2/experience-extractions/direct-input-v2", json=body,
        )
        second = self.client.post(
            "/api/v2/experience-extractions/direct-input-v2", json=body,
        )

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(len(self.fake_ai.requests), 1)
        self.assertEqual(
            second.json()["analysis_record_id"], first.json()["analysis_record_id"],
        )
        self.assertEqual(
            second.json()["proposal"]["units"][0]["unit_id"],
            first.json()["proposal"]["units"][0]["unit_id"],
        )

    def test_partial_draft_result_is_saved_and_remains_reviewable(self) -> None:
        class PartialExperienceAI(FakeExperienceAI):
            def organize(self, request, *, sources=()):
                result = super().organize(request, sources=sources)
                return result.model_copy(update={
                    "run": result.run.model_copy(update={"status": "partial"}),
                    "rejected_draft_count": 1,
                })

        app.dependency_overrides[get_experience_ai] = lambda: PartialExperienceAI()
        try:
            response = self.client.post(
                "/api/v2/experience-extractions/direct-input",
                json={
                    "client_request_id": str(uuid4()),
                    "input_type": "direct_input",
                    "text": "Career Memory에서 RAG를 구현했습니다.",
                },
            )
        finally:
            app.dependency_overrides[get_experience_ai] = lambda: self.fake_ai

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["run"]["status"], "partial")
        self.assertEqual(response.json()["rejected_draft_count"], 1)
        recoverable = self.client.get(
            "/api/v2/analysis-runs",
            params={"target_type": "experience_extraction", "unclaimed_only": True},
        )
        self.assertEqual(recoverable.status_code, 200)
        self.assertEqual(recoverable.json()["items"][0]["status"], "partial")

    def test_saved_attachment_is_used_as_experience_evidence(self) -> None:
        content = "파일 근거로 전환율을 50% 개선했습니다."
        encoded = content.encode()
        with self.session_factory() as database:
            database.add(Attachment(
                id="ATT-test",
                user_id="USER-test",
                filename="evidence.txt",
                normalized_filename="evidence.txt",
                mime_type="text/plain",
                size_bytes=len(encoded),
                content_hash=hashlib.sha256(encoded).hexdigest(),
                content=encoded,
                storage_backend="database",
                extracted_text=content,
                parse_status="ready",
                parser_version="test-v1",
                extraction_metadata={},
            ))
            database.commit()

        response = self.client.post(
            "/api/v2/experience-extractions/direct-input",
            json={
                "client_request_id": str(uuid4()),
                "input_type": "direct_input",
                "attachment_ids": ["ATT-test"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sources"][0]["attachment_id"], "ATT-test")
        self.assertIn("50%", response.json()["sources"][0]["text"])

    def test_public_url_is_added_as_experience_evidence(self) -> None:
        content = "FastAPI 응답 시간을 40% 단축한 프로젝트 경험"
        with self.session_factory() as database:
            database.add(Attachment(
                id="ATT-web-experience",
                user_id="USER-test",
                filename="career-page.html",
                normalized_filename="career-page.html",
                mime_type="text/html",
                size_bytes=len(content.encode()),
                content_hash="c" * 64,
                content=b"",
                storage_backend="database",
                extracted_text=content,
                parse_status="ready",
                parser_version="career-file-parser-v2",
                extraction_metadata={"source_type": "web_url"},
            ))
            database.commit()
        web_result = WebIngestionResult(
            attachment_ids=("ATT-web-experience",),
            urls=("https://example.com/experience",),
        )

        with patch(
            "AI_Engine.api.experience_extractions.web_content_service.ingest",
            return_value=web_result,
        ):
            response = self.client.post(
                "/api/v2/experience-extractions/direct-input",
                json={
                    "client_request_id": str(uuid4()),
                    "input_type": "direct_input",
                    "text": "https://example.com/experience",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        file_source = next(
            item for item in response.json()["sources"]
            if item.get("attachment_id") == "ATT-web-experience"
        )
        self.assertIn("40%", file_source["text"])
        self.assertEqual(
            self.fake_ai.requests[0].attachment_ids,
            ["ATT-web-experience"],
        )

    def test_text_and_txt_file_are_analyzed_together(self) -> None:
        response = self.client.post(
            "/api/v2/experience-extractions/direct-input-files",
            data={
                "client_request_id": str(uuid4()),
                "text": "저는 운영 대시보드 기획을 맡았습니다.",
            },
            files={
                "files": (
                    "result.txt",
                    "보고서 작성 시간이 4시간에서 1시간으로 줄었습니다.".encode(),
                    "text/plain",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["sources"]), 2)
        self.assertEqual(
            {source["type"] for source in payload["sources"]},
            {"manual_text", "file"},
        )
        self.assertIn(
            "보고서 작성 시간이",
            next(
                source["text"]
                for source in payload["sources"]
                if source["type"] == "file"
            ),
        )


if __name__ == "__main__":
    unittest.main()
