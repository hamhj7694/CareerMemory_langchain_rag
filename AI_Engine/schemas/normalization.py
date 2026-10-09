"""Lossless normalized representations for skills and quantitative facts."""

from __future__ import annotations

from enum import Enum

from pydantic import Field, field_validator, model_validator

from .common import Confidence, Identifier, SchemaModel, normalize_newlines


class NormalizationStatus(str, Enum):
    """Whether a raw expression could be safely normalized."""

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    REJECTED = "rejected"


class SkillMatchType(str, Enum):
    """Relationship between a raw skill expression and the skill registry."""

    EXACT = "exact"
    ALIAS = "alias"
    RELATED = "related"
    UNRESOLVED = "unresolved"


class SkillMention(SchemaModel):
    """A lossless skill mention plus an optional canonical projection."""

    raw_name: str
    normalized_name: str | None = None
    canonical_skill_id: Identifier | None = None
    match_type: SkillMatchType = SkillMatchType.UNRESOLVED
    normalization_status: NormalizationStatus = NormalizationStatus.UNRESOLVED
    source_ref_id: Identifier | None = None
    quote: str = ""
    confidence: Confidence | None = None
    ontology_version: Identifier | None = None

    @field_validator("raw_name")
    @classmethod
    def require_raw_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("raw_name must not be empty.")
        return normalized

    @field_validator("normalized_name")
    @classmethod
    def normalize_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("quote")
    @classmethod
    def normalize_quote(cls, value: str) -> str:
        return normalize_newlines(value).strip()

    @model_validator(mode="after")
    def validate_resolution(self) -> "SkillMention":
        if self.normalization_status == NormalizationStatus.RESOLVED.value:
            if not self.canonical_skill_id or not self.normalized_name:
                raise ValueError(
                    "Resolved skill mentions require canonical_skill_id and normalized_name."
                )
            if self.match_type == SkillMatchType.UNRESOLVED.value:
                raise ValueError("Resolved skill mentions need a resolved match_type.")
        if self.source_ref_id and not self.quote:
            raise ValueError("A sourced skill mention requires an exact quote.")
        return self


class MetricDirection(str, Enum):
    INCREASE = "increase"
    DECREASE = "decrease"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class MetricOperator(str, Enum):
    EXACT = "exact"
    APPROXIMATE = "approximate"
    RANGE = "range"
    AT_LEAST = "at_least"
    AT_MOST = "at_most"
    UNKNOWN = "unknown"


class QuantifiedMetric(SchemaModel):
    """A raw quantitative expression with optional validated numeric fields."""

    metric_name: str = ""
    raw_expression: str
    value: float | None = Field(default=None, allow_inf_nan=False)
    range_min: float | None = Field(default=None, allow_inf_nan=False)
    range_max: float | None = Field(default=None, allow_inf_nan=False)
    before_value: float | None = Field(default=None, allow_inf_nan=False)
    after_value: float | None = Field(default=None, allow_inf_nan=False)
    unit: str | None = None
    direction: MetricDirection = MetricDirection.UNKNOWN
    operator: MetricOperator = MetricOperator.UNKNOWN
    normalization_status: NormalizationStatus = NormalizationStatus.UNRESOLVED
    source_ref_id: Identifier | None = None
    quote: str = ""
    confidence: Confidence | None = None

    @field_validator("metric_name", "raw_expression", "quote")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return normalize_newlines(value).strip()

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().casefold()
        return normalized or None

    @model_validator(mode="after")
    def validate_metric(self) -> "QuantifiedMetric":
        if not self.raw_expression:
            raise ValueError("raw_expression must not be empty.")
        if self.range_min is not None and self.range_max is not None:
            if self.range_max < self.range_min:
                raise ValueError("range_max must be greater than or equal to range_min.")
        if self.source_ref_id and not self.quote:
            raise ValueError("A sourced metric requires an exact quote.")
        if self.normalization_status == NormalizationStatus.RESOLVED.value:
            has_value = any(
                value is not None
                for value in (
                    self.value,
                    self.range_min,
                    self.range_max,
                    self.before_value,
                    self.after_value,
                )
            )
            if not has_value:
                raise ValueError("Resolved metrics require at least one numeric value.")
        return self


class SkillMatchEvidence(SchemaModel):
    """Deterministic skill relationship attached to a recommendation."""

    requirement_skill_id: Identifier
    experience_skill_id: Identifier
    relationship: SkillMatchType
    requirement_raw_name: str
    experience_raw_name: str
    matching_policy: str = "candidate_only"
    satisfies_requirement: bool = False
    ontology_version: Identifier | None = None


__all__ = [
    "MetricDirection",
    "MetricOperator",
    "NormalizationStatus",
    "QuantifiedMetric",
    "SkillMatchEvidence",
    "SkillMatchType",
    "SkillMention",
]
