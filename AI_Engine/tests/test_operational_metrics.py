"""요청 관측값이 원문 없이 P50/P95와 오류율을 계산하는지 검증한다."""

from __future__ import annotations

import unittest

from AI_Engine.operational_metrics import RequestMetricsRegistry


class OperationalMetricsTests(unittest.TestCase):
    def test_snapshot_calculates_latency_and_error_rate_without_payload(self) -> None:
        registry = RequestMetricsRegistry()
        for duration, status in ((10, 200), (20, 200), (30, 500), (40, 200)):
            registry.record("post", "/api/v2/example", status, duration)

        metric = registry.snapshot()[0]

        self.assertEqual(metric.method, "POST")
        self.assertEqual(metric.route, "/api/v2/example")
        self.assertEqual(metric.count, 4)
        self.assertEqual(metric.error_count, 1)
        self.assertEqual(metric.error_rate, 0.25)
        self.assertEqual(metric.p50_ms, 20)
        self.assertEqual(metric.p95_ms, 40)


if __name__ == "__main__":
    unittest.main()
