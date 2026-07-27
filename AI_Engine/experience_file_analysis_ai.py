"""파일 원문을 최종 경험 스키마 변환 전에 파일별로 읽고 요약한다."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from AI_Engine.chat_context import split_text_chunks, truncate_to_token_budget
from AI_Engine.llm_provider import (
    create_structured_client,
    get_chat_model_name,
)
from AI_Engine.schemas import (
    EvidenceSource,
    EvidenceSourceType,
    FileEvidenceAnalysis,
    FileEvidenceExcerpt,
    FileEvidenceFact,
    FileExperienceSignal,
)


FILE_ANALYSIS_TOOL_NAME = "analyze_experience_file"
FILE_ANALYSIS_PROMPT_VERSION = "experience-file-analysis-prompt-v1"
FILE_ANALYSIS_SCHEMA_VERSION = "experience-file-analysis-schema-v1"

logger = logging.getLogger(__name__)


FILE_ANALYSIS_SYSTEM_PROMPT = """
[역할 role]
너는 Career Memory 경험정리 파이프라인의 파일 1차 분석 AI야.

[목표 task]
PDF, TXT 또는 이미지 OCR에서 추출한 파일 원문을 먼저 읽고 요약해.
아직 경험 분류 → 프로젝트·활동 → 상세 경험의 최종 스키마를 만들지 말고,
파일에 포함된 경험 후보와 핵심 사실, 정확한 원문 인용만 정리해.

[문맥 context]
긴 파일은 여러 청크로 나뉘어 전달될 수 있어.
현재 전달된 청크 안에서 확인되는 내용만 분석해.
페이지 표시는 "[N페이지]" 형식으로 포함될 수 있어.

[제약조건 constraint]
- 파일에 없는 사실, 역할, 수치, 기간을 추측하지 마.
- summary는 현재 청크의 핵심 내용을 간결하게 요약해.
- experience_signals에는 사용자가 직접 수행한 것으로 보이는 활동만 넣어.
- 확실하지 않은 역할이나 성과는 단정하지 마.
- excerpts와 key_facts.quote는 원문에서 그대로 복사한 짧은 문장이어야 해.
- page_number는 페이지를 확인할 수 있을 때만 숫자로 넣고, 아니면 null로 둬.
- 이 단계에서는 경험 분류명이나 프로젝트·활동명을 확정하지 마.

