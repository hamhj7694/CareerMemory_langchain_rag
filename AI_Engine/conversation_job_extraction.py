"""Conversation text helpers for finding one or more job postings.

The extraction in this module is deliberately deterministic.  It decides which
conversation sources look like job postings and leaves the actual requirement
analysis to the existing job-analysis AI pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re


@dataclass(frozen=True)
class JobSourceText:
    """A searchable piece of a conversation or one of its attachments."""

    message_id: str
    text: str
    attachment_id: str | None = None
    title: str = ""


@dataclass(frozen=True)
class ConversationJobCandidate:
    """A single posting ready for the existing job-analysis endpoint."""

    message_id: str
    posting_content: str
    attachment_id: str | None = None
    company_name: str = ""
    role_name: str = ""
    posting_title: str = ""
    source_url: str | None = None


_NUMBERED_POSTING_BOUNDARY = re.compile(
    r"(?im)^(?=\s*(?:#{1,6}\s*)?(?:\[\s*)?"
    r"(?:채용\s*공고|공고)\s*#?\s*\d+\s*(?:\])?\s*(?:[:：.\-].*)?$)"
)
_COMPANY_BOUNDARY = re.compile(r"(?im)^\s*회사(?:명)?\s*[:：]")
_URL_PATTERN = re.compile(r"https?://[^\s)>\]}]+", re.IGNORECASE)

_SIGNAL_PATTERNS = (
    re.compile(r"주요\s*업무|담당\s*업무|업무\s*내용|responsibilit(?:y|ies)", re.IGNORECASE),
    re.compile(
        r"자격\s*요건|지원\s*자격|필수\s*요건|qualifications?|requirements?",
        re.IGNORECASE,
    ),
    re.compile(r"우대\s*사항|우대\s*조건|preferred|nice\s+to\s+have", re.IGNORECASE),
    re.compile(
        r"채용\s*공고|모집\s*(?:분야|직무)|포지션|근무\s*(?:지|형태)|job\s+description",
        re.IGNORECASE,
    ),
)
_JOB_FILENAME_PATTERN = re.compile(r"채용|공고|포지션|job|jd", re.IGNORECASE)


def normalize_job_content(value: str) -> str:
    """Normalize insignificant whitespace/case for reliable duplicate checks."""

    return " ".join((value or "").split()).casefold()


def job_content_fingerprint(value: str) -> str:
    return hashlib.sha256(normalize_job_content(value).encode("utf-8")).hexdigest()


def job_contents_match(left: str, right: str) -> bool:
    """Treat a posting and the same posting with a short wrapper as identical."""

    normalized_left = normalize_job_content(left)
    normalized_right = normalize_job_content(right)
    if not normalized_left or not normalized_right:
        return False
    if normalized_left == normalized_right:
        return True
    shorter, longer = sorted(
        (normalized_left, normalized_right),
        key=len,
    )
    return (
        len(shorter) >= 60
        and shorter in longer
        and len(shorter) / len(longer) >= 0.75
    )


def _split_postings(text: str) -> list[str]:
    """Split only on strong repeated boundaries to avoid breaking one posting."""

    numbered = list(_NUMBERED_POSTING_BOUNDARY.finditer(text))
    boundaries = numbered
    if len(boundaries) < 2:
        companies = list(_COMPANY_BOUNDARY.finditer(text))
        if len(companies) >= 2:
            boundaries = companies

    if len(boundaries) < 2:
        return [text.strip()]

    # Keep any short introduction before the first marker with the first posting.
    starts = [0, *(match.start() for match in boundaries[1:])]
    ends = [*starts[1:], len(text)]
    return [text[start:end].strip() for start, end in zip(starts, ends) if text[start:end].strip()]


def _looks_like_job_posting(text: str, title: str) -> bool:
    compact = " ".join(text.split())
    if len(compact) < 60:
        return False

    signals = [bool(pattern.search(text)) for pattern in _SIGNAL_PATTERNS]
    signal_count = sum(signals)
    has_core_sections = signals[0] and signals[1]
    filename_hint = bool(_JOB_FILENAME_PATTERN.search(title))
    return has_core_sections or signal_count >= 3 or (filename_hint and signal_count >= 1)


def _field(text: str, labels: str, *, max_length: int = 200) -> str:
    match = re.search(
        rf"(?im)^\s*(?:{labels})\s*[:：]\s*(.+?)\s*$",
        text,
    )
    return match.group(1).strip()[:max_length] if match else ""


def _posting_title(text: str, source_title: str) -> str:
    explicit = _field(
        text,
        r"공고\s*(?:명|제목)|채용\s*제목",
        max_length=300,
    )
    if explicit:
        return explicit

    for line in text.splitlines():
        heading = re.sub(r"^\s*#{1,6}\s*", "", line).strip(" []")
        if heading and len(heading) <= 120 and re.search(r"채용|모집|개발자|엔지니어|디자이너|매니저", heading):
            return heading
    return source_title[:300] if _JOB_FILENAME_PATTERN.search(source_title) else ""


def extract_job_posting_candidates(
    sources: list[JobSourceText],
) -> list[ConversationJobCandidate]:
    """Find job-looking sections while preserving their conversation source."""

    candidates: list[ConversationJobCandidate] = []
    for source in sources:
        raw_text = (source.text or "").strip()
        if not raw_text:
            continue
        for section in _split_postings(raw_text):
            if not _looks_like_job_posting(section, source.title):
                continue
            url_match = _URL_PATTERN.search(section)
            candidates.append(ConversationJobCandidate(
                message_id=source.message_id,
                attachment_id=source.attachment_id,
                posting_content=section,
                company_name=_field(section, r"회사(?:명)?|기업(?:명)?"),
                role_name=_field(section, r"직무(?:명)?|포지션|모집\s*분야"),
                posting_title=_posting_title(section, source.title),
                source_url=url_match.group(0) if url_match else None,
            ))
    return candidates


__all__ = [
    "ConversationJobCandidate",
    "JobSourceText",
    "extract_job_posting_candidates",
    "job_content_fingerprint",
    "job_contents_match",
    "normalize_job_content",
]
