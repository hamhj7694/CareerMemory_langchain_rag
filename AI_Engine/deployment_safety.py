"""Persistent, atomic global AI operation budget shared by API and worker.

Counts attempted operations (embedding texts count individually), not dollars.
Reservations are never refunded: failures must not bypass the public demo cap.
"""
from __future__ import annotations

import os
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

from langchain_core.callbacks import BaseCallbackHandler


class AIBudgetExceeded(RuntimeError):
    pass


def production() -> bool:
    return os.getenv("APP_ENV", "development").lower() == "production"


def reserve_ai_operations(count: int = 1) -> None:
    enabled = os.getenv("AI_ENABLED", "false" if production() else "true")
    if enabled.lower() != "true":
        raise AIBudgetExceeded("AI 체험 기능이 현재 비활성화되어 있습니다.")
    limit = int(os.getenv("AI_DAILY_OPERATION_LIMIT", "100" if production() else "0"))
    if limit == 0 and not production():
        return
    if limit <= 0 or count <= 0:
        raise AIBudgetExceeded("AI 사용 한도가 설정되지 않았습니다.")
    path = Path(os.getenv("AI_BUDGET_DB", "data/ai_budget.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).date().isoformat()
    connection = sqlite3.connect(path, timeout=30)
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS daily_budget (day TEXT PRIMARY KEY, used INTEGER NOT NULL)")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("INSERT OR IGNORE INTO daily_budget VALUES (?, 0)", (day,))
        used = connection.execute("SELECT used FROM daily_budget WHERE day=?", (day,)).fetchone()[0]
        if used + count > limit:
            raise AIBudgetExceeded("오늘의 AI 체험 한도를 모두 사용했습니다.")
        connection.execute("UPDATE daily_budget SET used=used+? WHERE day=?", (count, day))
        connection.commit()
    finally:
        connection.close()


class BudgetCallback(BaseCallbackHandler):
    raise_error = True

    def on_chat_model_start(self, serialized, messages, **kwargs):
        reserve_ai_operations(len(messages))

    def on_llm_start(self, serialized, prompts, **kwargs):
        reserve_ai_operations(len(prompts))


class BudgetedEmbeddings:
    def __init__(self, delegate):
        self.delegate = delegate

    def embed_documents(self, texts, **kwargs):
        reserve_ai_operations(len(texts))
        return self.delegate.embed_documents(texts, **kwargs)

    def embed_query(self, text, **kwargs):
        reserve_ai_operations()
        return self.delegate.embed_query(text, **kwargs)


class BudgetedResponses:
    def __init__(self, delegate):
        self.delegate = delegate

    def create(self, **kwargs):
        ceiling = int(os.getenv("AI_STRUCTURED_OUTPUT_MAX_TOKENS", "8000"))
        if ceiling <= 0:
            raise AIBudgetExceeded("AI 출력 한도가 설정되지 않았습니다.")
        kwargs["max_output_tokens"] = min(int(kwargs.get("max_output_tokens", ceiling)), ceiling)
        if len(json.dumps(kwargs.get("input", ""), ensure_ascii=False)) > int(os.getenv("AI_MAX_STRUCTURED_INPUT_CHARS", "100000")):
            raise AIBudgetExceeded("분석 입력이 체험 서비스의 허용 길이를 초과합니다.")
        reserve_ai_operations()
        return self.delegate.create(**kwargs)