[형식 format]
- 반드시 analyze_experience_file 함수를 정확히 한 번 호출해.
- summary, experience_signals, key_facts를 반환해.
""".strip()


FILE_ANALYSIS_TOOL: dict[str, Any] = {
    "type": "function",
    "name": FILE_ANALYSIS_TOOL_NAME,
    "description": "파일 원문 청크를 요약하고 경험 후보와 인용 가능한 사실을 찾습니다.",
    "parameters": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "experience_signals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "details": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "excerpts": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "quote": {"type": "string"},
                                    "page_number": {
                                        "type": ["integer", "null"],
                                        "minimum": 1,
                                    },
                                },
                                "required": ["quote", "page_number"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": [
                        "title",
                        "summary",
                        "details",
                        "excerpts",
                    ],
                    "additionalProperties": False,
                },
            },
            "key_facts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "quote": {"type": "string"},
                        "page_number": {
                            "type": ["integer", "null"],
                            "minimum": 1,
                        },
                    },
                    "required": ["text", "quote", "page_number"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["summary", "experience_signals", "key_facts"],
        "additionalProperties": False,
    },
    "strict": True,
}


class ExperienceFileAnalysisError(RuntimeError):
    """파일 1차 분석 결과를 만들거나 검증하지 못한 경우."""


class ExperienceFileAnalysisAI:
    """파일을 청크별로 분석한 뒤 하나의 파일 단위 파생 요약으로 합친다."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        model_version: str | None = None,
        provider: str | None = None,
        prompt_version: str = FILE_ANALYSIS_PROMPT_VERSION,
        schema_version: str = FILE_ANALYSIS_SCHEMA_VERSION,
    ) -> None:
        self.client = client or create_structured_client(provider)
        self.model_version = (
            model_version or get_chat_model_name(provider)
        ).strip()
        self.prompt_version = prompt_version.strip()
        self.schema_version = schema_version.strip()
        if not all((
            self.model_version,
            self.prompt_version,
            self.schema_version,
        )):
            raise ValueError("파일 분석 모델·프롬프트·스키마 버전은 필수입니다.")

    def analyze_sources(
        self,
        sources: Sequence[EvidenceSource],
    ) -> list[FileEvidenceAnalysis]:
        """본문이 추출된 파일 근거만 파일별로 먼저 분석한다."""

        return [
            self.analyze_source(source)
            for source in sources
            if (
                source.type == EvidenceSourceType.FILE.value
                and source.text
                and source.text.strip()
            )
        ]

    def analyze_source(self, source: EvidenceSource) -> FileEvidenceAnalysis:
        if source.type != EvidenceSourceType.FILE.value:
            raise ValueError("파일 근거만 파일 1차 분석을 실행할 수 있습니다.")
        if not source.text or not source.text.strip():
            raise ValueError("파일 분석에는 추출된 원문 텍스트가 필요합니다.")

        chunk_tokens = max(
            500,
            int(os.getenv(
                "AI_EXPERIENCE_FILE_ANALYSIS_CHUNK_TOKENS",
                "12000",
            )),
        )
        overlap_tokens = max(
            0,
            int(os.getenv(
                "AI_EXPERIENCE_FILE_ANALYSIS_CHUNK_OVERLAP_TOKENS",
                "300",
            )),
        )
        overlap_tokens = min(overlap_tokens, chunk_tokens - 1)
        chunks = split_text_chunks(
            source.text,
            max_tokens=chunk_tokens,
            overlap_tokens=overlap_tokens,
        )
        if not chunks:
            raise ValueError("파일에서 분석할 원문을 찾지 못했습니다.")

        chunk_results = [
            self._analyze_chunk(
                source=source,
                content=content,
                chunk_index=index,
                chunk_count=len(chunks),
            )
            for index, (content, _start, _end) in enumerate(chunks, start=1)
        ]
        return self._merge_chunk_results(source, chunk_results)

    def _analyze_chunk(
        self,
        *,
        source: EvidenceSource,
        content: str,
        chunk_index: int,
        chunk_count: int,
    ) -> dict[str, Any]:
        model_input = (
            "[파일 정보]\n"
            f"source_ref_id: {source.id}\n"
            f"filename: {source.filename or source.title}\n"
            f"chunk: {chunk_index}/{chunk_count}\n\n"
            "[파일 원문 청크]\n"
            f"{content}"
        )
        last_error: Exception | None = None
        for attempt in range(2):
            retry_instruction = (
                ""
                if attempt == 0
                else (
                    "\n\n[형식 재검토]\n"
                    "인용문은 현재 파일 원문에서 그대로 복사하고 모든 필수 필드를 "
                    "정해진 형식으로 다시 반환하세요."
                )
            )
            response = self.client.responses.create(
                model=self.model_version,
                input=f"{model_input}{retry_instruction}",
                tools=[FILE_ANALYSIS_TOOL],
                tool_choice={
                    "type": "function",
                    "name": FILE_ANALYSIS_TOOL_NAME,
                },
                instructions=FILE_ANALYSIS_SYSTEM_PROMPT,
            )
            try:
                payload = _function_arguments(response)
                return _validate_chunk_payload(payload, original_text=content)
            except (ExperienceFileAnalysisError, ValidationError, ValueError) as error:
                last_error = error
                logger.warning(
                    "파일 1차 분석 형식 검증 실패(%s/%s, 시도 %s): %s",
                    chunk_index,
                    chunk_count,
                    attempt + 1,
                    error,
                )
        raise ExperienceFileAnalysisError(
            "파일 1차 분석 결과가 스키마를 통과하지 못했습니다."
        ) from last_error

    def _merge_chunk_results(
        self,
        source: EvidenceSource,
        chunk_results: Sequence[Mapping[str, Any]],
    ) -> FileEvidenceAnalysis:
        summaries = _unique_strings([
            str(result.get("summary", ""))
            for result in chunk_results
        ])
        summary_budget = max(
            500,
            int(os.getenv(
                "AI_EXPERIENCE_FILE_ANALYSIS_SUMMARY_TOKENS",
                "8000",
            )),
        )
        summary = truncate_to_token_budget(
            "\n".join(summaries),
            summary_budget,
        )

        signals: list[FileExperienceSignal] = []
        seen_signals: set[tuple[str, str]] = set()
        facts: list[FileEvidenceFact] = []
        seen_facts: set[tuple[str, str]] = set()
        for result in chunk_results:
            for signal in result.get("experience_signals", []):
                key = (signal.title, signal.summary)
                if key in seen_signals:
                    continue
                seen_signals.add(key)
                signals.append(signal)
            for fact in result.get("key_facts", []):
                key = (fact.text, fact.quote)
                if key in seen_facts:
                    continue
                seen_facts.add(key)
                facts.append(fact)

        return FileEvidenceAnalysis(
            source_ref_id=source.id,
            filename=source.filename or source.title or "이름 없는 파일",
            summary=summary,
            experience_signals=signals,
            key_facts=facts,
            chunk_count=len(chunk_results),
            model_version=self.model_version,
            prompt_version=self.prompt_version,
            schema_version=self.schema_version,
        )


