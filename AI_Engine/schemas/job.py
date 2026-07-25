"""Job posting analysis and requirement-to-experience matching schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from .common import (
    Confidence,
    Identifier,
    SchemaModel,
    normalize_http_url,
    normalize_newlines,
    unique_non_empty,
)


class JobRequirementType(str, Enum):
    """Semantic type of a requirement extracted from a job posting."""

    RESPONSIBILITY = "responsibility"
    QUALIFICATION = "qualification"
    COLLABORATION = "collaboration"
    OTHER = "other"


class JobRequirementImportance(str, Enum):
    """Importance explicitly or implicitly expressed in the posting."""

    REQUIRED = "required"
    PREFERRED = "preferred"
    UNKNOWN = "unknown"


class RequirementExperienceLinkSource(str, Enum):
    """Actor that created a requirement-to-experience relationship."""

    AI = "ai"
    USER = "user"


class RequirementExperienceLinkStatus(str, Enum):
    """Review state of a requirement-to-experience relationship."""

    SUGGESTED = "suggested"
    SELECTED = "selected"
    REJECTED = "rejected"


class JobSourceLocator(SchemaModel):
    """Location of an extracted requirement in the original job posting."""

    source: str = Field(
        default="posting_content",
        description="posting_content or an original attachment ID",
    )
    page_number: Annotated[int, Field(ge=1)] | None = None
    line: Annotated[int, Field(ge=1)] | None = None
    start_offset: Annotated[int, Field(ge=0)] | None = None
    end_offset: Annotated[int, Field(ge=0)] | None = None

    @field_validator("source")
    @classmethod
    def require_source(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("source는 비어 있을 수 없습니다.")
        return normalized

    @model_validator(mode="after")
    def validate_offsets(self) -> "JobSourceLocator":
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset < self.start_offset
        ):
            raise ValueError("end_offset은 start_offset보다 작을 수 없습니다.")
        return self


class JobPostingDraft(SchemaModel):
    """Job posting content and metadata supplied by the user."""

    posting_id: Identifier = Field(
        description="Job posting draft ID used within an analysis run",
    )
    company_name: str = ""
    role_name: str = Field(default="", description="채용 직무명")
    posting_title: str = Field(default="", description="채용공고 제목")
    source_url: str | None = None
    posting_content: str = Field(default="", description="채용공고 전체 원문")
    attachment_ids: list[Identifier] = Field(default_factory=list)

    @field_validator(
        "company_name",
        "role_name",
        "posting_title",
        "posting_content",
    )
    @classmethod
    def normalize_job_text(cls, value: str) -> str:
        return normalize_newlines(value).strip()

    @field_validator("source_url")
    @classmethod
    def normalize_source_url(cls, value: str | None) -> str | None:
        return normalize_http_url(value)

    @field_validator("attachment_ids")
    @classmethod
    def normalize_job_attachment_ids(cls, values: list[str]) -> list[str]:
        return unique_non_empty(values)

    @model_validator(mode="after")
    def require_posting_source(self) -> "JobPostingDraft":
        if not self.posting_content and not self.attachment_ids:
            raise ValueError(
                "채용공고 초안에는 posting_content 또는 attachment_ids가 필요합니다."
            )
        return self


class JobRequirement(SchemaModel):
    """One requirement card extracted from the original job posting."""

    id: Identifier = Field(description="Stable requirement ID inside one analysis")
    job_posting_id: Identifier
    type: JobRequirementType = JobRequirementType.OTHER
    title: str = Field(description="요구사항 카드 제목")
    summary: str = Field(description="AI가 원문의 의미를 요약한 설명")
    source_excerpt: str = Field(description="채용공고에서 그대로 인용한 실제 원문")
    source_locator: JobSourceLocator | None = None
    importance: JobRequirementImportance = JobRequirementImportance.UNKNOWN
    keywords: list[str] = Field(
        default_factory=list,
        description="확정 경험 RAG 검색에 사용할 핵심어",
    )
    order: Annotated[int, Field(ge=1)]
    confidence: Confidence | None = Field(
        default=None,
        description="AI 내부 분석 참고값. 확정성 UI로 사용하지 않음",
    )

    @field_validator("title")
    @classmethod
    def require_requirement_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("요구사항 제목은 비어 있을 수 없습니다.")
        return normalized

    @field_validator("summary", "source_excerpt")
    @classmethod
    def require_requirement_text(cls, value: str) -> str:
        normalized = normalize_newlines(value).strip()
        if not normalized:
            raise ValueError("요구사항 요약과 공고 원문은 비어 있을 수 없습니다.")
        return normalized

    @field_validator("keywords")
    @classmethod
    def normalize_requirement_keywords(cls, values: list[str]) -> list[str]:
        return unique_non_empty(values)


class RequirementExperienceLink(SchemaModel):
    """Relationship between a requirement and a confirmed experience."""

    id: Identifier | None = Field(
        default=None,
        description="Persistent relationship ID after saving",
    )
    requirement_id: Identifier
    experience_id: Identifier
    source: RequirementExperienceLinkSource
    status: RequirementExperienceLinkStatus
    similarity_score: Confidence | None = None
    reason: str = Field(
        default="",
        description="Recommendation or manual-link rationale",
    )
    evidence_ids: list[Identifier] = Field(
        default_factory=list,
        description="Evidence IDs supporting the recommendation",
    )
    model_version: Identifier | None = None
    index_version: Identifier | None = None

    @field_validator("reason")
    @classmethod
    def normalize_link_reason(cls, value: str) -> str:
        return normalize_newlines(value).strip()

    @field_validator("evidence_ids")
    @classmethod
    def normalize_link_evidence_ids(cls, values: list[str]) -> list[str]:
        return unique_non_empty(values)

    @model_validator(mode="after")
    def validate_ai_suggestion(self) -> "RequirementExperienceLink":
        if self.source == RequirementExperienceLinkSource.AI.value:
            if self.similarity_score is None:
                raise ValueError("AI 추천 연결에는 similarity_score가 필요합니다.")
            if not self.reason:
                raise ValueError("AI 추천 연결에는 reason이 필요합니다.")
            if not self.model_version:
                raise ValueError("AI 추천 연결에는 model_version이 필요합니다.")
            if not self.index_version:
                raise ValueError("AI 추천 연결에는 index_version이 필요합니다.")
            if not self.evidence_ids:
                raise ValueError("AI 추천 연결에는 evidence_ids가 필요합니다.")
        return self


class JobAnalysisRequest(SchemaModel):
    """Request contract for job posting analysis and experience matching."""

    client_request_id: Identifier = Field(
        description="Idempotency ID used to prevent duplicate analyses",
    )
    posting_id: Identifier
    company_name: str = ""
    role_name: str = ""
    posting_title: str = ""
    source_url: str | None = None
    posting_content: str = ""
    attachment_ids: list[Identifier] = Field(default_factory=list)

    @field_validator(
        "company_name",
        "role_name",
        "posting_title",
        "posting_content",
    )
    @classmethod
    def normalize_job_request_text(cls, value: str) -> str:
        return normalize_newlines(value).strip()

    @field_validator("source_url")
    @classmethod
    def normalize_job_request_url(cls, value: str | None) -> str | None:
        return normalize_http_url(value)

    @field_validator("attachment_ids")
    @classmethod
    def normalize_request_attachment_ids(cls, values: list[str]) -> list[str]:
        return unique_non_empty(values)

    @model_validator(mode="after")
    def require_job_input(self) -> "JobAnalysisRequest":
        if not self.posting_content and not self.attachment_ids:
            raise ValueError(
                "공고 분석 요청에는 posting_content 또는 attachment_ids가 필요합니다."
            )
        return self

    def to_posting_draft(self) -> JobPostingDraft:
        """Convert a validated request into the shared posting draft contract."""

        return JobPostingDraft(
            posting_id=self.posting_id,
            company_name=self.company_name,
            role_name=self.role_name,
            posting_title=self.posting_title,
            source_url=self.source_url,
            posting_content=self.posting_content,
            attachment_ids=self.attachment_ids,
        )


class JobAnalysisResult(SchemaModel):
    """Structured requirements and RAG-generated experience recommendations."""

    analysis_id: Identifier
    client_request_id: Identifier
    job_posting: JobPostingDraft
    requirements: list[JobRequirement] = Field(default_factory=list)
    experience_links: list[RequirementExperienceLink] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    analyzed_at: datetime
    model_version: Identifier
    prompt_version: Identifier
    schema_version: Identifier
    index_version: Identifier

    @field_validator("warnings")
    @classmethod
    def normalize_job_warnings(cls, values: list[str]) -> list[str]:
        return unique_non_empty(values)

    @model_validator(mode="after")
    def validate_job_analysis_relations(self) -> "JobAnalysisResult":
        requirement_ids = [requirement.id for requirement in self.requirements]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("requirements에 중복 요구사항 ID가 있습니다.")

        requirement_orders = [requirement.order for requirement in self.requirements]
        if len(requirement_orders) != len(set(requirement_orders)):
            raise ValueError("requirements에 중복 order가 있습니다.")

        invalid_posting_requirements = [
            requirement.id
            for requirement in self.requirements
            if requirement.job_posting_id != self.job_posting.posting_id
        ]
        if invalid_posting_requirements:
            invalid = ", ".join(invalid_posting_requirements)
            raise ValueError(
                "다른 job_posting_id를 참조하는 요구사항이 있습니다: "
                f"{invalid}"
            )

        for requirement in self.requirements:
            locator = requirement.source_locator
            source_name = locator.source if locator else "posting_content"
            if source_name == "posting_content":
                posting_content = self.job_posting.posting_content
                if not posting_content:
                    raise ValueError(
                        f"{requirement.id}의 공고 원문을 검증할 수 없습니다."
                    )
                if requirement.source_excerpt not in posting_content:
                    raise ValueError(
                        f"{requirement.id}의 source_excerpt가 공고 원문에 없습니다."
                    )
                if (
                    locator
                    and locator.start_offset is not None
                    and locator.end_offset is not None
                ):
                    located_excerpt = posting_content[
                        locator.start_offset : locator.end_offset
                    ]
                    if located_excerpt != requirement.source_excerpt:
                        raise ValueError(
                            f"{requirement.id}의 source_locator와 "
                            "source_excerpt가 일치하지 않습니다."
                        )
            elif source_name not in self.job_posting.attachment_ids:
                raise ValueError(
                    f"{requirement.id}가 등록되지 않은 공고 첨부를 참조합니다: "
                    f"{source_name}"
                )

        registered_requirement_ids = set(requirement_ids)
        unknown_link_requirement_ids = {
            link.requirement_id
            for link in self.experience_links
            if link.requirement_id not in registered_requirement_ids
        }
        if unknown_link_requirement_ids:
            unknown = ", ".join(sorted(unknown_link_requirement_ids))
            raise ValueError(
                "experience_links가 등록되지 않은 요구사항을 참조합니다: "
                f"{unknown}"
            )

        relation_keys = [
            (link.requirement_id, link.experience_id)
            for link in self.experience_links
        ]
        if len(relation_keys) != len(set(relation_keys)):
            raise ValueError("동일한 요구사항과 경험의 연결이 중복되어 있습니다.")
        return self


__all__ = [
    "JobAnalysisRequest",
    "JobAnalysisResult",
    "JobPostingDraft",
    "JobRequirement",
    "JobRequirementImportance",
    "JobRequirementType",
    "JobSourceLocator",
    "RequirementExperienceLink",
    "RequirementExperienceLinkSource",
    "RequirementExperienceLinkStatus",
]
