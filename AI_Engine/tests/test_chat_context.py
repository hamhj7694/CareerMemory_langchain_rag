"""챗봇 문맥 토큰 계산·청크·자동 축약을 검증한다."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from AI_Engine.chat_context import (
    build_budgeted_context,
    estimate_tokens,
    split_text_chunks,
)
from AI_Engine.schemas import ChatContextDocument


class ChatContextTests(unittest.TestCase):
    def test_korean_text_has_non_zero_estimated_tokens(self) -> None:
        self.assertGreater(estimate_tokens("지원 전환율을 개선했습니다."), 0)

    def test_long_text_is_split_with_source_offsets(self) -> None:
        text = ("첫 번째 경험 문장입니다.\n\n" * 300).strip()
        chunks = split_text_chunks(text, max_tokens=120, overlap_tokens=20)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(content for content, _start, _end in chunks))
        self.assertEqual(chunks[0][1], 0)
        self.assertLess(chunks[1][1], chunks[0][2])

    def test_context_omits_low_priority_documents_over_budget(self) -> None:
        documents = [
            ChatContextDocument(
                source_id=f"evidence-{index}",
                source_type="evidence",
                title=f"근거 {index}",
                content="근거 내용 " * 300,
            )
            for index in range(4)
        ]
        environment = {
            "AI_CHAT_INPUT_TOKEN_BUDGET": "500",
            "AI_CHAT_ATTACHMENT_CONTEXT_TOKENS": "500",
            "AI_CHAT_EXPERIENCE_CONTEXT_TOKENS": "500",
            "AI_CHAT_EVIDENCE_CONTEXT_TOKENS": "500",
        }
        with patch.dict(os.environ, environment):
            context = build_budgeted_context(
                summary=None,
                attachments=[],
                experiences=[],
                evidence=documents,
                base_sections={"system_prompt": 100},
            )

        self.assertTrue(context.token_usage.compacted)
        self.assertGreater(context.token_usage.omitted_context_count, 0)
        self.assertLessEqual(
            context.token_usage.estimated_input_tokens,
            context.token_usage.budget,
        )


if __name__ == "__main__":
    unittest.main()
