"""AI_Engine.schemas 회귀 테스트."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from AI_Engine.schemas import (
    AIRouteDecision,
    ChatRequest,
    ChatStreamEvent,
    EvidenceSource,
    ExperienceDraft,
    ExperiencePeriodDraft,
    JobAnalysisRequest,
    JobAnalysisResult,
    JobRequirement,
    JobSourceLocator,
    RequirementExperienceLink,
)
from AI_Engine.schemas.experience import ExperienceDraft as FocusedExperienceDraft
from AI_Engine.schemas.experience_job import (
    ExperienceDraft as LegacyExperienceDraft,
)
from AI_Engine.schemas.job import JobRequirement as FocusedJobRequirement


class ExperienceSchemaTests(unittest.TestCase):
    def test_public_and_legacy_imports_resolve_to_focused_models(self) -> None:
        self.assertIs(ExperienceDraft, FocusedExperienceDraft)
        self.assertIs(ExperienceDraft, LegacyExperienceDraft)
        self.assertIs(JobRequirement, FocusedJobRequirement)

    def test_evidence_uses_frontend_contract(self) -> None:
        source = EvidenceSource(
            id="source-1",
            type="message_text",
            message_id="message-1",
            text="대화 원문",
        )

        self.assertEqual(
            source.model_dump(),
            {
                "id": "source-1",
                "type": "message_text",
                "title": "",
                "message_id": "message-1",
                "manual_input_id": None,
                "attachment_id": None,
                "filename": None,
                "mime_type": None,
                "uploaded_at": None,
                "content_hash": None,
                "text": "대화 원문",
            },
        )

    def test_legacy_evidence_input_is_normalized(self) -> None:
        source = EvidenceSource(
            source_ref_id="source-1",
            source_type="conversation_message",
            message_id="message-1",
            original_text="대화 원문",
        )

        self.assertEqual(source.id, "source-1")
        self.assertEqual(source.type, "message_text")
        self.assertEqual(source.text, "대화 원문")

    def test_enum_defaults_are_serialized_as_values(self) -> None:
        draft = ExperienceDraft(
            draft_id="draft-1",
            domain={},
            project={},
        )

        self.assertEqual(draft.status, "draft")
        self.assertEqual(draft.model_dump()["status"], "draft")

    def test_identifier_cannot_be_whitespace(self) -> None:
        with self.assertRaises(ValidationError):
            ExperienceDraft(
                draft_id="   ",
                domain={},
                project={},
            )

    def test_period_end_cannot_precede_start(self) -> None:
        with self.assertRaises(ValidationError):
            ExperiencePeriodDraft(start="2026-12", end="2025-01")

    def test_content_requires_source_reference(self) -> None:
        with self.assertRaises(ValidationError):
            ExperienceDraft(
                draft_id="draft-1",
                domain={},
                project={},
                title="지원 전환율 개선",
            )

    def test_verified_fact_requires_citation(self) -> None:
        with self.assertRaises(ValidationError):
            ExperienceDraft(
                draft_id="draft-1",
                domain={},
                project={},
                facts=["지원 완료율 18% 향상"],
                source_ref_ids=["source-1"],
            )

    def test_verified_fact_with_citation_is_valid(self) -> None:
        draft = ExperienceDraft(
            draft_id="draft-1",
            domain={"name": "직장 경험"},
            project={"name": "커리어 플랫폼 개선"},
            title="지원 전환율 개선",
            facts=["지원 완료율 18% 향상"],
            source_ref_ids=["source-1"],
            field_citations={
                "facts.0": [
                    {
                        "source_ref_id": "source-1",
                        "quote": "지원 완료율을 18% 높였습니다.",
                    }
                ]
            },
        )

        self.assertEqual(draft.facts, ["지원 완료율 18% 향상"])

    def test_result_rejects_unregistered_evidence_reference(self) -> None:
        from AI_Engine.schemas import ExperienceExtractionResult, ExtractionRun

        run = ExtractionRun(
            id="run-1",
            client_request_id="request-1",
            input_type="direct_input",
            status="succeeded",
            model_version="model-v1",
            prompt_version="prompt-v1",
            schema_version="schema-v1",
        )
        draft = ExperienceDraft(
            draft_id="draft-1",
            domain={},
            project={},
            title="지원 전환율 개선",
            source_ref_ids=["source-missing"],
        )

        with self.assertRaises(ValidationError):
            ExperienceExtractionResult(run=run, experience_drafts=[draft])


class JobAnalysisSchemaTests(unittest.TestCase):
    posting_content = (
        "사용자 전환 퍼널을 분석하고 개선 과제를 도출한 경험이 있는 분"
    )

    def _requirement(self) -> JobRequirement:
        return JobRequirement(
            id="REQ-1",
            job_posting_id="JOB-1",
            type="qualification",
            title="데이터 기반 서비스 개선",
            summary="퍼널 지표를 분석하고 개선안을 실행할 수 있어야 합니다.",
            source_excerpt=self.posting_content,
            source_locator={
                "source": "posting_content",
                "start_offset": 0,
                "end_offset": len(self.posting_content),
            },
            importance="required",
            keywords=["퍼널 분석", "전환율", "서비스 개선"],
            order=1,
            confidence=0.94,
        )

    def _link(self) -> RequirementExperienceLink:
        return RequirementExperienceLink(
            requirement_id="REQ-1",
            experience_id="EXP-1",
            source="ai",
            status="suggested",
            similarity_score=0.87,
            reason="퍼널 분석과 전환율 개선 경험이 관련됩니다.",
            evidence_ids=["EVIDENCE-1"],
            model_version="job-matcher-v1",
            index_version="experience-index-v1",
        )

    def _result(
        self,
        requirement: JobRequirement,
        link: RequirementExperienceLink | None = None,
    ) -> JobAnalysisResult:
        request = JobAnalysisRequest(
            client_request_id="request-1",
            posting_id="JOB-1",
            source_url="https://example.com/jobs/123",
            posting_content=self.posting_content,
        )
        return JobAnalysisResult(
            analysis_id="analysis-1",
            client_request_id=request.client_request_id,
            job_posting=request.to_posting_draft(),
            requirements=[requirement],
            experience_links=[link] if link else [],
            analyzed_at=datetime.now(timezone.utc),
            model_version="job-analyzer-v1",
            prompt_version="job-prompt-v1",
            schema_version="schema-v1",
            index_version="experience-index-v1",
        )

    def test_complete_job_analysis_is_valid(self) -> None:
        result = self._result(self._requirement(), self._link())

        self.assertEqual(len(result.requirements), 1)
        self.assertEqual(len(result.experience_links), 1)

    def test_incomplete_url_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            JobAnalysisRequest(
                client_request_id="request-1",
                posting_id="JOB-1",
                source_url="https://",
                posting_content=self.posting_content,
            )

    def test_ai_link_requires_evidence(self) -> None:
        with self.assertRaises(ValidationError):
            RequirementExperienceLink(
                requirement_id="REQ-1",
                experience_id="EXP-1",
                source="ai",
                status="suggested",
                similarity_score=0.87,
                reason="관련 경험입니다.",
                model_version="job-matcher-v1",
                index_version="experience-index-v1",
            )

    def test_hallucinated_source_excerpt_is_rejected(self) -> None:
        requirement = self._requirement().model_copy(
            update={"source_excerpt": "공고에 존재하지 않는 원문"}
        )

        with self.assertRaises(ValidationError):
            self._result(requirement)

    def test_source_locator_must_match_excerpt(self) -> None:
        requirement = self._requirement().model_copy(
            update={
                "source_locator": JobSourceLocator(
                    source="posting_content",
                    start_offset=1,
                    end_offset=len(self.posting_content),
                )
            }
        )

        with self.assertRaises(ValidationError):
            self._result(requirement)

    def test_duplicate_requirement_experience_relation_is_rejected(self) -> None:
        link = self._link()

        with self.assertRaises(ValidationError):
            result = self._result(self._requirement(), link)
            duplicated = result.model_copy(
                update={"experience_links": [link, link]},
            )
            JobAnalysisResult.model_validate(duplicated.model_dump())


class ChatAndRoutingSchemaTests(unittest.TestCase):
    def test_chat_request_requires_content_or_attachment(self) -> None:
        with self.assertRaises(ValidationError):
            ChatRequest(
                client_request_id="request-1",
                conversation_id="conversation-1",
                message_id="message-1",
                sequence=1,
            )

    def test_chat_request_accepts_attachment_only(self) -> None:
        request = ChatRequest(
            client_request_id="request-1",
            conversation_id="conversation-1",
            message_id="message-1",
            sequence=1,
            attachment_ids=["attachment-1"],
        )

        self.assertEqual(request.attachment_ids, ["attachment-1"])

    def test_stream_event_requires_matching_payload(self) -> None:
        with self.assertRaises(ValidationError):
            ChatStreamEvent(
                event_id="event-1",
                request_id="request-1",
                conversation_id="conversation-1",
                type="token",
                sequence=1,
                created_at=datetime.now(timezone.utc),
            )

    def test_explicit_route_must_match_requested_type(self) -> None:
        with self.assertRaises(ValidationError):
            AIRouteDecision(
                request_id="request-1",
                requested_type="job_analysis",
                route="chat",
                source="explicit",
                confidence=1.0,
                reason="사용자가 공고 분석을 직접 실행했습니다.",
            )

    def test_automatic_route_records_classifier_version(self) -> None:
        decision = AIRouteDecision(
            request_id="request-1",
            requested_type="auto",
            route="chat",
            source="automatic",
            confidence=0.82,
            reason="일반적인 커리어 질문으로 판정했습니다.",
            classifier_version="intent-router-v1",
        )

        self.assertEqual(decision.route, "chat")


if __name__ == "__main__":
    unittest.main()