def _function_arguments(response: Any) -> Mapping[str, Any]:
    output = getattr(response, "output", None)
    if not isinstance(output, Sequence) or isinstance(output, (str, bytes)):
        raise ExperienceFileAnalysisError("파일 분석 함수 호출 결과가 없습니다.")
    calls = [
        item
        for item in output
        if _item_value(item, "type") == "function_call"
        and _item_value(item, "name") == FILE_ANALYSIS_TOOL_NAME
    ]
    if len(calls) != 1:
        raise ExperienceFileAnalysisError(
            "analyze_experience_file 함수를 정확히 한 번 호출해야 합니다."
        )
    arguments = _item_value(calls[0], "arguments")
    if not isinstance(arguments, str):
        raise ExperienceFileAnalysisError("파일 분석 함수 인자가 JSON이 아닙니다.")
    try:
        payload = json.loads(arguments)
    except json.JSONDecodeError as error:
        raise ExperienceFileAnalysisError(
            "파일 분석 함수 인자를 JSON으로 해석할 수 없습니다."
        ) from error
    if not isinstance(payload, Mapping):
        raise ExperienceFileAnalysisError("파일 분석 결과는 객체여야 합니다.")
    return payload


def _validate_chunk_payload(
    payload: Mapping[str, Any],
    *,
    original_text: str,
) -> dict[str, Any]:
    summary = str(payload.get("summary", "")).strip()
    if not summary:
        raise ExperienceFileAnalysisError("파일 분석 summary가 비어 있습니다.")

    raw_signals = payload.get("experience_signals", [])
    raw_facts = payload.get("key_facts", [])
    if not isinstance(raw_signals, list) or not isinstance(raw_facts, list):
        raise ExperienceFileAnalysisError(
            "experience_signals와 key_facts는 배열이어야 합니다."
        )

    signals: list[FileExperienceSignal] = []
    for raw_signal in raw_signals:
        if not isinstance(raw_signal, Mapping):
            raise ExperienceFileAnalysisError("경험 후보는 객체여야 합니다.")
        supported_excerpts = [
            FileEvidenceExcerpt.model_validate(raw_excerpt)
            for raw_excerpt in raw_signal.get("excerpts", [])
            if (
                isinstance(raw_excerpt, Mapping)
                and _quote_is_supported(
                    str(raw_excerpt.get("quote", "")),
                    original_text,
                )
            )
        ]
        signals.append(FileExperienceSignal(
            title=raw_signal.get("title", ""),
            summary=raw_signal.get("summary", ""),
            details=raw_signal.get("details", []),
            excerpts=supported_excerpts,
        ))

    facts: list[FileEvidenceFact] = []
    for raw_fact in raw_facts:
        if not isinstance(raw_fact, Mapping):
            raise ExperienceFileAnalysisError("파일 핵심 사실은 객체여야 합니다.")
        quote = str(raw_fact.get("quote", ""))
        if not _quote_is_supported(quote, original_text):
            continue
        facts.append(FileEvidenceFact.model_validate(raw_fact))

    return {
        "summary": summary,
        "experience_signals": signals,
        "key_facts": facts,
    }


def _quote_is_supported(quote: str, original_text: str) -> bool:
    normalized_quote = " ".join(quote.split())
    normalized_original = " ".join(original_text.split())
    return bool(normalized_quote and normalized_quote in normalized_original)


def _unique_strings(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _item_value(item: Any, name: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(name)
    return getattr(item, name, None)


__all__ = [
    "ExperienceFileAnalysisAI",
    "ExperienceFileAnalysisError",
    "FILE_ANALYSIS_PROMPT_VERSION",
    "FILE_ANALYSIS_SCHEMA_VERSION",
    "FILE_ANALYSIS_SYSTEM_PROMPT",
    "FILE_ANALYSIS_TOOL",
    "FILE_ANALYSIS_TOOL_NAME",
]
