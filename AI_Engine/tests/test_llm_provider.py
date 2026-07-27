"""Gemini와 OpenAI Provider 선택 규칙 테스트."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    GoogleGenerativeAIEmbeddings,
)
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from AI_Engine.llm_provider import (
    GeminiStructuredClient,
    create_chat_model,
    create_embeddings,
    create_structured_client,
    get_ai_provider,
    get_chat_temperature,
    get_chat_model_name,
    get_experience_index_version,
)


class LLMProviderTests(unittest.TestCase):
    def test_openai_is_default_provider(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_ai_provider(), "openai")

    def test_invalid_provider_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "gemini.*openai"):
            get_ai_provider("unknown")

    def test_gemini_components_are_created(self) -> None:
        environment = {
            "GEMINI_API_KEY": "test-key",
            "GEMINI_MODEL": "gemini-test",
            "GEMINI_EMBEDDING_MODEL": "gemini-embedding-test",
        }
        with patch.dict(os.environ, environment, clear=True):
            self.assertIsInstance(
                create_chat_model(provider="gemini"),
                ChatGoogleGenerativeAI,
            )
            self.assertIsInstance(
                create_embeddings(provider="gemini"),
                GoogleGenerativeAIEmbeddings,
            )
            self.assertIsInstance(
                create_structured_client("gemini"),
                GeminiStructuredClient,
            )

    def test_openai_components_remain_available(self) -> None:
        environment = {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_MODEL": "gpt-test",
            "OPENAI_EMBEDDING_MODEL": "embedding-test",
        }
        with patch.dict(os.environ, environment, clear=True):
            self.assertIsInstance(
                create_chat_model(provider="openai"),
                ChatOpenAI,
            )
            self.assertIsInstance(
                create_embeddings(provider="openai"),
                OpenAIEmbeddings,
            )
            self.assertEqual(get_chat_model_name("openai"), "gpt-test")

    def test_chat_temperature_uses_configured_value(self) -> None:
        with patch.dict(
            os.environ,
            {"AI_CHAT_TEMPERATURE": "0.3"},
            clear=True,
        ):
            self.assertEqual(get_chat_temperature(), 0.3)

    def test_invalid_chat_temperature_is_rejected(self) -> None:
        for invalid_value in ("high", "-0.1", "2.1"):
            with self.subTest(value=invalid_value):
                with patch.dict(
                    os.environ,
                    {"AI_CHAT_TEMPERATURE": invalid_value},
                    clear=True,
                ):
                    with self.assertRaisesRegex(
                        ValueError,
                        "AI_CHAT_TEMPERATURE",
                    ):
                        get_chat_temperature()

    def test_embedding_indexes_are_separated_by_provider(self) -> None:
        self.assertNotEqual(
            get_experience_index_version("gemini"),
            get_experience_index_version("openai"),
        )


if __name__ == "__main__":
    unittest.main()
