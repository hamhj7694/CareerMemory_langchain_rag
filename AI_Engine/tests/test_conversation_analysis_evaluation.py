from __future__ import annotations

import unittest

from AI_Engine.benchmarks.evaluate_conversation_analysis import evaluate_report


class ConversationAnalysisEvaluationTests(unittest.TestCase):
    def test_scores_preservation_contamination_and_job_detection(self) -> None:
        fixture = {
            "fixture_id": "fixture-1",
            "messages": [
                {"id": "u1", "role": "user", "content": "전환율을 12% 높였습니다."},
                {"id": "j1", "role": "user", "content": "Python FastAPI React"},
                {"id": "a1", "role": "assistant", "content": "매출 50% 증가"},
            ],
            "gold": {
                "experience_facts": [{
                    "id": "conversion",
                    "required_terms": ["전환율", "12%"],
                    "source_message_ids": ["u1"],
                    "context_required": True,
                }],
                "jobs": [{
                    "id": "job-1",
                    "source_message_id": "j1",
                    "required_terms": ["Python", "FastAPI", "React"],
                }],
                "normalized_skills": [{
                    "scope": "job",
                    "canonical_skill_id": "skill-fastapi",
                }],
                "metrics": [{
                    "scope": "experience",
                    "value": 12.0,
                    "unit": "percent",
                    "direction": "increase",
                }],
                "forbidden_metric_values": [50],
                "forbidden_assistant_terms": ["매출", "50%"],
                "irrelevant_terms": ["점심"],
                "evidence_roles": ["user"],
            },
        }
        report = {
            "benchmark_version": "test",
            "architecture_version": "test-v1",
            "runs": [{
                "label": "cold",
                "result": {
                    "experience": {
                        "experience_drafts": [{
                            "facts": ["전환율 12% 증가"],
                            "metrics": [{
                                "value": 12.0,
                                "unit": "percent",
                                "direction": "increase",
                            }],
                            "source_ref_ids": ["source-u1"],
                            "field_citations": {
                                "facts.0": [{
                                    "source_ref_id": "source-u1",
                                    "quote": "전환율을 12% 높였습니다.",
                                }]
                            },
                        }]
                    },
                    "job_candidates": [{"message_id": "j1"}],
                    "jobs": [{"requirements": [{
                        "summary": "Python FastAPI React",
                        "skill_mentions": [{
                            "canonical_skill_id": "skill-fastapi",
                        }],
                    }]}],
                },
            }],
        }

        result = evaluate_report(report, fixture)["aggregate"]

        self.assertEqual(result["experience_fact_recall_pct"], 100.0)
        self.assertEqual(result["context_fact_recall_pct"], 100.0)
        self.assertEqual(result["expected_source_coverage_pct"], 100.0)
        self.assertEqual(
            result["expected_source_citation_coverage_pct"],
            100.0,
        )
        self.assertEqual(result["exact_citation_validity_pct"], 100.0)
        self.assertEqual(result["job_detection_recall_pct"], 100.0)
        self.assertEqual(result["job_detection_precision_pct"], 100.0)
        self.assertEqual(result["job_requirement_term_recall_pct"], 100.0)
        self.assertEqual(result["assistant_contamination_rate_pct"], 0.0)
        self.assertEqual(result["irrelevant_leakage_rate_pct"], 0.0)
        self.assertEqual(result["skill_normalization_recall_pct"], 100.0)
        self.assertEqual(result["metric_value_recall_pct"], 100.0)
        self.assertEqual(result["numeric_hallucination_rate_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
