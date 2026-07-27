"""대화 생성·조회와 저장된 메시지 이력을 제공하는 API."""

from __future__ import annotations

# 1. Python 기본 기능
import os
import json
import queue
import threading
from functools import lru_cache
from uuid import uuid4

# 2. FastAPI와 SQLAlchemy
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

# 3. 데이터베이스 모델과 공개 API 스키마
from AI_Engine.database.connection import get_database_session
from AI_Engine.database.models import Attachment, Conversation, Message, User, utc_now
from AI_Engine.auth.dependencies import get_current_user, require_csrf_user
from AI_Engine.database.schemas import (
    ConversationCreate,
    ConversationDelete,
    ConversationDeleteResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageCreate,
    MessageListResponse,
    MessageResponse,
)
from AI_Engine.chatbot_ai import ChatbotAI
from AI_Engine.AI_langchain import CareerMemoryAI
from AI_Engine.schemas import ChatMessage, ChatMode, ChatRequest, ChatRole


# 4. 대화 API 공통 경로
router = APIRouter(
    prefix="/api/v2/conversations",
    tags=["conversations"],
)


# 4-1. AI에 전달할 최근 대화 개수
# 대화가 매우 길어졌을 때 모델 입력 한도와 API 비용이 계속 커지는 것을 막는다.
CHAT_HISTORY_MESSAGE_LIMIT = max(
    0,
    int(os.getenv("CHAT_HISTORY_MESSAGE_LIMIT", "40")),
)


# 5. 대화 ID 생성
# DB의 숫자 순번을 외부에 노출하지 않고 프론트엔드가 문자열 ID로 다룰 수 있게 한다.
def create_resource_id(prefix: str) -> str:
    """자원 종류 접두어와 UUID를 조합해 충돌 가능성이 낮은 ID를 만든다."""

    return f"{prefix}-{uuid4()}"


# 6. 대화형 AI 생성
# 서버 프로세스 안에서 하나의 ChatbotAI를 재사용해야 conversation_id별 메모리가 유지된다.
@lru_cache(maxsize=1)
def get_chatbot_ai() -> ChatbotAI:
    """환경 변수로 선택한 Gemini 또는 OpenAI 챗봇을 한 번 생성해 재사용한다."""

    return ChatbotAI.create_default()


@lru_cache(maxsize=1)
def get_career_memory_ai() -> CareerMemoryAI:
    """대화 문맥·RAG·요약·자동 의도를 조립하는 공통 파이프라인."""

    return CareerMemoryAI()


# 7. 프론트엔드 intent 변환
# 일반 질문과 조언은 명시적인 chat 모드로, auto는 챗봇의 안전한 기본 경로로 전달한다.
def convert_intent_to_chat_mode(intent: str) -> ChatMode:
    """현재 대화형 챗봇이 처리할 수 있는 공개 intent를 내부 ChatMode로 바꾼다."""

    if intent == "auto":
        return ChatMode.AUTO
    if intent in {"question", "advice"}:
        return ChatMode.CHAT

    if intent == "job":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="공고 분석 기능은 아직 제공되지 않아요!",
        )

    # API 내부에서는 영문 값을 사용하지만 사용자에게는 화면의 한글 명칭으로 안내한다.
    intent_labels = {
        "experience": "경험 정리",
    }
    requested_intent = intent_labels.get(intent, intent)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            f"{requested_intent} 기능은 아직 메시지 API에 연결되지 않았습니다. "
            "현재는 자동, 일반 질문, 조언을 사용할 수 있습니다."
        ),
    )


# 8. 페이지 위치 확인
# 공개 cursor는 문자열이지만 현재 SQLite 단계에서는 조회 시작 위치를 숫자로 관리한다.
def decode_cursor(cursor: str | None) -> int:
    """문자열 cursor를 0 이상의 목록 시작 위치로 변환한다."""

    if cursor is None:
        return 0
    try:
        offset = int(cursor)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="cursor는 0 이상의 정수 문자열이어야 합니다.",
        ) from error
    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="cursor는 0 이상의 정수 문자열이어야 합니다.",
        )
    return offset


