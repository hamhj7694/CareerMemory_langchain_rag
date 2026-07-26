"""대화 API와 SQLAlchemy 저장 동작 테스트."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from AI_Engine.database.connection import Base, get_database_session
from AI_Engine.database import models  # noqa: F401
from AI_Engine.api.conversations import get_chatbot_ai
from AI_Engine.auth.dependencies import get_current_user, require_csrf_user
from AI_Engine.router import app


class FakeChatbot:
    """외부 API 호출 없이 고정된 assistant 답변을 반환한다."""

    def __init__(self) -> None:
        self.invoke_count = 0
        self.requests = []

    def invoke(self, request):
        self.invoke_count += 1
        self.requests.append(request)
        return SimpleNamespace(
            message=SimpleNamespace(
                id=f"MSG-AI-{self.invoke_count}",
                content=f"AI 답변: {request.content}",
                created_at=datetime.now(timezone.utc),
            ),
            citations=[],
            suggested_actions=[],
        )

    def stream(self, request):
        self.invoke_count += 1
        self.requests.append(request)
        yield SimpleNamespace(type="started")
        yield SimpleNamespace(type="token", text_delta="AI 답변: ")
        yield SimpleNamespace(type="token", text_delta=request.content)
        yield SimpleNamespace(type="completed")


class ConversationApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # 테스트가 끝나면 사라지는 메모리 SQLite를 사용해 실제 사용자 DB를 보호한다.
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

        # FastAPI가 기본 DB 대신 테스트 DB 세션을 받도록 의존성을 교체한다.
        def get_test_session():
            database = cls.session_factory()
            try:
                yield database
            finally:
                database.close()

        app.dependency_overrides[get_database_session] = get_test_session
        cls.chatbot = FakeChatbot()
        app.dependency_overrides[get_chatbot_ai] = lambda: cls.chatbot
        cls.current_user = SimpleNamespace(
            id="USER-test",
            display_name="테스트 사용자",
        )
        app.dependency_overrides[get_current_user] = (
            lambda: cls.current_user
        )
        app.dependency_overrides[require_csrf_user] = (
            lambda: cls.current_user
        )
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self) -> None:
        # 테스트끼리 저장 데이터가 영향을 주지 않도록 매번 테이블 내용을 비운다.
        with self.session_factory() as database:
            for table in reversed(Base.metadata.sorted_tables):
                database.execute(table.delete())
            database.commit()
        self.chatbot.invoke_count = 0
        self.chatbot.requests = []
        self.current_user.id = "USER-test"

    def create_conversation(self, *, title: str = "첫 대화"):
        return self.client.post(
            "/api/v2/conversations",
            json={
                "title": title,
                "client_request_id": str(uuid4()),
            },
        )

    def test_create_conversation_returns_saved_conversation(self) -> None:
        response = self.create_conversation(title="커리어 상담")

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["id"].startswith("CONV-"))
        self.assertEqual(payload["title"], "커리어 상담")
        self.assertEqual(payload["status"], "active")
        self.assertEqual(payload["message_count"], 0)
        self.assertEqual(payload["version"], 1)
        self.assertIn("+00:00", payload["created_at"])

    def test_same_client_request_id_does_not_create_duplicate(self) -> None:
        request_id = str(uuid4())
        request_body = {
            "title": "중복 방지 대화",
            "client_request_id": request_id,
        }

        first = self.client.post(
            "/api/v2/conversations",
            json=request_body,
        )
        second = self.client.post(
            "/api/v2/conversations",
            json=request_body,
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["id"], second.json()["id"])

        with self.session_factory() as database:
            stored_count = database.query(models.Conversation).count()
        self.assertEqual(stored_count, 1)

    def test_list_and_get_conversations(self) -> None:
        created = self.create_conversation(title="조회할 대화").json()

        list_response = self.client.get("/api/v2/conversations")
        detail_response = self.client.get(
            f"/api/v2/conversations/{created['id']}"
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["total_count"], 1)
        self.assertEqual(
            list_response.json()["items"][0]["id"],
            created["id"],
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["title"], "조회할 대화")

    def test_new_conversation_has_empty_message_history(self) -> None:
        conversation = self.create_conversation().json()

        response = self.client.get(
            f"/api/v2/conversations/{conversation['id']}/messages"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "items": [],
                "total_count": 0,
                "next_cursor": None,
            },
        )

    def test_send_message_saves_user_and_assistant_messages(self) -> None:
        conversation = self.create_conversation().json()
        request_id = str(uuid4())

        response = self.client.post(
            f"/api/v2/conversations/{conversation['id']}/messages",
            json={
                "content": "이직 준비를 어떻게 시작할까?",
                "intent": "question",
                "attachment_ids": [],
                "response_mode": "complete",
                "client_request_id": request_id,
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()["content"],
            "AI 답변: 이직 준비를 어떻게 시작할까?",
        )
        self.assertEqual(response.json()["role"], "assistant")
        self.assertTrue(response.json()["request_message_id"].startswith("MSG-"))

        history = self.client.get(
            f"/api/v2/conversations/{conversation['id']}/messages"
        ).json()
        self.assertEqual(history["total_count"], 2)
        self.assertEqual(
            [message["role"] for message in history["items"]],
            ["user", "assistant"],
        )
        self.assertEqual(
            [message["sequence"] for message in history["items"]],
            [1, 2],
        )
        self.assertEqual(
            self.chatbot.requests[0].user_display_name,
            "테스트 사용자",
        )

    def test_message_retry_returns_existing_answer(self) -> None:
        conversation = self.create_conversation().json()
        request_body = {
            "content": "같은 요청",
            "intent": "auto",
            "client_request_id": str(uuid4()),
        }
        endpoint = (
            f"/api/v2/conversations/{conversation['id']}/messages"
        )

        first = self.client.post(endpoint, json=request_body)
        second = self.client.post(endpoint, json=request_body)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(self.chatbot.invoke_count, 1)

    def test_saved_messages_are_restored_into_next_ai_request(self) -> None:
        conversation = self.create_conversation().json()
        endpoint = (
            f"/api/v2/conversations/{conversation['id']}/messages"
        )

        self.client.post(
            endpoint,
            json={
                "content": "저는 데이터 분석가로 일했어요.",
                "intent": "auto",
                "client_request_id": str(uuid4()),
            },
        )
        self.client.post(
            endpoint,
            json={
                "content": "방금 말한 직무가 뭐였지?",
                "intent": "auto",
                "client_request_id": str(uuid4()),
            },
        )

        second_request = self.chatbot.requests[1]
        self.assertEqual(
            [message.role for message in second_request.history],
            ["user", "assistant"],
        )
        self.assertEqual(
            [message.content for message in second_request.history],
            [
                "저는 데이터 분석가로 일했어요.",
                "AI 답변: 저는 데이터 분석가로 일했어요.",
            ],
        )
        self.assertNotIn(
            "방금 말한 직무가 뭐였지?",
            [message.content for message in second_request.history],
        )

    def test_stream_sends_deltas_and_saves_completed_message(self) -> None:
        conversation = self.create_conversation().json()

        with self.client.stream(
            "POST",
            f"/api/v2/conversations/{conversation['id']}/messages/stream",
            json={
                "content": "실시간으로 답해줘",
                "intent": "auto",
                "response_mode": "stream",
                "client_request_id": str(uuid4()),
            },
        ) as response:
            stream_text = "".join(response.iter_text())

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        self.assertIn("event: message.accepted", stream_text)
        self.assertIn("event: intent.resolved", stream_text)
        self.assertEqual(stream_text.count("event: assistant.delta"), 2)
        self.assertIn("event: message.completed", stream_text)

        history = self.client.get(
            f"/api/v2/conversations/{conversation['id']}/messages"
        ).json()
        self.assertEqual(history["total_count"], 2)
        self.assertEqual(history["items"][1]["status"], "completed")
        self.assertEqual(
            history["items"][1]["content"],
            "AI 답변: 실시간으로 답해줘",
        )

    def test_unconnected_intent_is_rejected_before_message_save(self) -> None:
        conversation = self.create_conversation().json()

        response = self.client.post(
            f"/api/v2/conversations/{conversation['id']}/messages",
            json={
                "content": "경험을 정리해줘",
                "intent": "experience",
                "client_request_id": str(uuid4()),
            },
        )

        self.assertEqual(response.status_code, 501)
        self.assertEqual(
            response.json()["error"]["message"],
            (
                "경험 정리 기능은 아직 메시지 API에 연결되지 않았습니다. "
                "현재는 자동, 일반 질문, 조언을 사용할 수 있습니다."
            ),
        )
        history = self.client.get(
            f"/api/v2/conversations/{conversation['id']}/messages"
        ).json()
        self.assertEqual(history["total_count"], 0)

    def test_unavailable_job_analysis_uses_user_friendly_message(
        self,
    ) -> None:
        conversation = self.create_conversation().json()

        response = self.client.post(
            f"/api/v2/conversations/{conversation['id']}/messages",
            json={
                "content": "공고를 분석해줘",
                "intent": "job",
                "client_request_id": str(uuid4()),
            },
        )

        self.assertEqual(response.status_code, 501)
        self.assertEqual(
            response.json()["error"]["message"],
            "공고 분석 기능은 아직 제공되지 않아요!",
        )

    def test_update_conversation_checks_and_increases_version(self) -> None:
        conversation = self.create_conversation(title="변경 전").json()

        response = self.client.patch(
            f"/api/v2/conversations/{conversation['id']}",
            json={
                "title": "변경 후",
                "base_version": conversation["version"],
                "client_request_id": str(uuid4()),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "변경 후")
        self.assertEqual(
            response.json()["version"],
            conversation["version"] + 1,
        )

    def test_update_with_old_version_is_rejected(self) -> None:
        conversation = self.create_conversation().json()

        response = self.client.patch(
            f"/api/v2/conversations/{conversation['id']}",
            json={
                "title": "충돌",
                "base_version": conversation["version"] + 1,
                "client_request_id": str(uuid4()),
            },
        )

        self.assertEqual(response.status_code, 409)

    def test_delete_conversation_also_deletes_messages(self) -> None:
        conversation = self.create_conversation().json()
        message_response = self.client.post(
            f"/api/v2/conversations/{conversation['id']}/messages",
            json={
                "content": "삭제할 대화",
                "intent": "auto",
                "client_request_id": str(uuid4()),
            },
        )
        current = self.client.get(
            f"/api/v2/conversations/{conversation['id']}"
        ).json()

        response = self.client.request(
            "DELETE",
            f"/api/v2/conversations/{conversation['id']}",
            json={
                "version": current["version"],
                "client_request_id": str(uuid4()),
            },
        )

        self.assertEqual(message_response.status_code, 201)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted_id"], conversation["id"])
        with self.session_factory() as database:
            message_count = database.query(models.Message).count()
        self.assertEqual(message_count, 0)

    def test_unknown_conversation_returns_not_found(self) -> None:
        response = self.client.get(
            "/api/v2/conversations/CONV-does-not-exist"
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")
        self.assertEqual(
            response.json()["error"]["message"],
            "대화를 찾을 수 없습니다.",
        )

    def test_other_user_cannot_read_conversation_by_id(self) -> None:
        conversation = self.create_conversation().json()
        self.current_user.id = "USER-other"

        response = self.client.get(
            f"/api/v2/conversations/{conversation['id']}"
        )

        self.assertEqual(response.status_code, 404)

    def test_invalid_request_returns_frontend_error_envelope(self) -> None:
        response = self.client.post(
            "/api/v2/conversations",
            json={
                "title": "잘못된 요청 ID",
                "client_request_id": "not-a-uuid",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["error"]["code"],
            "VALIDATION_ERROR",
        )
        self.assertTrue(response.json()["error"]["field_errors"])


if __name__ == "__main__":
    unittest.main()
