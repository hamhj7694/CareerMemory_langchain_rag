"""사용자 입력과 원본 근거를 0개 이상의 경험 초안으로 정리하는 AI."""

from __future__ import annotations

# 1. Python 기본 기능
# 함수 호출 인자(JSON), 시간, 고유 ID, 타입 표기를 위해 사용한다.
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

# 2. OpenAI Responses API
# 수업 레퍼런스의 strict function calling 방식으로 구조화 결과를 받는다.
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import ValidationError

# 3. 프론트엔드·백엔드·AI가 함께 사용하는 데이터 계약
# AI 출력은 아래 Pydantic 스키마를 통과해야만 경험 초안으로 반환한다.
from AI_Engine.schemas import (
    EvidenceCitation,
    EvidenceSource,
    EvidenceSourceType,
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

# 3. .env에서 키 불러오기
load_dotenv()

# 5. 모델·프롬프트·스키마 버전
# 저장된 초안이 어떤 구성으로 생성됐는지 추적할 수 있도록 실행 결과에 기록한다.
DEFAULT_EXPERIENCE_MODEL = "gpt-4o-mini"
EXPERIENCE_PROMPT_VERSION = "experience-prompt-v1"
EXPERIENCE_SCHEMA_VERSION = "experience-schema-v1"

# 6. 모델이 호출해야 하는 함수 이름
# 일반 텍스트 응답과 구조화된 경험 초안 출력을 구분하는 식별자다.
EXPERIENCE_DRAFT_TOOL_NAME = "create_experience_drafts"

# 7. 경험정리 AI 시스템 프롬프트
# 레퍼런스에서 사용한 역할·목표·문맥·제약조건·형식 구조를 그대로 따른다.
EXPERIENCE_SYSTEM_PROMPT = """
[역할 role]
너는 Career Memory의 경험정리 AI야.
사용자가 제공한 대화, 직접 입력한 텍스트, 파일에서 확인되는 내용만 근거로
경험을 분류하고 구조화해.

[목표 task]
입력 근거에서 서로 구분되는 경험을 0개 이상 찾아 아래 계층으로 정리해.

경험 분류
└─ 프로젝트·활동
   └─ 상세 경험

한 입력에 여러 경험이 있으면 여러 초안으로 분리하고,
같은 경험 분류와 프로젝트·활동에 속하면 같은 이름을 일관되게 사용해.

[문맥 context]
실제 분석 대상은 사용자 입력에 [분석할 원본 근거]로 전달돼.
각 근거에는 source_ref_id가 있으며, 이 ID로 사용한 원본을 추적해야 해.

[제약조건 constraint]
- 원본 근거에 없는 사실은 추측하거나 만들어내지 마.
- 경험으로 판단할 내용이 없으면 experience_drafts를 빈 배열로 반환해.
- 불확실한 경험 분류는 "미분류 경험"으로 작성해.
- 불확실한 프로젝트·활동은 "프로젝트·활동 미분류"로 작성해.
- 모르는 상세 항목은 빈 문자열 또는 빈 배열로 두고 missing_information에 기록해.
- 요약, 상황, 행동, 결과는 원문의 의미를 바꾸지 말고 한국어로 정리해.
- 상황, 행동, 결과는 Markdown 목록으로 사용할 수 있는 문장 단위로 정리해.
- 역량은 짧고 재사용 가능한 능력 이름으로 분리해.
- 근거에서 확인된 내용은 정확한 원문 인용과 source_ref_id가 있을 때만 작성해.
- source_ref_ids에는 해당 초안 작성에 실제 사용한 근거 ID만 넣어.
- 입력에 제공되지 않은 source_ref_id를 절대 만들지 마.
- 개인정보나 민감정보를 새로 추론하지 마.

[형식 format]
- 반드시 create_experience_drafts 함수를 한 번 호출해.
- 함수의 experience_drafts 배열에 0개 이상의 경험 초안을 넣어.
- 경험 하나마다 경험 분류, 프로젝트·활동, 제목, 요약, 상황, 행동, 결과,
  내 직군·직업 및 역할, 역량, 역량 그룹, 근거에서 확인된 내용,
  추가 확인 필요 정보, 사용한 원본 근거 ID를 반환해.
""".strip()


# 8. strict function calling용 JSON Schema
# 모델이 임의의 키를 만들지 못하게 모든 객체에 additionalProperties=False를 적용한다.
EXPERIENCE_DRAFT_TOOL: dict[str, Any] = {
    "type": "function",
    "name": EXPERIENCE_DRAFT_TOOL_NAME,
    "description": (
        "원본 근거에서 확인되는 경험을 "
        "경험 분류 → 프로젝트·활동 → 상세 경험 구조의 초안으로 반환합니다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "experience_drafts": {
                "type": "array",
                "description": "입력에서 확인한 경험 초안 0개 이상",
                "items": {
                    "type": "object",
                    "properties": {
                        "domain_name": {
                            "type": "string",
                            "description": "최상단 경험 분류",
                        },
                        "project_name": {
                            "type": "string",
                            "description": "중간 프로젝트·활동",
                        },
                        "organization": {
                            "type": ["string", "null"],
                            "description": "회사, 학교, 기관 또는 단체",
                        },
                        "period": {
                            "anyOf": [
                                {
                                    "type": "object",
                                    "properties": {
                                        "start": {
                                            "type": ["string", "null"],
                                            "description": "YYYY 또는 YYYY-MM",
                                        },
                                        "end": {
                                            "type": ["string", "null"],
                                            "description": "YYYY 또는 YYYY-MM",
                                        },
                                    },
                                    "required": ["start", "end"],
                                    "additionalProperties": False,
                                },
                                {"type": "null"},
                            ]
                        },
                        "title": {
                            "type": "string",
                            "description": "상세 경험 카드 제목",
                        },
                        "summary": {
                            "type": "string",
                            "description": "경험 전체를 한눈에 보여주는 요약",
                        },
                        "situation": {
                            "type": "string",
                            "description": "경험의 배경과 문제 상황",
                        },
                        "actions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "사용자가 수행한 행동",
                        },
                        "results": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "행동으로 만들어진 결과",
                        },
                        "role": {
                            "type": "string",
                            "description": "내 직군·직업 및 역할",
                        },
                        "skills": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "경험에서 확인된 역량",
                        },
                        "skill_groups": {
                            "type": "array",
                            "description": "내 역량 페이지용 유사 역량 그룹 후보",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "skill_names": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "confidence": {
                                        "type": ["number", "null"],
                                        "minimum": 0,
                                        "maximum": 1,
                                    },
                                },
                                "required": [
                                    "name",
                                    "skill_names",
                                    "confidence",
                                ],
                                "additionalProperties": False,
                            },
                        },
                        "facts": {
                            "type": "array",
                            "description": "근거에서 확인된 내용과 정확한 출처",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "text": {
                                        "type": "string",
                                        "description": "근거에서 확인된 내용",
                                    },
                                    "source_ref_id": {
                                        "type": "string",
                                        "description": "근거의 source_ref_id",
                                    },
                                    "quote": {
                                        "type": "string",
                                        "description": "내용을 뒷받침하는 짧은 원문",
                                    },
                                },
                                "required": [
                                    "text",
                                    "source_ref_id",
                                    "quote",
                                ],
                                "additionalProperties": False,
                            },
                        },
                        "missing_information": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "추가로 확인해야 하는 정보",
                        },
                        "source_ref_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "초안 작성에 사용한 원본 근거 ID",
                        },
                        "confidence": {
                            "type": ["number", "null"],
                            "minimum": 0,
                            "maximum": 1,
                            "description": "초안 구조화 신뢰도",
                        },
                    },
                    "required": [
                        "domain_name",
                        "project_name",
                        "organization",
                        "period",
                        "title",
                        "summary",
                        "situation",
                        "actions",
                        "results",
                        "role",
                        "skills",
                        "skill_groups",
                        "facts",
                        "missing_information",
                        "source_ref_ids",
                        "confidence",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["experience_drafts"],
        "additionalProperties": False,
    },
    "strict": True,
}


