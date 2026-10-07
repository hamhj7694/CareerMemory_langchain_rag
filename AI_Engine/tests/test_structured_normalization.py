"""Lossless skill and metric normalization tests."""

from __future__ import annotations

import unittest

from AI_Engine.job_analysis_ai import (
    _candidate_meets_explicit_constraints,
    _recover_exact_source_excerpt,
)
from AI_Engine.metric_normalization import (
    extract_metrics,
    metric_satisfies_requirement,
    validate_proposed_metrics,
)
from AI_Engine.normalization_backfill import structured_fields_for_experience
from AI_Engine.schemas import JobRequirement
from AI_Engine.skill_normalization import (
    normalize_skill_mention,
    skill_relationship,
)


class SkillNormalizationTests(unittest.TestCase):
    def test_curated_alias_resolves_without_losing_raw_name(self) -> None:
        mention = normalize_skill_mention("페스트API")

        self.assertEqual(mention.raw_name, "페스트API")
        self.assertEqual(mention.normalized_name, "FastAPI")
        self.assertEqual(mention.canonical_skill_id, "skill-fastapi")
        self.assertEqual(mention.match_type, "alias")

    def test_unknown_skill_is_preserved_as_unresolved(self) -> None:
        mention = normalize_skill_mention("사내 FluxEngine")

        self.assertEqual(mention.raw_name, "사내 FluxEngine")
        self.assertIsNone(mention.canonical_skill_id)
        self.assertEqual(mention.normalization_status, "unresolved")

    def test_related_technology_is_not_exact(self) -> None:
        javascript = normalize_skill_mention("JavaScript")
        typescript = normalize_skill_mention("TypeScript")

        self.assertEqual(
            skill_relationship(javascript, typescript),
            "related",
        )

    def test_required_fastapi_rejects_rest_api_only_candidate(self) -> None:
        requirement = JobRequirement(
            id="requirement-1",
            job_posting_id="posting-1",
            title="FastAPI 개발",
            summary="FastAPI 사용 경험",
            source_excerpt="FastAPI 사용 경험이 필요합니다.",
            keywords=["FastAPI"],
            skill_mentions=[normalize_skill_mention("FastAPI")],
            order=1,
        )
        candidate = {
            "content": "REST API를 설계했습니다.",
            "skill_mentions": [
                normalize_skill_mention("REST API").model_dump(mode="json")
            ],
        }

        self.assertFalse(
            _candidate_meets_explicit_constraints(requirement, candidate)
        )

    def test_sourced_fastapi_alias_satisfies_fastapi_requirement(self) -> None:
        requirement = JobRequirement(
            id="requirement-1",
            job_posting_id="posting-1",
            title="FastAPI 개발",
            summary="FastAPI 사용 경험",
            source_excerpt="FastAPI 사용 경험이 필요합니다.",
            keywords=["FastAPI"],
            skill_mentions=[normalize_skill_mention("FastAPI")],
            order=1,
        )
        candidate_mention = normalize_skill_mention(
            "페스트API",
            source_ref_id="source-1",
            quote="페스트API",
        )
        candidate = {
            "content": "페스트API로 서버를 개발했습니다.",
            "skill_mentions": [candidate_mention.model_dump(mode="json")],
        }

        self.assertTrue(
            _candidate_meets_explicit_constraints(requirement, candidate)
        )

    def test_lightly_rewritten_job_quote_recovers_exact_source_line(self) -> None:
        source = "자격 요건: Python과 FastAPI를 활용한 API 개발 경험이 필요합니다."
        recovered = _recover_exact_source_excerpt(
            source,
            {
                "source_excerpt": "Python 및 FastAPI를 활용한 API 개발 경험이 필요합니다.",
            },
        )

        self.assertEqual(recovered, source)


class MetricNormalizationTests(unittest.TestCase):
    def test_close_percentages_remain_distinct(self) -> None:
        forty_nine = extract_metrics("전환율 49% 증가")
        fifty = extract_metrics("전환율 50% 증가")

        self.assertEqual(forty_nine[0].value, 49.0)
        self.assertEqual(fifty[0].value, 50.0)
        self.assertNotEqual(forty_nine[0].value, fifty[0].value)

    def test_model_number_is_recomputed_from_exact_quote(self) -> None:
        metrics = validate_proposed_metrics(
            [{
                "metric_name": "전환율",
                "raw_expression": "49%",
                "value": 50,
                "source_ref_id": "source-1",
                "quote": "전환율을 49% 높였습니다.",
            }],
            source_text_by_id={
                "source-1": "전환율을 49% 높였습니다.",
            },
        )

        self.assertEqual(metrics[0].value, 49.0)

    def test_korean_percentage_and_direction_are_normalized(self) -> None:
        metrics = extract_metrics("오류율을 오십 퍼센트 감소시켰습니다.")

        self.assertEqual(metrics[0].value, 50.0)
        self.assertEqual(metrics[0].unit, "percent")
        self.assertEqual(metrics[0].direction, "decrease")

    def test_before_and_after_values_are_separate(self) -> None:
        metrics = extract_metrics("처리 시간을 5시간에서 2시간으로 줄였습니다.")

        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].before_value, 5.0)
        self.assertEqual(metrics[0].after_value, 2.0)
        self.assertEqual(metrics[0].unit, "hour")

    def test_approximate_half_keeps_raw_expression(self) -> None:
        metrics = extract_metrics("응답 시간이 거의 절반 정도로 줄었습니다.")

        self.assertEqual(metrics[0].raw_expression, "거의 절반 정도")
        self.assertEqual(metrics[0].value, 0.5)
        self.assertEqual(metrics[0].operator, "approximate")

    def test_minimum_numeric_requirement_uses_exact_values(self) -> None:
        requirement = extract_metrics("FastAPI 경력 3년 이상")[0]
        enough = extract_metrics("FastAPI 경력 5년")[0]
        insufficient = extract_metrics("FastAPI 경력 2년")[0]

        self.assertTrue(metric_satisfies_requirement(requirement, enough))
        self.assertFalse(metric_satisfies_requirement(requirement, insufficient))

    def test_calendar_year_is_not_a_performance_metric(self) -> None:
        self.assertEqual(extract_metrics("2024년 프로젝트를 시작했습니다."), [])

    def test_backfill_is_additive_and_preserves_unknowns(self) -> None:
        skill_mentions, metrics = structured_fields_for_experience(
            ["FastAPI", "사내 FluxEngine"],
            ["응답 시간을 35% 줄였습니다."],
        )

        self.assertEqual(len(skill_mentions), 2)
        self.assertEqual(skill_mentions[1]["raw_name"], "사내 FluxEngine")
        self.assertEqual(skill_mentions[1]["normalization_status"], "unresolved")
        self.assertEqual(metrics[0]["value"], 35.0)


if __name__ == "__main__":
    unittest.main()
