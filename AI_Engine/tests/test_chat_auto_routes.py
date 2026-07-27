"""Automatic chat routing persists the dedicated AI result in one conversation."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from AI_Engine.chat_auto_routes import execute_automatic_route
from AI_Engine.database.connection import Base
from AI_Engine.database import models  # noqa: F401


class _Serializable:
    def __init__(self, value) -> None:
        self.value = value

    def model_dump(self, *, mode: str):
        del mode
        return self.value


class ChatAutoRouteTests(unittest.TestCase):
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

    @classmethod
    def tearDownClass(cls) -> None:
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self) -> None:
        with self.session_factory() as database:
            for table in reversed(Base.metadata.sorted_tables):
                database.execute(table.delete())
            database.commit()

    def _conversation_and_message(self, database):
        conversation = models.Conversation(
            id="CONV-auto",
            user_id="USER-auto",
            client_request_id="conversation-request-auto",
            title="자동 분류 테스트",
            message_count=1,
        )
        message = models.Message(
            id="MSG-user",
            conversation_id=conversation.id,
            client_request_id="request-auto",
            sequence=1,
            role="user",
            status="completed",
            content="이 내용을 경험으로 정리해 줘.",
            requested_intent="auto",
            completed_at=datetime.now(timezone.utc),
        )
        database.add_all([conversation, message])
        database.commit()
        return conversation, message

    def test_experience_route_saves_proposal_action(self) -> None:
        draft = _Serializable(
            {
                "draft_id": "DRAFT-auto",
                "domain": {"name": "직장 경험"},
                "project": {"name": "서비스 개선"},
                "title": "전환율 개선",
                "summary": "전환 흐름을 개선했습니다.",
                "situation": "",
                "actions": [],
                "results": [],
                "role": "",
                "skills": [],
                "facts": [],
                "source_ref_ids": ["source-MSG-user"],
            }
        )
        source = SimpleNamespace(
            id="source-MSG-user",
            model_dump=lambda mode: {
                "id": "source-MSG-user",
                "type": "message_text",
                "title": "대화 메시지 1",
                "message_id": "MSG-user",
                "text": "이 내용을 경험으로 정리해 줘.",
            },
        )
        result = SimpleNamespace(
            experience_drafts=[draft],
            sources=[source],
            run=_Serializable({"id": "RUN-auto"}),
        )
        fake_ai = SimpleNamespace(
            organize=lambda request, sources: result
        )

        with self.session_factory() as database, patch(
            "AI_Engine.chat_auto_routes.get_experience_ai",
            return_value=fake_ai,
        ):
            conversation, message = self._conversation_and_message(database)
            routed = execute_automatic_route(
                "experience_extraction",
                database=database,
                conversation=conversation,
                current_user=SimpleNamespace(id="USER-auto"),
                user_message=message,
            )

            self.assertIsNotNone(routed)
            self.assertEqual(routed.message.resolved_intents, ["experience_extraction"])
            self.assertEqual(routed.message.actions[0]["type"], "experience_proposal")
            self.assertEqual(conversation.message_count, 2)
            self.assertEqual(conversation.pending_proposal_count, 1)

    def test_job_route_saves_result_link(self) -> None:
        with self.session_factory() as database, patch(
            "AI_Engine.chat_auto_routes.analyze_job",
            return_value={
                "jobId": "JOB-auto",
                "requirements": [{"id": "REQ-1"}, {"id": "REQ-2"}],
            },
        ):
            conversation, message = self._conversation_and_message(database)
            routed = execute_automatic_route(
                "job_analysis",
                database=database,
                conversation=conversation,
                current_user=SimpleNamespace(id="USER-auto"),
                user_message=message,
            )

            self.assertIsNotNone(routed)
            self.assertEqual(routed.message.resolved_intents, ["job_analysis"])
            self.assertEqual(
                routed.message.actions,
                [{"type": "open_job_analysis", "job_id": "JOB-auto"}],
            )
            self.assertEqual(conversation.message_count, 2)


if __name__ == "__main__":
    unittest.main()
