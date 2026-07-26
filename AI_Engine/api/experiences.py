"""로그인 사용자의 경험 분류·프로젝트·확정 경험 CRUD API."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from AI_Engine.auth.dependencies import get_current_user, require_csrf_user
from AI_Engine.database.connection import get_database_session
from AI_Engine.database.models import (
    Experience,
    ExperienceDomain,
    ExperienceProject,
    User,
    utc_now,
)

router = APIRouter(prefix="/api/v2", tags=["experiences"])


class DomainCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ProjectCreate(BaseModel):
    domain_id: str
    name: str = Field(min_length=1, max_length=150)
    organization: str = Field(default="", max_length=200)


class StructureUpdate(BaseModel):
    base_version: int = Field(ge=1)
    changes: dict[str, Any]


class BulkMoveRequest(BaseModel):
    experience_ids: list[str] = Field(min_length=1)
    target_project_id: str


class ExperienceCreate(BaseModel):
    project_id: str | None = None
    domain: dict[str, Any] | None = None
    project: dict[str, Any] | None = None
    title: str = Field(min_length=1, max_length=200)
    summary: str = ""
    situation: str = ""
    actions: list[str] = Field(default_factory=list)
    results: list[str] = Field(default_factory=list)
    role: str = ""
    skills: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    period: dict[str, Any] | str | None = None
    missing_information: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "confirmed"


class ExperienceUpdate(BaseModel):
    base_version: int = Field(ge=1)
    changes: dict[str, Any]


class DeleteRequest(BaseModel):
    version: int | None = None
    confirm: bool = False


def resource_id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def domain_dict(item: ExperienceDomain) -> dict[str, Any]:
    return {
        "id": item.id, "name": item.name, "created_at": item.created_at,
        "updated_at": item.updated_at, "version": item.version,
    }


def project_dict(item: ExperienceProject) -> dict[str, Any]:
    return {
        "id": item.id, "domain_id": item.domain_id, "name": item.name,
        "organization": item.organization, "created_at": item.created_at,
        "updated_at": item.updated_at, "version": item.version,
    }


def experience_dict(item: Experience) -> dict[str, Any]:
    project = item.project
    domain = project.domain
    return {
        "id": item.id, "title": item.title, "summary": item.summary,
        "situation": item.situation, "actions": item.actions,
        "results": item.results, "role": item.role, "skills": item.skills,
        "facts": item.facts, "period": item.period,
        "missing_information": item.missing_information,
        "source_ids": item.source_ids, "source_refs": item.source_refs,
        "status": item.status,
        "domain": {"id": domain.id, "name": domain.name},
        "domain_id": domain.id,
        "project": {
            "id": project.id, "name": project.name,
            "organization": project.organization,
        },
        "project_id": project.id,
        "evidence_count": len(item.source_ids),
        "evidence_status": "verified" if item.source_ids else "missing",
        "created_at": item.created_at, "updated_at": item.updated_at,
        "version": item.version,
    }


def owned_project(project_id: str, user_id: str, database: Session) -> ExperienceProject:
    project = database.scalar(
        select(ExperienceProject)
        .options(selectinload(ExperienceProject.domain))
        .where(
            ExperienceProject.id == project_id,
            ExperienceProject.user_id == user_id,
            ExperienceProject.deleted_at.is_(None),
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="프로젝트·활동을 찾을 수 없습니다.")
    return project


def owned_domain(domain_id: str, user_id: str, database: Session) -> ExperienceDomain:
    domain = database.scalar(
        select(ExperienceDomain).where(
            ExperienceDomain.id == domain_id,
            ExperienceDomain.user_id == user_id,
            ExperienceDomain.deleted_at.is_(None),
        )
    )
    if domain is None:
        raise HTTPException(status_code=404, detail="경험 분류를 찾을 수 없습니다.")
    return domain


def owned_experience(experience_id: str, user_id: str, database: Session) -> Experience:
    item = database.scalar(
        select(Experience)
        .options(selectinload(Experience.project).selectinload(ExperienceProject.domain))
        .where(
            Experience.id == experience_id,
            Experience.user_id == user_id,
            Experience.deleted_at.is_(None),
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="경험을 찾을 수 없습니다.")
    return item


@router.get("/experience-structure")
def list_structure(
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
):
    domains = list(database.scalars(
        select(ExperienceDomain)
        .options(
            selectinload(ExperienceDomain.projects)
            .selectinload(ExperienceProject.experiences)
        )
        .where(
            ExperienceDomain.user_id == current_user.id,
            ExperienceDomain.deleted_at.is_(None),
        )
        .order_by(ExperienceDomain.created_at)
    ))
    return {
        "domains": [
            {
                **domain_dict(domain),
                "projects": [
                    {
                        **project_dict(project),
                        "experiences": [
                            experience_dict(item)
                            for item in project.experiences
                            if item.deleted_at is None
                        ],
                    }
                    for project in domain.projects
                    if project.deleted_at is None
                ],
            }
            for domain in domains
        ],
        "total_count": len(domains),
    }


@router.post("/experience-domains", status_code=201)
def create_domain(
    request: DomainCreate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    item = ExperienceDomain(
        id=resource_id("DOM"), user_id=current_user.id, name=request.name.strip()
    )
    database.add(item)
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(status_code=409, detail="같은 이름의 경험 분류가 이미 있습니다.") from error
    database.refresh(item)
    return domain_dict(item)


@router.post("/experience-projects", status_code=201)
def create_project(
    request: ProjectCreate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    domain = database.scalar(select(ExperienceDomain).where(
        ExperienceDomain.id == request.domain_id,
        ExperienceDomain.user_id == current_user.id,
        ExperienceDomain.deleted_at.is_(None),
    ))
    if domain is None:
        raise HTTPException(status_code=404, detail="경험 분류를 찾을 수 없습니다.")
    item = ExperienceProject(
        id=resource_id("PROJ"), user_id=current_user.id, domain_id=domain.id,
        name=request.name.strip(), organization=request.organization.strip(),
    )
    database.add(item)
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(status_code=409, detail="같은 프로젝트·활동이 이미 있습니다.") from error
    database.refresh(item)
    return project_dict(item)


@router.patch("/experience-domains/{domain_id}")
def update_domain(
    domain_id: str,
    request: StructureUpdate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    item = owned_domain(domain_id, current_user.id, database)
    if item.version != request.base_version:
        raise HTTPException(status_code=409, detail="경험 분류가 다른 곳에서 수정되었습니다.")
    if "name" in request.changes:
        item.name = str(request.changes["name"]).strip()
    item.version += 1
    item.updated_at = utc_now()
    database.commit()
    database.refresh(item)
    return domain_dict(item)


@router.delete("/experience-domains/{domain_id}")
def delete_domain(
    domain_id: str,
    request: DeleteRequest,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    if not request.confirm:
        raise HTTPException(status_code=422, detail="삭제 확인이 필요합니다.")
    item = owned_domain(domain_id, current_user.id, database)
    if request.version is not None and item.version != request.version:
        raise HTTPException(status_code=409, detail="경험 분류 버전이 변경되었습니다.")
    item.deleted_at = utc_now()
    item.version += 1
    for project in item.projects:
        project.deleted_at = utc_now()
        for experience in project.experiences:
            experience.deleted_at = utc_now()
    database.commit()
    return {"deleted_id": item.id, "recoverable": True}


@router.patch("/experience-projects/{project_id}")
def update_project(
    project_id: str,
    request: StructureUpdate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    item = owned_project(project_id, current_user.id, database)
    if item.version != request.base_version:
        raise HTTPException(status_code=409, detail="프로젝트·활동이 다른 곳에서 수정되었습니다.")
    if "domain_id" in request.changes:
        target_domain = owned_domain(
            str(request.changes["domain_id"]), current_user.id, database
        )
        item.domain_id = target_domain.id
    for key in ("name", "organization"):
        if key in request.changes:
            setattr(item, key, str(request.changes[key]).strip())
    item.version += 1
    item.updated_at = utc_now()
    database.commit()
    database.refresh(item)
    return project_dict(item)


@router.delete("/experience-projects/{project_id}")
def delete_project(
    project_id: str,
    request: DeleteRequest,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    if not request.confirm:
        raise HTTPException(status_code=422, detail="삭제 확인이 필요합니다.")
    item = owned_project(project_id, current_user.id, database)
    if request.version is not None and item.version != request.version:
        raise HTTPException(status_code=409, detail="프로젝트·활동 버전이 변경되었습니다.")
    item.deleted_at = utc_now()
    item.version += 1
    for experience in item.experiences:
        experience.deleted_at = utc_now()
    database.commit()
    return {"deleted_id": item.id, "recoverable": True}


def resolve_project(request: ExperienceCreate, user: User, database: Session) -> ExperienceProject:
    if request.project_id:
        return owned_project(request.project_id, user.id, database)
    domain_name = str((request.domain or {}).get("name", "")).strip() or "미분류 경험"
    project_name = str((request.project or {}).get("name", "")).strip() or "프로젝트·활동 미분류"
    domain = database.scalar(select(ExperienceDomain).where(
        ExperienceDomain.user_id == user.id,
        ExperienceDomain.name == domain_name,
        ExperienceDomain.deleted_at.is_(None),
    ))
    if domain is None:
        domain = ExperienceDomain(id=resource_id("DOM"), user_id=user.id, name=domain_name)
        database.add(domain)
        database.flush()
    project = database.scalar(select(ExperienceProject).where(
        ExperienceProject.domain_id == domain.id,
        ExperienceProject.name == project_name,
        ExperienceProject.deleted_at.is_(None),
    ))
    if project is None:
        project = ExperienceProject(
            id=resource_id("PROJ"), user_id=user.id, domain_id=domain.id,
            name=project_name,
            organization=str((request.project or {}).get("organization", "")).strip(),
        )
        database.add(project)
        database.flush()
    project.domain = domain
    return project


@router.get("/experiences")
def list_experiences(
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
):
    items = list(database.scalars(
        select(Experience)
        .options(selectinload(Experience.project).selectinload(ExperienceProject.domain))
        .where(Experience.user_id == current_user.id, Experience.deleted_at.is_(None))
        .order_by(Experience.updated_at.desc())
    ))
    return {"items": [experience_dict(item) for item in items], "total_count": len(items)}


@router.post("/experiences", status_code=201)
def create_experience(
    request: ExperienceCreate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    project = resolve_project(request, current_user, database)
    period = request.period if isinstance(request.period, dict) else {}
    item = Experience(
        id=resource_id("EXP"), user_id=current_user.id, project_id=project.id,
        title=request.title.strip(), summary=request.summary,
        situation=request.situation, actions=request.actions, results=request.results,
        role=request.role, skills=request.skills, facts=request.facts,
        period=period, missing_information=request.missing_information,
        source_ids=request.source_ids, source_refs=request.source_refs,
        status="confirmed",
    )
    item.project = project
    database.add(item)
    database.commit()
    database.refresh(item)
    return experience_dict(owned_experience(item.id, current_user.id, database))


@router.get("/experiences/{experience_id}")
def get_experience(
    experience_id: str,
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
):
    return experience_dict(owned_experience(experience_id, current_user.id, database))


@router.patch("/experiences/{experience_id}")
def update_experience(
    experience_id: str,
    request: ExperienceUpdate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    item = owned_experience(experience_id, current_user.id, database)
    if item.version != request.base_version:
        raise HTTPException(status_code=409, detail="경험이 다른 곳에서 수정되었습니다.")
    allowed = {
        "title", "summary", "situation", "actions", "results", "role", "skills",
        "facts", "period", "missing_information", "source_ids", "source_refs", "status",
    }
    for key, value in request.changes.items():
        if key in allowed:
            setattr(item, key, value)
    item.version += 1
    item.updated_at = utc_now()
    database.commit()
    return experience_dict(owned_experience(item.id, current_user.id, database))


@router.delete("/experiences/{experience_id}")
def delete_experience(
    experience_id: str,
    request: DeleteRequest,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    if not request.confirm:
        raise HTTPException(status_code=422, detail="삭제 확인이 필요합니다.")
    item = owned_experience(experience_id, current_user.id, database)
    if request.version is not None and item.version != request.version:
        raise HTTPException(status_code=409, detail="경험 버전이 변경되었습니다.")
    item.deleted_at = utc_now()
    item.version += 1
    database.commit()
    return {"deleted_id": item.id, "recoverable": True}


@router.post("/experiences/bulk-move")
def bulk_move_experiences(
    request: BulkMoveRequest,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    project = owned_project(request.target_project_id, current_user.id, database)
    items = [
        owned_experience(experience_id, current_user.id, database)
        for experience_id in request.experience_ids
    ]
    for item in items:
        item.project_id = project.id
        item.version += 1
        item.updated_at = utc_now()
    database.commit()
    return {
        "items": [
            experience_dict(owned_experience(item.id, current_user.id, database))
            for item in items
        ],
        "moved_count": len(items),
    }


__all__ = ["router"]
