"""Protect provider access and verify a shared budget under concurrent writers."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from AI_Engine.deployment_safety import AIBudgetExceeded, reserve_ai_operations
from AI_Engine.llm_provider import create_chat_model, create_embeddings, create_structured_client
from AI_Engine.chatbot_ai import create_chatbot_agent


class DeploymentSafetyTests(unittest.TestCase):
    def test_disabled_ai_blocks_every_openai_entry_before_network_access(self):
        with patch.dict(os.environ, {"APP_ENV": "production", "AI_ENABLED": "false", "OPENAI_API_KEY": "test-key"}):
            model = create_chat_model(provider="openai")
            with patch.object(type(model), "_generate") as network:
                with self.assertRaises(AIBudgetExceeded):
                    model.invoke("hello")
                network.assert_not_called()
                with self.assertRaises(AIBudgetExceeded):
                    create_chatbot_agent(model=model).invoke({"messages": [("user", "hello")]})
                network.assert_not_called()
            embeddings = create_embeddings(provider="openai")
            with patch.object(type(embeddings.delegate), "embed_query") as network:
                with self.assertRaises(AIBudgetExceeded):
                    embeddings.embed_query("hello")
                network.assert_not_called()
            client = create_structured_client("openai")
            with patch.object(type(client.responses.delegate), "create") as network:
                with self.assertRaises(AIBudgetExceeded):
                    client.responses.create(model="test", input="hello")
                network.assert_not_called()

    def test_daily_budget_is_atomic_and_survives_new_connections(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {
            "APP_ENV": "production", "AI_ENABLED": "true", "AI_DAILY_OPERATION_LIMIT": "7",
            "AI_BUDGET_DB": str(Path(directory) / "budget.db"),
        }):
            def reserve(_):
                try:
                    reserve_ai_operations()
                    return True
                except AIBudgetExceeded:
                    return False
            with ThreadPoolExecutor(max_workers=8) as workers:
                self.assertEqual(sum(workers.map(reserve, range(25))), 7)
            with self.assertRaises(AIBudgetExceeded):
                reserve_ai_operations()

    def test_embedding_batches_cannot_bypass_limit(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {
            "APP_ENV": "production", "AI_ENABLED": "true", "AI_DAILY_OPERATION_LIMIT": "3",
            "AI_BUDGET_DB": str(Path(directory) / "budget.db"),
        }):
            reserve_ai_operations(2)
            with self.assertRaises(AIBudgetExceeded):
                reserve_ai_operations(2)
            reserve_ai_operations(1)
