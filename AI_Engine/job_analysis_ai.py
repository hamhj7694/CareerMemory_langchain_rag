"""채용공고를 요구사항으로 구조화하고 관련 경험을 추천하는 AI."""

from __future__ import annotations

# 1. Python 기본 기능
# 함수 호출 JSON, 실행 시간, 고유 ID, 타입 표기에 사용한다.
import json
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

from AI_Engine.llm_provider import (
    create_embeddings,
    create_structured_client,
    get_chat_model_name,
    get_experience_index_version,
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
)

# 5. 모델·프롬프트·스키마·검색 인덱스 버전
# 분석 결과와 추천 결과가 어떤 구성으로 생성됐는지 추적하기 위한 값이다.
DEFAULT_JOB_ANALYSIS_MODEL = "gpt-4o-mini"
JOB_ANALYSIS_PROMPT_VERSION = "job-analysis-prompt-v1"
JOB_ANALYSIS_SCHEMA_VERSION = "job-analysis-schema-v1"
DEFAULT_EXPERIENCE_INDEX_VERSION = "experience-index-v2"
DEFAULT_EXPERIENCE_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EXPERIENCE_COLLECTION_NAME = "career_memory_experiences"

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
- 입력에 제공되지 않은 source 이름을 만들지 마.
- 자기소개서 문항이나 자기소개서 작성 내용은 생성하지 마.

[형식 format]
- 반드시 create_job_requirements 함수를 한 번 호출해.
- requirements 배열에 0개 이상의 요구사항을 넣어.
- 각 요구사항에는 type, title, summary, source, source_excerpt,
  importance, keywords, confidence를 모두 반환해.
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

    # 12-3. 분석 가능한 공고 원문 준비
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
        response = self.client.responses.create(
            model=self.model_version,
            input=self._build_requirement_input(request, source_texts),
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

        requirements: list[JobRequirement] = []
        for index, raw_requirement in enumerate(raw_requirements):
            requirements.append(
                self._to_job_requirement(
                    request,
                    raw_requirement,
                    source_texts,
                    order=index + 1,
                )
            )
        return requirements

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
            raise JobAnalysisAIOutputError(
                "요구사항의 source_excerpt가 실제 공고 원문에 없습니다."
            )
        end_offset = start_offset + len(source_excerpt)

        try:
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
            candidates_by_requirement[requirement.id] = (
                self._normalize_candidates(documents)
            )
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
                },
                "confirmed_experience_candidates": list(
                    candidates_by_requirement.get(requirement.id, ())
                ),
            }
            for requirement in requirements
        ]
        response = self.client.responses.create(
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

            try:
                links.append(
                    RequirementExperienceLink(
                        requirement_id=requirement_id,
                        experience_id=experience_id,
                        source=RequirementExperienceLinkSource.AI,
                        status=RequirementExperienceLinkStatus.SUGGESTED,
                        similarity_score=raw_link.get(
                            "similarity_score"
                        ),
                        reason=raw_link.get("reason", ""),
                        evidence_ids=evidence_ids,
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
            facts=experience.get("facts", []),
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


# 21. 외부 공개 목록
__all__ = [
    "DEFAULT_EXPERIENCE_COLLECTION_NAME",
    "DEFAULT_EXPERIENCE_EMBEDDING_MODEL",
    "DEFAULT_EXPERIENCE_INDEX_VERSION",
    "DEFAULT_JOB_ANALYSIS_MODEL",
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
    "sync_experience_vector_store",
]
