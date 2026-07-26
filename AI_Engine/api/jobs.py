"""채용공고를 분석하고 로그인 사용자의 경험과 연결하는 API."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from AI_Engine.auth.dependencies import get_current_user, require_csrf_user
from AI_Engine.database.connection import PROJECT_ROOT, get_database_session
from AI_Engine.database.models import (
    Experience,
    ExperienceProject,
    JobAnalysisRecord,
    User,
    utc_now,
)
from AI_Engine.job_analysis_ai import (
    JobAnalysisAIInputError,
    JobAnalysisAIOutputError,
    JobAnalysisAIRetrievalError,
    create_experience_retriever,
    create_job_analysis_ai,
)
from AI_Engine.job_file_text import (
    JobFile,
    JobFileExtractionError,
    JobFileInputError,
    MAX_JOB_FILE_BYTES,
    extract_job_file_text,
)
from AI_Engine.schemas import JobAnalysisRequest, JobRequirement


router = APIRouter(prefix="/api/jobs", tags=["jobs"])
VECTOR_ROOT = PROJECT_ROOT / "data" / "vector_store" / "jobs"


class JobAnalyzeBody(BaseModel):
    client_request_id: str = Field(min_length=1, max_length=100)
    company_name: str = ""
    role_name: str = ""
    posting_title: str = ""
    source_url: str | None = None
    posting_content: str = Field(min_length=1)


class MatchBody(BaseModel):
    requirement_ids: list[str] = Field(default_factory=list)
    client_request_id: str | None = None
    refresh: bool = False


def _owned_job(job_id: str, user_id: str, database: Session) -> JobAnalysisRecord:
    item = database.scalar(
        select(JobAnalysisRecord).where(
            JobAnalysisRecord.id == job_id,
            JobAnalysisRecord.user_id == user_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="채용공고 분석 기록을 찾을 수 없습니다.")
    return item


def _experience_dict(item: Experience) -> dict[str, Any]:
    """DB 경험을 채용공고 RAG 문서가 이해하는 공통 필드로 바꾼다."""

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


def _frontend_experience(item: Experience) -> dict[str, Any]:
    return {
        "experienceId": item.id,
        "title": item.title,
        "summary": item.summary,
        "situation": item.situation,
        "actions": item.actions,
        "results": item.results,
        "role": item.role,
        "skills": item.skills,
        "facts": item.facts,
        "domainId": item.project.domain.id,
        "domainName": item.project.domain.name,
        "projectId": item.project.id,
        "projectName": item.project.name,
        "evidenceCount": len(item.source_ids),
    }


def _requirement_to_frontend(requirement: dict[str, Any]) -> dict[str, Any]:
    locator = requirement.get("source_locator")
    return {
        "id": requirement["id"],
        "order": requirement.get("order"),
        "type": requirement.get("type", "other"),
        "text": requirement.get("title", ""),
        "title": requirement.get("title", ""),
        "summary": requirement.get("summary", ""),
        "sourceExcerpt": requirement.get("source_excerpt", ""),
        "sourceLocator": locator,
        "importance": requirement.get("importance", "unknown"),
        "keywords": requirement.get("keywords", []),
        "confidence": requirement.get("confidence"),
        "needsReview": (
            requirement.get("confidence") is not None
            and float(requirement["confidence"]) < 0.5
        ),
    }


def _job_to_frontend(item: JobAnalysisRecord) -> dict[str, Any]:
    return {
        "jobId": item.id,
        "companyName": item.company_name,
        "roleName": item.role_name,
        "postingTitle": item.posting_title,
        "sourceUrl": item.source_url,
        "postingContent": item.posting_content,
        "requirements": [
            _requirement_to_frontend(requirement)
            for requirement in item.requirements
        ],
        "warnings": item.warnings,
        "analyzedAt": item.analyzed_at,
    }


def _load_rag_experiences(user_id: str, database: Session) -> list[Experience]:
    # 근거가 있는 확정 경험만 AI 추천의 검색 대상이 된다.
    return list(
        database.scalars(
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
        ).all()
    )


def _user_collection_name(user_id: str) -> str:
    # 사용자 ID 원문을 벡터 DB 이름에 노출하지 않는다.
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]
    return f"career_memory_experiences_{digest}"


@router.get("")
def list_jobs(
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
) -> dict[str, Any]:
    items = database.scalars(
        select(JobAnalysisRecord)
        .where(JobAnalysisRecord.user_id == current_user.id)
        .order_by(JobAnalysisRecord.analyzed_at.desc())
    ).all()
    return {"items": [_job_to_frontend(item) for item in items]}


@router.post("/extract-text")
async def extract_job_text(
    files: list[UploadFile] = File(...),
    _current_user: User = Depends(require_csrf_user),
) -> dict[str, Any]:
    """공고 파일을 읽어 사용자가 검토할 수 있는 원문 텍스트로 반환한다."""

    job_files: list[JobFile] = []
    for uploaded in files:
        # 제한보다 1바이트만 더 읽어 대용량 파일을 메모리에 전부 올리지 않는다.
        content = await uploaded.read(MAX_JOB_FILE_BYTES + 1)
        job_files.append(JobFile(
            filename=uploaded.filename or "이름 없는 파일",
            mime_type=(uploaded.content_type or "").lower(),
            content=content,
        ))
        await uploaded.close()
    try:
        text = extract_job_file_text(job_files)
    except JobFileInputError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except JobFileExtractionError as error:
        message = str(error).lower()
        if "quota" in message or "resource_exhausted" in message or "429" in message:
            raise HTTPException(
                status_code=429,
                detail="Gemini 무료 할당량을 모두 사용해 파일을 읽지 못했습니다.",
            ) from error
        raise HTTPException(
            status_code=502,
            detail="파일에서 채용공고 글자를 읽지 못했습니다. 선명한 파일로 다시 시도해 주세요.",
        ) from error
    return {
        "text": text,
        "files": [
            {
                "filename": file.filename,
                "mime_type": file.mime_type,
                "size_bytes": len(file.content),
            }
            for file in job_files
        ],
    }


@router.post("/analyze")
def analyze_job(
    body: JobAnalyzeBody,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> dict[str, Any]:
    existing = database.scalar(
        select(JobAnalysisRecord).where(
            JobAnalysisRecord.user_id == current_user.id,
            JobAnalysisRecord.client_request_id == body.client_request_id,
        )
    )
    if existing is not None:
        return _job_to_frontend(existing)

    experiences = _load_rag_experiences(current_user.id, database)
    searchable = [item for item in experiences if item.source_ids]
    retriever = None
    rag_warning = ""
    if searchable:
        try:
            VECTOR_ROOT.mkdir(parents=True, exist_ok=True)
            retriever = create_experience_retriever(
                [_experience_dict(item) for item in searchable],
                persist_directory=str(VECTOR_ROOT),
                collection_name=_user_collection_name(current_user.id),
            )
        except Exception:
            # 임베딩 할당량 문제여도 공고 요구사항 분석 자체는 계속 제공한다.
            rag_warning = "경험 검색을 준비하지 못해 이번 분석에서는 요구사항만 정리했습니다."

    request = JobAnalysisRequest(
        client_request_id=body.client_request_id,
        posting_id=f"job-posting-{uuid4()}",
        company_name=body.company_name,
        role_name=body.role_name,
        posting_title=body.posting_title,
        source_url=body.source_url,
        posting_content=body.posting_content,
    )
    try:
        result = create_job_analysis_ai(
            experience_retriever=retriever
        ).invoke(request)
    except JobAnalysisAIInputError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (JobAnalysisAIOutputError, JobAnalysisAIRetrievalError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="채용공고 분석 결과를 정리하지 못했습니다. 다시 시도해 주세요.",
        ) from error
    except Exception as error:
        message = str(error).lower()
        if "quota" in message or "resource_exhausted" in message or "429" in message:
            raise HTTPException(
                status_code=429,
                detail="Gemini 무료 할당량을 모두 사용했습니다. 잠시 후 다시 시도해 주세요.",
            ) from error
        raise HTTPException(
            status_code=502,
            detail="AI 채용공고 분석 호출에 실패했습니다. 잠시 후 다시 시도해 주세요.",
        ) from error

    result_data = result.model_dump(mode="json")
    warnings = list(result_data["warnings"])
    if rag_warning:
        warnings.append(rag_warning)
    elif not searchable:
        warnings = [
            "근거가 있는 저장 경험이 없어 이번 분석에서는 요구사항만 정리했습니다."
        ]

    item = JobAnalysisRecord(
        id=result.analysis_id,
        user_id=current_user.id,
        client_request_id=body.client_request_id,
        company_name=body.company_name,
        role_name=body.role_name,
        posting_title=body.posting_title,
        source_url=body.source_url,
        posting_content=body.posting_content,
        requirements=result_data["requirements"],
        experience_links=result_data["experience_links"],
        warnings=warnings,
        versions={
            "model": result.model_version,
            "prompt": result.prompt_version,
            "schema": result.schema_version,
            "index": result.index_version,
        },
        analyzed_at=result.analyzed_at,
    )
    database.add(item)
    database.commit()
    return _job_to_frontend(item)


@router.get("/{job_id}")
def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
) -> dict[str, Any]:
    return _job_to_frontend(_owned_job(job_id, current_user.id, database))


@router.post("/{job_id}/match")
def match_job(
    job_id: str,
    body: MatchBody,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> dict[str, Any]:
    item = _owned_job(job_id, current_user.id, database)
    selected = set(body.requirement_ids)
    requirements = {
        requirement["id"]: requirement for requirement in item.requirements
        if not selected or requirement["id"] in selected
    }
    if body.refresh:
        # 사용자가 직접 연결한 항목과 선택하지 않은 요구사항의 추천은 보존한다.
        # 선택한 요구사항의 AI 추천만 최신 확정 경험을 기준으로 교체한다.
        manual_or_unselected_links = [
            link for link in item.experience_links
            if link.get("source") == "user"
            or link.get("requirement_id") not in requirements
        ]
        experiences_for_rag = _load_rag_experiences(current_user.id, database)
        searchable = [experience for experience in experiences_for_rag if experience.source_ids]
        refreshed_links: list[dict[str, Any]] = []
        if searchable and requirements:
            try:
                VECTOR_ROOT.mkdir(parents=True, exist_ok=True)
                retriever = create_experience_retriever(
                    [_experience_dict(experience) for experience in searchable],
                    persist_directory=str(VECTOR_ROOT),
                    collection_name=_user_collection_name(current_user.id),
                )
                analyzer = create_job_analysis_ai(experience_retriever=retriever)
                refreshed_links = [
                    link.model_dump(mode="json")
                    for link in analyzer.rematch_requirements([
                        JobRequirement.model_validate(requirement)
                        for requirement in requirements.values()
                    ])
                ]
            except (JobAnalysisAIOutputError, JobAnalysisAIRetrievalError) as error:
                raise HTTPException(
                    status_code=502,
                    detail="최신 경험으로 다시 매칭하지 못했습니다. 다시 시도해 주세요.",
                ) from error
            except Exception as error:
                message = str(error).lower()
                if "quota" in message or "resource_exhausted" in message or "429" in message:
                    raise HTTPException(
                        status_code=429,
                        detail="Gemini 무료 할당량을 모두 사용했습니다. 잠시 후 다시 시도해 주세요.",
                    ) from error
                raise HTTPException(
                    status_code=502,
                    detail="최신 경험 검색을 준비하지 못했습니다.",
                ) from error
        item.experience_links = manual_or_unselected_links + refreshed_links
        item.updated_at = utc_now()
        database.commit()

    experience_ids = {
        str(link["experience_id"]) for link in item.experience_links
        if link.get("requirement_id") in requirements
        and link.get("status") != "rejected"
    }
    experiences = {
        experience.id: experience
        for experience in _load_rag_experiences(current_user.id, database)
        if experience.id in experience_ids
    }
    matches = []
    for requirement_id, requirement in requirements.items():
        links = [
            link for link in item.experience_links
            if link.get("requirement_id") == requirement_id
            and link.get("status") != "rejected"
            and link.get("experience_id") in experiences
        ]
        linked = [str(link["experience_id"]) for link in links]
        matches.append({
            "requirementId": requirement_id,
            "requirementText": requirement.get("title", ""),
            "status": "direct" if linked else "noEvidence",
            "reason": links[0].get("reason", "") if links else "",
            "linkedExperienceIds": linked,
            "experiences": [
                {
                    **_frontend_experience(experiences[experience_id]),
                    "score": next(
                        link.get("similarity_score")
                        for link in links
                        if link["experience_id"] == experience_id
                    ),
                    "evidence": [
                        {"sourceId": source_id}
                        for source_id in next(
                            link.get("evidence_ids", [])
                            for link in links
                            if link["experience_id"] == experience_id
                        )
                    ],
                }
                for experience_id in linked
            ],
            "missingInformation": [] if linked else ["연결할 근거 경험이 없습니다."],
        })
    return {"jobId": item.id, "matches": matches, "failures": []}


@router.put(
    "/{job_id}/requirements/{requirement_id}/experience-links/{experience_id}"
)
def add_requirement_link(
    job_id: str,
    requirement_id: str,
    experience_id: str,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> dict[str, bool]:
    item = _owned_job(job_id, current_user.id, database)
    if not any(row["id"] == requirement_id for row in item.requirements):
        raise HTTPException(status_code=404, detail="요구사항을 찾을 수 없습니다.")
    experience = database.scalar(
        select(Experience).where(
            Experience.id == experience_id,
            Experience.user_id == current_user.id,
            Experience.deleted_at.is_(None),
        )
    )
    if experience is None:
        raise HTTPException(status_code=404, detail="경험을 찾을 수 없습니다.")
    links = [
        link for link in item.experience_links
        if not (
            link.get("requirement_id") == requirement_id
            and link.get("experience_id") == experience_id
        )
    ]
    links.append({
        "requirement_id": requirement_id,
        "experience_id": experience_id,
        "source": "user",
        "status": "selected",
        "reason": "사용자가 직접 연결한 경험입니다.",
        "evidence_ids": experience.source_ids,
    })
    item.experience_links = links
    item.updated_at = utc_now()
    database.commit()
    return {"linked": True}


@router.delete(
    "/{job_id}/requirements/{requirement_id}/experience-links/{experience_id}"
)
def remove_requirement_link(
    job_id: str,
    requirement_id: str,
    experience_id: str,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> dict[str, bool]:
    item = _owned_job(job_id, current_user.id, database)
    item.experience_links = [
        link for link in item.experience_links
        if not (
            link.get("requirement_id") == requirement_id
            and link.get("experience_id") == experience_id
        )
    ]
    item.updated_at = utc_now()
    database.commit()
    return {"linked": False}


@router.delete("/{job_id}", status_code=204)
def delete_job(
    job_id: str,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> Response:
    database.delete(_owned_job(job_id, current_user.id, database))
    database.commit()
    return Response(status_code=204)


__all__ = ["router"]
