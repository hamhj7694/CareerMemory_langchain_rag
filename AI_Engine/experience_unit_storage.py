"""Match and save V2 experience units without duplicating canonical experiences."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from difflib import SequenceMatcher
import json
import re
import unicodedata
from typing import Any, Mapping
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from AI_Engine.database.models import (
    AnalysisRunRecord,
    ContentDocument,
    Experience,
    ExperienceDomain,
    ExperienceProject,
    User,
    utc_now,
)
from AI_Engine.evidence_repository import sync_experience_evidence
from AI_Engine.knowledge_documents import (
    content_document_dict,
    experience_content_blocks,
    link_analysis_target,
    merge_projected_blocks,
    upsert_content_document,
)
from AI_Engine.normalization_backfill import structured_fields_for_experience


_WORD = re.compile(r"[0-9A-Za-z가-힣+#.]{2,}")


@dataclass
class UnitExperienceCreate:
    project_id: str | None = None
    domain: dict[str, Any] | None = None
    project: dict[str, Any] | None = None
    title: str = "제목 없는 경험"
    summary: str = ""
    situation: str = ""
    actions: list[str] = field(default_factory=list)
    results: list[str] = field(default_factory=list)
    role: str = ""
    skills: list[str] = field(default_factory=list)
    skill_mentions: list[dict[str, Any]] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    period: dict[str, Any] | str | None = None
    missing_information: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    draft_id: str | None = None
    field_citations: dict[str, Any] = field(default_factory=dict)
    skill_groups: list[dict[str, Any]] = field(default_factory=list)
    confidence: float | None = None
    extensions: dict[str, Any] = field(default_factory=dict)
    analysis_run_id: str | None = None
    content_blocks: list[dict[str, Any]] = field(default_factory=list)


def _resource_id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def _name(value: object) -> str:
    if isinstance(value, Mapping):
        return str(value.get("name") or "")
    return str(value or "")


def _normalized(value: object) -> str:
    return " ".join(
        unicodedata.normalize("NFKC", str(value or "")).casefold().split()
    )


def _tokens(*values: object) -> set[str]:
    return {
        token
        for value in values
        for token in _WORD.findall(_normalized(value))
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _unique_strings(*groups: object) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group if isinstance(group, (list, tuple)) else []:
            text = str(value).strip()
            key = _normalized(text)
            if not key or key in seen:
                continue
            seen.add(key)
            values.append(text)
    return values


def _unique_dicts(*groups: object) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for value in group if isinstance(group, (list, tuple)) else []:
            if not isinstance(value, Mapping):
                continue
            item = dict(value)
            key = str(item.get("id") or "")
            if not key:
                key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            values.append(item)
    return values


def _merge_citations(
    existing: Mapping[str, object] | None,
    incoming: Mapping[str, object] | None,
) -> dict[str, list[dict[str, Any]]]:
    keys = list(dict.fromkeys([*(existing or {}), *(incoming or {})]))
    return {
        key: _unique_dicts(
            (existing or {}).get(key, []),
            (incoming or {}).get(key, []),
        )
        for key in keys
    }


def _merge_indexed_citations(
    existing: Mapping[str, object] | None,
    incoming: Mapping[str, object] | None,
    *,
    incoming_lists: Mapping[str, list[str]],
    merged_lists: Mapping[str, list[str]],
) -> dict[str, list[dict[str, Any]]]:
    remapped: dict[str, list[dict[str, Any]]] = {}
    for key, citations in (incoming or {}).items():
        target_key = key
        match = re.fullmatch(r"(actions|results|facts|skills)\.(\d+)", str(key))
        if match:
            field_name, raw_index = match.groups()
            index = int(raw_index)
            values = incoming_lists.get(field_name, [])
            if index < len(values):
                value_key = _normalized(values[index])
                target_index = next(
                    (
                        item_index
                        for item_index, item in enumerate(merged_lists.get(field_name, []))
                        if _normalized(item) == value_key
                    ),
                    index,
                )
                target_key = f"{field_name}.{target_index}"
        remapped[target_key] = _unique_dicts(remapped.get(target_key, []), citations)
    return _merge_citations(existing, remapped)


def _experience_candidates(database: Session, user_id: str) -> list[Experience]:
    return list(database.scalars(
        select(Experience)
        .options(
            selectinload(Experience.project).selectinload(ExperienceProject.domain),
            selectinload(Experience.content_document).selectinload(ContentDocument.blocks),
        )
        .where(
            Experience.user_id == user_id,
            Experience.deleted_at.is_(None),
            Experience.status == "confirmed",
        )
        .order_by(Experience.updated_at.desc())
    ))


def _match_score(unit: Mapping[str, object], item: Experience) -> tuple[float, list[str]]:
    unit_sources = set(str(value) for value in unit.get("source_ref_ids", []) or [])
    item_sources = set(str(value) for value in item.source_ids or [])
    if unit_sources & item_sources:
        return 0.99, ["같은 원문 근거"]

    project = item.project
    same_project = (
        _normalized(_name(unit.get("project"))) == _normalized(project.name)
        and _normalized(_name(unit.get("domain"))) == _normalized(project.domain.name)
    )
    if not same_project:
        return 0.0, []

    title_similarity = SequenceMatcher(
        None,
        _normalized(unit.get("title")),
        _normalized(item.title),
    ).ratio()
    unit_content = _tokens(
        unit.get("title"), unit.get("summary"), unit.get("situation"),
        *(unit.get("actions", []) or []), *(unit.get("results", []) or []),
        *(unit.get("facts", []) or []),
    )
    item_content = _tokens(
        item.title, item.summary, item.situation,
        *(item.actions or []), *(item.results or []), *(item.facts or []),
    )
    content_overlap = _jaccard(unit_content, item_content)
    skill_overlap = _jaccard(
        {_normalized(value) for value in unit.get("skills", []) or []},
        {_normalized(value) for value in item.skills or []},
    )
    score = 0.35 + title_similarity * 0.35 + content_overlap * 0.25 + skill_overlap * 0.05
    reasons = ["같은 경험 분류·프로젝트"]
    if title_similarity >= 0.78:
        reasons.append("유사한 경험 제목")
    if content_overlap >= 0.30:
        reasons.append("행동·성과 내용 중복")
    if skill_overlap:
        reasons.append("기존 기술·역량 재사용")
    eligible = (
        (_normalized(unit.get("title")) == _normalized(item.title))
        or (title_similarity >= 0.78 and content_overlap >= 0.18)
        or content_overlap >= 0.62
    )
    return (score, reasons) if eligible and score >= 0.72 else (0.0, [])


def annotate_proposal_matches(
    database: Session,
    proposal: Mapping[str, object],
    *,
    user_id: str,
) -> dict[str, Any]:
    """Add conservative create/update intent and reuse canonical skill spelling."""

    result = deepcopy(dict(proposal))
    candidates = _experience_candidates(database, user_id)
    canonical_skills: dict[str, str] = {}
    for candidate in candidates:
        for skill in candidate.skills or []:
            canonical_skills.setdefault(_normalized(skill), skill)
    claimed_existing_ids: set[str] = set()
    for unit in result.get("units", []):
        reused_skills: list[str] = []
        normalized_skills: list[str] = []
        for skill in unit.get("skills", []) or []:
            canonical = canonical_skills.get(_normalized(skill), str(skill).strip())
            if _normalized(skill) in canonical_skills:
                reused_skills.append(canonical)
            normalized_skills.append(canonical)
        unit["skills"] = _unique_strings(normalized_skills)
        unit["reused_skills"] = _unique_strings(reused_skills)

        ranked = sorted(
            (
                (*_match_score(unit, candidate), candidate)
                for candidate in candidates
                if candidate.id not in claimed_existing_ids
            ),
            key=lambda value: value[0],
            reverse=True,
        )
        score, reasons, match = ranked[0] if ranked else (0.0, [], None)
        if match is None or score <= 0:
            unit["save_strategy"] = {"operation": "create"}
            continue
        claimed_existing_ids.add(match.id)
        unit["save_strategy"] = {
            "operation": "update",
            "experience_id": match.id,
            "experience_title": match.title,
            "score": round(score, 4),
            "reasons": reasons,
        }
    return result


def experience_create_from_unit(unit: Mapping[str, object]) -> UnitExperienceCreate:
    extensions = dict(unit.get("extensions") or {})
    if unit.get("unit_id"):
        extensions["experience_unit_v2"] = {
            "unit_id": unit["unit_id"],
            "contract_version": "experience-units-v2",
            "primary_span_ids": list(unit.get("primary_span_ids") or []),
            "context_span_ids": list(unit.get("context_span_ids") or []),
            "field_span_ids": dict(unit.get("field_span_ids") or {}),
            "fact_ids": list(unit.get("fact_ids") or []),
        }
    return UnitExperienceCreate(
        project_id=unit.get("project_id"),
        domain=unit.get("domain"), project=unit.get("project"),
        title=str(unit.get("title") or "제목 없는 경험").strip(),
        summary=str(unit.get("summary") or ""),
        situation=str(unit.get("situation") or ""),
        actions=list(unit.get("actions") or []), results=list(unit.get("results") or []),
        role=str(unit.get("role") or ""), skills=list(unit.get("skills") or []),
        skill_mentions=list(unit.get("skill_mentions") or []),
        facts=list(unit.get("facts") or []), metrics=list(unit.get("metrics") or []),
        period=unit.get("period"),
        missing_information=list(unit.get("missing_information") or []),
        source_ids=list(unit.get("source_ref_ids") or unit.get("source_ids") or []),
        source_refs=list(unit.get("source_refs") or []),
        draft_id=unit.get("draft_id"),
        field_citations=dict(unit.get("field_citations") or {}),
        skill_groups=list(unit.get("skill_groups") or []),
        confidence=unit.get("confidence"), extensions=extensions,
        analysis_run_id=unit.get("analysis_run_id"),
        content_blocks=list(unit.get("content_blocks") or []),
    )


def _analysis_run(
    database: Session,
    request: UnitExperienceCreate,
    user_id: str,
) -> AnalysisRunRecord | None:
    if not request.analysis_run_id:
        return None
    run = database.scalar(select(AnalysisRunRecord).where(
        AnalysisRunRecord.id == request.analysis_run_id,
        AnalysisRunRecord.user_id == user_id,
    ))
    if run is None:
        raise HTTPException(status_code=422, detail="연결할 수 없는 AI 분석 기록입니다.")
    return run


def _projected_blocks(item: Experience) -> list[dict[str, Any]]:
    return experience_content_blocks({
        "summary": item.summary, "situation": item.situation,
        "actions": item.actions, "results": item.results, "role": item.role,
        "skills": item.skills, "skill_mentions": item.skill_mentions,
        "skill_groups": item.skill_groups, "facts": item.facts,
        "fact_evidence_status": item.fact_evidence_status,
        "metrics": item.metrics, "period": item.period,
        "missing_information": item.missing_information,
        "extensions": item.extensions,
    })


def _merge_existing(
    database: Session,
    item: Experience,
    request: UnitExperienceCreate,
    *,
    run: AnalysisRunRecord | None,
    unit_id: str,
) -> Experience:
    item.summary = item.summary or request.summary
    item.situation = item.situation or request.situation
    item.role = item.role or request.role
    item.actions = _unique_strings(item.actions, request.actions)
    item.results = _unique_strings(item.results, request.results)
    item.skills = _unique_strings(item.skills, request.skills)
    previous_fact_status = dict(item.fact_evidence_status or {})
    item.facts = _unique_strings(item.facts, request.facts)
    item.missing_information = _unique_strings(
        item.missing_information, request.missing_information
    )
    item.source_ids = _unique_strings(item.source_ids, request.source_ids)
    item.source_refs = _unique_dicts(item.source_refs, request.source_refs)
    item.skill_mentions = _unique_dicts(item.skill_mentions, request.skill_mentions)
    item.metrics = _unique_dicts(item.metrics, request.metrics)
    item.skill_groups = _unique_dicts(item.skill_groups, request.skill_groups)
    item.field_citations = _merge_indexed_citations(
        item.field_citations,
        request.field_citations,
        incoming_lists={
            "actions": request.actions,
            "results": request.results,
            "facts": request.facts,
            "skills": request.skills,
        },
        merged_lists={
            "actions": item.actions,
            "results": item.results,
            "facts": item.facts,
            "skills": item.skills,
        },
    )
    item.skill_mentions, item.metrics = structured_fields_for_experience(
        item.skills, item.facts,
        skill_mentions=item.skill_mentions,
        metrics=item.metrics,
        source_refs=item.source_refs,
    )
    existing_period = dict(item.period or {})
    incoming_period = dict(request.period or {}) if isinstance(request.period, dict) else {}
    item.period = {
        "start": existing_period.get("start") or incoming_period.get("start"),
        "end": existing_period.get("end") or incoming_period.get("end"),
    }
    incoming_fact_status = {
        fact: ("supported" if request.field_citations.get(f"facts.{index}") else "needs_evidence")
        for index, fact in enumerate(request.facts)
    }
    item.fact_evidence_status = {
        fact: previous_fact_status.get(fact) or incoming_fact_status.get(fact, "needs_evidence")
        for fact in item.facts
    }
    updates = list((item.extensions or {}).get("_experience_unit_updates") or [])
    updates.append({
        "unit_id": unit_id,
        "analysis_run_id": request.analysis_run_id,
        "merged_at": utc_now().isoformat(),
    })
    item.extensions = {
        **(item.extensions or {}),
        "_experience_unit_updates": updates,
    }
    item.confidence = max(
        value for value in (item.confidence, request.confidence) if value is not None
    ) if any(value is not None for value in (item.confidence, request.confidence)) else None
    item.updated_at = utc_now()
    item.version += 1
    current_document = content_document_dict(item.content_document) or {"blocks": []}
    custom_blocks = [
        block for block in current_document["blocks"]
        if block.get("origin") != "system_projection"
    ]
    document = upsert_content_document(
        database, user_id=item.user_id, owner_type="experience", owner_id=item.id,
        title=item.title,
        blocks=merge_projected_blocks(_projected_blocks(item), custom_blocks),
        extensions=item.extensions, document_id=item.content_document_id,
    )
    item.content_document_id = document.id
    if run is not None:
        link_analysis_target(
            database, run, unit_id=unit_id,
            target_type="experience", target_id=item.id, commit=False,
        )
    sync_experience_evidence(database, item)
    database.flush()
    return item


def _resolve_project(
    request: UnitExperienceCreate,
    user: User,
    database: Session,
) -> ExperienceProject:
    if request.project_id:
        project = database.scalar(select(ExperienceProject).where(
            ExperienceProject.id == request.project_id,
            ExperienceProject.user_id == user.id,
            ExperienceProject.deleted_at.is_(None),
        ))
        if project is None:
            raise HTTPException(status_code=404, detail="프로젝트·활동을 찾을 수 없습니다.")
        project.domain = database.get(ExperienceDomain, project.domain_id)
        return project
    domain_name = _name(request.domain).strip() or "미분류 경험"
    project_name = _name(request.project).strip() or "프로젝트·활동 미분류"
    domain = database.scalar(select(ExperienceDomain).where(
        ExperienceDomain.user_id == user.id,
        ExperienceDomain.name == domain_name,
    ))
    if domain is None:
        domain = ExperienceDomain(
            id=_resource_id("DOM"), user_id=user.id, name=domain_name,
        )
        database.add(domain)
        database.flush()
    elif domain.deleted_at is not None:
        domain.deleted_at = None
        domain.updated_at = utc_now()
        domain.version += 1
    project = database.scalar(select(ExperienceProject).where(
        ExperienceProject.domain_id == domain.id,
        ExperienceProject.name == project_name,
    ))
    if project is None:
        project = ExperienceProject(
            id=_resource_id("PROJ"), user_id=user.id, domain_id=domain.id,
            name=project_name,
            organization=str((request.project or {}).get("organization", "")).strip(),
        )
        database.add(project)
        database.flush()
    elif project.deleted_at is not None:
        project.deleted_at = None
        project.updated_at = utc_now()
        project.version += 1
    project.domain = domain
    return project


def save_experience_unit(
    database: Session,
    *,
    unit: Mapping[str, object],
    source_refs: list[dict[str, Any]],
    current_user: User,
) -> tuple[Experience, str]:
    """Create a new canonical experience or add new evidence to a strong match."""

    draft = deepcopy(dict(unit))
    draft["source_refs"] = source_refs
    request = experience_create_from_unit(draft)
    run = _analysis_run(database, request, current_user.id)
    strategy = unit.get("save_strategy") if isinstance(unit.get("save_strategy"), Mapping) else {}
    target_id = strategy.get("experience_id") if strategy.get("operation") == "update" else None
    if target_id:
        existing = next(
            (item for item in _experience_candidates(database, current_user.id) if item.id == target_id),
            None,
        )
        if existing is not None:
            return _merge_existing(
                database, existing, request, run=run,
                unit_id=str(unit.get("unit_id") or request.draft_id or "unit"),
            ), "updated"

    project = _resolve_project(request, current_user, database)
    period = request.period if isinstance(request.period, dict) else {}
    skill_mentions, metrics = structured_fields_for_experience(
        request.skills, request.facts,
        skill_mentions=request.skill_mentions, metrics=request.metrics,
        source_refs=request.source_refs,
    )
    item = Experience(
        id=_resource_id("EXP"), user_id=current_user.id, project_id=project.id,
        title=request.title, summary=request.summary, situation=request.situation,
        actions=request.actions, results=request.results, role=request.role,
        skills=request.skills, skill_mentions=skill_mentions, facts=request.facts,
        fact_evidence_status={
            fact: ("supported" if request.field_citations.get(f"facts.{index}") else "needs_evidence")
            for index, fact in enumerate(request.facts)
        },
        metrics=metrics, period=period,
        missing_information=request.missing_information,
        source_ids=request.source_ids, source_refs=request.source_refs,
        draft_id=request.draft_id, field_citations=request.field_citations,
        skill_groups=request.skill_groups, confidence=request.confidence,
        extensions=request.extensions,
        analysis_run_id=run.id if run else None, status="confirmed",
    )
    item.project = project
    database.add(item)
    database.flush()
    document = upsert_content_document(
        database, user_id=current_user.id, owner_type="experience", owner_id=item.id,
        title=item.title,
        blocks=merge_projected_blocks(_projected_blocks(item), request.content_blocks),
        extensions=item.extensions,
    )
    item.content_document_id = document.id
    if run is not None:
        link_analysis_target(
            database, run,
            unit_id=str(unit.get("unit_id") or request.draft_id or "unit"),
            target_type="experience", target_id=item.id, commit=False,
        )
    sync_experience_evidence(database, item)
    database.flush()
    return item, "created"


__all__ = [
    "annotate_proposal_matches",
    "experience_create_from_unit",
    "save_experience_unit",
]
