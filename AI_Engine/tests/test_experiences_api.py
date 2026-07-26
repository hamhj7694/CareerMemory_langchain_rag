"""사용자별 경험 저장 API의 핵심 흐름 테스트."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from AI_Engine.database import models  # noqa: F401
from AI_Engine.database.connection import Base, get_database_session
from AI_Engine.router import app


class ExperiencesApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.session_factory = sessionmaker(bind=cls.engine, expire_on_commit=False)
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

    @staticmethod
    def register(client: TestClient, suffix: str) -> str:
        response = client.post(
            "/api/v2/auth/register",
            json={
                "email": f"{suffix}@example.com",
                "username": f"user_{suffix}",
                "display_name": f"사용자 {suffix}",
                "password": "abc123",
                "password_confirm": "abc123",
                "recovery_question": "father_name",
                "recovery_answer": "홍길동",
            },
        )
        return response.json()["csrf_token"]

    def test_ai_draft_fields_are_saved_and_user_isolated(self) -> None:
        owner = TestClient(app)
        other = TestClient(app)
        owner_csrf = self.register(owner, "owner")
        self.register(other, "other")

        created = owner.post(
            "/api/v2/experiences",
            headers={"X-CSRF-Token": owner_csrf},
            json={
                "domain": {"name": "직장 경험"},
                "project": {"name": "서비스 개선", "organization": "커리어메모리"},
                "title": "전환율 12% 개선",
                "summary": "사용자 흐름을 분석해 전환율을 개선했습니다.",
                "situation": "가입 이탈률이 높았습니다.",
                "actions": ["퍼널 분석", "가입 화면 개선"],
                "results": ["전환율 12% 증가"],
                "skills": ["데이터 분석", "UX"],
                "source_ids": ["source-manual-1"],
                "source_refs": [{"id": "source-manual-1", "type": "manual_text"}],
            },
        )

        self.assertEqual(created.status_code, 201)
        payload = created.json()
        self.assertEqual(payload["title"], "전환율 12% 개선")
        self.assertEqual(payload["actions"], ["퍼널 분석", "가입 화면 개선"])
        self.assertEqual(payload["domain"]["name"], "직장 경험")
        self.assertEqual(payload["project"]["name"], "서비스 개선")

        owner_items = owner.get("/api/v2/experiences").json()["items"]
        other_items = other.get("/api/v2/experiences").json()["items"]
        self.assertEqual(len(owner_items), 1)
        self.assertEqual(other_items, [])

    def test_saved_experience_can_be_updated_and_deleted(self) -> None:
        client = TestClient(app)
        csrf = self.register(client, "editor")
        created = client.post(
            "/api/v2/experiences",
            headers={"X-CSRF-Token": csrf},
            json={
                "domain": {"name": "개인 경험"},
                "project": {"name": "학습"},
                "title": "초기 제목",
            },
        ).json()

        updated = client.patch(
            f"/api/v2/experiences/{created['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "base_version": created["version"],
                "changes": {"title": "수정된 제목"},
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["title"], "수정된 제목")

        deleted = client.request(
            "DELETE",
            f"/api/v2/experiences/{created['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"version": updated.json()["version"], "confirm": True},
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(client.get("/api/v2/experiences").json()["items"], [])


if __name__ == "__main__":
    unittest.main()
