"""원본 근거 추가·수정·연결 해제·AI 재정리 API 회귀 테스트."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from AI_Engine.api.experience_extractions import get_experience_ai
from AI_Engine.database import models  # noqa: F401
from AI_Engine.database.connection import Base, get_database_session
from AI_Engine.router import app


class ExperienceSourcesApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
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


if __name__ == "__main__":
    unittest.main()
