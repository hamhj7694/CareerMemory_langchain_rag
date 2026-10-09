"""채용공고를 요구사항으로 구조화하고 관련 경험을 추천하는 AI."""

from __future__ import annotations

# 1. Python 기본 기능
# 함수 호출 JSON, 실행 시간, 고유 ID, 타입 표기에 사용한다.
import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

# 2. OpenAI Responses API
# 공고 요구사항과 추천 연결을 strict function calling 결과로 받는다.
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from pydantic import ValidationError

# 3. .env에서 키 불러오기
load_dotenv()

from AI_Engine.analysis_metrics import tracked_responses_create
from AI_Engine.llm_provider import (
    create_embeddings,
    create_structured_client,
    get_chat_model_name,
    get_experience_index_version,
)
from AI_Engine.metric_normalization import (
    extract_metrics,
    metric_satisfies_requirement,
    validate_proposed_metrics,
)
from AI_Engine.ontology_seed import ONTOLOGY_VERSION
from AI_Engine.skill_normalization import (
    build_skill_match_evidence,
    extract_registered_skill_mentions,
    normalize_skill_list,
)

# 4. 공통 데이터 계약
# AI 출력은 프론트엔드와 백엔드가 공유하는 공고 분석 스키마로 검증한다.
from AI_Engine.schemas import (
    JobAnalysisRequest,
    JobAnalysisResult,
    ExperienceSearchDocument,
    JobRequirement,
    JobRequirementImportance,
    JobRequirementType,
    JobSourceLocator,
    RequirementExperienceLink,
    RequirementExperienceLinkSource,
    RequirementExperienceLinkStatus,
    QuantifiedMetric,
    SkillMention,
)

# 5. 모델·프롬프트·스키마·검색 인덱스 버전
# 분석 결과와 추천 결과가 어떤 구성으로 생성됐는지 추적하기 위한 값이다.
DEFAULT_JOB_ANALYSIS_MODEL = "gpt-4o-mini"
JOB_ANALYSIS_PROMPT_VERSION = "job-analysis-prompt-v3"
JOB_ANALYSIS_SCHEMA_VERSION = "job-analysis-schema-v2"
DEFAULT_EXPERIENCE_INDEX_VERSION = "experience-index-v3"
DEFAULT_EXPERIENCE_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EXPERIENCE_COLLECTION_NAME = "career_memory_experiences"
DEFAULT_JOB_MATCH_MIN_SCORE = 0.65

_CREDENTIAL_MARKERS = {
    "자격",
    "자격증",
    "기능사",
    "기사",
    "산업기사",
    "면허",
    "certification",
    "certificate",
    "license",
}
_CREDENTIAL_GENERIC_TERMS = _CREDENTIAL_MARKERS | {
    "관련",
    "보유",
    "소지",
    "취득",
    "우대",
    "필수",
    "요건",
    "경험",
    "능력",
    "가능",
    "지원자",
    "소지자",
    "해당",
    "있는",
    "관련자",
}

# 6. 모델이 호출해야 하는 함수 이름
# 공고 요구사항 추출과 경험 추천을 서로 다른 구조화 함수로 구분한다.
JOB_REQUIREMENT_TOOL_NAME = "create_job_requirements"
JOB_MATCH_TOOL_NAME = "create_requirement_experience_links"

# 7. 공고 요구사항 구조화 프롬프트
# 공고에 실제로 적힌 원문만 사용해 요구사항 카드를 만들도록 지시한다.
JOB_REQUIREMENT_SYSTEM_PROMPT = """
[역할 role]
너는 Career Memory의 채용공고 분석 AI야.
사용자가 제공한 채용공고 원문에서 핵심 업무와 자격 요건을 구조화해.

[목표 task]
공고 원문을 읽고 서로 구분되는 요구사항을 0개 이상의 카드로 정리해.
각 카드는 요구사항 제목, 요약, 실제 공고 원문, 유형, 중요도, 검색 키워드를 가져야 해.

[문맥 context]
분석할 공고는 사용자 입력의 [분석할 채용공고 원문]에 전달돼.
posting_content와 첨부 파일은 source 이름으로 구분돼.

[제약조건 constraint]
- 공고 원문에 없는 요구사항을 추측하거나 만들어내지 마.
- source_excerpt는 제공된 공고에서 글자를 바꾸지 않고 그대로 인용해.
- 하나의 원문을 의미 없이 여러 요구사항으로 중복 분리하지 마.
- 필수·우대 여부가 명시되거나 문맥상 분명할 때만 importance를 정해.
- 확실하지 않으면 importance를 unknown으로 정해.
- type은 responsibility, qualification, collaboration, other 중 하나만 사용해.
- keywords는 확정 경험 RAG 검색에 유용한 짧은 핵심어만 작성해.
- skill_mentions에는 공고 원문에 실제로 나타난 기술 표현만 넣고,
  raw_name, source_ref_id, 원문의 정확한 quote를 반환해.
- metrics에는 공고 원문에 실제로 나타난 수치 조건만 넣고,
  수치의 의미, 원문 표현, source_ref_id, 정확한 quote를 반환해.
- 기술명과 수치를 임의로 표준화하거나 추측하지 마. 원문 표현을 그대로 보존해.
- 입력에 제공되지 않은 source 이름을 만들지 마.
- 자기소개서 문항이나 자기소개서 작성 내용은 생성하지 마.

[형식 format]
- 반드시 create_job_requirements 함수를 한 번 호출해.
- requirements 배열에 0개 이상의 요구사항을 넣어.
- 각 요구사항에는 type, title, summary, source, source_excerpt,
  importance, keywords, skill_mentions, metrics, confidence를 모두 반환해.
""".strip()