# 9. 대화 존재 확인
def get_conversation_or_404(
    conversation_id: str,
    user_id: str,
    database: Session,
) -> Conversation:
    """현재 사용자가 소유한 대화만 조회하고 그 외에는 404를 반환한다."""

    conversation = database.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="대화를 찾을 수 없습니다.",
        )
    return conversation


def validate_attachment_ownership(
    attachment_ids: list[str],
    user_id: str,
    database: Session,
) -> None:
    """메시지를 저장하기 전에 모든 첨부가 현재 사용자 소유인지 확인한다."""

    if not attachment_ids:
        return
    owned_ids = set(database.scalars(
        select(Attachment.id).where(
            Attachment.user_id == user_id,
            Attachment.id.in_(attachment_ids),
        )
    ))
    missing = [
        attachment_id for attachment_id in attachment_ids
        if attachment_id not in owned_ids
    ]
    if missing:
        raise HTTPException(
            status_code=422,
            detail="열 수 없는 첨부 파일이 포함되어 있습니다.",
        )


# 10. 새 대화 생성
# 같은 client_request_id가 다시 오면 기존 대화를 반환해 재시도 중 중복 생성을 막는다.
@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    request: ConversationCreate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> Conversation:
    """제목과 요청 UUID를 받아 새 대화를 저장하고 반환한다."""

    request_id = str(request.client_request_id)
    existing_conversation = database.scalar(
        select(Conversation).where(
            Conversation.client_request_id == request_id,
            Conversation.user_id == current_user.id,
        )
    )
    if existing_conversation is not None:
        return existing_conversation

    conversation = Conversation(
        id=create_resource_id("CONV"),
        user_id=current_user.id,
        client_request_id=request_id,
        title=request.title,
    )
    database.add(conversation)
    try:
        database.commit()
    except IntegrityError:
        # 동시에 같은 요청이 처리된 경우 먼저 저장된 결과를 다시 조회한다.
        database.rollback()
        existing_conversation = database.scalar(
            select(Conversation).where(
                Conversation.client_request_id == request_id,
                Conversation.user_id == current_user.id,
            )
        )
        if existing_conversation is None:
            raise
        return existing_conversation

    database.refresh(conversation)
    return conversation


# 11. 대화 목록 조회
@router.get(
    "",
    response_model=ConversationListResponse,
)
def list_conversations(
    conversation_status: str = Query(
        default="active",
        alias="status",
        pattern="^(active|archived)$",
    ),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
) -> ConversationListResponse:
    """상태와 페이지 위치를 기준으로 최근 대화 목록을 반환한다."""

    offset = decode_cursor(cursor)
    status_filter = (
        (Conversation.status == conversation_status)
        & (Conversation.user_id == current_user.id)
    )
    total_count = database.scalar(
        select(func.count(Conversation.id)).where(status_filter)
    )
    conversations = list(
        database.scalars(
            select(Conversation)
            .where(status_filter)
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
    )

    next_offset = offset + len(conversations)
    next_cursor = (
        str(next_offset)
        if next_offset < (total_count or 0)
        else None
    )
    return ConversationListResponse(
        items=[
            ConversationResponse.model_validate(conversation)
            for conversation in conversations
        ],
        total_count=total_count or 0,
        next_cursor=next_cursor,
    )


# 12. 대화 상세 조회
@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse,
)
def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
) -> Conversation:
    """주소의 대화 ID와 일치하는 대화 하나를 반환한다."""

    return get_conversation_or_404(
        conversation_id,
        current_user.id,
        database,
    )


# 13. 대화 수정
# base_version이 현재 값과 같을 때만 변경해 여러 화면의 동시 수정을 감지한다.
@router.patch(
    "/{conversation_id}",
    response_model=ConversationResponse,
)
def update_conversation(
    conversation_id: str,
    request: ConversationUpdate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> Conversation:
    """대화 제목 또는 활성·보관 상태를 변경하고 버전을 증가시킨다."""

    conversation = get_conversation_or_404(
        conversation_id,
        current_user.id,
        database,
    )
    if conversation.version != request.base_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="대화가 다른 곳에서 변경되었습니다. 목록을 새로고침해 주세요.",
        )

    if request.title is not None:
        conversation.title = request.title
    if request.status is not None:
        conversation.status = request.status
    conversation.version += 1
    database.commit()
    database.refresh(conversation)
    return conversation


