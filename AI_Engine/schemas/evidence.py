"""Evidence schemas for chat, manual text, and uploaded file sources."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator, model_validator

from .common import Confidence, Identifier, SchemaModel, normalize_newlines


class EvidenceSourceType(str, Enum):
    """Original source type used to create or support an experience draft."""

    MESSAGE_TEXT = "message_text"
    MANUAL_TEXT = "manual_text"
    FILE = "file"


class EvidenceSource(SchemaModel):
    """Original evidence produced from a chat message, manual text, or file."""

    id: Identifier = Field(
        validation_alias=AliasChoices("id", "source_ref_id"),
        description="Evidence ID referenced by ExperienceDraft.source_ref_ids",
    )
    type: EvidenceSourceType = Field(
        validation_alias=AliasChoices("type", "source_type"),
    )
    title: str = Field(default="", description="Display title for the evidence")

    message_id: Identifier | None = None
    manual_input_id: Identifier | None = None
    attachment_id: Identifier | None = None

    filename: str | None = None
    mime_type: str | None = None
    uploaded_at: datetime | None = None
    content_hash: str | None = None

    text: str | None = Field(
        default=None,
        validation_alias=AliasChoices("text", "original_text"),
        description="Original text for chat/manual evidence. Files may use storage refs.",
    )

    @field_validator("type", mode="before")
    @classmethod
    def normalize_source_type(cls, value: object) -> object:
        if value == "conversation_message":
            return EvidenceSourceType.MESSAGE_TEXT.value
        return value

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return value.strip()

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_newlines(value)

    @model_validator(mode="after")
    def validate_source_identifier(self) -> "EvidenceSource":
        identifier_by_type = {
            EvidenceSourceType.MESSAGE_TEXT.value: self.message_id,
            EvidenceSourceType.MANUAL_TEXT.value: self.manual_input_id,
            EvidenceSourceType.FILE.value: self.attachment_id,
        }
        if not identifier_by_type[self.type]:
            raise ValueError(
                f"{self.type} 근거에는 대응하는 원본 ID가 필요합니다."
            )
        if self.type == EvidenceSourceType.FILE.value and not self.filename:
            raise ValueError("파일 근거에는 filename이 필요합니다.")
        return self


class EvidenceCitation(SchemaModel):
    """Source location used by an experience field or evidence-confirmed fact."""

    source_ref_id: Identifier
    quote: str = Field(
        default="",
        description="Short original excerpt used for the claim",
    )
    page_number: Annotated[int, Field(ge=1)] | None = None
    start_offset: Annotated[int, Field(ge=0)] | None = None
    end_offset: Annotated[int, Field(ge=0)] | None = None
    confidence: Confidence | None = None

    @field_validator("quote")
    @classmethod
    def normalize_quote(cls, value: str) -> str:
        return normalize_newlines(value).strip()

    @model_validator(mode="after")
    def validate_offsets(self) -> "EvidenceCitation":
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset < self.start_offset
        ):
            raise ValueError("end_offset은 start_offset보다 작을 수 없습니다.")
        if (
            not self.quote
            and self.page_number is None
            and self.start_offset is None
        ):
            raise ValueError(
                "인용에는 quote, page_number 또는 start_offset 중 하나가 필요합니다."
            )
        return self


__all__ = [
    "EvidenceCitation",
    "EvidenceSource",
    "EvidenceSourceType",
]
