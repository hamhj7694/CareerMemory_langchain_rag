"""저장 경험과 원본 근거를 사용자별로 검색하는 챗봇 RAG 계층."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from AI_Engine.chat_context import split_text_chunks
from AI_Engine.database.connection import PROJECT_ROOT
from AI_Engine.database.models import Experience, ExperienceProject
from AI_Engine.job_analysis_ai import create_experience_retriever
from AI_Engine.llm_provider import create_embeddings
from AI_Engine.schemas import ChatContextDocument


EXPERIENCE_VECTOR_ROOT = PROJECT_ROOT / "data" / "vector_store" / "jobs"
EVIDENCE_VECTOR_ROOT = PROJECT_ROOT / "data" / "vector_store" / "evidence"
EVIDENCE_INDEX_VERSION = "evidence-index-v1"


def _collection_name(prefix: str, user_id: str) -> str:
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _experience_mapping(item: Experience) -> dict[str, Any]:
    return {
        "id": item.id,
        "status": item.status,
        "domain_name": item.project.domain.name,
        "project_name": item.project.name,
        "title": item.title,
        "summary": item.summary,
        "situation": item.situation,
        "actions": item.actions,
        "results": item.results,
        "role": item.role,
        "skills": item.skills,
        "facts": item.facts,
        "source_ids": item.source_ids,
        "updated_at": item.updated_at,
    }


def load_searchable_experiences(
    database: Session,
    user_id: str,
) -> list[Experience]:
    """현재 사용자의 근거 보유 확정 경험만 조회한다."""

    return list(database.scalars(
        select(Experience)
        .options(
            selectinload(Experience.project).selectinload(
                ExperienceProject.domain
            )
        )
        .where(
            Experience.user_id == user_id,
            Experience.status == "confirmed",
            Experience.deleted_at.is_(None),
        )
        .order_by(Experience.updated_at.desc())
    ))


def retrieve_experience_context(
    database: Session,
    user_id: str,
    query: str,
    *,
    search_k: int | None = None,
) -> list[ChatContextDocument]:
    """확정 경험 검색 문서를 벡터 검색하고 챗봇 문맥으로 변환한다."""

    experiences = [
        item for item in load_searchable_experiences(database, user_id)
        if item.source_ids
    ]
    if not query.strip() or not experiences:
        return []
    k = search_k or max(1, int(os.getenv("AI_CHAT_EXPERIENCE_TOP_K", "5")))
    mappings = [_experience_mapping(item) for item in experiences]
    try:
        EXPERIENCE_VECTOR_ROOT.mkdir(parents=True, exist_ok=True)
        retriever = create_experience_retriever(
            mappings,
            persist_directory=str(EXPERIENCE_VECTOR_ROOT),
            collection_name=_collection_name(
                "career_memory_experiences",
                user_id,
            ),
            search_k=k,
        )
        documents = retriever.invoke(query)
    except Exception:
        documents = _lexical_experience_documents(mappings, query, k)
    return [
        ChatContextDocument(
            source_id=str(document.metadata["experience_id"]),
            source_type="experience",
            title=str(document.metadata.get("title", "")),
            content=document.page_content,
            metadata={
                "domain_name": document.metadata.get("domain_name", ""),
                "project_name": document.metadata.get("project_name", ""),
                "evidence_ids": _json_list(
                    document.metadata.get("evidence_ids_json")
                ),
            },
        )
        for document in documents
    ]


def _lexical_experience_documents(
    experiences: Sequence[Mapping[str, Any]],
    query: str,
    limit: int,
) -> list[Document]:
    query_terms = _query_terms(query)
    ranked: list[tuple[int, Document]] = []
    for item in experiences:
        text = "\n".join([
            str(item.get("domain_name", "")),
            str(item.get("project_name", "")),
            str(item.get("title", "")),
            str(item.get("summary", "")),
            str(item.get("situation", "")),
            "\n".join(item.get("actions", [])),
            "\n".join(item.get("results", [])),
            str(item.get("role", "")),
            ", ".join(item.get("skills", [])),
            "\n".join(item.get("facts", [])),
        ]).strip()
        score = sum(text.casefold().count(term) for term in query_terms)
        if score:
            ranked.append((
                score,
                Document(
                    id=str(item["id"]),
                    page_content=text,
                    metadata={
                        "experience_id": str(item["id"]),
                        "title": str(item.get("title", "")),
                        "domain_name": str(item.get("domain_name", "")),
                        "project_name": str(item.get("project_name", "")),
                        "evidence_ids_json": json.dumps(
                            item.get("source_ids", []),
                            ensure_ascii=False,
                        ),
                    },
                ),
            ))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [document for _score, document in ranked[:limit]]


def build_evidence_documents(
    experiences: Sequence[Experience],
) -> list[Document]:
    """확정 경험에 연결된 원본 텍스트를 위치 보존 청크로 만든다."""

    source_records: dict[str, dict[str, Any]] = {}
    for experience in experiences:
        for source in experience.source_refs or []:
            if not isinstance(source, Mapping):
                continue
            source_id = str(
                source.get("id")
                or source.get("source_ref_id")
                or ""
            ).strip()
            text = str(
                source.get("text")
                or source.get("original_text")
                or ""
            ).strip()
            if not source_id or not text:
                continue
            current = source_records.get(source_id)
            if current is None or len(text) > len(str(current.get("text", ""))):
                source_records[source_id] = {
                    "source_id": source_id,
                    "source_type": str(
                        source.get("source_type")
                        or source.get("type")
                        or "evidence"
                    ),
                    "title": str(
                        source.get("filename")
                        or source.get("title")
                        or "원본 근거"
                    ),
                    "text": text,
                    "filename": source.get("filename"),
                    "message_id": source.get("message_id"),
                    "attachment_id": source.get("attachment_id"),
                }

    documents: list[Document] = []
    for source in source_records.values():
        for chunk_index, (text, start, end) in enumerate(
            split_text_chunks(source["text"])
        ):
            chunk_id = f"{source['source_id']}:{chunk_index}"
            documents.append(Document(
                id=chunk_id,
                page_content=text,
                metadata={
                    "source_id": source["source_id"],
                    "source_type": source["source_type"],
                    "title": source["title"],
                    "filename": str(source.get("filename") or ""),
                    "message_id": str(source.get("message_id") or ""),
                    "attachment_id": str(source.get("attachment_id") or ""),
                    "chunk_index": chunk_index,
                    "start_offset": start,
                    "end_offset": end,
                    "content_hash": hashlib.sha256(
                        text.encode("utf-8")
                    ).hexdigest(),
                    "index_version": EVIDENCE_INDEX_VERSION,
                },
            ))
    return documents


def _sync_evidence_store(
    documents: Sequence[Document],
    *,
    user_id: str,
    embeddings: Any | None = None,
) -> Chroma:
    EVIDENCE_VECTOR_ROOT.mkdir(parents=True, exist_ok=True)
    vector_db = Chroma(
        collection_name=_collection_name(
            "career_memory_evidence",
            user_id,
        ),
        embedding_function=embeddings or create_embeddings(),
        persist_directory=str(EVIDENCE_VECTOR_ROOT),
    )
    desired = {
        str(document.id): document
        for document in documents
        if document.id is not None
    }
    stored = vector_db.get(include=["metadatas"])
    stored_ids = [str(value) for value in stored.get("ids", [])]
    stored_hashes = {
        stored_id: (
            metadata.get("content_hash")
            if isinstance(metadata, Mapping)
            else None
        )
        for stored_id, metadata in zip(
            stored_ids,
            stored.get("metadatas", []),
            strict=False,
        )
    }
    stale = sorted(set(stored_ids) - set(desired))
    changed = sorted(
        document_id
        for document_id in set(stored_ids) & set(desired)
        if stored_hashes.get(document_id)
        != desired[document_id].metadata.get("content_hash")
    )
    new = sorted(set(desired) - set(stored_ids))
    if stale:
        vector_db.delete(ids=stale)
    if changed:
        vector_db.update_documents(
            ids=changed,
            documents=[desired[item] for item in changed],
        )
    if new:
        vector_db.add_documents(
            ids=new,
            documents=[desired[item] for item in new],
        )
    return vector_db


def retrieve_evidence_context(
    database: Session,
    user_id: str,
    query: str,
    *,
    search_k: int | None = None,
) -> list[ChatContextDocument]:
    """확정 경험에 연결된 원본 근거 청크를 검색한다."""

    if not query.strip():
        return []
    documents = build_evidence_documents(
        load_searchable_experiences(database, user_id)
    )
    if not documents:
        return []
    k = search_k or max(1, int(os.getenv("AI_CHAT_EVIDENCE_TOP_K", "6")))
    try:
        vector_db = _sync_evidence_store(documents, user_id=user_id)
        matches = vector_db.as_retriever(
            search_kwargs={"k": k}
        ).invoke(query)
    except Exception:
        matches = _lexical_documents(documents, query, k)
    return [
        ChatContextDocument(
            source_id=str(document.metadata["source_id"]),
            source_type="evidence",
            title=str(document.metadata.get("title", "")),
            content=document.page_content,
            metadata={
                "chunk_id": str(document.id),
                "filename": document.metadata.get("filename", ""),
                "message_id": document.metadata.get("message_id", ""),
                "attachment_id": document.metadata.get("attachment_id", ""),
                "start_offset": document.metadata.get("start_offset"),
                "end_offset": document.metadata.get("end_offset"),
            },
        )
        for document in matches
    ]


def _lexical_documents(
    documents: Sequence[Document],
    query: str,
    limit: int,
) -> list[Document]:
    query_terms = _query_terms(query)
    ranked = [
        (
            sum(document.page_content.casefold().count(term) for term in query_terms),
            document,
        )
        for document in documents
    ]
    ranked = [pair for pair in ranked if pair[0] > 0]
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [document for _score, document in ranked[:limit]]


def _query_terms(query: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"[가-힣A-Za-z0-9_]+", query)
        if len(token) >= 2
    }


def _json_list(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


__all__ = [
    "build_evidence_documents",
    "load_searchable_experiences",
    "retrieve_evidence_context",
    "retrieve_experience_context",
]
