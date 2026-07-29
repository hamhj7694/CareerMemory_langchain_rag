"""사용자별 채용공고 분석 저장 API 테스트."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from AI_Engine.database import models  # noqa: F401
from AI_Engine.database.connection import Base, get_database_session
from AI_Engine.router import app


class JobsApiTests(unittest.TestCase):
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
                "username": f"job_{suffix}",
                "display_name": f"사용자 {suffix}",
                "password": "abc123",
                "password_confirm": "abc123",
                "recovery_question": "father_name",
                "recovery_answer": "정답",
            },
        )
        return response.json()["csrf_token"]

    @staticmethod
    def fake_result(client_request_id: str) -> SimpleNamespace:
        requirement = {
            "id": "requirement-1",
            "job_posting_id": "posting-1",
            "type": "qualification",
            "title": "데이터 분석 역량",
            "summary": "고객 데이터를 분석할 수 있어야 합니다.",
            "source_excerpt": "고객 데이터 분석 경험",
            "source_locator": {"source": "posting_content", "start_offset": 0, "end_offset": 12},
            "importance": "required",
            "keywords": ["데이터 분석"],
            "order": 1,
            "confidence": 0.9,
        }
        values = {
            "requirements": [requirement],
            "experience_links": [],
            "warnings": [],
        }
        return SimpleNamespace(
            analysis_id="job-analysis-1",
            model_version="model-test",
            prompt_version="prompt-test",
            schema_version="schema-test",
            index_version="index-test",
            analyzed_at=datetime.now(timezone.utc),
            model_dump=lambda mode: values,
        )

    def test_analysis_is_saved_and_other_user_cannot_read_it(self) -> None:
        owner = TestClient(app)
        other = TestClient(app)
        owner_csrf = self.register(owner, "owner")
        self.register(other, "other")

        analyzer = MagicMock()
        analyzer.invoke.return_value = self.fake_result("request-1")
        with (
            patch("AI_Engine.api.jobs.create_job_analysis_ai", return_value=analyzer),
            patch("AI_Engine.api.jobs.create_experience_retriever"),
        ):
            response = owner.post(
                "/api/jobs/analyze",
                headers={"X-CSRF-Token": owner_csrf},
                json={
                    "client_request_id": "request-1",
                    "company_name": "커리어 메모리",
                    "role_name": "서비스 기획자",
                    "posting_content": "고객 데이터 분석 경험",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["jobId"], "job-analysis-1")
        self.assertEqual(len(owner.get("/api/jobs").json()["items"]), 1)
        self.assertEqual(other.get("/api/jobs").json()["items"], [])
        self.assertEqual(
            other.get("/api/jobs/job-analysis-1").status_code,
            404,
        )

    def test_job_can_be_deleted_only_by_owner(self) -> None:
        owner = TestClient(app)
        other = TestClient(app)
        owner_csrf = self.register(owner, "delete_owner")
        other_csrf = self.register(other, "delete_other")
        with self.session_factory() as database:
            owner_user = database.query(models.User).filter_by(
                username="job_delete_owner"
            ).one()
            database.add(models.JobAnalysisRecord(
                id="job-delete-1",
                user_id=owner_user.id,
                client_request_id="delete-request",
                posting_content="공고",
            ))
            database.commit()

        self.assertEqual(
            other.delete(
                "/api/jobs/job-delete-1",
                headers={"X-CSRF-Token": other_csrf},
            ).status_code,
            404,
        )
        self.assertEqual(
            owner.delete(
                "/api/jobs/job-delete-1",
                headers={"X-CSRF-Token": owner_csrf},
            ).status_code,
            204,
        )

    def test_job_text_file_requires_login_and_returns_extracted_text(self) -> None:
        anonymous = TestClient(app)
        self.assertEqual(
            anonymous.post(
                "/api/jobs/extract-text",
                files={"files": ("job.txt", b"service planning", "text/plain")},
            ).status_code,
            401,
        )

        client = TestClient(app)
        csrf = self.register(client, "file_owner")
        response = client.post(
            "/api/jobs/extract-text",
            headers={"X-CSRF-Token": csrf},
            files={"files": (
                "job.txt",
                "주요 업무\n서비스 기획".encode(),
                "text/plain",
            )},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("서비스 기획", response.json()["text"])
        self.assertEqual(response.json()["files"][0]["filename"], "job.txt")

    def test_rematch_replaces_ai_links_and_preserves_user_links(self) -> None:
        client = TestClient(app)
        csrf = self.register(client, "rematch_owner")
        with self.session_factory() as database:
            user = database.query(models.User).filter_by(
                username="job_rematch_owner"
            ).one()
            domain = models.ExperienceDomain(id="domain-1", user_id=user.id, name="서비스 기획")
            project = models.ExperienceProject(id="project-1", user_id=user.id, domain_id=domain.id, name="결제 개선")
            old_experience = models.Experience(
                id="experience-old", user_id=user.id, project_id=project.id,
                title="기존 추천", source_ids=["source-old"], status="confirmed",
            )
            new_experience = models.Experience(
                id="experience-new", user_id=user.id, project_id=project.id,
                title="최신 추천", source_ids=["source-new"], status="confirmed",
            )
            manual_experience = models.Experience(
                id="experience-manual", user_id=user.id, project_id=project.id,
                title="직접 연결", source_ids=["source-manual"], status="confirmed",
            )
            requirement = self.fake_result("rematch-request").model_dump("json")["requirements"][0]
            job = models.JobAnalysisRecord(
                id="job-rematch-1",
                user_id=user.id,
                client_request_id="rematch-request",
                posting_content="고객 데이터 분석 경험",
                requirements=[requirement],
                experience_links=[
                    {
                        "requirement_id": "requirement-1",
                        "experience_id": "experience-old",
                        "source": "ai",
                        "status": "suggested",
                        "similarity_score": 0.5,
                        "reason": "기존 추천",
                        "evidence_ids": ["source-old"],
                    },
                    {
                        "requirement_id": "requirement-1",
                        "experience_id": "experience-manual",
                        "source": "user",
                        "status": "selected",
                        "reason": "사용자 직접 연결",
                        "evidence_ids": ["source-manual"],
                    },
                ],
            )
            database.add_all([domain, project, old_experience, new_experience, manual_experience, job])
            database.commit()

        refreshed_link = SimpleNamespace(model_dump=lambda mode: {
            "requirement_id": "requirement-1",
            "experience_id": "experience-new",
            "source": "ai",
            "status": "suggested",
            "similarity_score": 0.91,
            "reason": "최신 경험 추천",
            "evidence_ids": ["source-new"],
            "model_version": "model-test",
            "index_version": "index-test",
        })
        analyzer = MagicMock()
        analyzer.rematch_requirements.return_value = [refreshed_link]
        with (
            patch("AI_Engine.api.jobs.create_experience_retriever", return_value=MagicMock()),
            patch("AI_Engine.api.jobs.create_job_analysis_ai", return_value=analyzer),
        ):
            response = client.post(
                "/api/jobs/job-rematch-1/match",
                headers={"X-CSRF-Token": csrf},
                json={"requirement_ids": [], "refresh": True},
            )

        self.assertEqual(response.status_code, 200)
        linked_ids = response.json()["matches"][0]["linkedExperienceIds"]
        self.assertIn("experience-new", linked_ids)
        self.assertIn("experience-manual", linked_ids)
        self.assertNotIn("experience-old", linked_ids)
        returned_experiences = {
            item["experienceId"]: item
            for item in response.json()["matches"][0]["experiences"]
        }
        self.assertEqual(
            returned_experiences["experience-new"]["linkSource"],
            "ai",
        )
        self.assertEqual(
            returned_experiences["experience-new"]["linkStatus"],
            "suggested",
        )
        self.assertEqual(
            returned_experiences["experience-manual"]["linkSource"],
            "user",
        )

    def test_low_score_ai_link_is_hidden_but_user_link_is_preserved(self) -> None:
        client = TestClient(app)
        csrf = self.register(client, "threshold_owner")
        with self.session_factory() as database:
            user = database.query(models.User).filter_by(
                username="job_threshold_owner"
            ).one()
            domain = models.ExperienceDomain(
                id="threshold-domain",
                user_id=user.id,
                name="자격 경험",
            )
            project = models.ExperienceProject(
                id="threshold-project",
                user_id=user.id,
                domain_id=domain.id,
                name="자격증",
            )
            low_score = models.Experience(
                id="low-score-experience",
                user_id=user.id,
                project_id=project.id,
                title="낮은 점수 추천",
                source_ids=["source-low"],
                status="confirmed",
            )
            manual = models.Experience(
                id="manual-experience",
                user_id=user.id,
                project_id=project.id,
                title="사용자 직접 연결",
                source_ids=["source-manual"],
                status="confirmed",
            )
            requirement = self.fake_result(
                "threshold-request"
            ).model_dump("json")["requirements"][0]
            job = models.JobAnalysisRecord(
                id="job-threshold-1",
                user_id=user.id,
                client_request_id="threshold-request",
                posting_content="데이터 분석 자격증",
                requirements=[requirement],
                experience_links=[
                    {
                        "requirement_id": "requirement-1",
                        "experience_id": "low-score-experience",
                        "source": "ai",
                        "status": "suggested",
                        "similarity_score": 0.4,
                        "reason": "낮은 추천",
                        "evidence_ids": ["source-low"],
                    },
                    {
                        "requirement_id": "requirement-1",
                        "experience_id": "manual-experience",
                        "source": "user",
                        "status": "selected",
                        "reason": "사용자 직접 연결",
                        "evidence_ids": ["source-manual"],
                    },
                ],
            )
            database.add_all([domain, project, low_score, manual, job])
            database.commit()

        response = client.post(
            "/api/jobs/job-threshold-1/match",
            headers={"X-CSRF-Token": csrf},
            json={"requirement_ids": [], "refresh": False},
        )

        self.assertEqual(response.status_code, 200)
        experiences = response.json()["matches"][0]["experiences"]
        self.assertEqual(
            [item["experienceId"] for item in experiences],
            ["manual-experience"],
        )
        self.assertEqual(experiences[0]["linkSource"], "user")


if __name__ == "__main__":
    unittest.main()
