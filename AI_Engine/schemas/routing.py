"""자동 모드의 의도 판정과 체인 선택 데이터 계약."""

from __future__ import annotations

from enum import Enum

from pydantic import Field, field_validator, model_validator

from .common import Confidence, Identifier, SchemaModel


class AIRequestType(str, Enum):
    """프론트엔드/API가 요청하는 AI 작업 종류."""

    AUTO = "auto"
    CHAT = "chat"
    EXPERIENCE_EXTRACTION = "experience_extraction"
    JOB_ANALYSIS = "job_analysis"


class AIRoute(str, Enum):
    """라우터가 실제로 실행할 체인."""

    CHAT = "chat"
    EXPERIENCE_EXTRACTION = "experience_extraction"
    JOB_ANALYSIS = "job_analysis"


class RouteDecisionSource(str, Enum):
    """체인 선택 근거."""

    EXPLICIT = "explicit"
    AUTOMATIC = "automatic"
    FALLBACK = "fallback"


class AIRouteRequest(SchemaModel):
    """라우터가 체인을 선택할 때 사용하는 최소 입력."""

    request_id: Identifier
    request_type: AIRequestType
    conversation_id: Identifier | None = None
    text: str = ""
    attachment_ids: list[Identifier] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.replace("\r\n", "\n").replace("\r", "\n")

    @field_validator("attachment_ids")
    @classmethod
    def normalize_attachment_ids(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class AIRouteDecision(SchemaModel):
    """라우터의 재현 가능한 체인 선택 결과."""

    request_id: Identifier
    requested_type: AIRequestType
    route: AIRoute
    source: RouteDecisionSource
    confidence: Confidence
    reason: str
    classifier_version: Identifier | None = None

    @field_validator("reason")
    @classmethod
    def require_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("라우팅 이유는 비어 있을 수 없습니다.")
        return normalized

    @model_validator(mode="after")
    def validate_decision_source(self) -> "AIRouteDecision":
        if self.requested_type != AIRequestType.AUTO.value:
            if self.source != RouteDecisionSource.EXPLICIT.value:
                raise ValueError("명시적 요청은 explicit 라우팅이어야 합니다.")
            if self.route != self.requested_type:
                raise ValueError("명시적 요청은 같은 이름의 체인으로 전달해야 합니다.")
        elif self.source == RouteDecisionSource.EXPLICIT.value:
            raise ValueError("auto 요청은 explicit 라우팅일 수 없습니다.")

        if (
            self.source == RouteDecisionSource.AUTOMATIC.value
            and not self.classifier_version
        ):
            raise ValueError("자동 라우팅에는 classifier_version이 필요합니다.")
        return self


__all__ = [
    "AIRequestType",
    "AIRoute",
    "AIRouteDecision",
    "AIRouteRequest",
    "RouteDecisionSource",
]
