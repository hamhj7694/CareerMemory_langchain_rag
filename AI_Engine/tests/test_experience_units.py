import hashlib
from types import SimpleNamespace
import unittest

from AI_Engine.experience_units import (
    build_experience_units_proposal,
    organize_segmented_sources,
    partition_analysis_sources,
    recalculate_proposal_coverage,
    segment_sources,
    validate_proposal_invariants,
)
from AI_Engine.schemas import (
    EvidenceSource,
    ExperienceExtractionInputType,
    ExperienceExtractionRequest,
)
from AI_Engine.privacy import redact_guest_text


def _source(text: str) -> EvidenceSource:
    return EvidenceSource(
        id="source-message-1",
        type="message_text",
        message_id="MESSAGE-1",
        title="사용자 메시지",
        text=text,
    )


def _numbered_source(index: int, text: str) -> EvidenceSource:
    return EvidenceSource(
        id=f"source-message-{index}",
        type="message_text",
        message_id=f"MESSAGE-{index}",
        title=f"사용자 메시지 {index}",
        text=text,
    )


class ExperienceUnitsTests(unittest.TestCase):
    def test_segment_sources_reconstructs_analysis_text_and_tracks_utf8_offsets(self):
        source = _source("# 프로젝트\r\n- 설계함\r\n- 71.43% 감소")

        segmented = segment_sources([source])
        snapshot = segmented.snapshots[0]
        reconstructed = "".join(
            source.text[span["char_start"]:span["char_end"]]
            for span in snapshot["spans"]
        )

        self.assertEqual(reconstructed, source.text)
        self.assertEqual(snapshot["byte_length"], len(source.text.encode("utf-8")))
        self.assertEqual(len(segmented.groups), 2)
        self.assertTrue(all("# 프로젝트" in group.text for group in segmented.groups))


    def test_job_posting_marks_only_the_concrete_matched_occurrence(self):
        posting = "백엔드 개발자 채용"
        source = _source(f"{posting}\n내 경험: {posting}\n")

        segmented = segment_sources(
            [source],
            job_postings_by_source_id={source.id: [posting]},
        )
        categories = [span["category"] for span in segmented.snapshots[0]["spans"]]

        self.assertEqual(categories, ["job", "unresolved"])
        self.assertIn("내 경험", segmented.groups[0].text)

    def test_guest_redacted_contact_spans_are_not_sent_as_experience_groups(self):
        text = redact_guest_text(
            "# 홍길동 | AI 엔지니어\nEmail · user@example.com\nRAG를 구현했습니다."
        )
        segmented = segment_sources([_source(text)], privacy_policy="guest_redacted")
        categories = [span["category"] for span in segmented.snapshots[0]["spans"]]

        self.assertEqual(categories[:2], ["privacy_excluded", "privacy_excluded"])
        self.assertEqual(len(segmented.analysis_sources), 1)
        self.assertIn("RAG를 구현했습니다", segmented.analysis_sources[0].text)


    def test_v2_proposal_uses_stable_units_and_original_source_references(self):
        source = _source("# Career Memory\n- RAG를 설계했다.\n- 호출을 71% 줄였다.")
        segmented = segment_sources([source])
        first_group, second_group = segmented.groups
        draft = {
        "draft_id": "DRAFT-1",
        "domain": {"name": "AI 애플리케이션"},
        "project": {"name": "Career Memory"},
        "title": "RAG 최적화",
        "summary": "근거 기반 구조를 개선했다.",
        "actions": ["RAG를 설계했다."],
        "results": ["호출을 71% 줄였다."],
        "facts": ["호출 71% 감소"],
        "source_ref_ids": [first_group.id, second_group.id],
        "field_citations": {
            "actions.0": [{
                "source_ref_id": first_group.id,
                "quote": "RAG를 설계했다.",
            }]
        },
        }
        result = SimpleNamespace(experience_drafts=[draft])

        first = build_experience_units_proposal(result, segmented, analysis_run_id="RUN-1")
        second = build_experience_units_proposal(result, segmented, analysis_run_id="RUN-1")

        self.assertEqual(first["units"][0]["unit_id"], second["units"][0]["unit_id"])
        self.assertEqual(first["units"][0]["source_ref_ids"], [source.id])
        self.assertTrue(first["units"][0]["field_citations"]["actions.0"][0]["span_id"])
        self.assertEqual(first["coverage"]["integrity_status"], "verified")
        self.assertEqual(first["coverage"]["unresolved_span_ids"], [])
        self.assertEqual(len(first["canonical_facts"]), 1)
        self.assertEqual(first["units"][0]["fact_ids"], [first["canonical_facts"][0]["fact_id"]])
        validate_proposal_invariants(first)

        first["units"] = []
        recalculated = recalculate_proposal_coverage(first)
        self.assertEqual(recalculated["experience_span_count"], 0)
        self.assertEqual(len(recalculated["unresolved_span_ids"]), 2)


    def test_v2_proposal_rejects_duplicate_primary_span_ownership(self):
        source = _source("하나의 원문")
        segmented = segment_sources([source])
        span_id = segmented.groups[0].primary_span_ids[0]
        proposal = {
        "contract_version": "experience-units-v2",
        "source_snapshots": list(segmented.snapshots),
        "units": [
            {"unit_id": "UNIT-1", "primary_span_ids": [span_id]},
            {"unit_id": "UNIT-2", "primary_span_ids": [span_id]},
        ],
        }

        with self.assertRaisesRegex(ValueError, "여러 경험"):
            validate_proposal_invariants(proposal)

    def test_long_input_batches_retain_success_and_report_failed_batch(self):
        source = _source("".join(f"- 경험 구간 {index}\n" for index in range(61)))
        segmented = segment_sources([source])
        self.assertEqual(len(partition_analysis_sources(segmented.analysis_sources)), 2)
        calls = []

        class PartialAI:
            def organize(self, _request, *, sources, **_kwargs):
                calls.append(sources)
                if len(calls) == 2:
                    raise RuntimeError("second batch failed")
                return SimpleNamespace(
                    run={"id": "RUN"},
                    experience_drafts=[],
                    sources=sources,
                    analyzed_source_ids=[item.id for item in sources],
                )

        result = organize_segmented_sources(
            PartialAI(),
            ExperienceExtractionRequest(
                client_request_id="REQUEST-1",
                input_type=ExperienceExtractionInputType.CONVERSATION,
                conversation_id="CONV-1",
                message_ids=["MESSAGE-1"],
            ),
            segmented,
        )

        self.assertEqual(len(calls), 2)
        self.assertEqual(result.failed_batch_ids, ["batch-2"])
        self.assertEqual(len(result.analyzed_source_ids), 60)

    def test_long_mixed_multi_message_input_keeps_every_character_and_unit(self):
        sources = [
            _numbered_source(
                message_index,
                "".join([
                    f"# 프로젝트 {message_index}\n",
                    *(
                        f"- [경험] 기능 {message_index}-{line_index}을 구현했습니다. "
                        f"상세 설명 {'개선 ' * 260}\n"
                        if line_index % 3 == 0
                        else f"- 잡담 또는 메모 {message_index}-{line_index}입니다. "
                        f"참고 메모 {'무관 ' * 260}\n"
                        for line_index in range(35)
                    ),
                    "\n---\n",
                ]),
            )
            for message_index in range(1, 4)
        ]
        self.assertTrue(all(len(source.text) > 24_000 for source in sources))
        segmented = segment_sources(sources)
        calls: list[list[EvidenceSource]] = []

        class MixedAI:
            def organize(self, _request, *, sources, **_kwargs):
                calls.append(list(sources))
                drafts = []
                for source in sources:
                    if "[경험]" not in (source.text or ""):
                        continue
                    drafts.append({
                        "draft_id": f"DRAFT-{source.id}",
                        "domain": {"name": "개발 경험"},
                        "project": {"name": "혼합 입력 검증"},
                        "title": source.text.strip().splitlines()[-1],
                        "summary": source.text.strip().splitlines()[-1],
                        "actions": [source.text.strip().splitlines()[-1]],
                        "results": [],
                        "facts": [],
                        "source_ref_ids": [source.id],
                        "field_citations": {},
                    })
                return SimpleNamespace(
                    run={"id": "RUN-MIXED"},
                    experience_drafts=drafts,
                    sources=sources,
                    analyzed_source_ids=[source.id for source in sources],
                )

        result = organize_segmented_sources(
            MixedAI(),
            ExperienceExtractionRequest(
                client_request_id="REQUEST-MIXED",
                input_type=ExperienceExtractionInputType.CONVERSATION,
                conversation_id="CONV-MIXED",
                message_ids=[source.message_id for source in sources],
            ),
            segmented,
        )
        proposal = build_experience_units_proposal(
            result,
            segmented,
            analysis_run_id="RUN-MIXED",
        )

        self.assertGreater(len(calls), 1)
        self.assertEqual(len(proposal["units"]), 36)
        self.assertEqual(proposal["coverage"]["experience_span_count"], 36)
        self.assertEqual(len(proposal["coverage"]["unresolved_span_ids"]), 69)
        self.assertEqual(
            sum(proposal["coverage"][key] for key in (
                "experience_span_count",
                "job_span_count",
                "context_span_count",
                "other_span_count",
            )) + len(proposal["coverage"]["unresolved_span_ids"]),
            proposal["coverage"]["total_span_count"],
        )
        for source, snapshot in zip(sources, segmented.snapshots, strict=True):
            reconstructed = "".join(
                source.text[span["char_start"]:span["char_end"]]
                for span in snapshot["spans"]
            )
            self.assertEqual(reconstructed, source.text)
            self.assertEqual(snapshot["text_hash"], hashlib.sha256(
                source.text.encode("utf-8")
            ).hexdigest())
        validate_proposal_invariants(proposal)


if __name__ == "__main__":
    unittest.main()
