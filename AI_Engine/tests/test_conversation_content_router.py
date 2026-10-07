from __future__ import annotations

import json
from types import SimpleNamespace
import unittest

from AI_Engine.api.conversation_analysis import _needs_assistant_context
from AI_Engine.conversation_content_router import (
    AssistantConversationContext,
    ConversationContentRouterAI,
    ConversationRouteSource,
    conservative_fallback_route,
    _looks_like_complete_job_posting,
)


class _Responses:
    def __init__(self, payload):
        self.payload = payload

    def create(self, **_kwargs):
        return SimpleNamespace(output=[SimpleNamespace(
            type="function_call",
            name="route_conversation_content",
            arguments=json.dumps(self.payload, ensure_ascii=False),
        )])


class ConversationContentRouterTests(unittest.TestCase):
    def test_complete_job_guard_rejects_isolated_requirement_bullet(self):
        self.assertFalse(_looks_like_complete_job_posting(
            "LLM 활용 및 웹 개발 역량이 있고 프론트엔드와 백엔드를 다룰 수 있는 분"
        ))
        self.assertTrue(_looks_like_complete_job_posting(
            "채용공고: AI 웹 개발자\n"
            "주요 업무: 생성형 AI 기반 커리어 웹 서비스를 개발하고 운영합니다. "
            "FastAPI 백엔드와 React 프론트엔드를 구현합니다.\n"
            "자격 요건: Python API 개발 경험과 React 개발 경험이 필요합니다.\n"
            "우대 사항: LLM 애플리케이션 개발 경험"
        ))

    def test_only_short_value_answers_need_assistant_context(self):
        self.assertTrue(_needs_assistant_context("12% 높였습니다."))
        self.assertTrue(_needs_assistant_context("3개월이었습니다."))
        self.assertFalse(_needs_assistant_context("백엔드 개발자로 참여했습니다."))
        self.assertFalse(_needs_assistant_context("오늘 점심 메뉴를 추천해줘."))

    def test_routes_user_evidence_and_limits_context_to_previous_assistant(self):
        sources = [
            ConversationRouteSource(
                source_id="message:u1",
                message_id="u1",
                role="user",
                sequence=1,
                text="결제 단계를 개선했습니다.",
            ),
            ConversationRouteSource(
                source_id="message:a1",
                message_id="a1",
                role="assistant",
                sequence=2,
                text="가입 전환율은 얼마나 좋아졌나요?",
            ),
            ConversationRouteSource(
                source_id="message:u2",
                message_id="u2",
                role="user",
                sequence=3,
                text="12% 높였습니다.",
            ),
            ConversationRouteSource(
                source_id="message:a2",
                message_id="a2",
                role="assistant",
                sequence=4,
                text="매출도 50% 증가했네요.",
            ),
        ]
        payload = {
            "routes": [
                {
                    "source_index": 1,
                    "category": "experience",
                    "assistant_context_source_indexes": [],
                },
                {
                    "source_index": 3,
                    "category": "experience",
                    "assistant_context_source_indexes": [],
                },
            ],
            "job_postings": [],
        }
        router = ConversationContentRouterAI(
            client=SimpleNamespace(responses=_Responses(payload)),
            model_version="test-model",
        )

        routed = router.route(sources)

        self.assertEqual(routed.categories["message:u1"], "experience")
        self.assertEqual(routed.categories["message:u2"], "experience")
        self.assertEqual(routed.assistant_contexts, [
            AssistantConversationContext(
                source_id="message:a1",
                text="가입 전환율은 얼마나 좋아졌나요?",
                for_user_source_ids=("message:u2",),
                required_subject="가입 전환율",
            )
        ])

    def test_missing_model_route_defaults_to_uncertain(self):
        source = ConversationRouteSource(
            source_id="message:u1",
            message_id="u1",
            role="user",
            sequence=1,
            text="제가 수행한 업무입니다.",
        )
        router = ConversationContentRouterAI(
            client=SimpleNamespace(responses=_Responses({
                "routes": [],
                "job_postings": [],
            })),
            model_version="test-model",
        )

        routed = router.route([source])

        self.assertEqual(routed.categories["message:u1"], "uncertain")
        self.assertIn("message:u1", routed.experience_source_ids)

    def test_contextual_value_answer_cannot_be_discarded_as_irrelevant(self):
        sources = [
            ConversationRouteSource(
                source_id="message:a1",
                message_id="a1",
                role="assistant",
                sequence=1,
                text="가입 전환율은 얼마나 좋아졌나요?",
            ),
            ConversationRouteSource(
                source_id="message:u1",
                message_id="u1",
                role="user",
                sequence=2,
                text="12% 높였습니다.",
            ),
        ]
        router = ConversationContentRouterAI(
            client=SimpleNamespace(responses=_Responses({
                "routes": [{
                    "source_index": 2,
                    "category": "irrelevant",
                    "assistant_context_source_indexes": [],
                }],
                "job_postings": [],
            })),
            model_version="test-model",
        )

        routed = router.route(sources)

        self.assertEqual(routed.categories["message:u1"], "uncertain")
        self.assertIn("message:u1", routed.experience_source_ids)

    def test_fallback_preserves_user_content_as_uncertain(self):
        source = ConversationRouteSource(
            source_id="message:u1",
            message_id="u1",
            role="user",
            sequence=1,
            text="모호하지만 보존해야 하는 사용자 원문",
        )

        routed = conservative_fallback_route([source])

        self.assertTrue(routed.fallback_used)
        self.assertEqual(routed.categories["message:u1"], "uncertain")


if __name__ == "__main__":
    unittest.main()
