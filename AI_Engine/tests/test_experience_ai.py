"""experience_ai.py의 strict function calling과 스키마 변환을 검증한다."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from AI_Engine.experience_ai import (
    EXPERIENCE_DRAFT_TOOL,
    EXPERIENCE_DRAFT_TOOL_NAME,
    EXPERIENCE_SYSTEM_PROMPT,
    ExperienceAI,
    ExperienceAIInputError,
    ExperienceAIOutputError,
)
from AI_Engine.schemas import (
    EvidenceSource,
    ExperienceExtractionRequest,
)


FIXED_TIME = datetime(2026, 7, 25, 15, 0, tzinfo=timezone.utc)


class FakeResponses:
    """OpenAI client.responses.create와 같은 최소 테스트 인터페이스."""

    def __init__(self, payload=None, *, output=None) -> None:
        self.payload = (
            {"experience_drafts": []}
            if payload is None
            else payload
        )
        self.output = output
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.output is not None:
            return SimpleNamespace(output=self.output)
        return SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="function_call",
                    name=EXPERIENCE_DRAFT_TOOL_NAME,
                    arguments=json.dumps(
                        self.payload,
                        ensure_ascii=False,
                    ),
                )
            ]
        )


class FakeClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.responses = responses


class IncrementingIdFactory:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> str:
        self.value += 1
        return str(self.value)


def valid_raw_draft(
    *,
    title: str = "지원 전환율 개선",
    source_ref_id: str = "source-manual-1",
):
    return {
        "domain_name": "직장 경험",
        "project_name": "커리어 플랫폼 개선",
        "organization": "ABC 테크",
        "period": {"start": "2025-01", "end": "2025-06"},
        "title": title,
        "summary": "지원 흐름을 개선했습니다.",
        "situation": "지원 단계의 이탈률이 높았습니다.",
        "actions": [
            "단계별 퍼널을 분석했습니다.",
            "두 가지 흐름을 A/B 테스트했습니다.",
        ],
        "results": ["지원 완료율을 18% 높였습니다."],
        "role": "서비스 기획",
        "skills": ["데이터 분석", "UX 기획", "A/B 테스트"],
        "skill_groups": [
            {
                "name": "데이터·분석",
                "skill_names": ["데이터 분석", "A/B 테스트"],
                "confidence": 0.9,
            }
        ],
        "facts": [
            {
                "text": "지원 완료율 18% 향상",
                "source_ref_id": source_ref_id,
                "quote": "지원 완료율을 18% 높였습니다.",
            }
        ],
        "missing_information": [],
        "source_ref_ids": [source_ref_id],
        "confidence": 0.92,
    }


class ExperiencePromptAndToolTests(unittest.TestCase):
    def test_prompt_uses_required_prompt_sections(self) -> None:
        for section in (
            "[역할 role]",
            "[목표 task]",
            "[문맥 context]",
            "[제약조건 constraint]",
            "[형식 format]",
        ):
            self.assertIn(section, EXPERIENCE_SYSTEM_PROMPT)

    def test_tool_uses_strict_json_schema(self) -> None:
        self.assertTrue(EXPERIENCE_DRAFT_TOOL["strict"])
        self.assertFalse(
            EXPERIENCE_DRAFT_TOOL["parameters"]["additionalProperties"]
        )
        draft_schema = EXPERIENCE_DRAFT_TOOL["parameters"]["properties"][
            "experience_drafts"
        ]["items"]
        self.assertFalse(draft_schema["additionalProperties"])
        self.assertEqual(
            set(draft_schema["properties"]),
            set(draft_schema["required"]),
        )


class ExperienceAITests(unittest.TestCase):
    def setUp(self) -> None:
        self.request = ExperienceExtractionRequest(
            client_request_id="request-1",
            input_type="direct_input",
            text=(
                "지원 단계 퍼널을 분석하고 A/B 테스트해 "
                "지원 완료율을 18% 높였습니다."
            ),
            manual_input_id="manual-1",
        )

    def create_ai(self, responses: FakeResponses) -> ExperienceAI:
        return ExperienceAI(
            FakeClient(responses),
            model_version="test-model-v1",
            prompt_version="test-prompt-v1",
            schema_version="test-schema-v1",
            id_factory=IncrementingIdFactory(),
            clock=lambda: FIXED_TIME,
        )

    def test_direct_text_becomes_evidence_and_one_draft(self) -> None:
        responses = FakeResponses(
            {"experience_drafts": [valid_raw_draft()]}
        )
        ai = self.create_ai(responses)

        result = ai.organize(self.request)

        self.assertEqual(len(result.experience_drafts), 1)
        self.assertEqual(result.experience_drafts[0].title, "지원 전환율 개선")
        self.assertEqual(
            result.experience_drafts[0].domain.name,
            "직장 경험",
        )
        self.assertEqual(
            result.experience_drafts[0].project.name,
            "커리어 플랫폼 개선",
        )
        self.assertEqual(
            result.experience_drafts[0].field_citations[
                "facts.0"
            ][0].source_ref_id,
            "source-manual-1",
        )
        self.assertEqual(result.sources[0].id, "source-manual-1")
        self.assertEqual(
            result.analyzed_source_ids,
            ["source-manual-1"],
        )
        self.assertEqual(result.run.status, "succeeded")

        call = responses.calls[0]
        self.assertEqual(call["model"], "test-model-v1")
        self.assertEqual(
            call["tool_choice"],
            {
                "type": "function",
                "name": EXPERIENCE_DRAFT_TOOL_NAME,
            },
        )
        self.assertEqual(call["tools"], [EXPERIENCE_DRAFT_TOOL])
        self.assertEqual(call["instructions"], EXPERIENCE_SYSTEM_PROMPT)
        self.assertIn("source_ref_id: source-manual-1", call["input"])

    def test_zero_experience_drafts_is_valid(self) -> None:
        ai = self.create_ai(
            FakeResponses({"experience_drafts": []})
        )

        result = ai.organize(self.request)

        self.assertEqual(result.experience_drafts, [])
        self.assertEqual(result.run.status, "succeeded")

    def test_multiple_experience_drafts_are_preserved(self) -> None:
        payload = {
            "experience_drafts": [
                valid_raw_draft(),
                valid_raw_draft(title="운영 지표 대시보드 기획"),
            ]
        }
        ai = self.create_ai(FakeResponses(payload))

        result = ai.organize(self.request)

        self.assertEqual(len(result.experience_drafts), 2)
        self.assertEqual(
            [draft.title for draft in result.experience_drafts],
            ["지원 전환율 개선", "운영 지표 대시보드 기획"],
        )
        self.assertNotEqual(
            result.experience_drafts[0].draft_id,
            result.experience_drafts[1].draft_id,
        )

    def test_extracted_file_text_can_be_used_as_evidence(self) -> None:
        request = ExperienceExtractionRequest(
            client_request_id="request-file",
            input_type="direct_input",
            attachment_ids=["attachment-1"],
        )
        source = EvidenceSource(
            id="source-file-1",
            type="file",
            title="성과 보고서",
            attachment_id="attachment-1",
            filename="report.txt",
            text="고객 문의 처리 시간을 20% 단축했습니다.",
        )
        payload = {
            "experience_drafts": [
                valid_raw_draft(source_ref_id="source-file-1")
            ]
        }
        responses = FakeResponses(payload)
        ai = self.create_ai(responses)

        result = ai.organize(request, sources=[source])

        self.assertEqual(result.sources[0].filename, "report.txt")
        self.assertEqual(result.analyzed_source_ids, ["source-file-1"])
        self.assertIn(
            "고객 문의 처리 시간을 20% 단축했습니다.",
            responses.calls[0]["input"],
        )

    def test_attachment_without_evidence_source_is_rejected(self) -> None:
        request = ExperienceExtractionRequest(
            client_request_id="request-file",
            input_type="direct_input",
            attachment_ids=["attachment-missing"],
        )
        ai = self.create_ai(FakeResponses())

        with self.assertRaises(ExperienceAIInputError):
            ai.organize(request)

    def test_unknown_source_reference_is_rejected(self) -> None:
        payload = {
            "experience_drafts": [
                valid_raw_draft(source_ref_id="source-unknown")
            ]
        }
        ai = self.create_ai(FakeResponses(payload))

        with self.assertRaises(ExperienceAIOutputError):
            ai.organize(self.request)

    def test_missing_function_call_is_rejected(self) -> None:
        ai = self.create_ai(
            FakeResponses(
                output=[
                    SimpleNamespace(
                        type="message",
                        name=None,
                        arguments=None,
                    )
                ]
            )
        )

        with self.assertRaises(ExperienceAIOutputError):
            ai.organize(self.request)


if __name__ == "__main__":
    unittest.main()
