"""대화 원문을 보존하면서 오래된 범위를 구조적으로 요약하는 메모리."""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from AI_Engine.chat_context import estimate_tokens, fit_history
from AI_Engine.database.models import Conversation, ConversationMemory, Message
from AI_Engine.llm_provider import create_chat_model, get_chat_model_name
from AI_Engine.schemas import ConversationSummaryContext


CONVERSATION_MEMORY_PROMPT_VERSION = "conversation-memory-v1"
CONVERSATION_MEMORY_SYSTEM_PROMPT = """
[역할 role]
너는 Career Memory의 장기 대화 메모리 정리기다.

[목표 task]
기존 요약과 새 대화 원문을 합쳐 이후 대화에 필요한 사실만 구조적으로 요약한다.

[제약조건 constraint]
- 사용자가 말하지 않은 경험, 수치, 역할을 만들지 않는다.
- 원문을 삭제하거나 대체하지 않고 파생 요약만 만든다.
- 이미 경험으로 확정됐는지 알 수 없으면 확정됐다고 쓰지 않는다.
- 불확실한 내용과 추가 확인할 내용을 분리한다.

[형식 format]
## 사용자 목표
## 주요 경험과 사실
## 사용자 선호
## 진행 중인 작업
## 추가 확인 필요
""".strip()


class ConversationMemoryManager:
    def __init__(self, model: Any | None = None) -> None:
        self.model = model

    def prepare(
        self,
        database: Session,
        conversation: Conversation,
        history: Sequence[Message],
        *,
        before_sequence: int | None = None,
    ) -> tuple[ConversationSummaryContext | None, list[Message]]:
        """필요할 때만 오래된 메시지를 요약하고 최근 원문 범위를 반환한다."""

        # API의 최근 이력 제한과 별개로 아직 요약하지 않은 원문 범위는 DB에서
        # 전부 확인한다. 그렇지 않으면 제한 밖의 오래된 메시지가 영구히 빠진다.
        history_query = (
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.status == "completed",
                Message.role.in_(("user", "assistant")),
            )
            .order_by(Message.sequence)
        )
        if before_sequence is not None:
            history_query = history_query.where(
                Message.sequence < before_sequence
            )
        complete_history = list(database.scalars(history_query))
        if not complete_history:
            complete_history = list(history)
        stored = conversation.memory
        through_sequence = stored.through_sequence if stored else 0
        unsummarized = [
            message for message in complete_history
            if message.sequence > through_sequence and message.content.strip()
        ]
        trigger_tokens = int(os.getenv(
            "AI_CHAT_SUMMARY_TRIGGER_TOKENS",
            "16000",
        ))
        keep_recent_count = max(4, int(os.getenv(
            "AI_CHAT_SUMMARY_KEEP_RECENT_MESSAGES",
            "12",
        )))
        should_summarize = (
            len(unsummarized) > keep_recent_count
            and sum(estimate_tokens(item.content) for item in unsummarized)
            >= trigger_tokens
        )

        if should_summarize:
            summarize_messages = unsummarized[:-keep_recent_count]
            summary_text = self._summarize(
                previous_summary=stored.summary_text if stored else "",
                messages=summarize_messages,
            )
            summary_through = summarize_messages[-1].sequence
            if stored is None:
                stored = ConversationMemory(
                    conversation_id=conversation.id,
                    summary_text=summary_text,
                    through_sequence=summary_through,
                    estimated_tokens=estimate_tokens(summary_text),
                    model_version=get_chat_model_name(),
                    prompt_version=CONVERSATION_MEMORY_PROMPT_VERSION,
                )
                database.add(stored)
            else:
                stored.summary_text = summary_text
                stored.through_sequence = summary_through
                stored.estimated_tokens = estimate_tokens(summary_text)
                stored.model_version = get_chat_model_name()
                stored.prompt_version = CONVERSATION_MEMORY_PROMPT_VERSION
                stored.version += 1
            database.commit()
            through_sequence = summary_through

        summary = None
        if stored is not None and stored.summary_text.strip():
            summary = ConversationSummaryContext(
                text=stored.summary_text,
                through_sequence=stored.through_sequence,
                updated_at=stored.updated_at,
            )
        recent = [
            message for message in complete_history
            if message.sequence > through_sequence
        ]
        return summary, recent

    def _summarize(
        self,
        *,
        previous_summary: str,
        messages: Sequence[Message],
    ) -> str:
        transcript = "\n".join(
            f"[{message.role} #{message.sequence}] {message.content}"
            for message in messages
        )
        model = self.model or create_chat_model()
        response = model.invoke([
            SystemMessage(content=CONVERSATION_MEMORY_SYSTEM_PROMPT),
            HumanMessage(content=(
                f"[기존 요약]\n{previous_summary or '없음'}\n\n"
                f"[새 대화 원문]\n{transcript}"
            )),
        ])
        text = getattr(response, "content", response)
        if isinstance(text, list):
            text = "".join(
                str(item.get("text", ""))
                for item in text
                if isinstance(item, dict)
            )
        normalized = str(text or "").strip()
        if not normalized:
            raise RuntimeError("대화 요약 모델이 빈 결과를 반환했습니다.")
        return normalized


def compact_recent_history(messages):
    """DB Message 목록을 토큰 예산에 맞는 최근 범위로 제한한다."""

    return fit_history(messages)


__all__ = [
    "CONVERSATION_MEMORY_PROMPT_VERSION",
    "CONVERSATION_MEMORY_SYSTEM_PROMPT",
    "ConversationMemoryManager",
]
