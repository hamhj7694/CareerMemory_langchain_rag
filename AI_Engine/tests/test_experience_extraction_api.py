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
from AI_Engine.auth.dependencies import require_csrf_user
from AI_Engine.blob_store import clear_blob_store_cache
from AI_Engine.database import models  # noqa: F401
from AI_Engine.database.connection import Base, get_database_session
from AI_Engine.database.models import Attachment
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
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.pop(get_experience_ai, None)
        app.dependency_overrides.pop(require_csrf_user, None)
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
