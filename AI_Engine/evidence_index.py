"""EvidenceChunk의 content hash 기반 증분 Chroma 인덱싱."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document
from sqlalchemy import select
from sqlalchemy.orm import Session

from AI_Engine.database.models import (
    EmbeddingRecord,
    EvidenceChunk,
    EvidenceDocument,
    utc_now,
)
from AI_Engine.evidence_repository import current_evidence_chunks
from AI_Engine.llm_provider import (
    create_embeddings,
    get_ai_provider,
    get_embedding_model_name,
)


EVIDENCE_INDEX_VERSION = "evidence-index-v2"


@dataclass(frozen=True)
class EvidenceIndexReport:
    desired: int
    added: int
    updated: int
    deleted: int
    skipped_unchanged: int
    rebuilt: bool = False


def evidence_collection_name(user_id: str, index_version: str) -> str:
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]
    version = hashlib.sha256(index_version.encode("utf-8")).hexdigest()[:8]
    return f"career_memory_evidence_{digest}_{version}"


def build_persisted_evidence_documents(
    database: Session,
    user_id: str,
) -> list[Document]:
    chunks = current_evidence_chunks(database, user_id)
    document_ids = {chunk.document_id for chunk in chunks}
    evidence_documents = {
        item.id: item
        for item in database.scalars(select(EvidenceDocument).where(
            EvidenceDocument.id.in_(document_ids)
        ))
    } if document_ids else {}
    documents: list[Document] = []
    for chunk in chunks:
        source = evidence_documents.get(chunk.document_id)
        if source is None:
            continue
        documents.append(Document(
            id=chunk.id,
            page_content=chunk.text,
            metadata={
                "source_id": source.legacy_source_ref_id or source.source_record_id,
                "source_type": source.source_type,
                "title": source.title,
                "source_record_id": source.source_record_id,
                "filename": source.title if source.source_type == "file" else "",
                "message_id": (
                    source.source_record_id
                    if source.source_type in {"message_text", "conversation_message"}
                    else ""
                ),
                "attachment_id": (
                    source.source_record_id if source.source_type == "file" else ""
                ),
                "document_id": source.id,
                "chunk_index": chunk.chunk_index,
                "start_offset": chunk.start_offset,
                "end_offset": chunk.end_offset,
                "content_hash": chunk.content_hash,
                "chunker_version": chunk.chunker_version,
                "index_version": EVIDENCE_INDEX_VERSION,
            },
        ))
    return documents


def _vector_store(
    *,
    user_id: str,
    persist_directory: Path,
    index_version: str,
    embeddings: Any | None,
) -> Chroma:
    persist_directory.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=evidence_collection_name(user_id, index_version),
        embedding_function=embeddings or create_embeddings(),
        persist_directory=str(persist_directory),
    )


def _stored_hashes(vector_db: Any) -> dict[str, str | None]:
    stored = vector_db.get(include=["metadatas"])
    ids = [str(value) for value in stored.get("ids", [])]
    return {
        vector_id: (
            metadata.get("content_hash")
            if isinstance(metadata, Mapping)
            else None
        )
        for vector_id, metadata in zip(
            ids,
            stored.get("metadatas", []),
            strict=False,
        )
    }


def _mark_old_records_stale(
    database: Session,
    *,
    user_id: str,
    desired: Mapping[str, Document],
    provider: str,
    model: str,
    index_version: str,
) -> None:
    records = database.scalars(select(EmbeddingRecord).where(
        EmbeddingRecord.user_id == user_id,
        EmbeddingRecord.target_type == "evidence_chunk",
        EmbeddingRecord.status == "current",
    ))
    for record in records:
        document = desired.get(record.target_id)
        expected_hash = (
            document.metadata.get("content_hash")
            if document is not None
            else None
        )
        if (
            document is None
            or record.provider != provider
            or record.model != model
            or record.index_version != index_version
            or record.content_hash != expected_hash
        ):
            record.status = "stale"
            record.stale_at = utc_now()


def _record_indexed(
    database: Session,
    *,
    user_id: str,
    document: Document,
    provider: str,
    model: str,
    index_version: str,
    collection_name: str,
) -> None:
    target_id = str(document.id)
    content_hash = str(document.metadata["content_hash"])
    record_key = (
        f"{user_id}:{target_id}:{provider}:{model}:{index_version}:{content_hash}"
    )
    record_id = f"EMB-{hashlib.sha256(record_key.encode('utf-8')).hexdigest()[:32]}"
    record = database.get(EmbeddingRecord, record_id)
    if record is None:
        database.add(EmbeddingRecord(
            id=record_id,
            user_id=user_id,
            target_type="evidence_chunk",
            target_id=target_id,
            provider=provider,
            model=model,
            dimensions=None,
            content_hash=content_hash,
            index_version=index_version,
            collection_name=collection_name,
            vector_id=target_id,
            status="current",
        ))
    else:
        record.status = "current"
        record.stale_at = None
        record.indexed_at = utc_now()


def sync_evidence_index(
    database: Session,
    user_id: str,
    *,
    persist_directory: Path,
    embeddings: Any | None = None,
    vector_db: Any | None = None,
    index_version: str = EVIDENCE_INDEX_VERSION,
    rebuild: bool = False,
) -> tuple[Any, EvidenceIndexReport]:
    documents = build_persisted_evidence_documents(database, user_id)
    desired = {str(item.id): item for item in documents if item.id is not None}
    provider = get_ai_provider()
    model = get_embedding_model_name(provider)
    collection_name = evidence_collection_name(user_id, index_version)
    store = vector_db or _vector_store(
        user_id=user_id,
        persist_directory=persist_directory,
        index_version=index_version,
        embeddings=embeddings,
    )
    stored_hashes = _stored_hashes(store)
    stored_ids = set(stored_hashes)
    desired_ids = set(desired)
    stale = sorted(stored_ids - desired_ids)
    changed = sorted(
        item for item in stored_ids & desired_ids
        if stored_hashes[item] != desired[item].metadata.get("content_hash")
    )
    new = sorted(desired_ids - stored_ids)
    if rebuild:
        stale = sorted(stored_ids)
        changed = []
        new = sorted(desired_ids)

    if stale:
        store.delete(ids=stale)
    if changed:
        store.update_documents(
            ids=changed,
            documents=[desired[item] for item in changed],
        )
    if new:
        store.add_documents(
            ids=new,
            documents=[desired[item] for item in new],
        )

    _mark_old_records_stale(
        database,
        user_id=user_id,
        desired=desired,
        provider=provider,
        model=model,
        index_version=index_version,
    )
    for item in sorted(set(changed) | set(new)):
        _record_indexed(
            database,
            user_id=user_id,
            document=desired[item],
            provider=provider,
            model=model,
            index_version=index_version,
            collection_name=collection_name,
        )
    database.flush()
    return store, EvidenceIndexReport(
        desired=len(desired),
        added=len(new),
        updated=len(changed),
        deleted=len(stale),
        skipped_unchanged=len(desired_ids - set(new) - set(changed)),
        rebuilt=rebuild,
    )


__all__ = [
    "EVIDENCE_INDEX_VERSION",
    "EvidenceIndexReport",
    "build_persisted_evidence_documents",
    "evidence_collection_name",
    "sync_evidence_index",
]
