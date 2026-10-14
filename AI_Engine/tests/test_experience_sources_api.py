"""원본 근거 추가·수정·연결 해제·AI 재정리 API 회귀 테스트."""

from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from AI_Engine.api.experience_extractions import get_experience_ai
from AI_Engine.blob_store import clear_blob_store_cache
from AI_Engine.database import models  # noqa: F401
from AI_Engine.database.connection import Base, get_database_session
from AI_Engine.router import app


class ExperienceSourcesApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.attachment_storage = TemporaryDirectory()
        cls.storage_environment = patch.dict(
            "os.environ",
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

        app.dependency_overrides[get_database_session] = get_test_session

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()
        clear_blob_store_cache()
        cls.storage_environment.stop()
        cls.attachment_storage.cleanup()

    def setUp(self) -> None:
        with self.session_factory() as database:
            for table in reversed(Base.metadata.sorted_tables):
                database.execute(table.delete())
            database.commit()
        self.client = TestClient(app)
        registered = self.client.post(
            "/api/v2/auth/register",
            json={
                "email": "evidence@example.com",
                "username": "evidence_user",
                "display_name": "근거 사용자",
                "password": "abc123",
                "password_confirm": "abc123",
                "recovery_question": "father_name",
                "recovery_answer": "정답",
            },
        )
        self.csrf = registered.json()["csrf_token"]
        self.headers = {"X-CSRF-Token": self.csrf}
        self.experience = self.client.post(
            "/api/v2/experiences",
            headers=self.headers,
            json={
                "domain": {"name": "서비스 기획"},
                "project": {"name": "결제 개선"},
                "title": "결제 절차 개선",
                "summary": "기존 정리본",
            },
        ).json()

    def test_worker_mode_queues_upload_and_worker_completes_it(self) -> None:
        from AI_Engine.attachment_service import attachment_service
        with patch.dict("os.environ", {"FILE_PROCESSING_MODE": "worker"}):
            with patch.object(attachment_service, "process_job", wraps=attachment_service.process_job) as process:
                uploaded = self.client.post("/api/v2/attachments", headers=self.headers,
                                            files={"file": ("worker.txt", b"queued evidence", "text/plain")})
                self.assertEqual(uploaded.status_code, 201)
                self.assertEqual(uploaded.json()["status"], "queued")
                process.assert_not_called()
            with self.session_factory() as database:
                job = attachment_service.claim_next_queued_job(database, worker_id="test-worker")
                attachment_service.process_job(database, job.id, worker_id="test-worker")
            result = self.client.get(f'/api/v2/attachments/{uploaded.json()["id"]}')
            self.assertEqual(result.json()["status"], "ready")
            original = self.client.get(f'/api/v2/attachments/{uploaded.json()["id"]}/download')
            self.assertEqual(original.content, b"queued evidence")

    def test_sources_can_be_added_and_reorganized_as_independent_copy(self) -> None:
        added_text = self.client.post(
            f"/api/v2/experiences/{self.experience['id']}/sources/text",
            headers=self.headers,
            json={
                "title": "사용자 메모",
                "text": "결제 완료율이 14% 증가했습니다.",
                "client_request_id": str(uuid4()),
            },
        )
        self.assertEqual(added_text.status_code, 201)
        text_source_id = added_text.json()["added_source_ids"][0]

        uploaded = self.client.post(
            "/api/v2/attachments",
            headers=self.headers,
            files={
                "file": (
                    "result.txt",
                    "고객 문의가 22% 감소했습니다.".encode("utf-8"),
                    "text/plain",
                ),
            },
        )
        self.assertEqual(uploaded.status_code, 201)
        attachment_id = uploaded.json()["id"]
        added_file = self.client.post(
            f"/api/v2/experiences/{self.experience['id']}/sources/files",
            headers=self.headers,
            json={
                "attachment_ids": [attachment_id],
                "client_request_id": str(uuid4()),
            },
        )
        self.assertEqual(added_file.status_code, 200)
        self.assertEqual(len(added_file.json()["sources"]), 2)

        downloaded = self.client.get(
            f"/api/v2/attachments/{attachment_id}/download"
        )
        self.assertEqual(downloaded.status_code, 200)
        self.assertIn("22%", downloaded.content.decode("utf-8"))
        protected_delete = self.client.delete(
            f"/api/v2/attachments/{attachment_id}",
            headers=self.headers,
        )
        self.assertEqual(protected_delete.status_code, 409)

        updated_text = self.client.patch(
            (
                f"/api/v2/experiences/{self.experience['id']}"
                f"/sources/{text_source_id}"
            ),
            headers=self.headers,
            json={
                "changes": {
                    "text": "결제 완료율이 14% 증가하고 문의가 감소했습니다.",
                },
                "client_request_id": str(uuid4()),
            },
        )
        self.assertEqual(updated_text.status_code, 200)
        self.assertIn("문의가 감소", updated_text.json()["text"])

        captured = {}
        draft = SimpleNamespace(
            project=SimpleNamespace(period=None),
            summary="현재 근거를 반영한 요약",
            situation="결제 이탈이 높았습니다.",
            actions=["결제 단계를 줄였습니다."],
            results=["결제 완료율이 14% 증가했습니다."],
            role="서비스 기획자",
            skills=["데이터 분석"],
            facts=["고객 문의가 22% 감소했습니다."],
            missing_information=[],
        )

        def organize(request, *, sources):
            captured["request"] = request
            captured["sources"] = sources
            return SimpleNamespace(
                experience_drafts=[draft],
                run=SimpleNamespace(
                    model_dump=lambda mode: {
                        "id": "RUN-reorganize",
                        "source_ref_ids": request.source_ref_ids,
                    },
                ),
            )

        app.dependency_overrides[get_experience_ai] = lambda: SimpleNamespace(
            organize=organize,
        )
        try:
            reorganized = self.client.post(
                (
                    f"/api/v2/experiences/{self.experience['id']}"
                    "/reorganize-from-sources"
                ),
                headers=self.headers,
                json={"client_request_id": str(uuid4())},
            )
        finally:
            app.dependency_overrides.pop(get_experience_ai, None)

        self.assertEqual(reorganized.status_code, 200)
        copy = reorganized.json()["experience"]
        self.assertEqual(copy["title"], "결제 절차 개선 - 새 정리본")
        self.assertEqual(copy["summary"], "현재 근거를 반영한 요약")
        self.assertEqual(len(copy["source_ids"]), 2)
        self.assertEqual(captured["request"].input_type, "evidence_reorganization")
        self.assertEqual(len(captured["sources"]), 2)

        unlinked = self.client.request(
            "DELETE",
            (
                f"/api/v2/experiences/{self.experience['id']}"
                f"/sources/{text_source_id}"
            ),
            headers=self.headers,
            json={"client_request_id": str(uuid4())},
        )
        self.assertEqual(unlinked.status_code, 200)
        self.assertEqual(len(unlinked.json()["experience"]["source_ids"]), 1)
        saved_copy = self.client.get(
            f"/api/v2/experiences/{copy['id']}",
        ).json()
        self.assertEqual(len(saved_copy["source_ids"]), 2)

    def test_editing_and_unlinking_source_invalidates_dependent_fact(self) -> None:
        source_id = "source-manual-fact"
        fact = "Checkout completion increased by 14%."
        created = self.client.post(
            "/api/v2/experiences",
            headers=self.headers,
            json={
                "domain": {"name": "Work"},
                "project": {"name": "Evidence lifecycle"},
                "title": "Checkout improvement",
                "facts": [fact],
                "source_ids": [source_id],
                "source_refs": [{
                    "id": source_id,
                    "type": "manual_text",
                    "title": "Original note",
                    "text": fact,
                }],
                "field_citations": {
                    "facts.0": [{"source_ref_id": source_id, "quote": fact}],
                },
            },
        )
        self.assertEqual(created.status_code, 201)
        experience = created.json()
        self.assertEqual(experience["fact_evidence_status"][fact], "supported")
        fact_block = next(
            block for block in experience["content_blocks"]
            if block["type"] == "facts"
        )
        self.assertEqual(fact_block["citations"][0]["quote"], fact)

        edited = self.client.patch(
            f"/api/v2/experiences/{experience['id']}/sources/{source_id}",
            headers=self.headers,
            json={
                "changes": {"text": "The source note was corrected."},
                "client_request_id": str(uuid4()),
            },
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["unsupported_facts"], [fact])
        self.assertEqual(
            edited.json()["experiences"][0]["fact_evidence_status"][fact],
            "stale",
        )

        unlinked = self.client.request(
            "DELETE",
            f"/api/v2/experiences/{experience['id']}/sources/{source_id}",
            headers=self.headers,
            json={"client_request_id": str(uuid4())},
        )
        self.assertEqual(unlinked.status_code, 200)
        self.assertEqual(unlinked.json()["unsupported_facts"], [fact])
        self.assertEqual(
            unlinked.json()["experience"]["fact_evidence_status"][fact],
            "needs_evidence",
        )
        self.assertEqual(unlinked.json()["experience"]["field_citations"], {})


if __name__ == "__main__":
    unittest.main()
