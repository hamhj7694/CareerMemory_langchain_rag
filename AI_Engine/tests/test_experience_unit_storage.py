import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from AI_Engine.database.connection import Base
from AI_Engine.database.models import Experience, ExperienceDomain, ExperienceProject, User
from AI_Engine.experience_unit_storage import annotate_proposal_matches, save_experience_unit


class ExperienceUnitStorageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_same_skill_reuses_canonical_spelling_without_merging_different_experience(self):
        with self.Session() as database:
            user = User(
                id="USER-SKILL", email="skill@example.com", display_name="Skill",
                password_hash="unused", account_type="simple",
            )
            domain = ExperienceDomain(id="DOM-1", user_id=user.id, name="개발 경험")
            project = ExperienceProject(
                id="PROJ-1", user_id=user.id, domain_id=domain.id, name="기존 프로젝트",
            )
            experience = Experience(
                id="EXP-1", user_id=user.id, project_id=project.id,
                title="기존 API 개발", summary="기존 API를 개발했다.",
                skills=["FastAPI"], status="confirmed",
            )
            project.domain = domain
            experience.project = project
            database.add_all([user, domain, project, experience])
            database.commit()

            proposal = annotate_proposal_matches(database, {
                "units": [{
                    "unit_id": "UNIT-NEW",
                    "domain": {"name": "개발 경험"},
                    "project": {"name": "새 프로젝트"},
                    "title": "React 관리 화면 구현",
                    "summary": "다른 제품의 관리 화면을 구현했다.",
                    "skills": ["fastapi", "React"],
                }],
            }, user_id=user.id)

            unit = proposal["units"][0]
            self.assertEqual(unit["save_strategy"]["operation"], "create")
            self.assertEqual(unit["skills"], ["FastAPI", "React"])
            self.assertEqual(unit["reused_skills"], ["FastAPI"])

    def test_update_preserves_user_text_and_adds_new_details_without_duplicates(self):
        with self.Session() as database:
            user = User(
                id="USER-MERGE", email="merge@example.com", display_name="Merge",
                password_hash="unused", account_type="simple",
            )
            domain = ExperienceDomain(id="DOM-1", user_id=user.id, name="개발 경험")
            project = ExperienceProject(
                id="PROJ-1", user_id=user.id, domain_id=domain.id, name="Career Memory",
            )
            experience = Experience(
                id="EXP-1", user_id=user.id, project_id=project.id,
                title="RAG 개선", summary="사용자가 직접 다듬은 요약",
                situation="기존 상황", role="기존 역할",
                actions=["검색 흐름을 설계했다."], results=["응답 품질을 높였다."],
                skills=["FastAPI"], facts=["기존 사실"],
                fact_evidence_status={"기존 사실": "supported"},
                status="confirmed",
            )
            project.domain = domain
            experience.project = project
            database.add_all([user, domain, project, experience])
            database.commit()

            unit = {
                "unit_id": "UNIT-NEW",
                "domain": {"name": "개발 경험"},
                "project": {"name": "Career Memory"},
                "title": "RAG 개선",
                "summary": "AI가 새로 만든 요약",
                "situation": "AI가 새로 만든 상황",
                "role": "AI 역할",
                "actions": ["검색 흐름을 설계했다.", "근거 추적을 추가했다."],
                "results": ["응답 품질을 높였다.", "호출 수를 줄였다."],
                "skills": ["FastAPI", "LangGraph"],
                "facts": ["기존 사실", "호출 수 감소"],
                "source_ref_ids": ["SOURCE-NEW"],
                "field_citations": {
                    "facts.1": [{"source_ref_id": "SOURCE-NEW", "quote": "호출 수 감소"}],
                },
                "save_strategy": {"operation": "update", "experience_id": experience.id},
            }
            with patch("AI_Engine.experience_unit_storage.sync_experience_evidence"):
                saved, operation = save_experience_unit(
                    database,
                    unit=unit,
                    source_refs=[],
                    current_user=SimpleNamespace(id=user.id),
                )

            self.assertEqual(operation, "updated")
            self.assertEqual(saved.id, experience.id)
            self.assertEqual(saved.summary, "사용자가 직접 다듬은 요약")
            self.assertEqual(saved.situation, "기존 상황")
            self.assertEqual(saved.role, "기존 역할")
            self.assertEqual(
                saved.actions,
                ["검색 흐름을 설계했다.", "근거 추적을 추가했다."],
            )
            self.assertEqual(
                saved.results,
                ["응답 품질을 높였다.", "호출 수를 줄였다."],
            )
            self.assertEqual(saved.skills, ["FastAPI", "LangGraph"])
            self.assertEqual(saved.facts, ["기존 사실", "호출 수 감소"])
            self.assertIn("facts.1", saved.field_citations)
            self.assertEqual(saved.source_ids, ["SOURCE-NEW"])


if __name__ == "__main__":
    unittest.main()
