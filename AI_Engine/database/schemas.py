"""프론트엔드가 사용하는 대화·메시지 API 요청과 응답 스키마."""

from __future__ import annotations

# 1. Python 기본 기능
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

# 2. Pydantic 검증 기능
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

InputIntent = Literal[
    "auto",
    "experience",
    "file",
    "job",
    "question",
    "advice",
]


# 3. API 응답의 공통 부모
# from_attributes를 켜서 SQLAlchemy 객체를 API 응답으로 안전하게 변환한다.
class DatabaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# 4. 대화 생성 요청
class ConversationCreate(BaseModel):
    title: str = "새 대화"
    client_request_id: UUID

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        return normalized or "새 대화"


# 5. 대화 수정·삭제 요청
class ConversationUpdate(BaseModel):
    title: str | None = None
    status: Literal["active", "archived"] | None = None
    base_version: int = Field(ge=1)
    client_request_id: UUID

    @field_validator("title")
    @classmethod
    def normalize_optional_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("대화 제목은 비어 있을 수 없습니다.")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> "ConversationUpdate":
        if self.title is None and self.status is None:
            raise ValueError("변경할 제목 또는 상태가 필요합니다.")
        return self


class ConversationDelete(BaseModel):
    version: int = Field(ge=1)
    client_request_id: UUID


class ConversationDeleteResponse(BaseModel):
    deleted_id: str


# 6. 대화 응답
class ConversationResponse(DatabaseResponse):
    id: str
    title: str
    status: Literal["active", "archived"]
    last_message_preview: str | None = None
    message_count: int = Field(ge=0)
    pending_proposal_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime
    version: int = Field(ge=1)

    @field_serializer("created_at", "updated_at")
    def serialize_utc_datetime(self, value: datetime) -> str:
        # SQLite가 timezone 정보를 제거해 반환해도 공개 API에는 UTC 오프셋을 복원한다.
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total_count: int = Field(ge=0)
    next_cursor: str | None = None


# 7. 메시지 전송 요청
class MessageContext(BaseModel):
    experience_ids: list[str] = Field(default_factory=list)
    job_id: str | None = None
    selected_proposal_id: str | None = None


class MessageCreate(BaseModel):
    content: str = Field(default="", max_length=50_000)
    intent: InputIntent = "auto"
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)
    context: MessageContext = Field(default_factory=MessageContext)
    response_mode: Literal["complete", "stream"] = "complete"
    client_request_id: UUID

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return value.replace("\r\n", "\n").replace("\r", "\n").strip()

    @field_validator("attachment_ids")
    @classmethod
    def normalize_attachment_ids(cls, values: list[str]) -> list[str]:
        normalized = [
            value.strip()
            for value in values
            if value.strip()
        ]
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def require_content_or_attachment(self) -> "MessageCreate":
        if not self.content and not self.attachment_ids:
            raise ValueError("메시지 또는 첨부 파일이 필요합니다.")
        return self


# 8. 메시지 응답
class MessageResponse(DatabaseResponse):
    id: str
    conversation_id: str
    sequence: int = Field(ge=0)
    role: Literal["user", "assistant", "system"]
    status: Literal[
        "queued",
        "processing",
        "streaming",
        "completed",
        "failed",
        "cancelled",
    ]
    content: str
    requested_intent: str
    resolved_intents: list[str]
    attachment_ids: list[str]
    citations: list[dict[str, object]]
    proposal_ids: list[str]
    actions: list[dict[str, object]]
    error: dict[str, object] | None = None
    created_at: datetime
    completed_at: datetime | None = None
    request_message_id: str | None = None

    @field_serializer("created_at", "completed_at")
    def serialize_optional_utc_datetime(
        self,
        value: datetime | None,
    ) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    total_count: int = Field(ge=0)
    next_cursor: str | None = None


__all__ = [
    "ConversationCreate",
    "ConversationDelete",
    "ConversationDeleteResponse",
    "ConversationListResponse",
    "ConversationResponse",
    "ConversationUpdate",
    "DatabaseResponse",
    "InputIntent",
    "MessageContext",
    "MessageCreate",
    "MessageListResponse",
    "MessageResponse",
]