# 8. 요구사항별 경험 추천 프롬프트
# RAG 검색으로 전달된 확정 경험 후보 안에서만 관련 경험을 추천하도록 제한한다.
JOB_MATCH_SYSTEM_PROMPT = """
[역할 role]
너는 Career Memory의 요구사항별 경험 매칭 AI야.

[목표 task]
공고 요구사항과 RAG로 검색된 확정 경험 후보를 비교해,
실제로 관련성이 있는 경험만 요구사항별로 추천해.

[문맥 context]
[요구사항과 검색 후보]에는 requirement와 해당 요구사항으로 검색된
confirmed_experience_candidates가 함께 전달돼.

[제약조건 constraint]
- 검색 후보에 없는 experience_id를 절대 만들지 마.
- 해당 요구사항의 후보로 제공되지 않은 경험을 연결하지 마.
- 초안이 아닌 확정 경험 후보만 사용해.
- 관련성이 낮거나 근거가 부족하면 추천하지 마.
- similarity_score가 0.65 미만인 연결은 결과에 포함하지 마.
- 자격증·면허처럼 명칭이 중요한 요구사항은 같은 분야의 자격 명칭이나
  명백한 동의어가 경험에 확인될 때만 추천해.
- 공통적으로 "자격증"이라는 단어만 있다는 이유로 서로 다른 분야의
  자격증 경험을 연결하지 마.
- 임베딩 유사도는 후보 검색 신호일 뿐 기술 보유의 증거가 아니야.
- FastAPI와 REST API, JavaScript와 TypeScript처럼 관련 있지만 다른 기술은
  동일 기술이라고 주장하지 마. 필수 기술은 canonical skill ID가 같은 후보만 추천해.
- recommendation evidence_ids는 후보에 제공된 ID만 사용해.
- evidence_ids가 없는 후보는 추천하지 마.
- similarity_score는 0 이상 1 이하로 작성해.
- reason에는 요구사항과 경험이 연결되는 구체적인 이유를 간결하게 작성해.
- 사용자의 선택·확정 상태를 대신 결정하지 마.

[형식 format]
- 반드시 create_requirement_experience_links 함수를 한 번 호출해.
- experience_links 배열에 0개 이상의 AI 추천 연결을 넣어.
- 각 연결에는 requirement_id, experience_id, similarity_score,
  reason, evidence_ids를 모두 반환해.
""".strip()


# 9. 공고 요구사항 strict 함수 스키마
# ID·순서·원문 위치는 애플리케이션이 만들고 AI는 의미 분석 결과만 반환한다.
JOB_REQUIREMENT_TOOL: dict[str, Any] = {
    "type": "function",
    "name": JOB_REQUIREMENT_TOOL_NAME,
    "description": "채용공고 원문을 요구사항 카드 배열로 구조화합니다.",
    "parameters": {
        "type": "object",
        "properties": {
            "requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": [
                                "responsibility",
                                "qualification",
                                "collaboration",
                                "other",
                            ],
                        },
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "source": {
                            "type": "string",
                            "description": (
                                "posting_content 또는 제공된 첨부 파일 ID"
                            ),
                        },
                        "source_excerpt": {
                            "type": "string",
                            "description": "공고에서 그대로 복사한 원문",
                        },
                        "importance": {
                            "type": "string",
                            "enum": ["required", "preferred", "unknown"],
                        },
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "skill_mentions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "raw_name": {"type": "string"},
                                    "source_ref_id": {"type": "string"},
                                    "quote": {"type": "string"},
                                },
                                "required": ["raw_name", "source_ref_id", "quote"],
                                "additionalProperties": False,
                            },
                        },
                        "metrics": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "metric_name": {"type": "string"},
                                    "raw_expression": {"type": "string"},
                                    "source_ref_id": {"type": "string"},
                                    "quote": {"type": "string"},
                                },
                                "required": [
                                    "metric_name",
                                    "raw_expression",
                                    "source_ref_id",
                                    "quote",
                                ],
                                "additionalProperties": False,
                            },
                        },
                        "confidence": {
                            "type": ["number", "null"],
                            "minimum": 0,
                            "maximum": 1,
                        },
                    },
                    "required": [
                        "type",
                        "title",
                        "summary",
                        "source",
                        "source_excerpt",
                        "importance",
                        "keywords",
                        "skill_mentions",
                        "metrics",
                        "confidence",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["requirements"],
        "additionalProperties": False,
    },
    "strict": True,
}