# 14. 대화 삭제
# ORM 관계의 delete-orphan 규칙에 따라 해당 대화의 메시지도 함께 제거한다.
@router.delete(
    "/{conversation_id}",
    response_model=ConversationDeleteResponse,
)
def delete_conversation(
    conversation_id: str,
    request: ConversationDelete,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> ConversationDeleteResponse:
    """버전을 확인한 뒤 대화와 그 메시지 이력을 삭제한다."""

    conversation = get_conversation_or_404(
        conversation_id,
        current_user.id,
        database,
    )
    if conversation.version != request.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="대화가 다른 곳에서 변경되었습니다. 목록을 새로고침해 주세요.",
        )

    database.delete(conversation)
    database.commit()
    return ConversationDeleteResponse(deleted_id=conversation_id)


# 15. 대화 메시지 전송
# 사용자 메시지를 먼저 저장하고 AI 호출이 끝나면 assistant 메시지를 이어서 저장한다.
@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_message(
    conversation_id: str,
    request: MessageCreate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
    chatbot: ChatbotAI = Depends(get_chatbot_ai),
    ai_pipeline: CareerMemoryAI = Depends(get_career_memory_ai),
) -> MessageResponse:
    """사용자 메시지를 저장하고 대화형 AI의 완성된 답변을 반환한다."""

    conversation = get_conversation_or_404(
        conversation_id,
        current_user.id,
        database,
    )
    ai_mode = convert_intent_to_chat_mode(request.intent)
    validate_attachment_ownership(
        request.attachment_ids,
        current_user.id,
        database,
    )
    request_id = str(request.client_request_id)

    # 같은 사용자 동작을 재시도했으면 이미 완료된 assistant 메시지를 반환한다.
    existing_user_message = database.scalar(
        select(Message).where(
            Message.client_request_id == request_id,
            Message.role == "user",
        )
    )
    if existing_user_message is not None:
        existing_answer = database.scalar(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.sequence == existing_user_message.sequence + 1,
                Message.role == "assistant",
            )
        )
        if existing_answer is not None:
            response = MessageResponse.model_validate(existing_answer)
            return response.model_copy(
                update={"request_message_id": existing_user_message.id}
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="같은 요청의 AI 처리가 아직 완료되지 않았습니다.",
        )

    user_sequence = conversation.message_count + 1
    user_message = Message(
        id=create_resource_id("MSG"),
        conversation_id=conversation.id,
        client_request_id=request_id,
        sequence=user_sequence,
        role="user",
        status="completed",
        content=request.content,
        requested_intent=request.intent,
        resolved_intents=[],
        attachment_ids=request.attachment_ids,
        completed_at=utc_now(),
    )
    database.add(user_message)
    conversation.message_count = user_sequence
    conversation.last_message_preview = request.content[:300]
    conversation.version += 1
    database.commit()
    database.refresh(user_message)

    # 현재 사용자 메시지보다 앞에 저장된 완료 메시지를 최근 순서부터 제한해서 읽는다.
    # 조회 결과는 Gemini가 대화 순서를 이해할 수 있도록 다시 오래된 순서로 뒤집는다.
    stored_history = list(
        database.scalars(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.sequence < user_sequence,
                Message.status == "completed",
                Message.role.in_(("user", "assistant")),
            )
            .order_by(Message.sequence.desc())
            .limit(CHAT_HISTORY_MESSAGE_LIMIT)
        )
    )
    stored_history.reverse()

    prepared = ai_pipeline.prepare_chat(
        database=database,
        conversation=conversation,
        current_user=current_user,
        user_message=user_message,
        stored_history=stored_history,
    )
    resolved_intent = str(prepared.route.route)

    ai_request = prepared.request.model_copy(update={"mode": ai_mode})

    try:
        ai_response = chatbot.invoke(ai_request)
    except Exception as error:
        # 실패 사실도 메시지 이력에 남겨 새로고침 후 상태를 확인할 수 있게 한다.
        failed_message = Message(
            id=create_resource_id("MSG"),
            conversation_id=conversation.id,
            sequence=user_sequence + 1,
            role="assistant",
            status="failed",
            content="",
            requested_intent=request.intent,
            resolved_intents=[],
            error={
                "code": "chat_model_error",
                "message": "AI 답변을 생성하지 못했습니다.",
                "retryable": True,
            },
        )
        database.add(failed_message)
        conversation.message_count = user_sequence + 1
        conversation.version += 1
        database.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 답변을 생성하지 못했습니다.",
        ) from error

    assistant_message = Message(
        id=ai_response.message.id,
        conversation_id=conversation.id,
        sequence=user_sequence + 1,
        role="assistant",
        status="completed",
        content=ai_response.message.content,
        requested_intent=request.intent,
        resolved_intents=[resolved_intent],
        attachment_ids=[],
        citations=[
            citation.model_dump(mode="json")
            for citation in ai_response.citations
        ],
        actions=[
            action.model_dump(mode="json")
            for action in ai_response.suggested_actions
        ],
        completed_at=ai_response.message.created_at,
    )
    database.add(assistant_message)
    conversation.message_count = user_sequence + 1
    conversation.last_message_preview = assistant_message.content[:300]
    conversation.version += 1
    database.commit()
    database.refresh(assistant_message)

    response = MessageResponse.model_validate(assistant_message)
    return response.model_copy(
        update={"request_message_id": user_message.id}
    )


