"""Tests for independently extracting job postings from chat history."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from AI_Engine.api.conversation_jobs import (
    JOB_SCAN_ACTION,
    get_conversation_job_discovery_ai,
)
from AI_Engine.api.experience_extractions import get_experience_ai
from AI_Engine.auth.dependencies import get_current_user, require_csrf_user
from AI_Engine.conversation_analysis_workflow import ConversationAnalysisWorkflow
from AI_Engine.conversation_job_extraction import (
    ConversationJobCandidate,
    JobSourceText,
    extract_job_posting_candidates,
)
from AI_Engine.conversation_job_workflow import (
    ConversationJobDiscoveryAI,
    ConversationJobWorkflow,
    JOB_DISCOVERY_TOOL_NAME,
    JobWorkflowResolution,
)
from AI_Engine.database import models
from AI_Engine.database.connection import Base, get_database_session
from AI_Engine.router import app


POSTING_ONE = """[공고 1]
회사명: Alpha
직무: Backend Engineer
주요 업무: Python API와 데이터 파이프라인을 개발하고 운영합니다.
자격 요건: Python 개발 경력 3년 이상과 협업 경험이 필요합니다.
우대 사항: 클라우드 운영 경험을 우대합니다.
"""

POSTING_TWO = """[공고 2]
회사명: Beta
직무: Frontend Engineer
주요 업무: React 기반 사용자 화면과 디자인 시스템을 개발합니다.
자격 요건: React 개발 경력 3년 이상과 접근성 지식이 필요합니다.
우대 사항: 대규모 서비스 경험을 우대합니다.
"""


class ConversationJobCandidateTests(unittest.TestCase):
    def test_splits_numbered_postings_and_ignores_general_chat(self) -> None:
        candidates = extract_job_posting_candidates([
            JobSourceText(message_id="message-1", text=POSTING_ONE + POSTING_TWO),
            JobSourceText(message_id="message-2", text="면접 준비는 어떻게 하면 좋을까요?"),
        ])

        self.assertEqual(len(candidates), 2)
        self.assertEqual([item.company_name for item in candidates], ["Alpha", "Beta"])

    def test_discovery_ai_uses_strict_function_call_and_exact_source_text(self) -> None:
        calls = []

        class FakeResponses:
            def create(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(output=[SimpleNamespace(
                    type="function_call",
                    name=JOB_DISCOVERY_TOOL_NAME,
                    arguments=json.dumps({
                        "postings": [{
                            "source_id": "message:message-1",
                            "posting_content": POSTING_ONE,
                            "company_name": "Alpha",
                            "role_name": "Backend Engineer",
                            "posting_title": "Backend Engineer",
                            "source_url": None,
                        }],
                    }),
                )])

        client = SimpleNamespace(responses=FakeResponses())
        discovery = ConversationJobDiscoveryAI(
            client=client,
            model_version="model-test",
        )
        candidates = discovery.discover([
            JobSourceText(message_id="message-1", text=POSTING_ONE),
        ])

        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].company_name, "Alpha")
        self.assertEqual(calls[0]["tools"][0]["strict"], True)
        self.assertEqual(
            calls[0]["tool_choice"]["name"],
            JOB_DISCOVERY_TOOL_NAME,
        )

    def test_langgraph_deduplicates_wrapped_posting_before_analysis(self) -> None:
        resolved = []
        plain = ConversationJobCandidate(
            message_id="message-1",
            posting_content=POSTING_ONE,
        )
        wrapped = ConversationJobCandidate(
            message_id="message-1",
            posting_content=f"분석할 공고입니다.\n{POSTING_ONE}",
        )
        workflow = ConversationJobWorkflow(
            discover=lambda _sources: [plain, wrapped],
            resolve=lambda candidate: (
                resolved.append(candidate)
                or JobWorkflowResolution(job_id="JOB-1", created=True)
            ),
        )

        state = workflow.invoke([
            JobSourceText(message_id="message-1", text=wrapped.posting_content),
        ])

        self.assertEqual(len(resolved), 1)
        self.assertEqual(len(state["unique_candidates"]), 1)
        self.assertEqual(
            state["steps"],
            [
                "discover_postings",
                "deduplicate_postings",
                "analyze_postings",
                "complete",
            ],
        )

    def test_langgraph_skips_analysis_node_when_no_posting_is_found(self) -> None:
        workflow = ConversationJobWorkflow(
            discover=lambda _sources: [],
            resolve=lambda _candidate: self.fail("analysis node must be skipped"),
        )

        state = workflow.invoke([
            JobSourceText(message_id="message-1", text="일반적인 면접 질문입니다."),
        ])

        self.assertEqual(state.get("results", []), [])
        self.assertEqual(
            state["steps"],
            ["discover_postings", "deduplicate_postings", "complete"],
        )

    def test_integrated_graph_keeps_experience_branch_after_job_failure(self) -> None:
        candidate = ConversationJobCandidate(
            message_id="message-1",
            posting_content=POSTING_ONE,
        )
        workflow = ConversationAnalysisWorkflow(
            discover_jobs=lambda _sources: [candidate],
            resolve_job=lambda _candidate: (_ for _ in ()).throw(
                RuntimeError("job provider failure")
            ),
            build_experience_sources=lambda _candidates: ["experience-source"],
            analyze_experiences=lambda sources: {"source_count": len(sources)},
        )

        state = workflow.invoke([
            JobSourceText(message_id="message-1", text=POSTING_ONE),
        ])

        self.assertEqual(state["job_results"], [])
        self.assertTrue(state["experience_succeeded"])
        self.assertEqual(state["experience_result"], {"source_count": 1})
        self.assertEqual(state["failures"][0]["stage"], "analyze_jobs")


class ConversationJobExtractionApiTests(unittest.TestCase):
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
        cls.current_user = SimpleNamespace(id="USER-conversation-job")
        app.dependency_overrides[get_current_user] = lambda: cls.current_user
        app.dependency_overrides[require_csrf_user] = lambda: cls.current_user
        app.dependency_overrides[get_conversation_job_discovery_ai] = (
            lambda: SimpleNamespace(discover=extract_job_posting_candidates)
        )
        cls.client = TestClient(app)

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

    def _add_conversation(self, content: str) -> str:
        conversation_id = f"CONV-{uuid4()}"
        with self.session_factory() as database:
            conversation = models.Conversation(
                id=conversation_id,
                user_id=self.current_user.id,
                client_request_id=str(uuid4()),
                title="Job extraction",
                message_count=1,
            )
            message = models.Message(
                id=f"MSG-{uuid4()}",
                conversation_id=conversation_id,
                client_request_id=str(uuid4()),
                sequence=1,
                role="user",
                status="completed",
                content=content,
                requested_intent="auto",
                completed_at=datetime.now(timezone.utc),
            )
            database.add_all([conversation, message])
            database.commit()
        return conversation_id

    @staticmethod
    def _fake_analyze(calls):
        def analyze(*, body, current_user, database):
            calls.append(body.posting_content)
            item = models.JobAnalysisRecord(
                id=f"JOB-{len(calls)}",
                user_id=current_user.id,
                client_request_id=body.client_request_id,
                company_name=body.company_name,
                role_name=body.role_name,
                posting_title=body.posting_title,
                source_url=body.source_url,
                posting_content=body.posting_content,
                requirements=[],
                experience_links=[],
                warnings=[],
                versions={},
            )
            database.add(item)
            database.commit()
            return {"jobId": item.id}

        return analyze

    def test_analyzes_multiple_postings_and_replays_without_duplicates(self) -> None:
        conversation_id = self._add_conversation(POSTING_ONE + POSTING_TWO)
        calls: list[str] = []
        request_id = str(uuid4())

        with patch(
            "AI_Engine.api.conversation_jobs.analyze_job",
            side_effect=self._fake_analyze(calls),
        ):
            first = self.client.post(
                f"/api/v2/conversations/{conversation_id}/job-extractions",
                json={"client_request_id": request_id},
            )
            replay = self.client.post(
                f"/api/v2/conversations/{conversation_id}/job-extractions",
                json={"client_request_id": request_id},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["run"]["created_count"], 2)
        self.assertEqual(first.json()["job_ids"], ["JOB-1", "JOB-2"])
        self.assertEqual(first.json()["run"]["workflow"]["engine"], "langgraph")
        self.assertEqual(
            first.json()["run"]["workflow"]["steps"],
            [
                "discover_postings",
                "deduplicate_postings",
                "analyze_postings",
                "complete",
            ],
        )
        self.assertFalse(first.json()["replayed"])
        self.assertTrue(replay.json()["replayed"])
        self.assertEqual(len(calls), 2)

        with self.session_factory() as database:
            self.assertEqual(database.query(models.JobAnalysisRecord).count(), 2)
            source = database.query(models.Message).filter_by(role="user").one()
            self.assertTrue(any(
                action.get("type") == JOB_SCAN_ACTION for action in source.actions
            ))

        status_response = self.client.get(
            f"/api/v2/conversations/{conversation_id}/job-extraction-status"
        )
        self.assertEqual(status_response.json()["unprocessed_message_count"], 0)

    def test_reuses_matching_saved_posting_for_a_new_message(self) -> None:
        conversation_id = self._add_conversation(POSTING_ONE)
        with self.session_factory() as database:
            database.add(models.JobAnalysisRecord(
                id="JOB-existing",
                user_id=self.current_user.id,
                client_request_id="existing-request",
                posting_content=POSTING_ONE,
            ))
            database.commit()

        calls: list[str] = []
        with patch(
            "AI_Engine.api.conversation_jobs.analyze_job",
            side_effect=self._fake_analyze(calls),
        ):
            response = self.client.post(
                f"/api/v2/conversations/{conversation_id}/job-extractions",
                json={"client_request_id": str(uuid4())},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["run"]["created_count"], 0)
        self.assertEqual(response.json()["existing_job_ids"], ["JOB-existing"])
        self.assertEqual(calls, [])

    def test_integrated_analysis_separates_job_text_from_experience_text(self) -> None:
        experience_text = (
            "고객 문의 응답 시간을 분석하고 자동 분류 규칙을 적용해 "
            "평균 처리 시간을 20% 줄였습니다."
        )
        conversation_id = self._add_conversation(
            f"{experience_text}\n\n{POSTING_ONE}"
        )
        captured_sources = []

        draft = SimpleNamespace(model_dump=lambda mode: {
            "draft_id": "integrated-draft-1",
            "domain": {"name": "고객 경험"},
            "project": {"name": "문의 개선"},
            "title": "문의 처리 시간 개선",
            "summary": "문의 처리 시간을 20% 줄였습니다.",
            "source_ref_ids": [],
        })
        run = SimpleNamespace(model_dump=lambda mode: {
            "id": "integrated-experience-run-1",
            "message_ids": [],
        })

        def organize(_request, sources):
            captured_sources.extend(sources)
            return SimpleNamespace(
                experience_drafts=[draft],
                sources=sources,
                run=run,
            )

        discovery = SimpleNamespace(discover=lambda _sources: [
            ConversationJobCandidate(
                message_id=_sources[0].message_id,
                posting_content=POSTING_ONE,
                company_name="Alpha",
                role_name="Backend Engineer",
            ),
        ])
        calls: list[str] = []
        app.dependency_overrides[get_conversation_job_discovery_ai] = (
            lambda: discovery
        )
        app.dependency_overrides[get_experience_ai] = (
            lambda: SimpleNamespace(organize=organize)
        )
        request_id = str(uuid4())
        try:
            with patch(
                "AI_Engine.api.conversation_analysis.analyze_job",
                side_effect=self._fake_analyze(calls),
            ):
                response = self.client.post(
                    f"/api/v2/conversations/{conversation_id}/analyses",
                    json={"client_request_id": request_id},
                )
                replay = self.client.post(
                    f"/api/v2/conversations/{conversation_id}/analyses",
                    json={"client_request_id": request_id},
                )
        finally:
            app.dependency_overrides[get_conversation_job_discovery_ai] = (
                lambda: SimpleNamespace(discover=extract_job_posting_candidates)
            )
            app.dependency_overrides.pop(get_experience_ai, None)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["run"]["experience_count"], 1)
        self.assertEqual(payload["run"]["job_count"], 1)
        self.assertEqual(payload["run"]["workflow"]["engine"], "langgraph")
        self.assertEqual(payload["job_ids"], ["JOB-1"])
        self.assertIsNotNone(payload["proposal"])
        self.assertTrue(replay.json()["replayed"])
        self.assertEqual(len(calls), 1)
        analyzed_experience_text = "\n".join(
            source.text or "" for source in captured_sources
        )
        self.assertIn("20%", analyzed_experience_text)
        self.assertNotIn("회사명: Alpha", analyzed_experience_text)

        status_response = self.client.get(
            f"/api/v2/conversations/{conversation_id}/analysis-status"
        )
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(
            status_response.json()["unprocessed_message_count"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
