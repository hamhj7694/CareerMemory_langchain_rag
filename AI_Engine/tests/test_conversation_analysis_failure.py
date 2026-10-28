"""Safe, useful failure metadata for integrated conversation analysis."""

import unittest
from types import SimpleNamespace

from AI_Engine.api.conversation_analysis import _safe_failures
from AI_Engine.conversation_analysis_workflow import ConversationAnalysisWorkflow, _failure_code
from AI_Engine.experience_ai import ExperienceAIOutputError


class ConversationAnalysisFailureTest(unittest.TestCase):
    def test_invalid_model_output_has_a_safe_code(self) -> None:
        error = ExperienceAIOutputError("private source text")
        self.assertEqual(_failure_code(error), "invalid_output")
        self.assertEqual(_safe_failures([{
            "stage": "analyze_experiences",
            "code": _failure_code(error),
            "message": str(error),
        }]), [{
            "stage": "analyze_experiences",
            "label": "경험 분석",
            "code": "invalid_output",
        }])

    def test_provider_rate_limit_has_a_safe_code(self) -> None:
        class ProviderError(Exception):
            status_code = 429

        self.assertEqual(_failure_code(ProviderError()), "provider_limit")

    def test_partial_experience_keeps_result_retryable(self) -> None:
        result = SimpleNamespace(
            run=SimpleNamespace(status="partial"),
            experience_drafts=[object()],
        )
        workflow = ConversationAnalysisWorkflow(
            discover_jobs=lambda _sources: [],
            resolve_job=lambda _candidate: None,
            build_experience_sources=lambda _candidates: [object()],
            analyze_experiences=lambda _sources: result,
        )

        state = workflow.invoke([])

        self.assertIs(state["experience_result"], result)
        self.assertFalse(state["experience_succeeded"])
        self.assertEqual(state["failures"][0]["code"], "invalid_output")


if __name__ == "__main__":
    unittest.main()
