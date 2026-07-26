"""대화형 챗봇의 요청·응답·스트리밍 데이터 계약."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .common import AIError, Identifier, SchemaModel, SequenceNumber


class ChatMode(str, Enum):
    """커리어 챗에서 사용자가 선택하는 실행 모드."""

    AUTO = "auto"
    CHAT = "chat"
    EXPERIENCE_EXTRACTION = "experience_extraction"
    JOB_ANALYSIS = "job_analysis"


class ChatRole(str, Enum):
    """대화 메시지 작성 주체."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class AttachmentReference(SchemaModel):
    """이미 업로드된 첨부 파일을 AI 요청에서 참조하는 정보."""

    id: Identifier
    filename: str
    mime_type: str | None = None
    size_bytes: int = Field(ge=0)
    content_hash: str | None = None
    extracted_text_available: bool = False

    @field_validator("filename")
    @classmethod
    def require_filename(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("첨부 파일 이름은 비어 있을 수 없습니다.")
        return normalized


class ChatMessage(SchemaModel):
    """저장되거나 AI 문맥에 전달되는 대화 메시지."""

    id: Identifier
    conversation_id: Identifier
    sequence: SequenceNumber
    role: ChatRole
    content: str = ""
    attachment_ids: list[Identifier] = Field(default_factory=list)
    created_at: datetime

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return value.replace("\r\n", "\n").replace("\r", "\n")

    @field_validator("attachment_ids")
    @classmethod
    def normalize_attachment_ids(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @model_validator(mode="after")
    def require_content_or_attachment(self) -> "ChatMessage":
        if not self.content.strip() and not self.attachment_ids:
            raise ValueError("메시지에는 content 또는 attachment_ids가 필요합니다.")
        return self


class ChatRequest(SchemaModel):
    """대화형 챗봇에 한 번의 사용자 메시지를 전달하는 요청."""

    client_request_id: Identifier
    conversation_id: Identifier
    message_id: Identifier
    sequence: SequenceNumber
    mode: ChatMode = ChatMode.AUTO
    content: str = ""
    attachment_ids: list[Identifier] = Field(default_factory=list)
    # 로그인 계정의 표시 이름만 AI 문맥에 전달한다.
    # 이메일과 내부 user_id 같은 개인정보·식별자는 전달하지 않는다.
    user_display_name: str = Field(default="", max_length=100)
    # DB에서 복원한 이전 대화입니다.
    # 현재 사용자 메시지는 content에 따로 들어가므로 history에는 포함하지 않습니다.
    history: list[ChatMessage] = Field(default_factory=list)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return value.replace("\r\n", "\n").replace("\r", "\n")

    @field_validator("user_display_name")
    @classmethod
    def normalize_user_display_name(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("attachment_ids")
    @classmethod
    def normalize_attachment_ids(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @model_validator(mode="after")
    def require_input(self) -> "ChatRequest":
        if not self.content.strip() and not self.attachment_ids:
            raise ValueError("채팅 요청에는 content 또는 attachment_ids가 필요합니다.")
        return self


class ChatCitation(SchemaModel):
    """챗봇 답변이 참조한 저장 경험 또는 원본 근거."""

    source_id: Identifier
    source_type: Literal["experience", "evidence", "attachment", "message"]
    title: str = ""
    quote: str = ""

    @field_validator("title", "quote")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.replace("\r\n", "\n").replace("\r", "\n").strip()


class SuggestedActionType(str, Enum):
    """답변 뒤에 프론트엔드가 제시할 수 있는 후속 행동."""

    ORGANIZE_EXPERIENCE = "organize_experience"
    ANALYZE_JOB = "analyze_job"
    OPEN_EXPERIENCE = "open_experience"
    ASK_FOLLOW_UP = "ask_follow_up"


class SuggestedAction(SchemaModel):
    """챗봇이 제안하되 자동 실행하지 않는 후속 행동."""

    type: SuggestedActionType
    label: str
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("label")
    @classmethod
    def require_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("후속 행동 라벨은 비어 있을 수 없습니다.")
        return normalized


class ChatResponse(SchemaModel):
    """스트리밍이 끝난 뒤 저장 가능한 최종 챗봇 응답."""

    request_id: Identifier
    conversation_id: Identifier
    message: ChatMessage
    citations: list[ChatCitation] = Field(default_factory=list)
    suggested_actions: list[SuggestedAction] = Field(default_factory=list)
    model_version: Identifier
    prompt_version: Identifier
    schema_version: Identifier
    error: AIError | None = None

    @model_validator(mode="after")
    def validate_assistant_message(self) -> "ChatResponse":
        if self.message.conversation_id != self.conversation_id:
            raise ValueError("응답 메시지의 conversation_id가 응답과 다릅니다.")
        if self.message.role != ChatRole.ASSISTANT.value:
            raise ValueError("ChatResponse.message 역할은 assistant여야 합니다.")
        return self


class ChatStreamEventType(str, Enum):
    """SSE 등으로 전달하는 챗봇 스트리밍 이벤트 종류."""

    STARTED = "started"
    TOKEN = "token"
    CITATION = "citation"
    ACTION = "action"
    COMPLETED = "completed"
    ERROR = "error"


class ChatStreamEvent(SchemaModel):
    """챗봇 스트리밍 전송의 공통 이벤트 봉투."""

    event_id: Identifier
    request_id: Identifier
    conversation_id: Identifier
    type: ChatStreamEventType
    sequence: SequenceNumber
    created_at: datetime
    text_delta: str | None = None
    citation: ChatCitation | None = None
    action: SuggestedAction | None = None
    response: ChatResponse | None = None
    error: AIError | None = None

    @model_validator(mode="after")
    def validate_payload_for_type(self) -> "ChatStreamEvent":
        required_payload = {
            ChatStreamEventType.TOKEN.value: self.text_delta,
            ChatStreamEventType.CITATION.value: self.citation,
            ChatStreamEventType.ACTION.value: self.action,
            ChatStreamEventType.COMPLETED.value: self.response,
            ChatStreamEventType.ERROR.value: self.error,
        }
        if self.type in required_payload and required_payload[self.type] is None:
            raise ValueError(f"{self.type} 이벤트에 필요한 payload가 없습니다.")
        return self


__all__ = [
    "AttachmentReference",
    "ChatCitation",
    "ChatMessage",
    "ChatMode",
    "ChatRequest",
    "ChatResponse",
    "ChatRole",
    "ChatStreamEvent",
    "ChatStreamEventType",
    "SuggestedAction",
    "SuggestedActionType",
]
