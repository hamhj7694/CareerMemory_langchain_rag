"""Evidence schemas for chat, manual text, and uploaded file sources."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator, model_validator

from .common import (
    Confidence,
    Identifier,
    SchemaModel,
    normalize_newlines,
    unique_non_empty,
)


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


class FileEvidenceExcerpt(SchemaModel):
    """파일 1차 분석에서 보존한 짧은 원문 인용."""

    quote: str
    page_number: Annotated[int, Field(ge=1)] | None = None

    @field_validator("quote")
    @classmethod
    def require_quote(cls, value: str) -> str:
        normalized = normalize_newlines(value).strip()
        if not normalized:
            raise ValueError("파일 분석 인용문은 비어 있을 수 없습니다.")
        return normalized


class FileExperienceSignal(SchemaModel):
    """파일에서 발견한 경험 후보. 아직 최종 ExperienceDraft는 아니다."""

    title: str
    summary: str
    details: list[str] = Field(default_factory=list)
    excerpts: list[FileEvidenceExcerpt] = Field(default_factory=list)

    @field_validator("title", "summary")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return normalize_newlines(value).strip()

    @field_validator("details")
    @classmethod
    def normalize_details(cls, values: list[str]) -> list[str]:
        return unique_non_empty(values)


class FileEvidenceFact(SchemaModel):
    """파일에서 확인한 핵심 사실과 이를 뒷받침하는 원문."""

    text: str
    quote: str
    page_number: Annotated[int, Field(ge=1)] | None = None

    @field_validator("text", "quote")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = normalize_newlines(value).strip()
        if not normalized:
            raise ValueError("파일 핵심 사실과 인용문은 비어 있을 수 없습니다.")
        return normalized


class FileEvidenceAnalysis(SchemaModel):
    """원본 파일을 청크별로 읽은 뒤 만든 파일 단위 파생 분석."""

    source_ref_id: Identifier
    filename: str
    summary: str
    experience_signals: list[FileExperienceSignal] = Field(
        default_factory=list,
    )
    key_facts: list[FileEvidenceFact] = Field(default_factory=list)
    chunk_count: Annotated[int, Field(ge=1)] = 1
    model_version: Identifier
    prompt_version: Identifier
    schema_version: Identifier

    @field_validator("filename", "summary")
    @classmethod
    def normalize_analysis_text(cls, value: str) -> str:
        return normalize_newlines(value).strip()


__all__ = [
    "EvidenceCitation",
    "EvidenceSource",
    "EvidenceSourceType",
    "FileEvidenceAnalysis",
    "FileEvidenceExcerpt",
    "FileEvidenceFact",
    "FileExperienceSignal",
]
