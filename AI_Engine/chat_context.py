"""챗봇 입력 토큰을 계산하고 문맥을 예산 안으로 축약하는 공통 기능."""

from __future__ import annotations

import math
import os
import re
from collections.abc import Iterable, Sequence

from AI_Engine.schemas import (
    ChatContext,
    ChatContextDocument,
    ChatMessage,
    ChatTokenUsage,
)


DEFAULT_CHAT_INPUT_TOKEN_BUDGET = 60_000
DEFAULT_RECENT_HISTORY_TOKEN_BUDGET = 14_000
DEFAULT_ATTACHMENT_TOKEN_BUDGET = 14_000
DEFAULT_EXPERIENCE_TOKEN_BUDGET = 10_000
DEFAULT_EVIDENCE_TOKEN_BUDGET = 12_000


def estimate_tokens(text: str) -> int:
    """Provider와 무관하게 일관된 보수적 예상 입력 토큰 수를 계산한다."""

    normalized = str(text or "")
    if not normalized:
        return 0
    # 한글은 UTF-8에서 3바이트이고 모델 토크나이저에서도 비교적 잘게
    # 나뉜다. 바이트/3과 공백 단위 추정치 중 큰 값을 사용해 과소 추정을 막는다.
    byte_estimate = math.ceil(len(normalized.encode("utf-8")) / 3)
    piece_estimate = len(re.findall(r"\S+|[\n]", normalized))
    return max(1, byte_estimate, piece_estimate)


