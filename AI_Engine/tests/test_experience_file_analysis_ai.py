"""경험 파일의 선행 요약·청크 분석 파이프라인을 검증한다."""

from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from AI_Engine.experience_file_analysis_ai import (
    FILE_ANALYSIS_TOOL_NAME,
    ExperienceFileAnalysisAI,
)
from AI_Engine.schemas import EvidenceSource


class FakeResponses:
    def __init__(self, payload) -> None:
        self.payload = payload
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output=[
            SimpleNamespace(
                type="function_call",
                name=FILE_ANALYSIS_TOOL_NAME,
                arguments=json.dumps(self.payload, ensure_ascii=False),
            )
        ])


class FakeClient:
    def __init__(self, payload) -> None:
        self.responses = FakeResponses(payload)


def file_source(text: str) -> EvidenceSource:
    return EvidenceSource(
        id="source-file-1",
        type="file",
        title="서비스 기획안",
        attachment_id="attachment-1",
        filename="service-plan.pdf",
        mime_type="application/pdf",
        text=text,
    )


class ExperienceFileAnalysisAITests(unittest.TestCase):
    def create_ai(self, payload):
        client = FakeClient(payload)
        return (
            ExperienceFileAnalysisAI(
                client=client,
                model_version="test-model",
            ),
            client,
        )

    def test_file_is_summarized_before_final_experience_structuring(self) -> None:
        original = (
            "[1페이지]\n결제 단계를 5단계에서 3단계로 줄였습니다. "
            "결제 완료율이 14% 증가했습니다."
        )
        payload = {
            "summary": "결제 절차를 개선한 서비스 기획 내용입니다.",
            "experience_signals": [{
                "title": "결제 절차 개선",
                "summary": "결제 단계를 단축했습니다.",
                "details": ["5단계를 3단계로 축소"],
                "excerpts": [{
                    "quote": "결제 단계를 5단계에서 3단계로 줄였습니다.",
                    "page_number": 1,
                }],
            }],
            "key_facts": [{
                "text": "결제 완료율 14% 증가",
                "quote": "결제 완료율이 14% 증가했습니다.",
                "page_number": 1,
            }],
        }
        ai, client = self.create_ai(payload)

        result = ai.analyze_source(file_source(original))

        self.assertEqual(result.source_ref_id, "source-file-1")
        self.assertEqual(result.chunk_count, 1)
        self.assertEqual(len(result.experience_signals), 1)
        self.assertEqual(len(result.key_facts), 1)
        self.assertEqual(len(client.responses.calls), 1)
        self.assertIn(
            "[파일 원문 청크]",
            client.responses.calls[0]["input"],
        )

    def test_long_file_is_analyzed_in_multiple_chunks(self) -> None:
        original = "운영 지표를 정의하고 대시보드를 기획했습니다.\n" * 80
        payload = {
            "summary": "운영 대시보드 관련 내용입니다.",
            "experience_signals": [],
            "key_facts": [],
        }
        ai, client = self.create_ai(payload)

        with patch.dict(os.environ, {
            "AI_EXPERIENCE_FILE_ANALYSIS_CHUNK_TOKENS": "500",
            "AI_EXPERIENCE_FILE_ANALYSIS_CHUNK_OVERLAP_TOKENS": "0",
        }):
            result = ai.analyze_source(file_source(original))

        self.assertGreater(result.chunk_count, 1)
        self.assertEqual(
            len(client.responses.calls),
            result.chunk_count,
        )

    def test_quote_not_found_in_original_is_not_kept_as_evidence(self) -> None:
        payload = {
            "summary": "서비스 기획 내용입니다.",
            "experience_signals": [{
                "title": "서비스 개선",
                "summary": "서비스를 개선했습니다.",
                "details": [],
                "excerpts": [{
                    "quote": "원문에 없는 성과입니다.",
                    "page_number": None,
                }],
            }],
            "key_facts": [{
                "text": "매출 100% 증가",
                "quote": "원문에 없는 성과입니다.",
                "page_number": None,
            }],
        }
        ai, _client = self.create_ai(payload)

        result = ai.analyze_source(
            file_source("서비스 화면을 기획했습니다.")
        )

        self.assertEqual(result.experience_signals[0].excerpts, [])
        self.assertEqual(result.key_facts, [])


if __name__ == "__main__":
    unittest.main()
