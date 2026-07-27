"""Experience extraction schemas for Career Memory structured drafts."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field, field_validator, model_validator

from .common import (
    Confidence,
    Identifier,
    SchemaModel,
    SequenceNumber,
    normalize_newlines,
    period_sort_key,
    unique_non_empty,
)
from .evidence import EvidenceCitation, EvidenceSource, FileEvidenceAnalysis


class ExperienceExtractionInputType(str, Enum):
    """Frontend entry point that triggered experience extraction."""

    CONVERSATION = "conversation"
    DIRECT_INPUT = "direct_input"


class ExtractionRunStatus(str, Enum):
    """Processing status for an experience extraction run."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ExperienceDraftStatus(str, Enum):
    """User-review status for an experience draft."""

    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"


class ExperienceClassificationDraft(SchemaModel):
    """Top-level experience category candidate."""

    id: Identifier | None = Field(
        default=None,
        description="Existing category ID when matched",
    )
    name: str = Field(
        default="미분류 경험",
        description="Experience category name. Use 미분류 경험 when uncertain.",
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip() or "미분류 경험"


class ExperiencePeriodDraft(SchemaModel):
    """Optional period for a project/activity."""

    start: str | None = Field(
        default=None,
        pattern=r"^\d{4}(?:-(?:0[1-9]|1[0-2]))?$",
        description="YYYY or YYYY-MM",
    )
    end: str | None = Field(
        default=None,
        pattern=r"^\d{4}(?:-(?:0[1-9]|1[0-2]))?$",
        description="YYYY or YYYY-MM",
    )

    @model_validator(mode="after")
    def validate_period_order(self) -> "ExperiencePeriodDraft":
        if self.start and self.end:
            start_key = period_sort_key(self.start, is_end=False)
            end_key = period_sort_key(self.end, is_end=True)
            if end_key < start_key:
                raise ValueError("기간 종료는 시작보다 빠를 수 없습니다.")
        return self


class ProjectActivityDraft(SchemaModel):
    """Middle-level project/activity candidate."""

    id: Identifier | None = Field(
        default=None,
        description="Existing project/activity ID when matched",
    )
    name: str = Field(
        default="프로젝트·활동 미분류",
        description="Project/activity name. Use 미분류 when uncertain.",
    )
    organization: str | None = Field(
        default=None,
        description="Company, school, organization, or group context",
    )
    period: ExperiencePeriodDraft | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip() or "프로젝트·활동 미분류"

    @field_validator("organization")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class SkillGroupCandidate(SchemaModel):
    """AI-proposed skill group candidate for the profile page."""

    id: Identifier | None = Field(
        default=None,
        description="Existing SkillGroup ID when matched",
    )
    name: str = Field(description="Skill group candidate name")
    skill_names: list[str] = Field(
        default_factory=list,
        description="Skill names grouped under this candidate",
    )
    confidence: Confidence | None = None

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("역량 그룹 이름은 비어 있을 수 없습니다.")
        return normalized

    @field_validator("skill_names")
    @classmethod
    def normalize_skill_names(cls, values: list[str]) -> list[str]:
        return unique_non_empty(values)


class ExperienceDraft(SchemaModel):
    """Structured experience draft returned by the experience extraction AI."""

    draft_id: Identifier = Field(description="Stable draft ID inside one run")
    domain: ExperienceClassificationDraft = Field(description="경험 분류")
    project: ProjectActivityDraft = Field(description="프로젝트·활동")

    title: str = Field(default="", description="상세 경험 제목")
    summary: str = Field(default="", description="Markdown summary")
    situation: str = Field(default="", description="Markdown situation")
    actions: list[str] = Field(
        default_factory=list,
        description="Line-level Markdown actions",
    )
    results: list[str] = Field(
        default_factory=list,
        description="Line-level Markdown results",
    )
    role: str = Field(
        default="",
        description="내 직군·직업 및 역할",
    )
    skills: list[str] = Field(
        default_factory=list,
        description="Raw skill names before normalization",
    )
    skill_groups: list[SkillGroupCandidate] = Field(
        default_factory=list,
        description="Skill group candidates for 내 역량",
    )
    facts: list[str] = Field(
        default_factory=list,
        description="근거에서 확인된 내용",
    )

    missing_information: list[str] = Field(
        default_factory=list,
        description="Information that could not be confirmed from evidence",
    )
    source_ref_ids: list[Identifier] = Field(
        default_factory=list,
        description="Original evidence IDs used by this draft",
    )
    field_citations: dict[str, list[EvidenceCitation]] = Field(
        default_factory=dict,
        description="Field-level citations. Example: summary, actions.0, facts.0",
    )
    confidence: Confidence | None = Field(
        default=None,
        description="Internal AI quality reference; do not present as certainty.",
    )
    status: ExperienceDraftStatus = ExperienceDraftStatus.DRAFT

    @field_validator("title", "summary", "situation", "role")
    @classmethod
    def normalize_markdown_text(cls, value: str) -> str:
        return normalize_newlines(value)

    @field_validator("actions", "results")
    @classmethod
    def normalize_markdown_lines(cls, values: list[str]) -> list[str]:
        return [normalize_newlines(value) for value in values]

    @field_validator(
        "skills",
        "facts",
        "missing_information",
        "source_ref_ids",
    )
    @classmethod
    def normalize_unique_lists(cls, values: list[str]) -> list[str]:
        return unique_non_empty(values)

    @model_validator(mode="after")
    def validate_citation_sources(self) -> "ExperienceDraft":
        known_source_ids = set(self.source_ref_ids)
        cited_source_ids = {
            citation.source_ref_id
            for citations in self.field_citations.values()
            for citation in citations
        }
        unknown_source_ids = cited_source_ids - known_source_ids
        if unknown_source_ids:
            unknown = ", ".join(sorted(unknown_source_ids))
            raise ValueError(
                f"field_citations가 source_ref_ids에 없는 근거를 참조합니다: {unknown}"
            )

        has_experience_content = any(
            (
                self.title.strip(),
                self.summary.strip(),
                self.situation.strip(),
                self.actions,
                self.results,
                self.role.strip(),
                self.skills,
                self.facts,
            )
        )
        if has_experience_content and not self.source_ref_ids:
            raise ValueError(
                "내용이 있는 경험 초안에는 source_ref_ids가 하나 이상 필요합니다."
            )

        missing_fact_citations = [
            f"facts.{index}"
            for index, _fact in enumerate(self.facts)
            if not self.field_citations.get(f"facts.{index}")
        ]
        if missing_fact_citations:
            missing = ", ".join(missing_fact_citations)
            raise ValueError(
                "근거에서 확인된 내용에는 원문 인용이 필요합니다: "
                f"{missing}"
            )
        return self


class ExperienceExtractionRequest(SchemaModel):
    """Request to run the experience extraction AI."""

    client_request_id: Identifier = Field(
        description="Idempotency ID used to prevent duplicate extraction runs",
    )
    input_type: ExperienceExtractionInputType

    conversation_id: Identifier | None = None
    from_sequence: SequenceNumber | None = None
    to_sequence: SequenceNumber | None = None
    message_ids: list[Identifier] = Field(default_factory=list)

    text: str | None = None
    manual_input_id: Identifier | None = None
    attachment_ids: list[Identifier] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def normalize_input_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_newlines(value)
        return normalized if normalized.strip() else None

    @field_validator("message_ids", "attachment_ids")
    @classmethod
    def normalize_identifier_lists(cls, values: list[str]) -> list[str]:
        return unique_non_empty(values)

    @model_validator(mode="after")
    def validate_input_source(self) -> "ExperienceExtractionRequest":
        if self.input_type == ExperienceExtractionInputType.CONVERSATION.value:
            if not self.conversation_id:
                raise ValueError("conversation 입력에는 conversation_id가 필요합니다.")
            if (
                self.from_sequence is not None
                and self.to_sequence is not None
                and self.to_sequence < self.from_sequence
            ):
                raise ValueError("to_sequence는 from_sequence보다 작을 수 없습니다.")
        elif not self.text and not self.attachment_ids:
            raise ValueError(
                "direct_input에는 text 또는 attachment_ids가 하나 이상 필요합니다."
            )
        return self


class ExtractionRun(SchemaModel):
    """Extraction run entity that records scope and AI versions."""

    id: Identifier
    client_request_id: Identifier
    input_type: ExperienceExtractionInputType
    status: ExtractionRunStatus

    conversation_id: Identifier | None = None
    from_sequence: SequenceNumber | None = None
    to_sequence: SequenceNumber | None = None
    message_ids: list[Identifier] = Field(default_factory=list)
    attachment_ids: list[Identifier] = Field(default_factory=list)

    model_version: Identifier
    prompt_version: Identifier
    schema_version: Identifier

    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None

    @field_validator("message_ids", "attachment_ids")
    @classmethod
    def normalize_run_identifier_lists(cls, values: list[str]) -> list[str]:
        return unique_non_empty(values)

    @model_validator(mode="after")
    def validate_run_state(self) -> "ExtractionRun":
        if (
            self.from_sequence is not None
            and self.to_sequence is not None
            and self.to_sequence < self.from_sequence
        ):
            raise ValueError("to_sequence는 from_sequence보다 작을 수 없습니다.")
        if (
            self.started_at is not None
            and self.completed_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValueError("completed_at은 started_at보다 빠를 수 없습니다.")
        return self


class ExperienceExtractionResult(SchemaModel):
    """Complete structured result returned by the experience extraction AI."""

    run: ExtractionRun
    experience_drafts: list[ExperienceDraft] = Field(
        default_factory=list,
        description="Experience drafts found in the input, 0..N",
    )
    sources: list[EvidenceSource] = Field(
        default_factory=list,
        description="Original evidence used by this extraction run",
    )
    file_analyses: list[FileEvidenceAnalysis] = Field(
        default_factory=list,
        description=(
            "Derived per-file summaries used before final experience structuring"
        ),
    )
    analyzed_source_ids: list[Identifier] = Field(
        default_factory=list,
        description="Original source IDs included in the successful analysis scope",
    )

    @field_validator("analyzed_source_ids")
    @classmethod
    def normalize_analyzed_source_ids(cls, values: list[str]) -> list[str]:
        return unique_non_empty(values)

    @model_validator(mode="after")
    def validate_source_registry(self) -> "ExperienceExtractionResult":
        source_ids = [source.id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("sources에 중복 source_ref_id가 있습니다.")

        registered_source_ids = set(source_ids)
        analyzed_file_source_ids = {
            analysis.source_ref_id for analysis in self.file_analyses
        }
        unknown_file_source_ids = (
            analyzed_file_source_ids - registered_source_ids
        )
        if unknown_file_source_ids:
            unknown = ", ".join(sorted(unknown_file_source_ids))
            raise ValueError(
                "file_analyses가 sources에 등록되지 않은 파일을 참조합니다: "
                f"{unknown}"
            )
        referenced_source_ids = {
            source_ref_id
            for draft in self.experience_drafts
            for source_ref_id in draft.source_ref_ids
        }
        unregistered_source_ids = referenced_source_ids - registered_source_ids
        if unregistered_source_ids:
            unknown = ", ".join(sorted(unregistered_source_ids))
            raise ValueError(
                f"초안이 sources에 등록되지 않은 근거를 참조합니다: {unknown}"
            )

        draft_ids = [draft.draft_id for draft in self.experience_drafts]
        if len(draft_ids) != len(set(draft_ids)):
            raise ValueError("experience_drafts에 중복 draft_id가 있습니다.")
        return self


__all__ = [
    "ExperienceClassificationDraft",
    "ExperienceDraft",
    "ExperienceDraftStatus",
    "ExperienceExtractionInputType",
    "ExperienceExtractionRequest",
    "ExperienceExtractionResult",
    "ExperiencePeriodDraft",
    "ExtractionRun",
    "ExtractionRunStatus",
    "ProjectActivityDraft",
    "SkillGroupCandidate",
]
