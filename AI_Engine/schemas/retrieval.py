"""확정 경험 RAG 검색 문서의 데이터 계약."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import (
    AliasChoices,
    Field,
    field_validator,
    model_validator,
)

from .common import (
    Identifier,
    SchemaModel,
    normalize_newlines,
    unique_non_empty,
)


class ExperienceSearchDocument(SchemaModel):
    """채용공고와 유사한 확정 경험을 찾기 위한 검색 전용 문서."""

    experience_id: Identifier = Field(
        validation_alias=AliasChoices("experience_id", "id"),
    )
    status: Literal["confirmed"] = "confirmed"
    domain_name: str = Field(
        default="",
        validation_alias=AliasChoices("domain_name", "domainName"),
    )
    project_name: str = Field(
        default="",
        validation_alias=AliasChoices("project_name", "projectName"),
    )
    title: str = ""
    summary: str = ""
    situation: str = ""
    actions: list[str] = Field(default_factory=list)
    results: list[str] = Field(default_factory=list)
    role: str = ""
    skills: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    evidence_ids: list[Identifier] = Field(
        min_length=1,
        validation_alias=AliasChoices(
            "evidence_ids",
            "evidenceIds",
            "source_ids",
        ),
        description="추천 근거를 추적할 수 있는 원본 근거 ID",
    )
    updated_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("updated_at", "updatedAt"),
    )

    @model_validator(mode="before")
    @classmethod
    def read_nested_classification(
        cls,
        value: Any,
    ) -> Any:
        """프론트엔드의 domain/project 중첩 형식도 같은 계약으로 읽는다."""

        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        domain = normalized.get("domain")
        project = normalized.get("project")
        if (
            "domain_name" not in normalized
            and "domainName" not in normalized
            and isinstance(domain, dict)
        ):
            normalized["domain_name"] = domain.get("name", "")
        if (
            "project_name" not in normalized
            and "projectName" not in normalized
            and isinstance(project, dict)
        ):
            normalized["project_name"] = project.get("name", "")
        normalized.pop("domain", None)
        normalized.pop("project", None)
        return normalized

    @field_validator(
        "domain_name",
        "project_name",
        "title",
        "summary",
        "situation",
        "role",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return normalize_newlines(value).strip()

    @field_validator("actions", "results")
    @classmethod
    def normalize_markdown_lines(
        cls,
        values: list[str],
    ) -> list[str]:
        return [
            normalize_newlines(value).strip()
            for value in values
            if normalize_newlines(value).strip()
        ]

    @field_validator("skills", "facts", "evidence_ids")
    @classmethod
    def normalize_unique_values(
        cls,
        values: list[str],
    ) -> list[str]:
        return unique_non_empty(values)

    @model_validator(mode="after")
    def require_searchable_content(self) -> "ExperienceSearchDocument":
        if not self.evidence_ids:
            raise ValueError(
                "확정 경험 검색 문서에는 evidence_ids가 하나 이상 필요합니다."
            )
        if not any(
            (
                self.title,
                self.summary,
                self.situation,
                self.actions,
                self.results,
                self.role,
                self.skills,
                self.facts,
            )
        ):
            raise ValueError(
                "확정 경험 검색 문서에는 검색 가능한 내용이 필요합니다."
            )
        return self

    def to_search_text(self) -> str:
        """확정 경험의 의미 필드를 검색 가능한 하나의 텍스트로 합친다."""

        sections = [
            ("경험 분류", self.domain_name),
            ("프로젝트·활동", self.project_name),
            ("제목", self.title),
            ("요약", self.summary),
            ("상황", self.situation),
            ("행동", "\n".join(self.actions)),
            ("결과", "\n".join(self.results)),
            ("내 직군·직업 및 역할", self.role),
            ("역량", ", ".join(self.skills)),
            ("근거에서 확인된 내용", "\n".join(self.facts)),
        ]
        return "\n\n".join(
            f"[{label}]\n{text}"
            for label, text in sections
            if text
        )

    def content_hash(self) -> str:
        """내용이 바뀌었는지 판정할 SHA-256 해시를 반환한다."""

        return hashlib.sha256(
            self.to_search_text().encode("utf-8")
        ).hexdigest()

    def to_chroma_metadata(self) -> dict[str, str]:
        """Chroma가 저장할 수 있는 단순 값 형태로 메타데이터를 변환한다."""

        return {
            "experience_id": self.experience_id,
            "status": self.status,
            "title": self.title,
            "domain_name": self.domain_name,
            "project_name": self.project_name,
            "evidence_ids_json": json.dumps(
                self.evidence_ids,
                ensure_ascii=False,
            ),
            "content_hash": self.content_hash(),
            "updated_at": (
                self.updated_at.isoformat()
                if self.updated_at is not None
                else ""
            ),
        }


__all__ = ["ExperienceSearchDocument"]
