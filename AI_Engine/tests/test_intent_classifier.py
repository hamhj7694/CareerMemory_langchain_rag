"""자동 모드가 단어 필터가 아닌 실행 의도 분류 결과를 사용하는지 검증한다."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from AI_Engine.intent_classifier import AutoIntentClassifier
from AI_Engine.schemas import AIRouteRequest


class FakeResponses:
    def __init__(self, payload) -> None:
        self.payload = payload
        self.calls = 0
        self.responses = self

    def create(self, **_kwargs):
        self.calls += 1
        return SimpleNamespace(output=[
            SimpleNamespace(
                type="function_call",
                name="classify_career_memory_intent",
                arguments=json.dumps(self.payload, ensure_ascii=False),
            )
        ])


class IntentClassifierTests(unittest.TestCase):
    def test_general_experience_question_stays_in_chat_without_model_call(self) -> None:
        client = FakeResponses({})
        classifier = AutoIntentClassifier(client=client)

        decision = classifier.decide(AIRouteRequest(
            request_id="request-1",
            request_type="auto",
            text="내 경험에서 어떤 강점을 찾을 수 있을까?",
        ))

        self.assertEqual(decision.route, "chat")
        self.assertEqual(client.calls, 0)

    def test_explicit_organize_request_uses_model_decision(self) -> None:
        client = FakeResponses({
            "route": "experience_extraction",
            "confidence": 0.96,
            "reason": "현재 입력을 경험 초안으로 만들어 달라는 실행 요청입니다.",
        })
        classifier = AutoIntentClassifier(client=client)

        decision = classifier.decide(AIRouteRequest(
            request_id="request-2",
            request_type="auto",
            text="이 내용을 경험 형식으로 구조화해서 초안으로 만들어 줘",
        ))

        self.assertEqual(decision.route, "experience_extraction")
        self.assertEqual(client.calls, 1)

    def test_low_confidence_uses_chat_fallback(self) -> None:
        client = FakeResponses({
            "route": "job_analysis",
            "confidence": 0.4,
            "reason": "분석 실행인지 상담인지 불분명합니다.",
        })
        classifier = AutoIntentClassifier(client=client)

        decision = classifier.decide(AIRouteRequest(
            request_id="request-3",
            request_type="auto",
            text="이 공고를 분석해 줘도 될까?",
        ))

        self.assertEqual(decision.route, "chat")
        self.assertEqual(decision.source, "fallback")


if __name__ == "__main__":
    unittest.main()
