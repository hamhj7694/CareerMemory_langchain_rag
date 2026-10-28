"""Text-only privacy boundary for temporary guest sessions.

The sanitizer deliberately keeps surrounding text and whitespace so evidence
quotes from the remaining content can still match the source exactly.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import TypeVar


_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_PHONE = re.compile(r"(?<!\d)(?:\+?82[- .]?)?0?1[016789][-. ]?\d{3,4}[-. ]?\d{4}(?!\d)")
_LANDLINE = re.compile(r"(?<!\d)(?:0(?:2|3[1-3]|4[1-4]|5[1-5]|6[1-4])[- .]?)\d{3,4}[- .]?\d{4}(?!\d)")
_RESIDENT_NUMBER = re.compile(r"(?<!\d)\d{6}[- ]?[1-8]\d{6}(?!\d)")
_CONTACT_LINE = re.compile(
    r"(?im)^([ \t]*(?:\*\*|[-*][ \t]*)?(?:email|e-mail|phone|mobile|tel|"
    r"location|address|name|주소|이름|성명|연락처|전화번호|휴대폰|이메일|github|깃허브)"
    r"(?:\*\*)?[ \t]*[·:：|][ \t]*)([^\r\n]+)$"
)
_ADDRESS = re.compile(
    r"(?:서울(?:특별시)?|부산(?:광역시)?|대구(?:광역시)?|인천(?:광역시)?|"
    r"광주(?:광역시)?|대전(?:광역시)?|울산(?:광역시)?|세종(?:특별자치시)?|"
    r"경기(?:도)?|강원(?:특별자치도)?|충청[남북]도|전라[남북]도|"
    r"경상[남북]도|제주(?:특별자치도)?)\s+"
    r"[가-힣]+(?:시|군|구)(?:\s+[가-힣\d-]+(?:동|읍|면|로|길)(?:\s+\d+(?:-\d+)?)?)?"
)
_NAME_HEADING = re.compile(r"(?m)^([ \t]*#{1,6}[ \t]*)([가-힣]{2,4})([ \t]*[|｜·][ \t]*.+)$")


def redact_guest_text(value: str | None) -> str:
    """Remove common direct identifiers while retaining useful work history."""

    text = value or ""

    def blank(match: re.Match[str]) -> str:
        return " " * len(match.group())

    text = _CONTACT_LINE.sub(
        lambda match: match.group(1) + " " * len(match.group(2)), text
    )
    text = _NAME_HEADING.sub(
        lambda match: match.group(1) + " " * len(match.group(2)) + match.group(3),
        text,
    )
    for pattern in (_EMAIL, _PHONE, _LANDLINE, _RESIDENT_NUMBER, _ADDRESS):
        text = pattern.sub(blank, text)
    return text


def guest_private_mode(user: object) -> bool:
    return getattr(user, "account_type", None) == "guest"


def redact_guest_data(value):
    """Sanitize text inside structured model context without changing keys."""

    if isinstance(value, str):
        return redact_guest_text(value)
    if isinstance(value, dict):
        return {key: redact_guest_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_guest_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_guest_data(item) for item in value)
    return value


T = TypeVar("T")


def redact_source_texts(sources: list[T], *, guest: bool) -> list[T]:
    if not guest:
        return sources
    result = []
    for source in sources:
        fields = {"text": redact_guest_text(source.text)}
        if getattr(source, "attachment_id", None):
            if hasattr(source, "title"):
                fields["title"] = "첨부 파일"
            if hasattr(source, "filename"):
                suffix = Path(getattr(source, "filename") or "").suffix.lower()
                fields["filename"] = f"attachment{suffix}"
        if hasattr(source, "__dataclass_fields__"):
            result.append(replace(source, **fields))
        else:
            result.append(source.model_copy(update=fields))
    return result