# 9. 경험정리 AI 전용 오류
# 입력 문제와 모델 출력 문제를 분리해 API 계층에서 서로 다른 안내를 만들 수 있게 한다.
class ExperienceAIError(RuntimeError):
    """경험정리 AI의 공통 오류."""


class ExperienceAIInputError(ExperienceAIError):
    """분석할 원본 근거가 없거나 요청 범위가 잘못된 경우."""


class ExperienceAIOutputError(ExperienceAIError):
    """모델의 함수 호출 결과가 약속한 스키마와 다른 경우."""


# 10. 경험정리 AI 실행 클래스
# 요청과 원본 근거를 입력받아 OpenAI 함수 호출 결과를 Pydantic 초안으로 변환한다.
class ExperienceAI:
    """원본 근거에서 검증 가능한 경험 초안을 0개 이상 생성한다."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        model_version: str = DEFAULT_EXPERIENCE_MODEL,
        prompt_version: str = EXPERIENCE_PROMPT_VERSION,
        schema_version: str = EXPERIENCE_SCHEMA_VERSION,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        # 실제 서비스에서는 기본 OpenAI 클라이언트를 사용하고,
        # 테스트에서는 같은 responses.create 모양의 가짜 클라이언트를 주입한다.
        self.client = client or OpenAI()
        self.model_version = _require_text(model_version, "model_version")
        self.prompt_version = _require_text(prompt_version, "prompt_version")
        self.schema_version = _require_text(schema_version, "schema_version")
        self.id_factory = id_factory or (lambda: str(uuid4()))
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    # 10-1. 경험 초안 생성
    # 호출 한 번의 입력 범위, 결과, 근거, 버전을 하나의 ExtractionResult로 묶는다.
    def organize(
        self,
        request: ExperienceExtractionRequest,
        *,
        sources: Sequence[EvidenceSource] = (),
    ) -> ExperienceExtractionResult:
        started_at = self.clock()
        run_id = self._new_id("extraction-run")
        registered_sources = self._prepare_sources(request, sources)
        analyzed_sources = [
            source
            for source in registered_sources
            if source.text is not None and source.text.strip()
        ]

        if not analyzed_sources:
            raise ExperienceAIInputError(
                "분석 가능한 원본 텍스트가 없습니다. "
                "파일은 본문을 추출한 뒤 EvidenceSource.text로 전달해 주세요."
            )

        response = self.client.responses.create(
            model=self.model_version,
            input=self._build_model_input(request, analyzed_sources),
            tools=[EXPERIENCE_DRAFT_TOOL],
            tool_choice="auto",
            instructions=EXPERIENCE_SYSTEM_PROMPT,
        )

        raw_drafts = self._function_arguments(response)
        drafts = [
            self._to_experience_draft(raw_draft)
            for raw_draft in raw_drafts
        ]
        completed_at = self.clock()

        try:
            return ExperienceExtractionResult(
                run=ExtractionRun(
                    id=run_id,
                    client_request_id=request.client_request_id,
                    input_type=request.input_type,
                    status=ExtractionRunStatus.SUCCEEDED,
                    conversation_id=request.conversation_id,
                    from_sequence=request.from_sequence,
                    to_sequence=request.to_sequence,
                    message_ids=request.message_ids,
                    attachment_ids=request.attachment_ids,
                    model_version=self.model_version,
                    prompt_version=self.prompt_version,
                    schema_version=self.schema_version,
                    started_at=started_at,
                    completed_at=completed_at,
                ),
                experience_drafts=drafts,
                sources=registered_sources,
                analyzed_source_ids=[
                    source.id for source in analyzed_sources
                ],
            )
        except ValidationError as error:
            raise ExperienceAIOutputError(
                "경험 초안이 공통 데이터 스키마 검증을 통과하지 못했습니다."
            ) from error

    # 10-2. 요청 원본 근거 준비
    # 직접 입력 텍스트는 EvidenceSource로 바꾸고, 첨부·대화 근거 ID도 누락 없이 확인한다.
    def _prepare_sources(
        self,
        request: ExperienceExtractionRequest,
        sources: Sequence[EvidenceSource],
    ) -> list[EvidenceSource]:
        registered_sources = list(sources)
        source_ids = [source.id for source in registered_sources]
        if len(source_ids) != len(set(source_ids)):
            raise ExperienceAIInputError(
                "동일한 source_ref_id를 가진 원본 근거가 중복되었습니다."
            )

        if request.text:
            manual_input_id = (
                request.manual_input_id or request.client_request_id
            )
            has_manual_source = any(
                source.manual_input_id == manual_input_id
                for source in registered_sources
            )
            if not has_manual_source:
                registered_sources.insert(
                    0,
                    EvidenceSource(
                        id=f"source-{manual_input_id}",
                        type=EvidenceSourceType.MANUAL_TEXT,
                        title="사용자 직접 입력",
                        manual_input_id=manual_input_id,
                        text=request.text,
                    ),
                )

        prepared_source_ids = [
            source.id for source in registered_sources
        ]
        if len(prepared_source_ids) != len(set(prepared_source_ids)):
            raise ExperienceAIInputError(
                "직접 입력을 원본 근거로 변환한 뒤 source_ref_id가 "
                "기존 근거와 중복되었습니다."
            )

        attachment_source_ids = {
            source.attachment_id
            for source in registered_sources
            if source.attachment_id
        }
        missing_attachment_ids = (
            set(request.attachment_ids) - attachment_source_ids
        )
        if missing_attachment_ids:
            missing = ", ".join(sorted(missing_attachment_ids))
            raise ExperienceAIInputError(
                f"첨부 파일의 원본 근거가 전달되지 않았습니다: {missing}"
            )

        message_source_ids = {
            source.message_id
            for source in registered_sources
            if source.message_id
        }
        missing_message_ids = set(request.message_ids) - message_source_ids
        if missing_message_ids:
            missing = ", ".join(sorted(missing_message_ids))
            raise ExperienceAIInputError(
                f"대화 메시지의 원본 근거가 전달되지 않았습니다: {missing}"
            )

        return registered_sources

    # 10-3. 모델 입력 문맥 만들기
    # 원본별 ID와 유형을 명확히 표시해 모델이 인용 ID를 혼동하지 않게 한다.
    @staticmethod
    def _build_model_input(
        request: ExperienceExtractionRequest,
        sources: Sequence[EvidenceSource],
    ) -> str:
        request_scope = {
            "client_request_id": request.client_request_id,
            "input_type": request.input_type,
            "conversation_id": request.conversation_id,
            "from_sequence": request.from_sequence,
            "to_sequence": request.to_sequence,
        }
        source_sections: list[str] = []
        for source in sources:
            source_sections.append(
                "\n".join(
                    (
                        "--- 원본 근거 시작 ---",
                        f"source_ref_id: {source.id}",
                        f"source_type: {source.type}",
                        f"title: {source.title or '제목 없음'}",
                        "original_text:",
                        source.text or "",
                        "--- 원본 근거 끝 ---",
                    )
                )
            )

        return (
            "[요청 범위]\n"
            f"{json.dumps(request_scope, ensure_ascii=False)}\n\n"
            "[분석할 원본 근거]\n"
            + "\n\n".join(source_sections)
        )

    # 10-4. 함수 호출 인자 읽기
    # 모델이 정해진 함수를 정확히 한 번 호출했는지 확인한 뒤 JSON을 해석한다.
    @staticmethod
    def _function_arguments(response: Any) -> list[Mapping[str, Any]]:
        output = getattr(response, "output", None)
        if not isinstance(output, Sequence) or isinstance(
            output, (str, bytes)
        ):
            raise ExperienceAIOutputError(
                "모델 응답에 function_call 출력이 없습니다."
            )

        function_calls = [
            item
            for item in output
            if _item_value(item, "type") == "function_call"
            and _item_value(item, "name") == EXPERIENCE_DRAFT_TOOL_NAME
        ]
        if len(function_calls) != 1:
            raise ExperienceAIOutputError(
                "모델은 create_experience_drafts 함수를 정확히 한 번 호출해야 합니다."
            )

        arguments = _item_value(function_calls[0], "arguments")
        if not isinstance(arguments, str):
            raise ExperienceAIOutputError(
                "함수 호출 arguments가 JSON 문자열이 아닙니다."
            )

        try:
            payload = json.loads(arguments)
        except json.JSONDecodeError as error:
            raise ExperienceAIOutputError(
                "함수 호출 arguments를 JSON으로 해석할 수 없습니다."
            ) from error

        if not isinstance(payload, Mapping):
            raise ExperienceAIOutputError(
                "함수 호출 결과의 최상위 값은 객체여야 합니다."
            )
        raw_drafts = payload.get("experience_drafts")
        if not isinstance(raw_drafts, list):
            raise ExperienceAIOutputError(
                "experience_drafts는 배열이어야 합니다."
            )
        if not all(isinstance(item, Mapping) for item in raw_drafts):
            raise ExperienceAIOutputError(
                "experience_drafts의 각 항목은 객체여야 합니다."
            )
        return raw_drafts

    # 10-5. 함수 호출 결과를 공통 ExperienceDraft로 변환
    # 근거에서 확인된 내용은 facts.N 위치별 EvidenceCitation과 함께 저장한다.
    def _to_experience_draft(
        self,
        raw_draft: Mapping[str, Any],
    ) -> ExperienceDraft:
        raw_facts = raw_draft.get("facts", [])
        if not isinstance(raw_facts, list):
            raise ExperienceAIOutputError("facts는 배열이어야 합니다.")

        fact_texts: list[str] = []
        field_citations: dict[str, list[EvidenceCitation]] = {}
        for index, raw_fact in enumerate(raw_facts):
            if not isinstance(raw_fact, Mapping):
                raise ExperienceAIOutputError(
                    "facts의 각 항목은 객체여야 합니다."
                )
            fact_text = raw_fact.get("text")
            source_ref_id = raw_fact.get("source_ref_id")
            quote = raw_fact.get("quote")
            if not all(
                isinstance(value, str)
                for value in (fact_text, source_ref_id, quote)
            ):
                raise ExperienceAIOutputError(
                    "근거에서 확인된 내용에는 text, source_ref_id, quote가 필요합니다."
                )
            fact_texts.append(fact_text)
            field_citations[f"facts.{index}"] = [
                EvidenceCitation(
                    source_ref_id=source_ref_id,
                    quote=quote,
                )
            ]

        try:
            raw_period = raw_draft.get("period")
            period = (
                ExperiencePeriodDraft.model_validate(raw_period)
                if raw_period is not None
                else None
            )
            return ExperienceDraft(
                draft_id=self._new_id("experience-draft"),
                domain=ExperienceClassificationDraft(
                    name=raw_draft.get("domain_name", "")
                ),
                project=ProjectActivityDraft(
                    name=raw_draft.get("project_name", ""),
                    organization=raw_draft.get("organization"),
                    period=period,
                ),
                title=raw_draft.get("title", ""),
                summary=raw_draft.get("summary", ""),
                situation=raw_draft.get("situation", ""),
                actions=raw_draft.get("actions", []),
                results=raw_draft.get("results", []),
                role=raw_draft.get("role", ""),
                skills=raw_draft.get("skills", []),
                skill_groups=[
                    SkillGroupCandidate.model_validate(group)
                    for group in raw_draft.get("skill_groups", [])
                ],
                facts=fact_texts,
                missing_information=raw_draft.get(
                    "missing_information", []
                ),
                source_ref_ids=raw_draft.get("source_ref_ids", []),
                field_citations=field_citations,
                confidence=raw_draft.get("confidence"),
                status=ExperienceDraftStatus.DRAFT,
            )
        except (TypeError, ValidationError, ValueError) as error:
            raise ExperienceAIOutputError(
                "모델이 반환한 경험 초안의 필드 형식이 올바르지 않습니다."
            ) from error

    # 10-6. 실행·초안 고유 ID 생성
    # 저장 전 초안도 서로 구분할 수 있도록 용도별 prefix를 붙인다.
    def _new_id(self, prefix: str) -> str:
        value = self.id_factory().strip()
        if not value:
            raise ExperienceAIOutputError(
                "id_factory가 빈 ID를 반환했습니다."
            )
        return f"{prefix}-{value}"


# 11. 기본 ExperienceAI 생성 함수
# 외부 조립 파일 AI_langchain.py에서 같은 방식으로 인스턴스를 만들 수 있게 한다.
def create_experience_ai(
    *,
    client: Any | None = None,
    model_version: str = DEFAULT_EXPERIENCE_MODEL,
) -> ExperienceAI:
    return ExperienceAI(
        client=client,
        model_version=model_version,
    )


# 12. 함수 호출 항목 읽기 보조 함수
# 실제 OpenAI 객체와 테스트용 dict/가짜 객체를 같은 방식으로 처리한다.
def _item_value(item: Any, name: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(name)
    return getattr(item, name, None)


# 13. 필수 문자열 검증 보조 함수
# 모델·프롬프트·스키마 버전이 빈 문자열로 기록되는 것을 막는다.
def _require_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ExperienceAIInputError(
            f"{field_name}은 비어 있을 수 없습니다."
        )
    return normalized


# 14. 외부 공개 목록
# 다른 파일에서 가져다 사용할 이름을 명시한다.
__all__ = [
    "DEFAULT_EXPERIENCE_MODEL",
    "EXPERIENCE_DRAFT_TOOL",
    "EXPERIENCE_DRAFT_TOOL_NAME",
    "EXPERIENCE_PROMPT_VERSION",
    "EXPERIENCE_SCHEMA_VERSION",
    "EXPERIENCE_SYSTEM_PROMPT",
    "ExperienceAI",
    "ExperienceAIError",
    "ExperienceAIInputError",
    "ExperienceAIOutputError",
    "create_experience_ai",
]
