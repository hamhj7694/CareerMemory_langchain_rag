"""Lossless source segmentation and the v2 atomic experience proposal contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import re
from typing import Any
from types import SimpleNamespace
from uuid import uuid4

from AI_Engine.schemas import EvidenceSource


EXPERIENCE_UNITS_CONTRACT_VERSION = "experience-units-v2"
EXPERIENCE_UNITS_ACTION = "experience_units_proposal"
EXPERIENCE_UNITS_SCHEMA_VERSION = "experience-units-v2"
EXPERIENCE_UNITS_SEGMENTER_VERSION = "source-lines-v1"

_LINE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+\S")
_DIVIDER = re.compile(r"^\s*(?:---+|___+|\*\*\*+)\s*(?:\r\n|\r|\n)?$")
_REDACTED_CONTACT = re.compile(
    r"(?i)^\s*(?:\*\*)?(?:email|e-mail|phone|mobile|tel|location|address|name|"
    r"주소|이름|성명|연락처|전화번호|휴대폰|이메일|github|깃허브)(?:\*\*)?"
    r"\s*[·:：|]\s*$"
)
_REDACTED_NAME_HEADING = re.compile(r"^\s*#{1,6}\s{3,}[|｜·]")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:32]}"


def _value(item: object, name: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


@dataclass(frozen=True)
class AnalysisGroup:
    id: str
    source_id: str
    primary_span_ids: tuple[str, ...]
    context_span_ids: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class SegmentedSources:
    snapshots: tuple[dict[str, Any], ...]
    groups: tuple[AnalysisGroup, ...]
    analysis_sources: tuple[EvidenceSource, ...]
    original_sources: tuple[EvidenceSource, ...]


def partition_analysis_sources(
    sources: Sequence[EvidenceSource],
    *,
    maximum_characters: int = 24_000,
    maximum_sources: int = 60,
) -> list[list[EvidenceSource]]:
    """Create deterministic bounded batches without dropping an oversized source."""

    batches: list[list[EvidenceSource]] = []
    current: list[EvidenceSource] = []
    current_size = 0
    for source in sources:
        size = len(source.text or "")
        if current and (
            current_size + size > maximum_characters
            or len(current) >= maximum_sources
        ):
            batches.append(current)
            current = []
            current_size = 0
        current.append(source)
        current_size += size
    if current:
        batches.append(current)
    return batches


def organize_segmented_sources(
    experience_ai: object,
    request: object,
    segmented: SegmentedSources,
    *,
    assistant_contexts: Sequence[object] = (),
) -> object:
    """Analyze every group in bounded calls and retain successful partial batches."""

    batches = partition_analysis_sources(segmented.analysis_sources)
    if not batches:
        return experience_ai.organize(request, sources=[])
    results: list[object] = []
    failed_batch_ids: list[str] = []
    last_error: Exception | None = None
    for index, batch in enumerate(batches):
        batch_id = f"batch-{index + 1}"
        message_ids = list(dict.fromkeys(
            source.message_id for source in batch if source.message_id
        ))
        attachment_ids = list(dict.fromkeys(
            source.attachment_id for source in batch if source.attachment_id
        ))
        has_manual = any(source.manual_input_id for source in batch)
        updates = {
            "client_request_id": f"{getattr(request, 'client_request_id', 'request')}-{batch_id}",
            "message_ids": message_ids,
            "attachment_ids": attachment_ids,
            "source_ref_ids": [],
        }
        if hasattr(request, "text") and not has_manual:
            updates["text"] = None
        batch_request = request.model_copy(update=updates) if hasattr(request, "model_copy") else request
        try:
            kwargs: dict[str, Any] = {"sources": batch}
            if assistant_contexts:
                kwargs["assistant_contexts"] = assistant_contexts
            results.append(experience_ai.organize(batch_request, **kwargs))
        except Exception as error:  # A successful batch must survive another batch's provider failure.
            failed_batch_ids.append(batch_id)
            last_error = error
    if not results:
        assert last_error is not None
        raise last_error
    if len(batches) == 1 and not failed_batch_ids:
        return results[0]

    drafts: list[dict[str, Any]] = []
    registered_sources: list[EvidenceSource] = []
    analyzed_source_ids: list[str] = []
    rejected_count = 0
    for result_index, result in enumerate(results):
        for draft in getattr(result, "experience_drafts", ()) or ():
            payload = _draft_payload(draft)
            payload["draft_id"] = f"B{result_index + 1}-{payload.get('draft_id', len(drafts))}"
            drafts.append(payload)
        registered_sources.extend(list(getattr(result, "sources", ()) or ()))
        analyzed_source_ids.extend(list(getattr(result, "analyzed_source_ids", ()) or ()))
        rejected_count += int(getattr(result, "rejected_draft_count", 0) or 0)
    return SimpleNamespace(
        run=getattr(results[0], "run", {}),
        experience_drafts=drafts,
        sources=registered_sources,
        analyzed_source_ids=list(dict.fromkeys(analyzed_source_ids)),
        rejected_draft_count=rejected_count,
        failed_batch_ids=failed_batch_ids,
    )


def _posting_ranges(text: str, postings: Sequence[str]) -> list[tuple[int, int]]:
    """Locate one concrete occurrence per posting without deleting equal prose."""

    ranges: list[tuple[int, int]] = []
    occupied: list[tuple[int, int]] = []
    for posting in sorted({item for item in postings if item.strip()}, key=len, reverse=True):
        cursor = 0
        while True:
            start = text.find(posting, cursor)
            if start < 0:
                break
            end = start + len(posting)
            cursor = end
            if any(start < used_end and end > used_start for used_start, used_end in occupied):
                continue
            ranges.append((start, end))
            occupied.append((start, end))
            break
    return sorted(ranges)


def _overlaps(start: int, end: int, ranges: Sequence[tuple[int, int]]) -> bool:
    return any(start < range_end and end > range_start for range_start, range_end in ranges)


def _source_origin(source: EvidenceSource) -> dict[str, Any]:
    return {
        "message_id": source.message_id,
        "manual_input_id": source.manual_input_id,
        "attachment_id": source.attachment_id,
    }


def segment_sources(
    sources: Sequence[EvidenceSource],
    *,
    job_postings_by_source_id: Mapping[str, Sequence[str]] | None = None,
    privacy_policy: str = "registered",
) -> SegmentedSources:
    """Split every source exactly and create model inputs around atomic leaf lines."""

    snapshots: list[dict[str, Any]] = []
    groups: list[AnalysisGroup] = []
    analysis_sources: list[EvidenceSource] = []
    postings = job_postings_by_source_id or {}

    for source in sources:
        text = source.text or ""
        ranges = _posting_ranges(text, postings.get(source.id, ()))
        spans: list[dict[str, Any]] = []
        heading_stack: list[tuple[int, str]] = []
        char_cursor = 0
        byte_cursor = 0

        for index, match in enumerate(_LINE.finditer(text)):
            value = match.group(0)
            start = char_cursor
            end = start + len(value)
            byte_start = byte_cursor
            byte_end = byte_start + len(value.encode("utf-8"))
            span_id = _stable_id(
                "SPAN",
                f"{source.id}:{start}:{end}:{_sha256(value)}",
            )
            stripped = value.strip()
            heading = _HEADING.match(value)
            if _overlaps(start, end, ranges):
                category = "job"
            elif privacy_policy == "guest_redacted" and (
                _REDACTED_CONTACT.match(value.strip())
                or _REDACTED_NAME_HEADING.match(value)
            ):
                category = "privacy_excluded"
            elif not stripped or _DIVIDER.match(value):
                category = "other"
            elif heading:
                category = "common_context"
            else:
                category = "unresolved"
            spans.append({
                "id": span_id,
                "index": index,
                "char_start": start,
                "char_end": end,
                "byte_start": byte_start,
                "byte_end": byte_end,
                "text_hash": _sha256(value),
                "category": category,
            })

            if heading and category != "job":
                level = len(heading.group(1))
                heading_stack = [item for item in heading_stack if item[0] < level]
                heading_stack.append((level, span_id))
            elif category == "unresolved":
                context_ids = tuple(item[1] for item in heading_stack)
                context_texts = [
                    text[item["char_start"]:item["char_end"]]
                    for item in spans
                    if item["id"] in context_ids
                ]
                group_id = _stable_id("GROUP", f"{source.id}:{span_id}")
                group_text = "".join([*context_texts, value])
                group = AnalysisGroup(
                    id=group_id,
                    source_id=source.id,
                    primary_span_ids=(span_id,),
                    context_span_ids=context_ids,
                    text=group_text,
                )
                groups.append(group)
                source_kwargs = {
                    "id": group_id,
                    "type": source.type,
                    "title": f"{source.title or '원문'} · 구간 {index + 1}",
                    "message_id": source.message_id,
                    "manual_input_id": source.manual_input_id,
                    "attachment_id": source.attachment_id,
                    "filename": source.filename,
                    "mime_type": source.mime_type,
                    "uploaded_at": source.uploaded_at,
                    "content_hash": source.content_hash,
                    "text": group_text,
                }
                analysis_sources.append(EvidenceSource.model_validate(source_kwargs))

            char_cursor = end
            byte_cursor = byte_end

        if char_cursor != len(text) or byte_cursor != len(text.encode("utf-8")):
            raise ValueError("원문 구간 분할 결과가 입력 길이와 일치하지 않습니다.")
        snapshots.append({
            "id": _stable_id(
                "SNAPSHOT",
                f"{source.id}:{privacy_policy}:{EXPERIENCE_UNITS_SEGMENTER_VERSION}:{_sha256(text)}",
            ),
            "source_id": source.id,
            "source_type": str(source.type),
            "title": source.title,
            **_source_origin(source),
            "text_hash": _sha256(text),
            "char_length": len(text),
            "byte_length": len(text.encode("utf-8")),
            "privacy_policy": privacy_policy,
            "segmenter_version": EXPERIENCE_UNITS_SEGMENTER_VERSION,
            "spans": spans,
        })

    return SegmentedSources(
        snapshots=tuple(snapshots),
        groups=tuple(groups),
        analysis_sources=tuple(analysis_sources),
        original_sources=tuple(sources),
    )


def source_manifest(segmented: SegmentedSources) -> list[dict[str, Any]]:
    """Return the durable metadata snapshot without copying source text."""

    return [dict(snapshot) for snapshot in segmented.snapshots]


def _draft_payload(draft: object) -> dict[str, Any]:
    if hasattr(draft, "model_dump"):
        return draft.model_dump(mode="json")
    if isinstance(draft, Mapping):
        return dict(draft)
    raise TypeError("경험 초안을 JSON 객체로 변환할 수 없습니다.")


def _citation_span_id(
    quote: str,
    *,
    group: AnalysisGroup,
    spans_by_id: Mapping[str, Mapping[str, Any]],
    source_text_by_id: Mapping[str, str],
) -> str | None:
    original = source_text_by_id.get(group.source_id, "")
    for span_id in (*group.primary_span_ids, *group.context_span_ids):
        span = spans_by_id.get(span_id)
        if span is None:
            continue
        span_text = original[span["char_start"]:span["char_end"]]
        if quote and quote in span_text:
            return span_id
    return group.primary_span_ids[0] if group.primary_span_ids else None


def build_experience_units_proposal(
    extraction_result: object,
    segmented: SegmentedSources,
    *,
    analysis_run_id: str,
    proposal_id: str | None = None,
) -> dict[str, Any]:
    """Convert validated old drafts into the new stable-ID proposal contract."""

    groups_by_id = {group.id: group for group in segmented.groups}
    snapshots_by_source = {
        snapshot["source_id"]: snapshot for snapshot in segmented.snapshots
    }
    spans_by_id = {
        span["id"]: span
        for snapshot in segmented.snapshots
        for span in snapshot["spans"]
    }
    source_text_by_id = {
        source.id: source.text or "" for source in segmented.original_sources
    }
    source_meta_by_id = {
        source.id: {
            "id": source.id,
            "source_type": str(source.type),
            "title": source.title,
            **_source_origin(source),
            "filename": source.filename,
            "mime_type": source.mime_type,
        }
        for source in segmented.original_sources
    }
    claimed_primary: set[str] = set()
    units: list[dict[str, Any]] = []
    canonical_fact_by_key: dict[str, dict[str, Any]] = {}

    for draft_index, draft in enumerate(
        list(_value(extraction_result, "experience_drafts", ()) or ())
    ):
        payload = _draft_payload(draft)
        group_ids = [
            source_id
            for source_id in payload.get("source_ref_ids", [])
            if source_id in groups_by_id
        ]
        draft_groups = [groups_by_id[group_id] for group_id in group_ids]
        primary_span_ids = list(dict.fromkeys(
            span_id for group in draft_groups for span_id in group.primary_span_ids
        ))
        context_span_ids = list(dict.fromkeys(
            span_id for group in draft_groups for span_id in group.context_span_ids
        ))
        overlapping = [span_id for span_id in primary_span_ids if span_id in claimed_primary]
        primary_span_ids = [span_id for span_id in primary_span_ids if span_id not in claimed_primary]
        context_span_ids = list(dict.fromkeys([*context_span_ids, *overlapping]))
        claimed_primary.update(primary_span_ids)

        original_source_ids = list(dict.fromkeys(
            group.source_id for group in draft_groups
        ))
        converted_citations: dict[str, list[dict[str, Any]]] = {}
        field_span_ids: dict[str, list[str]] = {}
        for field, citations in (payload.get("field_citations") or {}).items():
            converted: list[dict[str, Any]] = []
            linked_spans: list[str] = []
            for citation in citations or []:
                item = dict(citation)
                group = groups_by_id.get(str(item.get("source_ref_id") or ""))
                if group is None:
                    continue
                item["source_ref_id"] = group.source_id
                span_id = _citation_span_id(
                    str(item.get("quote") or ""),
                    group=group,
                    spans_by_id=spans_by_id,
                    source_text_by_id=source_text_by_id,
                )
                if span_id:
                    item["span_id"] = span_id
                    linked_spans.append(span_id)
                converted.append(item)
            if converted:
                converted_citations[field] = converted
            if linked_spans:
                field_span_ids[field] = list(dict.fromkeys(linked_spans))

        source_refs = [
            source_meta_by_id[source_id]
            for source_id in original_source_ids
            if source_id in source_meta_by_id
        ]
        preview = "\n".join(
            group.text.strip() for group in draft_groups if group.text.strip()
        )
        unit_id = _stable_id(
            "UNIT",
            f"{analysis_run_id}:{payload.get('draft_id', draft_index)}",
        )
        payload.update({
            "unit_id": unit_id,
            "analysis_run_id": analysis_run_id,
            "source_ref_ids": original_source_ids,
            "source_refs": source_refs,
            "field_citations": converted_citations,
            "primary_span_ids": primary_span_ids,
            "context_span_ids": context_span_ids,
            "field_span_ids": field_span_ids,
            "evidence_preview": preview[:1200],
            "status": "pending",
            "saved_experience_id": None,
            "saved_at": None,
        })
        fact_ids: list[str] = []
        for fact_index, fact in enumerate(payload.get("facts") or []):
            normalized_fact = " ".join(str(fact).split()).casefold()
            if not normalized_fact:
                continue
            fact_id = _stable_id("FACT", normalized_fact)
            fact_ids.append(fact_id)
            canonical = canonical_fact_by_key.setdefault(normalized_fact, {
                "fact_id": fact_id,
                "text": fact,
                "unit_ids": [],
                "evidence": [],
            })
            if unit_id not in canonical["unit_ids"]:
                canonical["unit_ids"].append(unit_id)
            for citation in converted_citations.get(f"facts.{fact_index}", []):
                evidence_key = (
                    citation.get("source_ref_id"), citation.get("span_id"), citation.get("quote")
                )
                if evidence_key not in {
                    (item.get("source_ref_id"), item.get("span_id"), item.get("quote"))
                    for item in canonical["evidence"]
                }:
                    canonical["evidence"].append(citation)
        payload["fact_ids"] = fact_ids
        units.append(payload)

    span_status: dict[str, str] = {}
    for snapshot in segmented.snapshots:
        for span in snapshot["spans"]:
            category = span["category"]
            if span["id"] in claimed_primary:
                category = "experience"
            elif category == "unresolved":
                category = "unresolved"
            span_status[span["id"]] = category

    unresolved = [span_id for span_id, value in span_status.items() if value == "unresolved"]
    failed_batch_ids = list(_value(extraction_result, "failed_batch_ids", ()) or ())
    coverage = {
        "integrity_status": "verified",
        "processing_status": "partial" if unresolved or failed_batch_ids else "complete",
        "review_status": "pending",
        "total_span_count": len(span_status),
        "experience_span_count": sum(value == "experience" for value in span_status.values()),
        "job_span_count": sum(value == "job" for value in span_status.values()),
        "context_span_count": sum(value == "common_context" for value in span_status.values()),
        "other_span_count": sum(value == "other" for value in span_status.values()),
        "unresolved_span_ids": unresolved,
        "failed_batch_ids": failed_batch_ids,
        "span_status": span_status,
    }
    status = "partial" if unresolved else "pending"
    return {
        "id": proposal_id or f"UNITS-PROPOSAL-{uuid4()}",
        "contract_version": EXPERIENCE_UNITS_CONTRACT_VERSION,
        "version": 1,
        "type": "create_experience_units",
        "status": status,
        "title": "경험 단위 분석 결과",
        "analysis_run_id": analysis_run_id,
        "source_snapshot_ids": [snapshot["id"] for snapshot in segmented.snapshots],
        "source_snapshots": source_manifest(segmented),
        "units": units,
        "canonical_facts": list(canonical_fact_by_key.values()),
        "coverage": coverage,
    }


def proposal_action(proposal: Mapping[str, Any]) -> dict[str, Any]:
    return {"type": EXPERIENCE_UNITS_ACTION, "proposal": dict(proposal)}


def recalculate_proposal_coverage(proposal: Mapping[str, Any]) -> dict[str, Any]:
    """Derive coverage from immutable spans and current unit ownership."""

    claimed = {
        span_id
        for unit in proposal.get("units", [])
        if isinstance(unit, Mapping)
        for span_id in unit.get("primary_span_ids", [])
    }
    span_status: dict[str, str] = {}
    for snapshot in proposal.get("source_snapshots", []):
        if not isinstance(snapshot, Mapping):
            continue
        for span in snapshot.get("spans", []):
            if not isinstance(span, Mapping) or not span.get("id"):
                continue
            category = str(span.get("category") or "unresolved")
            if span["id"] in claimed:
                category = "experience"
            elif category not in {"job", "common_context", "other", "privacy_excluded"}:
                category = "unresolved"
            span_status[str(span["id"])] = category
    unresolved = [span_id for span_id, value in span_status.items() if value == "unresolved"]
    previous = proposal.get("coverage") or {}
    failed = list(previous.get("failed_batch_ids") or [])
    return {
        "integrity_status": "verified",
        "processing_status": "partial" if unresolved or failed else "complete",
        "review_status": previous.get("review_status") or "pending",
        "total_span_count": len(span_status),
        "experience_span_count": sum(value == "experience" for value in span_status.values()),
        "job_span_count": sum(value == "job" for value in span_status.values()),
        "context_span_count": sum(value == "common_context" for value in span_status.values()),
        "other_span_count": sum(value in {"other", "privacy_excluded"} for value in span_status.values()),
        "unresolved_span_ids": unresolved,
        "failed_batch_ids": failed,
        "span_status": span_status,
    }


def validate_proposal_invariants(proposal: Mapping[str, Any]) -> None:
    """Reject edited proposals that lose stable IDs or duplicate primary ownership."""

    if proposal.get("contract_version") != EXPERIENCE_UNITS_CONTRACT_VERSION:
        raise ValueError("지원하지 않는 경험 단위 계약입니다.")
    units = proposal.get("units")
    if not isinstance(units, list):
        raise ValueError("units는 배열이어야 합니다.")
    unit_ids: set[str] = set()
    primary_owners: dict[str, str] = {}
    known_span_ids = {
        span.get("id")
        for snapshot in proposal.get("source_snapshots", [])
        if isinstance(snapshot, Mapping)
        for span in snapshot.get("spans", [])
        if isinstance(span, Mapping)
    }
    for unit in units:
        if not isinstance(unit, Mapping) or not str(unit.get("unit_id") or "").strip():
            raise ValueError("모든 경험 단위에는 unit_id가 필요합니다.")
        unit_id = str(unit["unit_id"])
        if unit_id in unit_ids:
            raise ValueError("unit_id가 중복되었습니다.")
        unit_ids.add(unit_id)
        for span_id in unit.get("primary_span_ids", []):
            if span_id not in known_span_ids:
                raise ValueError("경험 단위가 알 수 없는 원문 구간을 참조합니다.")
            owner = primary_owners.setdefault(span_id, unit_id)
            if owner != unit_id:
                raise ValueError("하나의 원문 구간을 여러 경험이 주 내용으로 소유할 수 없습니다.")


__all__ = [
    "EXPERIENCE_UNITS_ACTION",
    "EXPERIENCE_UNITS_CONTRACT_VERSION",
    "EXPERIENCE_UNITS_SCHEMA_VERSION",
    "EXPERIENCE_UNITS_SEGMENTER_VERSION",
    "SegmentedSources",
    "build_experience_units_proposal",
    "organize_segmented_sources",
    "partition_analysis_sources",
    "proposal_action",
    "recalculate_proposal_coverage",
    "segment_sources",
    "source_manifest",
    "validate_proposal_invariants",
]
