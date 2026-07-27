"""Career Memory의 챗봇 문맥·검색·메모리·라우팅 조립 진입점."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from AI_Engine.chat_context import (
    build_budgeted_context,
    estimate_tokens,
    fit_history,
    split_text_chunks,
    truncate_to_token_budget,
)
from AI_Engine.chat_retrieval import (
    retrieve_evidence_context,
    retrieve_experience_context,
)
from AI_Engine.conversation_memory import ConversationMemoryManager
from AI_Engine.database.models import Attachment, Conversation, Message, User
from AI_Engine.intent_classifier import AutoIntentClassifier
from AI_Engine.schemas import (
    AIRequestType,
    AIRoute,
    AIRouteDecision,
    AIRouteRequest,
    ChatContextDocument,
    ChatMessage,
    ChatMode,
    ChatRequest,
    ChatRole,
    RouteDecisionSource,
)

CHAT_MESSAGE_ROUTE_VERSION = "chat-message-route-v1"


@dataclass(frozen=True)
class PreparedChatRequest:
    request: ChatRequest
    route: AIRouteDecision


class CareerMemoryAI:
    """API 저장 데이터에서 모델에 전달할 최소 문맥을 조립한다."""

    def __init__(
        self,
        *,
        intent_classifier: AutoIntentClassifier | None = None,
        memory_manager: ConversationMemoryManager | None = None,
    ) -> None:
        self.intent_classifier = intent_classifier
        self.memory_manager = memory_manager or ConversationMemoryManager()

    def prepare_chat(
        self,
        *,
        database: Session,
        conversation: Conversation,
        current_user: User,
        user_message: Message,
        stored_history: Sequence[Message],
    ) -> PreparedChatRequest:
        context_attachment_ids = _conversation_attachment_ids(
            current_attachment_ids=user_message.attachment_ids,
            stored_history=stored_history,
        )
        attachments = self._attachment_context(
            database,
            current_user.id,
            context_attachment_ids,
            query=user_message.content,
            current_attachment_ids=set(user_message.attachment_ids),
        )
        route_request = AIRouteRequest(
            request_id=user_message.client_request_id or user_message.id,
            request_type=_request_type(user_message.requested_intent),
            conversation_id=conversation.id,
            text=user_message.content,
            attachment_ids=user_message.attachment_ids,
            attachment_context=_routing_attachment_context(attachments),
        )
        if route_request.request_type == AIRequestType.AUTO:
            # 커리어 챗의 일반 메시지는 파일이 첨부되거나 경험·공고 관련 표현이
            # 포함되어도 전용 AI를 자동 실행하지 않는다. 파일 본문은 아래에서
            # 챗봇 문맥으로만 전달하고, 경험 초안 생성은 별도 버튼 API가 맡는다.
            route = AIRouteDecision(
                request_id=route_request.request_id,
                requested_type=route_request.request_type,
                route=AIRoute.CHAT,
                source=RouteDecisionSource.AUTOMATIC,
                confidence=1,
                reason=(
                    "커리어 챗 메시지는 대화로 처리하며 전용 AI는 사용자의 "
                    "명시적인 실행 버튼을 통해서만 호출합니다."
                ),
                classifier_version=CHAT_MESSAGE_ROUTE_VERSION,
            )
        else:
            classifier = self.intent_classifier
            if classifier is None:
                classifier = AutoIntentClassifier()
            route = classifier.decide(route_request)

        summary, recent_history = self.memory_manager.prepare(
            database,
            conversation,
            stored_history,
            before_sequence=user_message.sequence,
        )
        history_models = [
            ChatMessage(
                id=message.id,
                conversation_id=message.conversation_id,
                sequence=message.sequence,
                role=ChatRole(message.role),
                content=message.content,
                attachment_ids=message.attachment_ids,
                created_at=message.created_at,
            )
            for message in recent_history
            if (
                message.role in {"user", "assistant"}
                and (message.content.strip() or message.attachment_ids)
            )
        ]
        history_models = fit_history(history_models)

        retrieval_query = _retrieval_query(
            user_message.content,
            attachments,
        )
        experiences = retrieve_experience_context(
            database,
            current_user.id,
            retrieval_query,
        )
        evidence = retrieve_evidence_context(
            database,
            current_user.id,
            retrieval_query,
        )
        attachment_ids = {item.source_id for item in attachments}
        evidence = [
            item for item in evidence
            if item.source_id not in attachment_ids
        ]
        context = build_budgeted_context(
            summary=summary,
            attachments=attachments,
            experiences=experiences,
            evidence=evidence,
            base_sections={
                "system_prompt": 1_500,
                "current_message": estimate_tokens(user_message.content),
                "recent_history": sum(
                    estimate_tokens(message.content)
                    for message in history_models
                ),
            },
        )
        request = ChatRequest(
            client_request_id=user_message.client_request_id or user_message.id,
            conversation_id=conversation.id,
            message_id=user_message.id,
            sequence=user_message.sequence,
            # 전용 경험/공고 파이프라인은 API가 별도로 실행한다. 자동 분류
            # 결과는 routed_intent로 보존하고 일반 답변 생성기는 chat 범위만 맡는다.
            mode=ChatMode.CHAT,
            routed_intent=route.route,
            content=user_message.content,
            attachment_ids=user_message.attachment_ids,
            user_display_name=current_user.display_name,
            history=history_models,
            context=context,
        )
        return PreparedChatRequest(request=request, route=route)

    @staticmethod
    def _attachment_context(
        database: Session,
        user_id: str,
        attachment_ids: Sequence[str],
        *,
        query: str,
        current_attachment_ids: set[str] | None = None,
    ) -> list[ChatContextDocument]:
        if not attachment_ids:
            return []
        attachments = list(database.scalars(
            select(Attachment).where(
                Attachment.user_id == user_id,
                Attachment.id.in_(attachment_ids),
            )
        ))
        by_id = {attachment.id: attachment for attachment in attachments}
        missing = [
            attachment_id for attachment_id in attachment_ids
            if attachment_id not in by_id
        ]
        if missing:
            raise ValueError(
                "현재 사용자가 열 수 없는 첨부 파일이 포함되어 있습니다: "
                + ", ".join(missing)
            )

        result: list[ChatContextDocument] = []
        query_terms = _query_terms(query)
        current_ids = current_attachment_ids or set()
        for attachment_id in attachment_ids:
            attachment = by_id[attachment_id]
            chunks = split_text_chunks(attachment.extracted_text)
            ranked = sorted(
                enumerate(chunks),
                key=lambda pair: (
                    sum(
                        pair[1][0].casefold().count(term)
                        for term in query_terms
                    ),
                    -pair[0],
                ),
                reverse=True,
            )
            # 질문이 없거나 키워드가 겹치지 않아도 파일의 앞부분은 전달한다.
            for chunk_index, (text, start, end) in ranked[:8]:
                result.append(ChatContextDocument(
                    source_id=attachment.id,
                    source_type="attachment",
                    title=attachment.filename,
                    content=text,
                    metadata={
                        "chunk_index": chunk_index,
                        "start_offset": start,
                        "end_offset": end,
                        "mime_type": attachment.mime_type,
                        "content_hash": attachment.content_hash,
                        "attachment_scope": (
                            "current_message"
                            if attachment.id in current_ids
                            else "conversation_history"
                        ),
                    },
                ))
        return result


def _routing_attachment_context(
    attachments: Sequence[ChatContextDocument],
) -> str:
    """Build a small file preview used only by the automatic intent classifier."""

    if not attachments:
        return ""
    previews: list[str] = []
    seen_source_ids: set[str] = set()
    for attachment in attachments:
        if attachment.source_id in seen_source_ids:
            continue
        seen_source_ids.add(attachment.source_id)
        previews.append(
            f"[파일명] {attachment.title}\n"
            f"[본문 일부] {attachment.content[:1_500]}"
        )
        if len(previews) >= 3:
            break
    return truncate_to_token_budget(
        "\n\n".join(previews),
        budget=2_500,
    )


def _conversation_attachment_ids(
    *,
    current_attachment_ids: Sequence[str],
    stored_history: Sequence[Message],
    limit: int = 5,
) -> list[str]:
    """현재 파일을 우선하고 최근 대화의 첨부를 이어지는 질문 문맥에 포함한다."""

    selected: list[str] = []

    def append_unique(attachment_id: str) -> None:
        normalized = attachment_id.strip()
        if normalized and normalized not in selected and len(selected) < limit:
            selected.append(normalized)

    for attachment_id in current_attachment_ids:
        append_unique(attachment_id)
    for message in reversed(stored_history):
        if message.role != "user":
            continue
        for attachment_id in reversed(message.attachment_ids):
            append_unique(attachment_id)
        if len(selected) >= limit:
            break
    return selected


def _request_type(intent: str) -> AIRequestType:
    if intent == "auto":
        return AIRequestType.AUTO
    if intent == "experience":
        return AIRequestType.EXPERIENCE_EXTRACTION
    if intent == "job":
        return AIRequestType.JOB_ANALYSIS
    return AIRequestType.CHAT


def _query_terms(text: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"[가-힣A-Za-z0-9_]+", text)
        if len(token) >= 2
    }


def _retrieval_query(
    content: str,
    attachments: Sequence[ChatContextDocument],
) -> str:
    normalized = content.strip()
    if normalized:
        return normalized
    if attachments:
        return "\n".join([
            attachments[0].title,
            attachments[0].content[:1_000],
        ])
    return "저장된 커리어 경험"


__all__ = ["CareerMemoryAI", "PreparedChatRequest"]
