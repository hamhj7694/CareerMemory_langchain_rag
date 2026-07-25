"""job_analysis_ai.py의 요구사항 추출과 경험 RAG 추천을 검증한다."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from AI_Engine.job_analysis_ai import (
    JOB_MATCH_SYSTEM_PROMPT,
    JOB_MATCH_TOOL,
    JOB_MATCH_TOOL_NAME,
    JOB_REQUIREMENT_SYSTEM_PROMPT,
    JOB_REQUIREMENT_TOOL,
    JOB_REQUIREMENT_TOOL_NAME,
    JobAnalysisAI,
    JobAnalysisAIOutputError,
)
from AI_Engine.schemas import JobAnalysisRequest


FIXED_TIME = datetime(2026, 7, 25, 17, 0, tzinfo=timezone.utc)
POSTING_CONTENT = (
    "사용자 전환 퍼널을 분석하고 개선 과제를 도출한 경험이 있는 분\n"
    "개발·디자인 조직과 원활하게 협업할 수 있는 분"
)


class FakeResponses:
    """호출된 함수 이름에 맞는 구조화 결과를 차례로 반환한다."""

    def __init__(self, payloads) -> None:
        self.payloads = list(payloads)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.payloads:
            raise AssertionError("준비된 가짜 응답이 없습니다.")
        payload = self.payloads.pop(0)
        tool_name = kwargs["tools"][0]["name"]
        return SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="function_call",
                    name=tool_name,
                    arguments=json.dumps(payload, ensure_ascii=False),
                )
            ]
        )


class FakeClient:
    def __init__(self, payloads) -> None:
        self.responses = FakeResponses(payloads)


class FakeRetriever:
    def __init__(self, documents) -> None:
        self.documents = documents
        self.queries = []

    def invoke(self, query):
        self.queries.append(query)
        return self.documents


class IncrementingIdFactory:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> str:
        self.value += 1
        return str(self.value)


def raw_requirement(
    *,
    title: str = "데이터 기반 서비스 개선",
    source: str = "posting_content",
    source_excerpt: str = (
        "사용자 전환 퍼널을 분석하고 개선 과제를 도출한 경험이 있는 분"
    ),
):
    return {
        "type": "qualification",
        "title": title,
        "summary": "퍼널 지표를 분석하고 개선안을 실행할 수 있어야 합니다.",
        "source": source,
        "source_excerpt": source_excerpt,
        "importance": "required",
        "keywords": ["퍼널 분석", "전환율", "서비스 개선"],
        "confidence": 0.94,
    }


class JobAnalysisPromptAndToolTests(unittest.TestCase):
    def test_prompts_use_required_sections(self) -> None:
        for prompt in (
            JOB_REQUIREMENT_SYSTEM_PROMPT,
            JOB_MATCH_SYSTEM_PROMPT,
        ):
            for section in (
                "[역할 role]",
                "[목표 task]",
                "[문맥 context]",
                "[제약조건 constraint]",
                "[형식 format]",
            ):
                self.assertIn(section, prompt)

    def test_tools_use_strict_json_schema(self) -> None:
        for tool, array_name in (
            (JOB_REQUIREMENT_TOOL, "requirements"),
            (JOB_MATCH_TOOL, "experience_links"),
        ):
            self.assertTrue(tool["strict"])
            self.assertFalse(
                tool["parameters"]["additionalProperties"]
            )
            item_schema = tool["parameters"]["properties"][
                array_name
            ]["items"]
            self.assertFalse(item_schema["additionalProperties"])
            self.assertEqual(
                set(item_schema["properties"]),
                set(item_schema["required"]),
            )


class JobAnalysisAITests(unittest.TestCase):
    def setUp(self) -> None:
        self.request = JobAnalysisRequest(
            client_request_id="request-1",
            posting_id="posting-1",
            company_name="넥스트랩",
            role_name="서비스 기획자",
            posting_title="2026년 서비스 기획자 채용",
            source_url="https://example.com/jobs/123",
            posting_content=POSTING_CONTENT,
        )

    def create_ai(
        self,
        payloads,
        *,
        retriever=None,
    ) -> tuple[JobAnalysisAI, FakeClient]:
        client = FakeClient(payloads)
        ai = JobAnalysisAI(
            client,
            experience_retriever=retriever,
            model_version="test-model-v1",
            prompt_version="test-prompt-v1",
            schema_version="test-schema-v1",
            index_version="test-index-v1",
            id_factory=IncrementingIdFactory(),
            clock=lambda: FIXED_TIME,
        )
        return ai, client

    def test_requirement_analysis_without_retriever(self) -> None:
        ai, client = self.create_ai(
            [{"requirements": [raw_requirement()]}]
        )

        result = ai.invoke(self.request)

        self.assertEqual(len(result.requirements), 1)
        requirement = result.requirements[0]
        self.assertEqual(requirement.id, "job-requirement-1")
        self.assertEqual(requirement.order, 1)
        self.assertEqual(
            requirement.source_locator.start_offset,
            POSTING_CONTENT.find(requirement.source_excerpt),
        )
        self.assertEqual(result.experience_links, [])
        self.assertIn("검색기가 연결되지 않아", result.warnings[0])
        self.assertEqual(result.analysis_id, "job-analysis-2")
        self.assertEqual(result.model_version, "test-model-v1")
        self.assertEqual(result.prompt_version, "test-prompt-v1")
        self.assertEqual(result.schema_version, "test-schema-v1")
        self.assertEqual(result.index_version, "test-index-v1")

        call = client.responses.calls[0]
        self.assertEqual(call["tool_choice"], "auto")
        self.assertEqual(call["tools"], [JOB_REQUIREMENT_TOOL])
        self.assertEqual(
            call["instructions"],
            JOB_REQUIREMENT_SYSTEM_PROMPT,
        )
        self.assertIn(POSTING_CONTENT, call["input"])

    def test_requirement_is_matched_with_rag_candidate(self) -> None:
        document = SimpleNamespace(
            page_content=(
                "지원 단계 퍼널을 분석하고 입력 흐름을 개선해 "
                "지원 완료율을 18% 높였습니다."
            ),
            metadata={
                "experience_id": "experience-1",
                "title": "지원 전환율 개선",
                "domain_name": "직장 경험",
                "project_name": "커리어 플랫폼 개선",
                "evidence_ids": ["evidence-1"],
            },
        )
        retriever = FakeRetriever([document])
        match_payload = {
            "experience_links": [
                {
                    "requirement_id": "job-requirement-1",
                    "experience_id": "experience-1",
                    "similarity_score": 0.88,
                    "reason": "퍼널 분석과 전환율 개선 경험이 관련됩니다.",
                    "evidence_ids": ["evidence-1"],
                }
            ]
        }
        ai, client = self.create_ai(
            [
                {"requirements": [raw_requirement()]},
                match_payload,
            ],
            retriever=retriever,
        )

        result = ai.invoke(self.request)

        self.assertEqual(len(result.experience_links), 1)
        link = result.experience_links[0]
        self.assertEqual(link.requirement_id, "job-requirement-1")
        self.assertEqual(link.experience_id, "experience-1")
        self.assertEqual(link.source, "ai")
        self.assertEqual(link.status, "suggested")
        self.assertEqual(link.evidence_ids, ["evidence-1"])
        self.assertIn("퍼널", retriever.queries[0])

        match_call = client.responses.calls[1]
        self.assertEqual(match_call["tools"], [JOB_MATCH_TOOL])
        self.assertEqual(
            match_call["instructions"],
            JOB_MATCH_SYSTEM_PROMPT,
        )
        self.assertIn("experience-1", match_call["input"])

    def test_zero_requirements_is_valid(self) -> None:
        retriever = FakeRetriever([])
        ai, _client = self.create_ai(
            [{"requirements": []}],
            retriever=retriever,
        )

        result = ai.invoke(self.request)

        self.assertEqual(result.requirements, [])
        self.assertEqual(result.experience_links, [])
        self.assertEqual(retriever.queries, [])

    def test_excerpt_not_in_posting_is_rejected(self) -> None:
        ai, _client = self.create_ai(
            [
                {
                    "requirements": [
                        raw_requirement(
                            source_excerpt="공고에 존재하지 않는 문장"
                        )
                    ]
                }
            ]
        )

        with self.assertRaises(JobAnalysisAIOutputError):
            ai.invoke(self.request)

    def test_match_outside_rag_candidates_is_rejected(self) -> None:
        document = SimpleNamespace(
            page_content="퍼널 분석 경험",
            metadata={
                "experience_id": "experience-1",
                "evidence_ids": ["evidence-1"],
            },
        )
        retriever = FakeRetriever([document])
        invalid_match_payload = {
            "experience_links": [
                {
                    "requirement_id": "job-requirement-1",
                    "experience_id": "experience-unknown",
                    "similarity_score": 0.9,
                    "reason": "관련 경험입니다.",
                    "evidence_ids": ["evidence-1"],
                }
            ]
        }
        ai, _client = self.create_ai(
            [
                {"requirements": [raw_requirement()]},
                invalid_match_payload,
            ],
            retriever=retriever,
        )

        with self.assertRaises(JobAnalysisAIOutputError):
            ai.invoke(self.request)

    def test_extracted_attachment_text_can_be_analyzed(self) -> None:
        attachment_excerpt = "서비스 개선 과제를 주도한 경험이 있는 분"
        request = JobAnalysisRequest(
            client_request_id="request-file",
            posting_id="posting-file",
            attachment_ids=["attachment-1"],
        )
        ai, _client = self.create_ai(
            [
                {
                    "requirements": [
                        raw_requirement(
                            source="attachment-1",
                            source_excerpt=attachment_excerpt,
                        )
                    ]
                }
            ]
        )

        result = ai.invoke(
            request,
            attachment_texts={
                "attachment-1": attachment_excerpt,
            },
        )

        self.assertEqual(
            result.requirements[0].source_locator.source,
            "attachment-1",
        )


if __name__ == "__main__":
    unittest.main()
