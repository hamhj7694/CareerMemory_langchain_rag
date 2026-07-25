"""Career Memory AI 엔진의 공개 Pydantic 데이터 계약.

외부 코드는 개별 파일 위치에 의존하지 않고 다음처럼 가져온다.

    from AI_Engine.schemas import ExperienceDraft, ChatRequest
"""

from .chat import (
    AttachmentReference,
    ChatCitation,
    ChatMessage,
    ChatMode,
    ChatRequest,
    ChatResponse,
    ChatRole,
    ChatStreamEvent,
    ChatStreamEventType,
    SuggestedAction,
    SuggestedActionType,
)
from .common import AIError, Confidence, Identifier, SchemaModel, SequenceNumber
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
from .routing import (
    AIRequestType,
    AIRoute,
    AIRouteDecision,
    AIRouteRequest,
    RouteDecisionSource,
)
from .retrieval import ExperienceSearchDocument

__all__ = [
    "AIError",
    "AIRequestType",
    "AIRoute",
    "AIRouteDecision",
    "AIRouteRequest",
    "AttachmentReference",
    "ChatCitation",
    "ChatMessage",
    "ChatMode",
    "ChatRequest",
    "ChatResponse",
    "ChatRole",
    "ChatStreamEvent",
    "ChatStreamEventType",
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
    "ExperienceSearchDocument",
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
    "RouteDecisionSource",
    "SchemaModel",
    "SequenceNumber",
    "SkillGroupCandidate",
    "SuggestedAction",
    "SuggestedActionType",
]