# 16. 대화 메시지 실시간 전송
# 공개 SSE 계약에 맞춰 접수, 의도, 답변 조각, 완료 또는 실패 이벤트를 순서대로 보낸다.
@router.post("/{conversation_id}/messages/stream")
def stream_message(
    conversation_id: str,
    request: MessageCreate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
    chatbot: ChatbotAI = Depends(get_chatbot_ai),
    ai_pipeline: CareerMemoryAI = Depends(get_career_memory_ai),
) -> StreamingResponse:
    """AI 답변을 생성되는 즉시 SSE 이벤트로 전달하고 최종 내용을 DB에 저장한다."""

    conversation = get_conversation_or_404(
        conversation_id,
        current_user.id,
        database,
    )
    ai_mode = convert_intent_to_chat_mode(request.intent)
    validate_attachment_ownership(
        request.attachment_ids,
        current_user.id,
        database,
    )
    request_id = str(request.client_request_id)
    existing_user = database.scalar(
        select(Message).where(
            Message.client_request_id == request_id,
            Message.role == "user",
        )
    )

    # 같은 요청을 다시 보내면 새 AI 호출을 만들지 않고 저장된 최종 답변을 재전송한다.
    if existing_user is not None:
        existing_assistant = database.scalar(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.sequence == existing_user.sequence + 1,
                Message.role == "assistant",
            )
        )
        if existing_assistant is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="같은 요청의 AI 처리가 아직 완료되지 않았습니다.",
            )

        def replay_saved_message():
            yield format_sse_event(
                "message.accepted",
                1,
                {
                    "type": "message.accepted",
                    "sequence": 1,
                    "user_message": MessageResponse.model_validate(
                        existing_user
                    ).model_dump(mode="json"),
                    "assistant_message_id": existing_assistant.id,
                },
            )
            yield format_sse_event(
                "message.completed",
                2,
                {
                    "type": "message.completed",
                    "sequence": 2,
                    "message": MessageResponse.model_validate(
                        existing_assistant
                    ).model_dump(mode="json"),
                },
            )

        return StreamingResponse(
            replay_saved_message(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    user_sequence = conversation.message_count + 1
    user_message = Message(
        id=create_resource_id("MSG"),
        conversation_id=conversation.id,
        client_request_id=request_id,
        sequence=user_sequence,
        role="user",
        status="completed",
        content=request.content,
        requested_intent=request.intent,
        resolved_intents=[],
        attachment_ids=request.attachment_ids,
        completed_at=utc_now(),
    )
    database.add(user_message)
    conversation.message_count = user_sequence
    conversation.last_message_preview = request.content[:300]
    conversation.version += 1
    database.commit()
    database.refresh(user_message)

    stored_history = list(
        database.scalars(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.sequence < user_sequence,
                Message.status == "completed",
                Message.role.in_(("user", "assistant")),
            )
            .order_by(Message.sequence.desc())
            .limit(CHAT_HISTORY_MESSAGE_LIMIT)
        )
    )
    stored_history.reverse()
    prepared = ai_pipeline.prepare_chat(
        database=database,
        conversation=conversation,
        current_user=current_user,
        user_message=user_message,
        stored_history=stored_history,
    )
    ai_request = prepared.request.model_copy(update={"mode": ai_mode})
    resolved_intent = str(prepared.route.route)

    # 브라우저가 새로고침되거나 다른 화면으로 이동해 SSE 연결이 끊겨도
    # AI 생성과 DB 저장이 계속되도록 별도의 작업 스레드와 DB 세션을 사용한다.
    # 경험 초안 생성은 이 메시지 스트림이 아니라 별도 경험 정리 버튼 API가 맡는다.

    assistant_id = create_resource_id("MSG")
    assistant_message = Message(
        id=assistant_id,
        conversation_id=conversation.id,
        sequence=user_sequence + 1,
        role="assistant",
        status="streaming",
        content="",
        requested_intent=request.intent,
        resolved_intents=[],
        attachment_ids=[],
    )
    database.add(assistant_message)
    conversation.message_count = user_sequence + 1
    conversation.version += 1
    database.commit()

    worker_events: queue.SimpleQueue[tuple[str, object]] = queue.SimpleQueue()
    worker_session_factory = sessionmaker(
        bind=database.get_bind(),
        autoflush=False,
        expire_on_commit=False,
    )

    def generate_answer_in_background() -> None:
        answer_parts: list[str] = []
        completed_response = None
        with worker_session_factory() as worker_database:
            saved_assistant = worker_database.get(Message, assistant_id)
            saved_conversation = worker_database.get(
                Conversation,
                conversation.id,
            )
            if saved_assistant is None or saved_conversation is None:
                worker_events.put(
                    (
                        "error",
                        {
                            "code": "message_not_found",
                            "message": "저장된 AI 답변 작업을 찾지 못했습니다.",
                            "retryable": True,
                        },
                    )
                )
                return

            try:
                for ai_event in chatbot.stream(ai_request):
                    if ai_event.type == "token":
                        delta = ai_event.text_delta or ""
                        if not delta:
                            continue
                        answer_parts.append(delta)

                        # 중간 답변도 저장하므로 다른 화면에서 돌아왔을 때
                        # 지금까지 생성된 내용을 다시 확인할 수 있다.
                        saved_assistant.content = "".join(answer_parts)
                        worker_database.commit()
                        worker_events.put(("token", delta))
                    elif ai_event.type == "error":
                        saved_assistant.status = "failed"
                        saved_assistant.error = ai_event.error.model_dump(
                            mode="json"
                        )
                        saved_assistant.completed_at = utc_now()
                        worker_database.commit()
                        worker_events.put(
                            ("error", saved_assistant.error)
                        )
                        return
                    elif ai_event.type == "completed":
                        completed_response = getattr(ai_event, "response", None)

                saved_assistant.content = "".join(answer_parts)
                saved_assistant.status = "completed"
                saved_assistant.resolved_intents = [resolved_intent]
                if completed_response is not None:
                    saved_assistant.citations = [
                        citation.model_dump(mode="json")
                        for citation in completed_response.citations
                    ]
                    saved_assistant.actions = [
                        action.model_dump(mode="json")
                        for action in completed_response.suggested_actions
                    ]
                saved_assistant.completed_at = utc_now()
                saved_conversation.last_message_preview = (
                    saved_assistant.content[:300]
                )
                saved_conversation.version += 1
                worker_database.commit()
                worker_database.refresh(saved_assistant)
                worker_events.put(
                    (
                        "completed",
                        MessageResponse.model_validate(
                            saved_assistant
                        ).model_dump(mode="json"),
                    )
                )
            except Exception:
                saved_assistant.status = "failed"
                saved_assistant.error = {
                    "code": "chat_model_error",
                    "message": "AI 답변을 생성하지 못했습니다.",
                    "retryable": True,
                }
                saved_assistant.completed_at = utc_now()
                worker_database.commit()
                worker_events.put(("error", saved_assistant.error))

    threading.Thread(
        target=generate_answer_in_background,
        name=f"chat-{assistant_id}",
        daemon=True,
    ).start()

    def generate_events():
        public_sequence = 1
        yield format_sse_event(
            "message.accepted",
            public_sequence,
            {
                "type": "message.accepted",
                "sequence": public_sequence,
                "user_message": MessageResponse.model_validate(
                    user_message
                ).model_dump(mode="json"),
                "assistant_message_id": assistant_id,
            },
        )
        public_sequence += 1
        yield format_sse_event(
            "intent.resolved",
            public_sequence,
            {
                "type": "intent.resolved",
                "sequence": public_sequence,
                "intents": [resolved_intent],
            },
        )
        public_sequence += 1

        while True:
            try:
                event_type, payload = worker_events.get(timeout=1)
            except queue.Empty:
                # 연결 상태를 확인할 수 있도록 주기적으로 SSE 주석을 보낸다.
                yield ": heartbeat\n\n"
                continue

            if event_type == "token":
                yield format_sse_event(
                    "assistant.delta",
                    public_sequence,
                    {
                        "type": "assistant.delta",
                        "sequence": public_sequence,
                        "message_id": assistant_id,
                        "delta": payload,
                    },
                )
                public_sequence += 1
            elif event_type == "error":
                yield format_sse_event(
                    "message.failed",
                    public_sequence,
                    {
                        "type": "message.failed",
                        "sequence": public_sequence,
                        "message_id": assistant_id,
                        "error": payload,
                    },
                )
                return
            elif event_type == "completed":
                yield format_sse_event(
                    "message.completed",
                    public_sequence,
                    {
                        "type": "message.completed",
                        "sequence": public_sequence,
                        "message": payload,
                    },
                )
                return

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def format_sse_event(
    event_type: str,
    sequence: int,
    payload: dict[str, object],
) -> str:
    """공개 이벤트를 브라우저가 읽는 SSE 텍스트 형식으로 변환한다."""

    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_type}\nid: {sequence}\ndata: {data}\n\n"


