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
        trash = client.get("/api/v2/experience-draft-trash").json()
        self.assertEqual(trash["total_count"], 1)
        self.assertEqual(trash["items"][0]["title"], "수정된 제목")
        self.assertEqual(
            trash["items"][0]["draft"]["original_experience_id"],
            created["id"],
        )
        self.assertEqual(trash["items"][0]["draft"]["domain"]["name"], "개인 경험")
        self.assertEqual(trash["items"][0]["draft"]["project"]["name"], "학습")

    def test_deleting_project_moves_all_child_experiences_to_trash(self) -> None:
        client = TestClient(app)
        csrf = self.register(client, "project_delete")
        for title in ("첫 경험", "두 번째 경험"):
            response = client.post(
                "/api/v2/experiences",
                headers={"X-CSRF-Token": csrf},
                json={
                    "domain": {"name": "직장 경험"},
                    "project": {"name": "서비스 개선"},
                    "title": title,
                },
            )
            self.assertEqual(response.status_code, 201)

        structure = client.get("/api/v2/experience-structure").json()
        project = structure["domains"][0]["projects"][0]
        deleted = client.request(
            "DELETE",
            f"/api/v2/experience-projects/{project['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"version": project["version"], "confirm": True},
        )

        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(client.get("/api/v2/experiences").json()["items"], [])
        trash = client.get("/api/v2/experience-draft-trash").json()
        self.assertEqual(trash["total_count"], 2)
        self.assertEqual(
            {item["draft"]["title"] for item in trash["items"]},
            {"첫 경험", "두 번째 경험"},
        )

    def test_deleting_domain_moves_all_nested_experiences_to_trash(self) -> None:
        client = TestClient(app)
        csrf = self.register(client, "domain_delete")
        for project_name, title in (("결제 개선", "결제 경험"), ("운영 개선", "운영 경험")):
            response = client.post(
                "/api/v2/experiences",
                headers={"X-CSRF-Token": csrf},
                json={
                    "domain": {"name": "직장 경험"},
                    "project": {"name": project_name},
                    "title": title,
                },
            )
            self.assertEqual(response.status_code, 201)

        structure = client.get("/api/v2/experience-structure").json()
        domain = structure["domains"][0]
        deleted = client.request(
            "DELETE",
            f"/api/v2/experience-domains/{domain['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"version": domain["version"], "confirm": True},
        )

        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(client.get("/api/v2/experiences").json()["items"], [])
        trash = client.get("/api/v2/experience-draft-trash").json()
        self.assertEqual(trash["total_count"], 2)
        self.assertEqual(
            {item["draft"]["title"] for item in trash["items"]},
            {"결제 경험", "운영 경험"},
        )

    def test_draft_trash_is_user_scoped_and_can_be_permanently_deleted(self) -> None:
        owner = TestClient(app)
        other = TestClient(app)
        owner_csrf = self.register(owner, "trash_owner")
        self.register(other, "trash_other")

        created = owner.post(
            "/api/v2/experience-draft-trash",
            headers={"X-CSRF-Token": owner_csrf},
            json={
                "status": "deleted",
                "reason": "사용자가 삭제한 초안",
                "draft": {
                    "title": "장바구니 개선",
                    "domain": "기획·운영",
                    "project": "결제 개선",
                    "actions": ["고객 문의 분석"],
                },
                "original_text": "",
            },
        )

        self.assertEqual(created.status_code, 201)
        item_id = created.json()["id"]
        self.assertEqual(
            owner.get("/api/v2/experience-draft-trash").json()["total_count"],
            1,
        )
        self.assertEqual(
            other.get("/api/v2/experience-draft-trash").json()["items"],
            [],
        )

        deleted = owner.request(
            "DELETE",
            f"/api/v2/experience-draft-trash/{item_id}",
            headers={"X-CSRF-Token": owner_csrf},
            json={"confirm": True},
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(
            owner.get("/api/v2/experience-draft-trash").json()["items"],
            [],
        )

    def test_all_trash_items_can_be_permanently_deleted_for_current_user(self) -> None:
        owner = TestClient(app)
        other = TestClient(app)
        owner_csrf = self.register(owner, "trash_bulk_owner")
        other_csrf = self.register(other, "trash_bulk_other")
        payload = {
            "status": "deleted",
            "reason": "bulk delete test",
            "draft": {"title": "deleted draft"},
            "original_text": "",
        }

        for index in range(2):
            created = owner.post(
                "/api/v2/experience-draft-trash",
                headers={"X-CSRF-Token": owner_csrf},
                json={**payload, "draft": {"title": f"owner draft {index}"}},
            )
            self.assertEqual(created.status_code, 201)
        other_created = other.post(
            "/api/v2/experience-draft-trash",
            headers={"X-CSRF-Token": other_csrf},
            json={**payload, "draft": {"title": "other draft"}},
        )
        self.assertEqual(other_created.status_code, 201)

        missing_confirmation = owner.request(
            "DELETE",
            "/api/v2/experience-draft-trash",
            headers={"X-CSRF-Token": owner_csrf},
            json={"confirm": False},
        )
        self.assertEqual(missing_confirmation.status_code, 422)

        deleted = owner.request(
            "DELETE",
            "/api/v2/experience-draft-trash",
            headers={"X-CSRF-Token": owner_csrf},
            json={"confirm": True},
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["deleted_count"], 2)
        self.assertEqual(
            owner.get("/api/v2/experience-draft-trash").json()["items"],
            [],
        )
        self.assertEqual(
            other.get("/api/v2/experience-draft-trash").json()["total_count"],
            1,
        )

    def test_failed_draft_trash_keeps_original_file_for_reanalysis(self) -> None:
        client = TestClient(app)
        csrf = self.register(client, "trash_file_owner")

        created = client.post(
            "/api/v2/experience-draft-trash/with-files",
            headers={"X-CSRF-Token": csrf},
            data={
                "status": "failed",
                "reason": "AI 형식 검증 실패",
                "draft_json": "{}",
                "original_text": "직접 입력한 경험",
            },
            files={
                "files": (
                    "experience.txt",
                    "파일에 작성한 경험".encode("utf-8"),
                    "text/plain",
                ),
            },
        )

        self.assertEqual(created.status_code, 201)
        item = created.json()
        self.assertEqual(item["files"][0]["filename"], "experience.txt")
        downloaded = client.get(
            f"/api/v2/experience-draft-trash/{item['id']}/files/"
            f"{item['files'][0]['id']}"
        )
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.content.decode("utf-8"), "파일에 작성한 경험")


if __name__ == "__main__":
    unittest.main()