def truncate_to_token_budget(text: str, budget: int) -> str:
    """원문 앞부분을 문단 경계 우선으로 보존해 예상 토큰 예산에 맞춘다."""

    normalized = str(text or "").strip()
    if budget <= 0 or not normalized:
        return ""
    if estimate_tokens(normalized) <= budget:
        return normalized

    low, high = 0, len(normalized)
    while low < high:
        middle = (low + high + 1) // 2
        if estimate_tokens(normalized[:middle]) <= budget:
            low = middle
        else:
            high = middle - 1
    candidate = normalized[:low].rstrip()
    paragraph_break = candidate.rfind("\n\n")
    if paragraph_break >= max(0, len(candidate) // 2):
        candidate = candidate[:paragraph_break].rstrip()
    return f"{candidate}\n\n[토큰 예산에 따라 이후 내용 생략]" if candidate else ""


def split_text_chunks(
    text: str,
    *,
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[tuple[str, int, int]]:
    """검색 인용 위치를 보존하며 긴 원문을 겹치는 청크로 나눈다."""

    max_tokens = max_tokens or int(os.getenv(
        "AI_EVIDENCE_CHUNK_TOKENS",
        "900",
    ))
    overlap_tokens = (
        int(os.getenv("AI_EVIDENCE_CHUNK_OVERLAP_TOKENS", "120"))
        if overlap_tokens is None
        else overlap_tokens
    )
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.strip():
        return []
    if max_tokens < 1 or overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError("청크 토큰과 겹침 토큰 설정이 올바르지 않습니다.")

    approximate_chars = max(200, max_tokens * 2)
    overlap_chars = min(approximate_chars - 1, overlap_tokens * 2)
    chunks: list[tuple[str, int, int]] = []
    start = 0
    while start < len(normalized):
        hard_end = min(len(normalized), start + approximate_chars)
        end = hard_end
        if hard_end < len(normalized):
            candidates = [
                normalized.rfind("\n\n", start, hard_end),
                normalized.rfind("\n", start, hard_end),
                normalized.rfind(". ", start, hard_end),
            ]
            boundary = max(candidates)
            if boundary > start + approximate_chars // 2:
                end = boundary + (2 if normalized[boundary:boundary + 2] == ". " else 1)
        content = normalized[start:end].strip()
        if content:
            chunks.append((content, start, end))
        if end >= len(normalized):
            break
        start = max(start + 1, end - overlap_chars)
    return chunks


def _fit_documents(
    documents: Sequence[ChatContextDocument],
    budget: int,
) -> tuple[list[ChatContextDocument], int]:
    selected: list[ChatContextDocument] = []
    omitted = 0
    remaining = max(0, budget)
    for document in documents:
        tokens = estimate_tokens(document.content)
        if tokens <= remaining:
            selected.append(document)
            remaining -= tokens
            continue
        if remaining >= 80:
            compacted = truncate_to_token_budget(document.content, remaining)
            if compacted:
                selected.append(document.model_copy(update={"content": compacted}))
                remaining = 0
        omitted += 1
    return selected, omitted


def fit_history(
    history: Sequence[ChatMessage],
    *,
    token_budget: int | None = None,
) -> list[ChatMessage]:
    """최근 발화부터 역순으로 담아 오래된 원문을 먼저 줄인다."""

    budget = token_budget or int(os.getenv(
        "AI_CHAT_RECENT_HISTORY_TOKENS",
        str(DEFAULT_RECENT_HISTORY_TOKEN_BUDGET),
    ))
    selected: list[ChatMessage] = []
    remaining = max(0, budget)
    for message in reversed(history):
        tokens = estimate_tokens(message.content)
        if tokens > remaining:
            break
        selected.append(message)
        remaining -= tokens
    selected.reverse()
    return selected


def build_budgeted_context(
    *,
    summary,
    attachments: Sequence[ChatContextDocument],
    experiences: Sequence[ChatContextDocument],
    evidence: Sequence[ChatContextDocument],
    base_sections: dict[str, int] | None = None,
) -> ChatContext:
    """문맥 종류별 상한과 전체 입력 예산을 함께 적용한다."""

    attachment_budget = int(os.getenv(
        "AI_CHAT_ATTACHMENT_CONTEXT_TOKENS",
        str(DEFAULT_ATTACHMENT_TOKEN_BUDGET),
    ))
    experience_budget = int(os.getenv(
        "AI_CHAT_EXPERIENCE_CONTEXT_TOKENS",
        str(DEFAULT_EXPERIENCE_TOKEN_BUDGET),
    ))
    evidence_budget = int(os.getenv(
        "AI_CHAT_EVIDENCE_CONTEXT_TOKENS",
        str(DEFAULT_EVIDENCE_TOKEN_BUDGET),
    ))
    total_budget = int(os.getenv(
        "AI_CHAT_INPUT_TOKEN_BUDGET",
        str(DEFAULT_CHAT_INPUT_TOKEN_BUDGET),
    ))

    selected_attachments, omitted_attachments = _fit_documents(
        attachments, attachment_budget
    )
    selected_experiences, omitted_experiences = _fit_documents(
        experiences, experience_budget
    )
    selected_evidence, omitted_evidence = _fit_documents(
        evidence, evidence_budget
    )
    sections = dict(base_sections or {})
    sections.update({
        "conversation_summary": estimate_tokens(summary.text) if summary else 0,
        "attachments": sum(estimate_tokens(item.content) for item in selected_attachments),
        "experiences": sum(estimate_tokens(item.content) for item in selected_experiences),
        "evidence": sum(estimate_tokens(item.content) for item in selected_evidence),
    })
    estimated = sum(sections.values())
    omitted = omitted_attachments + omitted_experiences + omitted_evidence

    # 종류별 예산을 모두 채운 뒤에도 모델 전체 예산을 넘으면 근거 → 경험 →
    # 첨부 순으로 뒤쪽의 낮은 우선순위 문서를 덜어낸다.
    while estimated > total_budget:
        target: list[ChatContextDocument] | None = None
        if selected_evidence:
            target = selected_evidence
        elif selected_experiences:
            target = selected_experiences
        elif selected_attachments:
            target = selected_attachments
        if target is None:
            break
        removed = target.pop()
        estimated -= estimate_tokens(removed.content)
        omitted += 1

    sections["attachments"] = sum(
        estimate_tokens(item.content) for item in selected_attachments
    )
    sections["experiences"] = sum(
        estimate_tokens(item.content) for item in selected_experiences
    )
    sections["evidence"] = sum(
        estimate_tokens(item.content) for item in selected_evidence
    )
    estimated = sum(sections.values())
    return ChatContext(
        conversation_summary=summary,
        attachments=selected_attachments,
        experiences=selected_experiences,
        evidence=selected_evidence,
        token_usage=ChatTokenUsage(
            budget=total_budget,
            estimated_input_tokens=estimated,
            sections=sections,
            compacted=omitted > 0,
            omitted_context_count=omitted,
        ),
    )


def combined_token_count(values: Iterable[str]) -> int:
    return sum(estimate_tokens(value) for value in values)


__all__ = [
    "build_budgeted_context",
    "combined_token_count",
    "estimate_tokens",
    "fit_history",
    "split_text_chunks",
    "truncate_to_token_budget",
]