# 17. 대화 메시지 이력 조회
@router.get(
    "/{conversation_id}/messages",
    response_model=MessageListResponse,
)
def list_messages(
    conversation_id: str,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
) -> MessageListResponse:
    """대화에 저장된 메시지를 오래된 순서대로 반환한다."""

    get_conversation_or_404(
        conversation_id,
        current_user.id,
        database,
    )
    offset = decode_cursor(cursor)
    conversation_filter = Message.conversation_id == conversation_id
    total_count = database.scalar(
        select(func.count(Message.id)).where(conversation_filter)
    )
    messages = list(
        database.scalars(
            select(Message)
            .where(conversation_filter)
            .order_by(Message.sequence.asc())
            .offset(offset)
            .limit(limit)
        )
    )

    next_offset = offset + len(messages)
    next_cursor = (
        str(next_offset)
        if next_offset < (total_count or 0)
        else None
    )
    return MessageListResponse(
        items=[
            MessageResponse.model_validate(message)
            for message in messages
        ],
        total_count=total_count or 0,
        next_cursor=next_cursor,
    )


__all__ = [
    "create_conversation",
    "create_resource_id",
    "convert_intent_to_chat_mode",
    "decode_cursor",
    "delete_conversation",
    "get_chatbot_ai",
    "get_conversation",
    "get_conversation_or_404",
    "list_conversations",
    "list_messages",
    "router",
    "send_message",
    "stream_message",
    "update_conversation",
]
