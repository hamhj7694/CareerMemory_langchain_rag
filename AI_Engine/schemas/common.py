"""Common schema primitives shared by every Career Memory AI pipeline."""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)


Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
SequenceNumber = Annotated[int, Field(ge=0)]


class SchemaModel(BaseModel):
    """Strict base model for AI input/output contracts."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        validate_default=True,
        str_strip_whitespace=False,
        use_enum_values=True,
        populate_by_name=True,
    )


class AIError(SchemaModel):
    """Common structured error returned by AI-facing APIs."""

    code: Identifier
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("message")
    @classmethod
    def require_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("오류 메시지는 비어 있을 수 없습니다.")
        return normalized


def normalize_newlines(value: str) -> str:
    """Store Windows and Unix newlines in one normalized form."""

    return value.replace("\r\n", "\n").replace("\r", "\n")


def unique_non_empty(values: list[str]) -> list[str]:
    """Remove empty and duplicate strings while preserving input order."""

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def normalize_http_url(value: str | None) -> str | None:
    """Allow only complete HTTP(S) URLs, while treating blanks as None."""

    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    parsed = urlsplit(normalized)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source_url은 완전한 http:// 또는 https:// URL이어야 합니다.")
    return normalized


def period_sort_key(value: str, *, is_end: bool) -> tuple[int, int]:
    """Return a comparable year/month tuple for YYYY or YYYY-MM strings."""

    year_text, *month_text = value.split("-", maxsplit=1)
    default_month = 12 if is_end else 1
    month = int(month_text[0]) if month_text else default_month
    return int(year_text), month


__all__ = [
    "AIError",
    "Confidence",
    "Identifier",
    "SchemaModel",
    "SequenceNumber",
    "normalize_http_url",
    "normalize_newlines",
    "period_sort_key",
    "unique_non_empty",
]