# 10. 요구사항별 경험 추천 strict 함수 스키마
# 검색 후보에서 선택한 경험과 추천 근거만 구조화해서 반환한다.
JOB_MATCH_TOOL: dict[str, Any] = {
    "type": "function",
    "name": JOB_MATCH_TOOL_NAME,
    "description": "공고 요구사항별로 관련 있는 확정 경험을 추천합니다.",
    "parameters": {
        "type": "object",
        "properties": {
            "experience_links": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "requirement_id": {"type": "string"},
                        "experience_id": {"type": "string"},
                        "similarity_score": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "reason": {"type": "string"},
                        "evidence_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": [
                        "requirement_id",
                        "experience_id",
                        "similarity_score",
                        "reason",
                        "evidence_ids",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["experience_links"],
        "additionalProperties": False,
    },
    "strict": True,
}


# 11. 채용공고 분석 AI 전용 오류
# 입력·검색·모델 출력 문제를 구분해 API에서 적절한 안내를 만들 수 있게 한다.
class JobAnalysisAIError(RuntimeError):
    """채용공고 분석 AI의 공통 오류."""


class JobAnalysisAIInputError(JobAnalysisAIError):
    """분석할 공고 본문이나 첨부 본문이 없는 경우."""


class JobAnalysisAIRetrievalError(JobAnalysisAIError):
    """확정 경험 RAG 검색을 실행하지 못한 경우."""


class JobAnalysisAIOutputError(JobAnalysisAIError):
    """모델 출력이 함수 또는 공통 스키마 규칙과 다른 경우."""


# 12. 채용공고 분석 AI 실행 클래스
# 요구사항 추출 → 경험 RAG 검색 → 요구사항별 추천 연결 순서로 실행한다.
class JobAnalysisAI:
    """공고 요구사항과 관련 경험 추천을 하나의 분석 결과로 반환한다."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        experience_retriever: Any | None = None,
        model_version: str | None = None,
        provider: str | None = None,
        prompt_version: str = JOB_ANALYSIS_PROMPT_VERSION,
        schema_version: str = JOB_ANALYSIS_SCHEMA_VERSION,
        index_version: str | None = None,
        ontology_version: str = ONTOLOGY_VERSION,
        match_min_score: float | None = None,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        # 실제 실행에서는 활성 Provider 클라이언트와 Chroma retriever를 사용하고,
        # 테스트에서는 같은 메서드 모양의 가짜 객체를 주입할 수 있다.
        self.client = client or create_structured_client(provider)
        self.experience_retriever = experience_retriever
        self.model_version = _require_text(
            model_version or get_chat_model_name(provider),
            "model_version",
        )
        self.prompt_version = _require_text(
            prompt_version,
            "prompt_version",
        )
        self.schema_version = _require_text(
            schema_version,
            "schema_version",
        )
        self.index_version = _require_text(
            index_version or get_experience_index_version(provider),
            "index_version",
        )
        self.ontology_version = _require_text(
            ontology_version,
            "ontology_version",
        )
        self.match_min_score = get_job_match_min_score(match_min_score)
        self.id_factory = id_factory or (lambda: str(uuid4()))
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    # 12-1. 공고 분석 실행
    # 독립 AI 파일의 공통 진입점 이름을 invoke로 통일한다.
    def invoke(
        self,
        request: JobAnalysisRequest,
        *,
        attachment_texts: Mapping[str, str] | None = None,
    ) -> JobAnalysisResult:
        source_texts = self._prepare_source_texts(
            request,
            attachment_texts or {},
        )
        requirements = self._extract_requirements(
            request,
            source_texts,
        )

        warnings: list[str] = []
        experience_links: list[RequirementExperienceLink] = []
        if self.experience_retriever is None:
            warnings.append(
                "확정 경험 검색기가 연결되지 않아 요구사항만 분석했습니다."
            )
        elif requirements:
            candidates_by_requirement = self._retrieve_candidates(
                requirements
            )
            if any(candidates_by_requirement.values()):
                experience_links = self._match_experiences(
                    requirements,
                    candidates_by_requirement,
                )
            else:
                warnings.append(
                    "공고 요구사항과 관련된 확정 경험을 찾지 못했습니다."
                )

        try:
            return JobAnalysisResult(
                analysis_id=self._new_id("job-analysis"),
                client_request_id=request.client_request_id,
                job_posting=request.to_posting_draft(),
                requirements=requirements,
                experience_links=experience_links,
                warnings=warnings,
                analyzed_at=self.clock(),
                model_version=self.model_version,
                prompt_version=self.prompt_version,
                schema_version=self.schema_version,
                index_version=self.index_version,
                ontology_version=self.ontology_version,
            )
        except ValidationError as error:
            raise JobAnalysisAIOutputError(
                "공고 분석 결과가 공통 데이터 스키마 검증을 통과하지 못했습니다."
            ) from error

    # 12-2. analyze 호환 메서드
    # 화면이나 API에서 의미가 더 분명한 이름이 필요할 때 invoke와 같은 결과를 반환한다.
    def analyze(
        self,
        request: JobAnalysisRequest,
        *,
        attachment_texts: Mapping[str, str] | None = None,
    ) -> JobAnalysisResult:
        return self.invoke(
            request,
            attachment_texts=attachment_texts,
        )

    # 12-3. 기존 요구사항을 최신 확정 경험과 다시 매칭
    # 공고 요구사항을 다시 추출하지 않고, 선택된 요구사항의 RAG 검색과 추천만 갱신한다.
    def rematch_requirements(
        self,
        requirements: Sequence[JobRequirement],
    ) -> list[RequirementExperienceLink]:
        if self.experience_retriever is None or not requirements:
            return []
        candidates_by_requirement = self._retrieve_candidates(requirements)
        if not any(candidates_by_requirement.values()):
            return []
        return self._match_experiences(requirements, candidates_by_requirement)

    # 12-4. 분석 가능한 공고 원문 준비
    # 직접 입력 공고와 본문 추출이 끝난 첨부 파일만 모델 문맥에 포함한다.
    @staticmethod
    def _prepare_source_texts(
        request: JobAnalysisRequest,
        attachment_texts: Mapping[str, str],
    ) -> dict[str, str]:
        unknown_attachment_ids = (
            set(attachment_texts) - set(request.attachment_ids)
        )
        if unknown_attachment_ids:
            unknown = ", ".join(sorted(unknown_attachment_ids))
            raise JobAnalysisAIInputError(
                f"요청에 등록되지 않은 공고 첨부 본문입니다: {unknown}"
            )

        source_texts: dict[str, str] = {}
        if request.posting_content:
            source_texts["posting_content"] = request.posting_content
        for attachment_id in request.attachment_ids:
            text = attachment_texts.get(attachment_id, "").strip()
            if text:
                source_texts[attachment_id] = text

        if not source_texts:
            raise JobAnalysisAIInputError(
                "분석 가능한 채용공고 원문이 없습니다. "
                "첨부 파일은 본문 추출 후 전달해 주세요."
            )
        return source_texts

    # 12-4. 공고 요구사항 추출
    # 첫 번째 함수 호출로 원문에서 0개 이상의 요구사항을 구조화한다.
    def _extract_requirements(
        self,
        request: JobAnalysisRequest,
        source_texts: Mapping[str, str],
    ) -> list[JobRequirement]:
        model_input = self._build_requirement_input(request, source_texts)
        response = tracked_responses_create(
            self.client,
            stage="job_requirements",
            model=self.model_version,
            input=model_input,
            tools=[JOB_REQUIREMENT_TOOL],
            tool_choice={
                "type": "function",
                "name": JOB_REQUIREMENT_TOOL_NAME,
            },
            instructions=JOB_REQUIREMENT_SYSTEM_PROMPT,
        )
        raw_requirements = _function_array(
            response,
            tool_name=JOB_REQUIREMENT_TOOL_NAME,
            array_name="requirements",
        )

        try:
            return self._convert_requirements(
                request,
                raw_requirements,
                source_texts,
            )
        except JobAnalysisAIOutputError:
            # Exact excerpts are a hard evidence boundary. Ask once more rather
            # than accepting a paraphrase or dropping the entire job analysis.
            retry_response = tracked_responses_create(
                self.client,
                stage="job_requirements_retry_format",
                model=self.model_version,
                input=(
                    f"{model_input}\n\n"
                    "[형식 재검토 지시]\n"
                    "이전 결과의 source_excerpt 중 하나 이상이 공고 원문과 "
                    "글자 단위로 일치하지 않았습니다. 요구사항 의미는 유지하되 "
                    "모든 source_excerpt를 위 원문에서 복사한 연속 문자열로 "
                    "작성해 전체 requirements를 다시 반환하세요."
                ),
                tools=[JOB_REQUIREMENT_TOOL],
                tool_choice={
                    "type": "function",
                    "name": JOB_REQUIREMENT_TOOL_NAME,
                },
                instructions=JOB_REQUIREMENT_SYSTEM_PROMPT,
            )
            retry_raw = _function_array(
                retry_response,
                tool_name=JOB_REQUIREMENT_TOOL_NAME,
                array_name="requirements",
            )
            return self._convert_requirements(
                request,
                retry_raw,
                source_texts,
            )

    def _convert_requirements(
        self,
        request: JobAnalysisRequest,
        raw_requirements: Sequence[Mapping[str, Any]],
        source_texts: Mapping[str, str],
    ) -> list[JobRequirement]:
        return [
            self._to_job_requirement(
                request,
                raw_requirement,
                source_texts,
                order=index + 1,
            )
            for index, raw_requirement in enumerate(raw_requirements)
        ]

    # 12-5. 요구사항 추출용 모델 입력 생성
    # 공고 메타정보와 원문 출처를 명확히 구분해 source 인용 오류를 줄인다.
    @staticmethod
    def _build_requirement_input(
        request: JobAnalysisRequest,
        source_texts: Mapping[str, str],
    ) -> str:
        metadata = {
            "posting_id": request.posting_id,
            "company_name": request.company_name,
            "role_name": request.role_name,
            "posting_title": request.posting_title,
            "source_url": request.source_url,
        }
        source_sections = [
            "\n".join(
                (
                    "--- 공고 원문 시작 ---",
                    f"source: {source_name}",
                    text,
                    "--- 공고 원문 끝 ---",
                )
            )
            for source_name, text in source_texts.items()
        ]
        return (
            "[공고 메타정보]\n"
            f"{json.dumps(metadata, ensure_ascii=False)}\n\n"
            "[분석할 채용공고 원문]\n"
            + "\n\n".join(source_sections)
        )

    # 12-6. 함수 결과를 JobRequirement로 변환
    # 원문 인용의 실제 위치는 모델 값이 아니라 애플리케이션이 직접 계산한다.
    def _to_job_requirement(
        self,
        request: JobAnalysisRequest,
        raw_requirement: Mapping[str, Any],
        source_texts: Mapping[str, str],
        *,
        order: int,
    ) -> JobRequirement:
        source_name = raw_requirement.get("source")
        source_excerpt = raw_requirement.get("source_excerpt")
        if not isinstance(source_name, str) or source_name not in source_texts:
            raise JobAnalysisAIOutputError(
                "요구사항이 등록되지 않은 공고 원문을 참조했습니다."
            )
        if not isinstance(source_excerpt, str) or not source_excerpt.strip():
            raise JobAnalysisAIOutputError(
                "요구사항의 공고 원문 인용이 비어 있습니다."
            )

        source_text = source_texts[source_name]
        start_offset = source_text.find(source_excerpt)
        if start_offset < 0:
            recovered_excerpt = _recover_exact_source_excerpt(
                source_text,
                raw_requirement,
            )
            if recovered_excerpt is None:
                raise JobAnalysisAIOutputError(
                    "요구사항의 source_excerpt가 실제 공고 원문에 없습니다."
                )
            source_excerpt = recovered_excerpt
            start_offset = source_text.find(source_excerpt)
        end_offset = start_offset + len(source_excerpt)

        try:
            raw_skill_mentions = raw_requirement.get("skill_mentions", [])
            if not isinstance(raw_skill_mentions, list):
                raw_skill_mentions = []
            skill_mentions = normalize_skill_list(
                [],
                source_text_by_id={source_name: source_text},
                proposed_mentions=[
                    item for item in raw_skill_mentions
                    if isinstance(item, Mapping)
                ],
            )
            skill_mentions = [
                item for item in skill_mentions
                if not item.quote or item.quote in source_excerpt
            ]
            existing_skill_ids = {
                item.canonical_skill_id for item in skill_mentions
                if item.canonical_skill_id
            }
            for mention in extract_registered_skill_mentions(
                source_excerpt,
                source_ref_id=source_name,
            ):
                if mention.canonical_skill_id not in existing_skill_ids:
                    existing_skill_ids.add(mention.canonical_skill_id)
                    skill_mentions.append(mention)
            raw_metrics = raw_requirement.get("metrics", [])
            if not isinstance(raw_metrics, list):
                raw_metrics = []
            metrics = validate_proposed_metrics(
                [item for item in raw_metrics if isinstance(item, Mapping)],
                source_text_by_id={source_name: source_text},
            )
            metrics = [
                item for item in metrics
                if not item.quote or item.quote in source_excerpt
            ]
            metric_keys = {
                (item.source_ref_id, item.quote, item.raw_expression)
                for item in metrics
            }
            for metric in extract_metrics(
                raw_requirement.get("title", "") or source_excerpt,
                source_ref_id=source_name,
                quote=source_excerpt,
            ):
                key = (metric.source_ref_id, metric.quote, metric.raw_expression)
                if key not in metric_keys:
                    metric_keys.add(key)
                    metrics.append(metric)
            return JobRequirement(
                id=self._new_id("job-requirement"),
                job_posting_id=request.posting_id,
                type=raw_requirement.get(
                    "type",
                    JobRequirementType.OTHER,
                ),
                title=raw_requirement.get("title", ""),
                summary=raw_requirement.get("summary", ""),
                source_excerpt=source_excerpt,
                source_locator=JobSourceLocator(
                    source=source_name,
                    start_offset=start_offset,
                    end_offset=end_offset,
                ),
                importance=raw_requirement.get(
                    "importance",
                    JobRequirementImportance.UNKNOWN,
                ),
                keywords=raw_requirement.get("keywords", []),
                skill_mentions=skill_mentions,
                metrics=metrics,
                order=order,
                confidence=raw_requirement.get("confidence"),
            )
        except (TypeError, ValidationError, ValueError) as error:
            raise JobAnalysisAIOutputError(
                "모델이 반환한 공고 요구사항의 필드 형식이 올바르지 않습니다."
            ) from error

    # 12-7. 요구사항별 확정 경험 RAG 검색
    # 주입된 Retriever에서 요구사항과 관련된 확정 경험 문서를 가져온다.
    def _retrieve_candidates(
        self,
        requirements: Sequence[JobRequirement],
    ) -> dict[str, list[dict[str, Any]]]:
        candidates_by_requirement: dict[str, list[dict[str, Any]]] = {}
        for requirement in requirements:
            query = " ".join(
                (
                    requirement.title,
                    requirement.summary,
                    " ".join(requirement.keywords),
                )
            ).strip()
            try:
                documents = self.experience_retriever.invoke(query)
            except Exception as error:
                raise JobAnalysisAIRetrievalError(
                    f"{requirement.id}의 확정 경험 검색에 실패했습니다."
                ) from error

            if not isinstance(documents, Sequence) or isinstance(
                documents, (str, bytes)
            ):
                raise JobAnalysisAIRetrievalError(
                    "경험 검색기는 문서 배열을 반환해야 합니다."
                )
            normalized_candidates = self._normalize_candidates(documents)
            candidates_by_requirement[requirement.id] = [
                candidate
                for candidate in normalized_candidates
                if _candidate_meets_explicit_constraints(
                    requirement,
                    candidate,
                )
            ]
        return candidates_by_requirement

    # 12-8. 검색 문서를 모델 문맥용 후보로 정규화
    # Document.metadata의 experience_id와 evidence_ids가 있어야 추천 후보로 사용한다.
    @staticmethod
    def _normalize_candidates(
        documents: Sequence[Any],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        seen_experience_ids: set[str] = set()
        for document in documents:
            metadata = getattr(document, "metadata", None)
            page_content = getattr(document, "page_content", None)
            if not isinstance(metadata, Mapping):
                continue
            experience_id = metadata.get("experience_id")
            evidence_ids = metadata.get("evidence_ids")
            if not isinstance(evidence_ids, list):
                evidence_ids_json = metadata.get("evidence_ids_json")
                if isinstance(evidence_ids_json, str):
                    try:
                        decoded_evidence_ids = json.loads(
                            evidence_ids_json
                        )
                    except json.JSONDecodeError:
                        decoded_evidence_ids = None
                    if isinstance(decoded_evidence_ids, list):
                        evidence_ids = decoded_evidence_ids
            skill_mentions: list[dict[str, Any]] = []
            skill_mentions_json = metadata.get("skill_mentions_json")
            if isinstance(skill_mentions_json, str):
                try:
                    decoded_skill_mentions = json.loads(skill_mentions_json)
                except json.JSONDecodeError:
                    decoded_skill_mentions = None
                if isinstance(decoded_skill_mentions, list):
                    skill_mentions = [
                        item for item in decoded_skill_mentions
                        if isinstance(item, dict)
                    ]
            if not skill_mentions and isinstance(page_content, str):
                skill_mentions = [
                    item.model_dump(mode="json")
                    for item in extract_registered_skill_mentions(page_content)
                ]
            metrics: list[dict[str, Any]] = []
            metrics_json = metadata.get("metrics_json")
            if isinstance(metrics_json, str):
                try:
                    decoded_metrics = json.loads(metrics_json)
                except json.JSONDecodeError:
                    decoded_metrics = None
                if isinstance(decoded_metrics, list):
                    metrics = [
                        item for item in decoded_metrics
                        if isinstance(item, dict)
                    ]
            if (
                not isinstance(experience_id, str)
                or not experience_id.strip()
                or experience_id in seen_experience_ids
                or not isinstance(evidence_ids, list)
                or not all(
                    isinstance(evidence_id, str)
                    and evidence_id.strip()
                    for evidence_id in evidence_ids
                )
                or not evidence_ids
            ):
                continue

            seen_experience_ids.add(experience_id)
            candidates.append(
                {
                    "experience_id": experience_id,
                    "title": str(metadata.get("title", "")),
                    "domain_name": str(
                        metadata.get("domain_name", "")
                    ),
                    "project_name": str(
                        metadata.get("project_name", "")
                    ),
                    "content": (
                        page_content
                        if isinstance(page_content, str)
                        else ""
                    ),
                    "evidence_ids": list(dict.fromkeys(evidence_ids)),
                    "skill_mentions": skill_mentions,
                    "metrics": metrics,
                }
            )
        return candidates

    # 12-9. 검색 후보에서 요구사항별 경험 추천
    # 두 번째 함수 호출로 후보 안에서만 RequirementExperienceLink를 만든다.
    def _match_experiences(
        self,
        requirements: Sequence[JobRequirement],
        candidates_by_requirement: Mapping[
            str, Sequence[Mapping[str, Any]]
        ],
    ) -> list[RequirementExperienceLink]:
        match_context = [
            {
                "requirement": {
                    "id": requirement.id,
                    "title": requirement.title,
                    "summary": requirement.summary,
                    "keywords": requirement.keywords,
                    "skill_mentions": [
                        item.model_dump(mode="json")
                        for item in requirement.skill_mentions
                    ],
                    "metrics": [
                        item.model_dump(mode="json")
                        for item in requirement.metrics
                    ],
                },
                "confirmed_experience_candidates": list(
                    candidates_by_requirement.get(requirement.id, ())
                ),
            }
            for requirement in requirements
        ]
        response = tracked_responses_create(
            self.client,
            stage="job_experience_match",
            model=self.model_version,
            input=(
                "[요구사항과 검색 후보]\n"
                + json.dumps(match_context, ensure_ascii=False)
            ),
            tools=[JOB_MATCH_TOOL],
            tool_choice={
                "type": "function",
                "name": JOB_MATCH_TOOL_NAME,
            },
            instructions=JOB_MATCH_SYSTEM_PROMPT,
        )
        raw_links = _function_array(
            response,
            tool_name=JOB_MATCH_TOOL_NAME,
            array_name="experience_links",
        )

        allowed_candidates = {
            requirement_id: {
                candidate["experience_id"]: candidate
                for candidate in candidates
            }
            for requirement_id, candidates in (
                candidates_by_requirement.items()
            )
        }

        links: list[RequirementExperienceLink] = []
        for raw_link in raw_links:
            requirement_id = raw_link.get("requirement_id")
            experience_id = raw_link.get("experience_id")
            if (
                not isinstance(requirement_id, str)
                or not isinstance(experience_id, str)
                or experience_id
                not in allowed_candidates.get(requirement_id, {})
            ):
                raise JobAnalysisAIOutputError(
                    "AI가 해당 요구사항의 RAG 후보에 없는 경험을 추천했습니다."
                )

            raw_score = raw_link.get("similarity_score")
            if (
                isinstance(raw_score, (int, float))
                and not isinstance(raw_score, bool)
                and float(raw_score) < self.match_min_score
            ):
                continue

            candidate = allowed_candidates[requirement_id][experience_id]
            evidence_ids = raw_link.get("evidence_ids")
            if (
                not isinstance(evidence_ids, list)
                or not evidence_ids
                or not set(evidence_ids).issubset(
                    set(candidate["evidence_ids"])
                )
            ):
                raise JobAnalysisAIOutputError(
                    "AI 추천이 검색 후보에 없는 근거를 참조했습니다."
                )

            requirement = next(
                item for item in requirements if item.id == requirement_id
            )
            candidate_skill_mentions = []
            for raw_mention in candidate.get("skill_mentions", []):
                try:
                    mention = SkillMention.model_validate(raw_mention)
                except (TypeError, ValidationError, ValueError):
                    continue
                if mention.source_ref_id and mention.quote:
                    candidate_skill_mentions.append(mention)
            skill_matches = build_skill_match_evidence(
                requirement.skill_mentions,
                candidate_skill_mentions,
            )

            try:
                links.append(
                    RequirementExperienceLink(
                        requirement_id=requirement_id,
                        experience_id=experience_id,
                        source=RequirementExperienceLinkSource.AI,
                        status=RequirementExperienceLinkStatus.SUGGESTED,
                        similarity_score=raw_score,
                        reason=raw_link.get("reason", ""),
                        evidence_ids=evidence_ids,
                        skill_matches=skill_matches,
                        model_version=self.model_version,
                        index_version=self.index_version,
                    )
                )
            except (TypeError, ValidationError, ValueError) as error:
                raise JobAnalysisAIOutputError(
                    "모델이 반환한 경험 추천 연결 형식이 올바르지 않습니다."
                ) from error
        return links

    # 12-10. 분석·요구사항 고유 ID 생성
    def _new_id(self, prefix: str) -> str:
        value = self.id_factory().strip()
        if not value:
            raise JobAnalysisAIOutputError(
                "id_factory가 빈 ID를 반환했습니다."
            )
        return f"{prefix}-{value}"


# 13. 확정 경험을 LangChain 검색 문서로 변환
# 프론트엔드 Experience의 의미 필드를 합치고 추적용 메타데이터를 보존한다.
def build_experience_search_documents(
    experiences: Sequence[
        ExperienceSearchDocument | Mapping[str, Any]
    ],
) -> list[Document]:
    documents: list[Document] = []
    seen_experience_ids: set[str] = set()
    for experience in experiences:
        record = (
            experience
            if isinstance(experience, ExperienceSearchDocument)
            else _to_experience_search_document(experience)
        )
        if record.experience_id in seen_experience_ids:
            raise JobAnalysisAIInputError(
                "동일한 experience_id의 확정 경험이 중복되었습니다: "
                f"{record.experience_id}"
            )
        seen_experience_ids.add(record.experience_id)
        documents.append(
            Document(
                id=record.experience_id,
                page_content=record.to_search_text(),
                metadata=record.to_chroma_metadata(),
            )
        )
    return documents


# 14. Chroma 확정 경험 인덱스 동기화
# 전체 확정 경험 스냅샷을 기준으로 추가·수정·삭제하고 내용 해시가 같으면 재임베딩하지 않는다.
def sync_experience_vector_store(
    experiences: Sequence[
        ExperienceSearchDocument | Mapping[str, Any]
    ],
    *,
    persist_directory: str | None = None,
    embeddings: Any | None = None,
    provider: str | None = None,
    collection_name: str = DEFAULT_EXPERIENCE_COLLECTION_NAME,
) -> Chroma:
    embedding_model = embeddings or create_embeddings(provider=provider)
    vector_db = Chroma(
        collection_name=_require_text(
            collection_name,
            "collection_name",
        ),
        embedding_function=embedding_model,
        persist_directory=persist_directory,
    )
    documents = build_experience_search_documents(experiences)
    desired_documents = {
        str(document.id): document
        for document in documents
        if document.id is not None
    }

    stored = vector_db.get(include=["metadatas"])
    stored_ids = [
        str(stored_id) for stored_id in stored.get("ids", [])
    ]
    stored_metadatas = stored.get("metadatas", [])
    stored_hashes = {
        stored_id: (
            metadata.get("content_hash")
            if isinstance(metadata, Mapping)
            else None
        )
        for stored_id, metadata in zip(
            stored_ids,
            stored_metadatas,
            strict=False,
        )
    }

    desired_ids = set(desired_documents)
    stored_id_set = set(stored_ids)
    stale_ids = sorted(stored_id_set - desired_ids)
    new_ids = sorted(desired_ids - stored_id_set)
    changed_ids = sorted(
        experience_id
        for experience_id in desired_ids & stored_id_set
        if stored_hashes.get(experience_id)
        != desired_documents[experience_id].metadata.get("content_hash")
    )

    if stale_ids:
        vector_db.delete(ids=stale_ids)
    if changed_ids:
        vector_db.update_documents(
            ids=changed_ids,
            documents=[
                desired_documents[experience_id]
                for experience_id in changed_ids
            ],
        )
    if new_ids:
        vector_db.add_documents(
            documents=[
                desired_documents[experience_id]
                for experience_id in new_ids
            ],
            ids=new_ids,
        )
    return vector_db


# 15. 공고 분석 AI용 확정 경험 Retriever 생성
# Chroma Vector Store를 요구사항별 유사 경험 검색기로 변환한다.
def create_experience_retriever(
    experiences: Sequence[
        ExperienceSearchDocument | Mapping[str, Any]
    ],
    *,
    persist_directory: str | None = None,
    embeddings: Any | None = None,
    provider: str | None = None,
    collection_name: str = DEFAULT_EXPERIENCE_COLLECTION_NAME,
    search_k: int = 5,
) -> Any:
    if search_k < 1:
        raise JobAnalysisAIInputError(
            "search_k는 1 이상이어야 합니다."
        )
    vector_db = sync_experience_vector_store(
        experiences,
        persist_directory=persist_directory,
        embeddings=embeddings,
        provider=provider,
        collection_name=collection_name,
    )
    return vector_db.as_retriever(
        search_kwargs={
            "k": search_k,
            "filter": {"status": "confirmed"},
        }
    )


# 16. 기본 JobAnalysisAI 생성 함수
# AI_langchain.py에서 실제 경험 retriever와 함께 조립할 때 사용한다.
def create_job_analysis_ai(
    *,
    client: Any | None = None,
    experience_retriever: Any | None = None,
    model_version: str | None = None,
    index_version: str | None = None,
    provider: str | None = None,
) -> JobAnalysisAI:
    return JobAnalysisAI(
        client=client,
        experience_retriever=experience_retriever,
        model_version=model_version,
        index_version=index_version,
        provider=provider,
    )


# 17. 프론트엔드 확정 경험을 검색 스키마로 변환
# camelCase·snake_case와 중첩 domain/project를 한 번 정규화한다.
def _to_experience_search_document(
    experience: Mapping[str, Any],
) -> ExperienceSearchDocument:
    status = experience.get("status", "confirmed")
    if status != "confirmed":
        raise JobAnalysisAIInputError(
            "확정 상태가 아닌 경험은 RAG 인덱스에 넣을 수 없습니다."
        )
    domain = experience.get("domain")
    project = experience.get("project")
    domain_name = experience.get(
        "domain_name",
        experience.get("domainName", ""),
    )
    project_name = experience.get(
        "project_name",
        experience.get("projectName", ""),
    )
    if not domain_name and isinstance(domain, Mapping):
        domain_name = domain.get("name", "")
    if not project_name and isinstance(project, Mapping):
        project_name = project.get("name", "")

    try:
        return ExperienceSearchDocument(
            experience_id=experience.get(
                "experience_id",
                experience.get("id"),
            ),
            status=status,
            domain_name=domain_name,
            project_name=project_name,
            title=experience.get("title", ""),
            summary=experience.get("summary", ""),
            situation=experience.get("situation", ""),
            actions=experience.get("actions", []),
            results=experience.get("results", []),
            role=experience.get("role", ""),
            skills=experience.get("skills", []),
            skill_mentions=experience.get("skill_mentions", []),
            facts=experience.get("facts", []),
            metrics=experience.get("metrics", []),
            evidence_ids=experience.get(
                "evidence_ids",
                experience.get(
                    "evidenceIds",
                    experience.get("source_ids", []),
                ),
            ),
            updated_at=experience.get(
                "updated_at",
                experience.get("updatedAt"),
            ),
        )
    except (TypeError, ValidationError, ValueError) as error:
        raise JobAnalysisAIInputError(
            "확정 경험을 RAG 검색 문서로 변환할 수 없습니다."
        ) from error


# 18. strict 함수 호출 배열 추출 보조 함수
# 실제 OpenAI 객체와 테스트용 가짜 객체에서 같은 방식으로 arguments를 읽는다.
def _function_array(
    response: Any,
    *,
    tool_name: str,
    array_name: str,
) -> list[Mapping[str, Any]]:
    output = getattr(response, "output", None)
    if not isinstance(output, Sequence) or isinstance(
        output, (str, bytes)
    ):
        raise JobAnalysisAIOutputError(
            f"모델 응답에 {tool_name} function_call이 없습니다."
        )

    function_calls = [
        item
        for item in output
        if _item_value(item, "type") == "function_call"
        and _item_value(item, "name") == tool_name
    ]
    if len(function_calls) != 1:
        raise JobAnalysisAIOutputError(
            f"모델은 {tool_name} 함수를 정확히 한 번 호출해야 합니다."
        )

    arguments = _item_value(function_calls[0], "arguments")
    if not isinstance(arguments, str):
        raise JobAnalysisAIOutputError(
            f"{tool_name} arguments가 JSON 문자열이 아닙니다."
        )
    try:
        payload = json.loads(arguments)
    except json.JSONDecodeError as error:
        raise JobAnalysisAIOutputError(
            f"{tool_name} arguments를 JSON으로 해석할 수 없습니다."
        ) from error

    if not isinstance(payload, Mapping):
        raise JobAnalysisAIOutputError(
            f"{tool_name} 결과의 최상위 값은 객체여야 합니다."
        )
    values = payload.get(array_name)
    if not isinstance(values, list):
        raise JobAnalysisAIOutputError(
            f"{array_name}는 배열이어야 합니다."
        )
    if not all(isinstance(item, Mapping) for item in values):
        raise JobAnalysisAIOutputError(
            f"{array_name}의 각 항목은 객체여야 합니다."
        )
    return values


# 19. 함수 호출 항목 읽기 보조 함수
def _item_value(item: Any, name: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(name)
    return getattr(item, name, None)


# 20. 필수 문자열 검증 보조 함수
def _require_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise JobAnalysisAIInputError(
            f"{field_name}은 비어 있을 수 없습니다."
        )
    return normalized


def _recover_exact_source_excerpt(
    source_text: str,
    raw_requirement: Mapping[str, Any],
) -> str | None:
    """Recover an exact source line when the model lightly rewrites its quote."""

    requested_excerpt = str(raw_requirement.get("source_excerpt") or "")
    hint_tokens = {
        token.casefold()
        for token in re.findall(r"[0-9A-Za-z가-힣+#.]+", requested_excerpt)
        if len(token) >= 2
    }
    if len(hint_tokens) < 2:
        return None
    candidates: list[tuple[int, int, str]] = []
    for line_number, line in enumerate(source_text.splitlines()):
        exact_line = line.strip()
        if not exact_line:
            continue
        normalized_line = exact_line.casefold()
        score = sum(token in normalized_line for token in hint_tokens)
        minimum_score = max(2, (len(hint_tokens) + 1) // 2)
        if score >= minimum_score:
            candidates.append((score, -line_number, exact_line))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][2]


def get_job_match_min_score(value: float | str | None = None) -> float:
    """현재 채용공고 추천에 적용할 최소 점수를 한 곳에서 읽는다."""

    configured = (
        value
        if value is not None
        else os.getenv(
            "AI_JOB_MATCH_MIN_SCORE",
            str(DEFAULT_JOB_MATCH_MIN_SCORE),
        )
    )
    try:
        score = float(configured)
    except (TypeError, ValueError) as error:
        raise JobAnalysisAIInputError(
            "AI_JOB_MATCH_MIN_SCORE는 0 이상 1 이하의 숫자여야 합니다."
        ) from error
    if not 0 <= score <= 1:
        raise JobAnalysisAIInputError(
            "AI_JOB_MATCH_MIN_SCORE는 0 이상 1 이하의 숫자여야 합니다."
        )
    return score


def _candidate_meets_explicit_constraints(
    requirement: JobRequirement,
    candidate: Mapping[str, Any],
) -> bool:
    """자격증처럼 명칭이 중요한 요구사항의 분야 불일치를 차단한다."""

    required_skill_ids = {
        item.canonical_skill_id
        for item in requirement.skill_mentions
        if item.canonical_skill_id
    }
    candidate_skill_ids = {
        str(item.get("canonical_skill_id"))
        for item in candidate.get("skill_mentions", [])
        if (
            isinstance(item, Mapping)
            and item.get("canonical_skill_id")
            and item.get("source_ref_id")
            and item.get("quote")
        )
    }
    # Embeddings may retrieve related technologies, but related is not exact
    # evidence that a required technology was used.
    if required_skill_ids and not required_skill_ids.issubset(candidate_skill_ids):
        return False

    numeric_constraints = [
        item for item in requirement.metrics
        if item.operator in {"at_least", "at_most", "range"}
    ]
    if required_skill_ids and numeric_constraints:
        candidate_metrics: list[QuantifiedMetric] = []
        for raw_metric in candidate.get("metrics", []):
            try:
                metric = QuantifiedMetric.model_validate(raw_metric)
            except (TypeError, ValidationError, ValueError):
                continue
            if metric.source_ref_id and metric.quote:
                candidate_metrics.append(metric)
        if any(
            not any(
                metric_satisfies_requirement(constraint, candidate_metric)
                for candidate_metric in candidate_metrics
            )
            for constraint in numeric_constraints
        ):
            return False

    requirement_text = " ".join((
        requirement.title,
        requirement.summary,
        requirement.source_excerpt,
        " ".join(requirement.keywords),
    )).casefold()
    if not any(marker in requirement_text for marker in _CREDENTIAL_MARKERS):
        return True

    constraint_text = " ".join((
        requirement.title,
        requirement.source_excerpt,
        " ".join(requirement.keywords),
    )).casefold()
    requirement_tokens = set(
        re.findall(r"[0-9a-zA-Z가-힣+#.]+", constraint_text)
    )
    specific_terms = {
        token
        for token in requirement_tokens
        if len(token) >= 2
        and not any(
            token.startswith(generic)
            for generic in _CREDENTIAL_GENERIC_TERMS
        )
    }
    if not specific_terms:
        return True

    candidate_text = " ".join((
        str(candidate.get("title", "")),
        str(candidate.get("domain_name", "")),
        str(candidate.get("project_name", "")),
        str(candidate.get("content", "")),
    )).casefold()
    return any(term in candidate_text for term in specific_terms)


# 21. 외부 공개 목록
__all__ = [
    "DEFAULT_EXPERIENCE_COLLECTION_NAME",
    "DEFAULT_EXPERIENCE_EMBEDDING_MODEL",
    "DEFAULT_EXPERIENCE_INDEX_VERSION",
    "DEFAULT_JOB_ANALYSIS_MODEL",
    "DEFAULT_JOB_MATCH_MIN_SCORE",
    "JOB_ANALYSIS_PROMPT_VERSION",
    "JOB_ANALYSIS_SCHEMA_VERSION",
    "JOB_MATCH_SYSTEM_PROMPT",
    "JOB_MATCH_TOOL",
    "JOB_MATCH_TOOL_NAME",
    "JOB_REQUIREMENT_SYSTEM_PROMPT",
    "JOB_REQUIREMENT_TOOL",
    "JOB_REQUIREMENT_TOOL_NAME",
    "JobAnalysisAI",
    "JobAnalysisAIError",
    "JobAnalysisAIInputError",
    "JobAnalysisAIOutputError",
    "JobAnalysisAIRetrievalError",
    "build_experience_search_documents",
    "create_experience_retriever",
    "create_job_analysis_ai",
    "get_job_match_min_score",
    "sync_experience_vector_store",
]
