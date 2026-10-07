"""Conversation analysis token and latency metric tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from AI_Engine.analysis_metrics import (
    AnalysisMetricsCollector,
    capture_analysis_metrics,
    measure_analysis_stage,
    tracked_responses_create,
)


class FakeResponses:
    def create(self, **_kwargs):
        return SimpleNamespace(
            usage=SimpleNamespace(
                input_tokens=100,
                input_tokens_details=SimpleNamespace(
                    cached_tokens=40,
                    cache_write_tokens=0,
                ),
                output_tokens=25,
                output_tokens_details=SimpleNamespace(reasoning_tokens=3),
                total_tokens=125,
            )
        )


class FakeClient:
    responses = FakeResponses()


class AnalysisMetricsTests(unittest.TestCase):
    def test_collects_usage_cost_and_stage_duration(self) -> None:
        collector = AnalysisMetricsCollector(
            run_id="run-1",
            provider="openai",
            model="gpt-4o-mini",
            source_message_count=2,
            unique_source_tokens=50,
        )
        with capture_analysis_metrics(collector):
            with measure_analysis_stage("discover_jobs"):
                tracked_responses_create(
                    FakeClient(),
                    stage="job_discovery",
                    model="gpt-4o-mini",
                    input="test",
                )

        metrics = collector.to_dict()
        self.assertEqual(metrics["llm_call_count"], 1)
        self.assertEqual(metrics["input_tokens"], 100)
        self.assertEqual(metrics["cached_tokens"], 40)
        self.assertEqual(metrics["output_tokens"], 25)
        self.assertEqual(metrics["total_tokens"], 125)
        self.assertEqual(metrics["token_amplification"], 2.0)
        self.assertEqual(metrics["unique_source_ratio_pct"], 50.0)
        self.assertEqual(metrics["calls"][0]["reasoning_tokens"], 3)
        self.assertEqual(metrics["stages"]["discover_jobs"]["count"], 1)
        self.assertGreaterEqual(metrics["total_duration_ms"], 0)
        self.assertEqual(metrics["estimated_cost_usd"], 0.000027)

    def test_calls_client_normally_without_active_collector(self) -> None:
        response = tracked_responses_create(
            FakeClient(),
            stage="unused",
            model="gpt-4o-mini",
            input="test",
        )
        self.assertEqual(response.usage.total_tokens, 125)


if __name__ == "__main__":
    unittest.main()
