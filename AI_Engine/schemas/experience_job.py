"""Backward-compatible imports for the former combined schema module.

New code should import from ``AI_Engine.schemas`` or the focused modules:
``common``, ``evidence``, ``experience``, and ``job``.
"""

from .common import Confidence, Identifier, SchemaModel, SequenceNumber
from .evidence import EvidenceCitation, EvidenceSource, EvidenceSourceType
from .experience import (
    ExperienceClassificationDraft,
    ExperienceDraft,
    ExperienceDraftStatus,
    ExperienceExtractionInputType,
    ExperienceExtractionRequest,
    ExperienceExtractionResult,
    ExperiencePeriodDraft,
    ExtractionRun,
    ExtractionRunStatus,
    ProjectActivityDraft,
    SkillGroupCandidate,
)
from .job import (
    JobAnalysisRequest,
    JobAnalysisResult,
    JobPostingDraft,
    JobRequirement,
    JobRequirementImportance,
    JobRequirementType,
    JobSourceLocator,
    RequirementExperienceLink,
    RequirementExperienceLinkSource,
    RequirementExperienceLinkStatus,
)

__all__ = [
    "Confidence",
    "EvidenceCitation",
    "EvidenceSource",
    "EvidenceSourceType",
    "ExperienceClassificationDraft",
    "ExperienceDraft",
    "ExperienceDraftStatus",
    "ExperienceExtractionInputType",
    "ExperienceExtractionRequest",
    "ExperienceExtractionResult",
    "ExperiencePeriodDraft",
    "ExtractionRun",
    "ExtractionRunStatus",
    "Identifier",
    "JobAnalysisRequest",
    "JobAnalysisResult",
    "JobPostingDraft",
    "JobRequirement",
    "JobRequirementImportance",
    "JobRequirementType",
    "JobSourceLocator",
    "ProjectActivityDraft",
    "RequirementExperienceLink",
    "RequirementExperienceLinkSource",
    "RequirementExperienceLinkStatus",
    "SchemaModel",
    "SequenceNumber",
    "SkillGroupCandidate",
]
