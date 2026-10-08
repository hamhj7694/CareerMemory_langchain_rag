"""기존 source_refs를 무손실 Evidence 문서·청크로 영속화한다."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from AI_Engine.chat_context import split_text_chunks
from AI_Engine.database.models import (
    Attachment,
    EmbeddingRecord,
    EvidenceChunk,
    EvidenceDocument,
    EvidenceExperienceLink,
    Experience,
    utc_now,
)


EVIDENCE_VERSION = "evidence-v1"
CHUNKER_VERSION = "evidence-chunker-v1"


@dataclass(frozen=True)
class EvidenceSyncReport:
    documents_created: int = 0
    documents_reused: int = 0
    documents_staled: int = 0
    chunks_created: int = 0
    chunks_reused: int = 0
    chunks_staled: int = 0
    links_created: int = 0
    links_removed: int = 0
    skipped_sources: int = 0
    would_write: bool = False


@dataclass(frozen=True)
class EvidenceLineage:
    source_ref_id: str
    document_id: str
    chunk_id: str
    source_type: str
    source_record_id: str
    start_offset: int
    end_offset: int
    quote_start_offset: int
    quote_end_offset: int


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}-{_hash(value)[:32]}"


def _source_id(source: Mapping[str, Any]) -> str:
    return str(source.get("id") or source.get("source_ref_id") or "").strip()


def _source_type(source: Mapping[str, Any]) -> str:
    raw = str(source.get("source_type") or source.get("type") or "evidence").strip()
    return raw or "evidence"


def _source_record_id(source: Mapping[str, Any], source_ref_id: str) -> str:
    return str(
        source.get("attachment_id")
        or source.get("message_id")
        or source.get("manual_input_id")
        or source.get("source_record_id")
        or source_ref_id
    ).strip()


def _source_text(
    database: Session,
    source: Mapping[str, Any],
) -> tuple[str, str | None, str, str]:
    text = str(source.get("text") or source.get("original_text") or "")
    attachment_id = str(source.get("attachment_id") or "").strip()
    storage_key = None
    parser_version = str(source.get("parser_version") or "source-ref-v1")
    parse_status = str(source.get("parse_status") or "ready")
    if attachment_id:
        attachment = database.get(Attachment, attachment_id)
        if attachment is not None:
            text = text or str(attachment.extracted_text or "")
            storage_key = attachment.storage_key
            parser_version = attachment.parser_version or parser_version
            parse_status = attachment.parse_status or parse_status
    return text.replace("\r\n", "\n").replace("\r", "\n"), storage_key, parser_version, parse_status


def _document_values(
    database: Session,
    user_id: str,
    source: Mapping[str, Any],
) -> dict[str, Any] | None:
    source_ref_id = _source_id(source)
    if not source_ref_id:
        return None
    text, storage_key, parser_version, parse_status = _source_text(database, source)
    if not text.strip():
        return None
    source_type = _source_type(source)
    source_record_id = _source_record_id(source, source_ref_id)
    content_hash = _hash(text)
    return {
        "id": _stable_id(
            "EVD",
            f"{user_id}:{source_type}:{source_record_id}:{content_hash}",
        ),
        "user_id": user_id,
        "source_type": source_type,
        "source_record_id": source_record_id,
        "legacy_source_ref_id": source_ref_id,
        "title": str(
            source.get("filename")
            or source.get("title")
            or "원본 근거"
        ).strip(),
        "original_text": text,
        "storage_key": storage_key,
        "content_hash": content_hash,
        "parser_version": parser_version,
        "parse_status": parse_status,
        "evidence_version": EVIDENCE_VERSION,
        "is_stale": False,
    }


def _stale_document(
    database: Session,
    document: EvidenceDocument,
    *,
    dry_run: bool,
) -> tuple[int, int]:
    chunks = list(database.scalars(select(EvidenceChunk).where(
        EvidenceChunk.document_id == document.id,
        EvidenceChunk.is_stale.is_(False),
    )))
    if not dry_run:
        document.is_stale = True
        for chunk in chunks:
            chunk.is_stale = True
            _stale_embedding_records(database, chunk.id)
    return 1, len(chunks)


def _stale_embedding_records(database: Session, chunk_id: str) -> None:
    records = database.scalars(select(EmbeddingRecord).where(
        EmbeddingRecord.target_type == "evidence_chunk",
        EmbeddingRecord.target_id == chunk_id,
        EmbeddingRecord.status == "current",
    ))
    for record in records:
        record.status = "stale"
        record.stale_at = utc_now()


def sync_source_refs(
    database: Session,
    user_id: str,
    source_refs: Sequence[Mapping[str, Any]],
    *,
    dry_run: bool = False,
    experience_id: str | None = None,
) -> EvidenceSyncReport:
    counts = {
        "documents_created": 0,
        "documents_reused": 0,
        "documents_staled": 0,
        "chunks_created": 0,
        "chunks_reused": 0,
        "chunks_staled": 0,
        "links_created": 0,
        "links_removed": 0,
        "skipped_sources": 0,
    }
    seen_documents: set[str] = set()
    listed_source_ids: set[str] = set()
    desired_document_by_source_id: dict[str, str] = {}
    for source in source_refs:
        if not isinstance(source, Mapping):
            counts["skipped_sources"] += 1
            continue
        values = _document_values(database, user_id, source)
        raw_source_id = _source_id(source)
        if raw_source_id:
            listed_source_ids.add(raw_source_id)
        if values is None or values["id"] in seen_documents:
            counts["skipped_sources"] += 1
            continue
        seen_documents.add(values["id"])
        desired_document_by_source_id[values["legacy_source_ref_id"]] = values["id"]

        prior_documents = list(database.scalars(select(EvidenceDocument).where(
            EvidenceDocument.user_id == user_id,
            EvidenceDocument.legacy_source_ref_id == values["legacy_source_ref_id"],
            EvidenceDocument.is_stale.is_(False),
            EvidenceDocument.id != values["id"],
        )))
        for prior in prior_documents:
            documents, chunks = _stale_document(database, prior, dry_run=dry_run)
            counts["documents_staled"] += documents
            counts["chunks_staled"] += chunks

        document = database.get(EvidenceDocument, values["id"])
        if document is None:
            counts["documents_created"] += 1
            if not dry_run:
                document = EvidenceDocument(**values)
                database.add(document)
                database.flush()
        else:
            counts["documents_reused"] += 1
            if not dry_run and document.is_stale:
                document.is_stale = False

        for chunk_index, (text, start, end) in enumerate(
            split_text_chunks(values["original_text"])
        ):
            content_hash = _hash(text)
            chunk_id = _stable_id(
                "ECH",
                f"{values['id']}:{chunk_index}:{content_hash}:{CHUNKER_VERSION}",
            )
            existing = database.get(EvidenceChunk, chunk_id)
            if existing is None:
                counts["chunks_created"] += 1
                if not dry_run:
                    database.add(EvidenceChunk(
                        id=chunk_id,
                        document_id=values["id"],
                        chunk_index=chunk_index,
                        text=text,
                        start_offset=start,
                        end_offset=end,
                        content_hash=content_hash,
                        chunker_version=CHUNKER_VERSION,
                        is_stale=False,
                    ))
            else:
                counts["chunks_reused"] += 1
                if not dry_run and existing.is_stale:
                    existing.is_stale = False

        active_chunk_ids = {
            _stable_id(
                "ECH",
                f"{values['id']}:{index}:{_hash(text)}:{CHUNKER_VERSION}",
            )
            for index, (text, _start, _end) in enumerate(
                split_text_chunks(values["original_text"])
            )
        }
        stale_chunks = list(database.scalars(select(EvidenceChunk).where(
            EvidenceChunk.document_id == values["id"],
            EvidenceChunk.is_stale.is_(False),
            EvidenceChunk.id.not_in(active_chunk_ids),
        ))) if active_chunk_ids else []
        counts["chunks_staled"] += len(stale_chunks)
        if not dry_run:
            for chunk in stale_chunks:
                chunk.is_stale = True
                _stale_embedding_records(database, chunk.id)

    if experience_id:
        existing_links = list(database.scalars(select(EvidenceExperienceLink).where(
            EvidenceExperienceLink.experience_id == experience_id,
            EvidenceExperienceLink.user_id == user_id,
        )))
        existing_by_document = {link.document_id: link for link in existing_links}
        for document_id in seen_documents - set(existing_by_document):
            counts["links_created"] += 1
            if not dry_run:
                database.add(EvidenceExperienceLink(
                    id=_stable_id("EVL", f"{experience_id}:{document_id}"),
                    user_id=user_id,
                    experience_id=experience_id,
                    document_id=document_id,
                ))
        documents_by_id = {
            document.id: document
            for document in database.scalars(select(EvidenceDocument).where(
                EvidenceDocument.id.in_(set(existing_by_document))
            ))
        } if existing_by_document else {}
        for document_id, link in existing_by_document.items():
            document = documents_by_id.get(document_id)
            source_still_listed = bool(
                document
                and document.legacy_source_ref_id in listed_source_ids
            )
            desired_document_id = (
                desired_document_by_source_id.get(document.legacy_source_ref_id)
                if document is not None and document.legacy_source_ref_id
                else None
            )
            if document_id in seen_documents or (
                source_still_listed and desired_document_id is None
            ):
                continue
            counts["links_removed"] += 1
            other_link = database.scalar(select(EvidenceExperienceLink.id).where(
                EvidenceExperienceLink.document_id == document_id,
                EvidenceExperienceLink.experience_id != experience_id,
            ).limit(1))
            if document is not None and not document.is_stale and other_link is None:
                documents, chunks = _stale_document(
                    database,
                    document,
                    dry_run=dry_run,
                )
                counts["documents_staled"] += documents
                counts["chunks_staled"] += chunks
            if not dry_run:
                database.delete(link)

    if not dry_run:
        database.flush()
    writes = sum(
        counts[key]
        for key in (
            "documents_created",
            "documents_staled",
            "chunks_created",
            "chunks_staled",
            "links_created",
            "links_removed",
        )
    )
    return EvidenceSyncReport(**counts, would_write=writes > 0)


def sync_experience_evidence(
    database: Session,
    experience: Experience,
    *,
    dry_run: bool = False,
) -> EvidenceSyncReport:
    return sync_source_refs(
        database,
        experience.user_id,
        [item for item in (experience.source_refs or []) if isinstance(item, Mapping)],
        dry_run=dry_run,
        experience_id=experience.id,
    )


def find_citation_lineage(
    database: Session,
    user_id: str,
    source_ref_id: str,
    quote: str,
) -> EvidenceLineage | None:
    if not quote:
        return None
    documents = database.scalars(select(EvidenceDocument).where(
        EvidenceDocument.user_id == user_id,
        EvidenceDocument.legacy_source_ref_id == source_ref_id,
        EvidenceDocument.is_stale.is_(False),
    ).order_by(EvidenceDocument.updated_at.desc()))
    for document in documents:
        for chunk in database.scalars(select(EvidenceChunk).where(
            EvidenceChunk.document_id == document.id,
            EvidenceChunk.is_stale.is_(False),
        ).order_by(EvidenceChunk.chunk_index)):
            local_start = chunk.text.find(quote)
            if local_start < 0:
                continue
            return EvidenceLineage(
                source_ref_id=source_ref_id,
                document_id=document.id,
                chunk_id=chunk.id,
                source_type=document.source_type,
                source_record_id=document.source_record_id,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                quote_start_offset=chunk.start_offset + local_start,
                quote_end_offset=chunk.start_offset + local_start + len(quote),
            )
    return None


def current_evidence_chunks(database: Session, user_id: str) -> list[EvidenceChunk]:
    return list(database.scalars(
        select(EvidenceChunk)
        .join(EvidenceDocument, EvidenceDocument.id == EvidenceChunk.document_id)
        .join(
            EvidenceExperienceLink,
            EvidenceExperienceLink.document_id == EvidenceDocument.id,
        )
        .join(Experience, Experience.id == EvidenceExperienceLink.experience_id)
        .where(
            EvidenceDocument.user_id == user_id,
            EvidenceDocument.is_stale.is_(False),
            EvidenceChunk.is_stale.is_(False),
            Experience.user_id == user_id,
            Experience.status == "confirmed",
            Experience.deleted_at.is_(None),
        )
        .distinct()
        .order_by(EvidenceDocument.id, EvidenceChunk.chunk_index)
    ))


__all__ = [
    "CHUNKER_VERSION",
    "EVIDENCE_VERSION",
    "EvidenceLineage",
    "EvidenceSyncReport",
    "current_evidence_chunks",
    "find_citation_lineage",
    "sync_experience_evidence",
    "sync_source_refs",
]
