"""chatbot_ai.py의 create_agent 실행 흐름을 검증한다."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, AIMessageChunk
from langgraph.checkpoint.memory import InMemorySaver

from AI_Engine.chatbot_ai import (
    CHATBOT_PROMPT_VERSION,
    CHATBOT_SCHEMA_VERSION,
    CHATBOT_SYSTEM_PROMPT,
    DEFAULT_CHATBOT_MODEL,
    ChatbotAI,
    ChatbotAIInputError,
    create_chatbot_agent,
)
from AI_Engine.schemas import ChatMessage, ChatRequest


FIXED_TIME = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


class FakeAgent:
    def __init__(self, *, answer: str = "함께 정리해 볼게요.") -> None:
        self.answer = answer
        self.invoke_input = None
        self.invoke_config = None
        self.stream_input = None
        self.stream_config = None
        self.stream_mode = None

    def invoke(self, agent_input, config=None):
        self.invoke_input = agent_input
        self.invoke_config = config
        return {"messages": [AIMessage(content=self.answer)]}

    def stream(self, agent_input, config=None, stream_mode=None):
        self.stream_input = agent_input
        self.stream_config = config
        self.stream_mode = stream_mode
        yield AIMessageChunk(content="함께 "), {"node": "model"}
        yield AIMessageChunk(content="살펴볼게요."), {"node": "model"}


class FailingStreamAgent(FakeAgent):
    def stream(self, agent_input, config=None, stream_mode=None):
        raise RuntimeError("provider failure")
        yield


class IncrementingIdFactory:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> str:
        self.value += 1
        return str(self.value)


class ChatbotAgentFactoryTests(unittest.TestCase):
    def test_system_prompt_uses_required_prompt_sections(self) -> None:
        for section in (
            "[역할 role]",
            "[목표 task]",
            "[문맥 context]",
            "[대화 전략 conversation strategy]",
            "[제약조건 constraint]",
            "[형식 format]",
        ):
            self.assertIn(section, CHATBOT_SYSTEM_PROMPT)

    def test_system_prompt_requires_proactive_but_focused_dialogue(self) -> None:
        self.assertIn("구체적인 질문", CHATBOT_SYSTEM_PROMPT)
        self.assertIn("핵심 질문은 하나만", CHATBOT_SYSTEM_PROMPT)
        self.assertIn(
            "“어떤 도움이 필요하세요?”",
            CHATBOT_SYSTEM_PROMPT,
        )
        self.assertIn("사용자가 “내가 누구게?”라고 물으면", CHATBOT_SYSTEM_PROMPT)
        self.assertIn("마크다운 bullet(`-`)", CHATBOT_SYSTEM_PROMPT)
        self.assertIn("마크다운 굵은 글씨(`**내용**`)", CHATBOT_SYSTEM_PROMPT)
        self.assertIn("문단 사이에는 빈 줄", CHATBOT_SYSTEM_PROMPT)

    @patch("AI_Engine.chatbot_ai.create_agent")
    def test_agent_uses_required_components(self, create_agent_mock) -> None:
        model = MagicMock(name="model")
        memory = InMemorySaver()

        agent = create_chatbot_agent(model=model, memory=memory)

        create_agent_mock.assert_called_once_with(
            model=model,
            tools=[],
            checkpointer=memory,
            system_prompt=CHATBOT_SYSTEM_PROMPT,
        )
        self.assertIs(agent, create_agent_mock.return_value)


class ChatbotAITests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = FakeAgent()
        self.chatbot = ChatbotAI(
            self.agent,
            model_version="test-model-v1",
            prompt_version="test-prompt-v1",
            schema_version="test-schema-v1",
            id_factory=IncrementingIdFactory(),
            clock=lambda: FIXED_TIME,
        )
        self.request = ChatRequest(
            client_request_id="request-1",
            conversation_id="conversation-1",
            message_id="user-message-1",
            sequence=0,
            content="내 강점을 어떻게 설명하면 좋을까?",
        )

    def test_invoke_uses_conversation_id_as_thread_id(self) -> None:
        response = self.chatbot.invoke(self.request)

        self.assertEqual(
            self.agent.invoke_input,
            {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "[대화 단계]\n"
                            "새 대화의 첫 사용자 메시지입니다. 인사나 모호한 입력이면 "
                            "Career Memory가 무엇을 돕는지 짧게 소개하고, 사용자가 바로 "
                            "답할 수 있는 구체적인 질문 하나로 대화를 시작하세요. "
                            "요청이 명확하면 소개보다 요청에 대한 답을 우선하세요."
                        ),
                    },
                    {
                        "role": "user",
                        "content": "내 강점을 어떻게 설명하면 좋을까?",
                    }
                ]
            },
        )
        self.assertEqual(
            self.agent.invoke_config,
            {"configurable": {"thread_id": "conversation-1"}},
        )
        self.assertEqual(response.message.content, "함께 정리해 볼게요.")
        self.assertEqual(response.message.sequence, 1)
        self.assertEqual(response.citations, [])
        self.assertEqual(response.suggested_actions, [])
        self.assertEqual(response.model_version, "test-model-v1")
        self.assertEqual(response.prompt_version, "test-prompt-v1")
        self.assertEqual(response.schema_version, "test-schema-v1")

    def test_invoke_sends_saved_history_before_current_message(self) -> None:
        request = self.request.model_copy(
            update={
                "history": [
                    ChatMessage(
                        id="user-message-old",
                        conversation_id="conversation-1",
                        sequence=1,
                        role="user",
                        content="저는 데이터 분석 업무를 했어요.",
                        created_at=FIXED_TIME,
                    ),
                    ChatMessage(
                        id="assistant-message-old",
                        conversation_id="conversation-1",
                        sequence=2,
                        role="assistant",
                        content="어떤 성과가 있었나요?",
                        created_at=FIXED_TIME,
                    ),
                ]
            }
        )

        self.chatbot.invoke(request)

        self.assertEqual(
            self.agent.invoke_input["messages"],
            [
                {
                    "role": "user",
                    "content": "저는 데이터 분석 업무를 했어요.",
                },
                {
                    "role": "assistant",
                    "content": "어떤 성과가 있었나요?",
                },
                {
                    "role": "user",
                    "content": "내 강점을 어떻게 설명하면 좋을까?",
                },
            ],
        )

    def test_invoke_sends_only_account_display_name_as_system_context(
        self,
    ) -> None:
        request = self.request.model_copy(
            update={"user_display_name": "홍길동"}
        )

        self.chatbot.invoke(request)

        messages = self.agent.invoke_input["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("홍길동", messages[0]["content"])
        self.assertNotIn("user@example.com", messages[0]["content"])
        self.assertEqual(messages[-1]["role"], "user")

    def test_first_turn_adds_onboarding_phase_context(self) -> None:
        request = self.request.model_copy(update={"sequence": 1})

        self.chatbot.invoke(request)

        messages = self.agent.invoke_input["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("[대화 단계]", messages[0]["content"])
        self.assertIn("새 대화의 첫 사용자 메시지", messages[0]["content"])

    def test_follow_up_turn_does_not_repeat_onboarding_phase_context(
        self,
    ) -> None:
        request = self.request.model_copy(
            update={
                "sequence": 2,
                "history": [
                    ChatMessage(
                        id="user-message-old",
                        conversation_id="conversation-1",
                        sequence=1,
                        role="user",
                        content="안녕",
                        created_at=FIXED_TIME,
                    ),
                ],
            }
        )

        self.chatbot.invoke(request)

        messages = self.agent.invoke_input["messages"]
        self.assertFalse(
            any(
                message["role"] == "system"
                and "[대화 단계]" in message["content"]
                for message in messages
            )
        )

    def test_default_versions_use_chatbot_constants(self) -> None:
        chatbot = ChatbotAI(
            self.agent,
            id_factory=IncrementingIdFactory(),
            clock=lambda: FIXED_TIME,
        )

        response = chatbot.invoke(self.request)

        self.assertEqual(response.model_version, DEFAULT_CHATBOT_MODEL)
        self.assertEqual(
            response.prompt_version,
            CHATBOT_PROMPT_VERSION,
        )
        self.assertEqual(
            response.schema_version,
            CHATBOT_SCHEMA_VERSION,
        )

    def test_explicit_chat_mode_is_executed_by_chatbot(self) -> None:
        request = self.request.model_copy(update={"mode": "chat"})

        response = self.chatbot.invoke(request)

        self.assertEqual(response.message.content, "함께 정리해 볼게요.")

    def test_explicit_experience_mode_is_not_executed_by_chatbot(self) -> None:
        request = self.request.model_copy(
            update={"mode": "experience_extraction"}
        )

        with self.assertRaises(ChatbotAIInputError):
            self.chatbot.invoke(request)

    def test_attachment_only_request_does_not_claim_file_was_read(self) -> None:
        request = ChatRequest(
            client_request_id="request-file",
            conversation_id="conversation-file",
            message_id="user-file",
            sequence=0,
            attachment_ids=["attachment-1"],
        )

        self.chatbot.invoke(request)

        content = self.agent.invoke_input["messages"][-1]["content"]
        self.assertIn("파일을 첨부", content)
        self.assertIn("내용을 추측하지 마세요", content)

    def test_stream_uses_message_stream_mode(self) -> None:
        events = list(self.chatbot.stream(self.request))

        self.assertEqual(
            [event.type for event in events],
            ["started", "token", "token", "completed"],
        )
        self.assertEqual(
            self.agent.stream_config,
            {"configurable": {"thread_id": "conversation-1"}},
        )
        self.assertEqual(self.agent.stream_mode, "messages")
        self.assertEqual(
            events[-1].response.message.content,
            "함께 살펴볼게요.",
        )

    def test_stream_failure_returns_safe_error_event(self) -> None:
        chatbot = ChatbotAI(
            FailingStreamAgent(),
            model_version="test-model-v1",
            id_factory=IncrementingIdFactory(),
            clock=lambda: FIXED_TIME,
        )

        events = list(chatbot.stream(self.request))

        self.assertEqual([event.type for event in events], ["started", "error"])
        self.assertEqual(events[-1].error.code, "chat_model_error")
        self.assertNotIn("provider failure", events[-1].error.message)

    def test_stream_invalid_mode_returns_non_retryable_input_error(self) -> None:
        request = self.request.model_copy(
            update={"mode": "job_analysis"}
        )

        events = list(self.chatbot.stream(request))

        self.assertEqual([event.type for event in events], ["started", "error"])
        self.assertEqual(events[-1].error.code, "invalid_request")
        self.assertFalse(events[-1].error.retryable)


if __name__ == "__main__":
    unittest.main()
