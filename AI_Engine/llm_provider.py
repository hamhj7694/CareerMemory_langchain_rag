"""AI 엔진에서 Gemini와 OpenAI를 같은 방식으로 선택하는 공통 모듈."""

from __future__ import annotations

# 1. Python 기본 기능
# 환경 변수, JSON 변환, OpenAI 호환 응답 객체를 만드는 데 사용한다.
import json
import os
from types import SimpleNamespace
from typing import Any, Literal, Mapping

# 2. 모델 및 임베딩 Provider
# 채팅과 구조화 출력은 LangChain 모델을 사용하고 GPT 경로는 기존 OpenAI SDK를 유지한다.
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    GoogleGenerativeAIEmbeddings,
)
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from openai import OpenAI

# 3. .env 설정 불러오기
load_dotenv()

AIProvider = Literal["gemini", "openai"]

DEFAULT_AI_PROVIDER: AIProvider = "openai"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_GEMINI_EMBEDDING_MODEL = "gemini-embedding-2"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_CHAT_TEMPERATURE = 0.3


# 4. 활성 Provider 확인
# 함수 인자가 있으면 우선 사용하고, 없으면 AI_PROVIDER 환경 변수를 사용한다.
def get_ai_provider(provider: str | None = None) -> AIProvider:
    value = (provider or os.getenv("AI_PROVIDER") or DEFAULT_AI_PROVIDER)
    normalized = value.strip().lower()
    if normalized not in {"gemini", "openai"}:
        raise ValueError(
            "AI_PROVIDER는 'gemini' 또는 'openai'여야 합니다."
        )
    return normalized  # type: ignore[return-value]


# 5. Provider별 모델 이름 확인
def get_chat_model_name(provider: str | None = None) -> str:
    active_provider = get_ai_provider(provider)
    if active_provider == "gemini":
        return (
            os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
        ).strip()
    return (os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL).strip()


# 6. Provider별 임베딩 모델 이름 확인
def get_embedding_model_name(provider: str | None = None) -> str:
    active_provider = get_ai_provider(provider)
    if active_provider == "gemini":
        return (
            os.getenv("GEMINI_EMBEDDING_MODEL")
            or DEFAULT_GEMINI_EMBEDDING_MODEL
        ).strip()
    return (
        os.getenv("OPENAI_EMBEDDING_MODEL")
        or DEFAULT_OPENAI_EMBEDDING_MODEL
    ).strip()


def get_chat_temperature() -> float:
    raw_value = os.getenv(
        "AI_CHAT_TEMPERATURE",
        str(DEFAULT_CHAT_TEMPERATURE),
    ).strip()
    try:
        temperature = float(raw_value)
    except ValueError as exc:
        raise ValueError(
            "AI_CHAT_TEMPERATURE는 0.0~2.0 사이의 숫자여야 합니다."
        ) from exc
    if not 0.0 <= temperature <= 2.0:
        raise ValueError(
            "AI_CHAT_TEMPERATURE는 0.0~2.0 사이의 숫자여야 합니다."
        )
    return temperature


# 7. 대화형 모델 생성
# OpenAI가 기본이며 AI_PROVIDER=gemini로 설정하면 Gemini 모델을 만든다.
def create_chat_model(
    *,
    provider: str | None = None,
    model_name: str | None = None,
) -> Any:
    active_provider = get_ai_provider(provider)
    selected_model = model_name or get_chat_model_name(active_provider)
    # 일반 채팅 답변 길이는 구조화 분석 결과와 별도로 조절한다.
    # 이후 대화 요약 엔진을 추가해도 용도별 한도가 서로 영향을 주지 않는다.
    chat_output_tokens = int(os.getenv("AI_CHAT_MAX_TOKENS", "8000"))
    chat_temperature = get_chat_temperature()
    if active_provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=selected_model,
            api_key=_required_api_key("GEMINI_API_KEY"),
            max_tokens=chat_output_tokens,
            temperature=chat_temperature,
        )
    return ChatOpenAI(
        model=selected_model,
        api_key=_required_api_key("OPENAI_API_KEY"),
        temperature=chat_temperature,
        max_completion_tokens=chat_output_tokens,
    )


# 8. 임베딩 모델 생성
# Provider가 바뀌면 기존 벡터와 차원이 달라질 수 있으므로 호출부에서 인덱스도 분리한다.
def create_embeddings(
    *,
    provider: str | None = None,
    model_name: str | None = None,
) -> Any:
    active_provider = get_ai_provider(provider)
    selected_model = model_name or get_embedding_model_name(active_provider)
    if active_provider == "gemini":
        return GoogleGenerativeAIEmbeddings(
            model=selected_model,
            api_key=_required_api_key("GEMINI_API_KEY"),
        )
    return OpenAIEmbeddings(
        model=selected_model,
        api_key=_required_api_key("OPENAI_API_KEY"),
    )


# 9. 구조화 출력용 Gemini 어댑터
# 기존 AI 엔진의 responses.create 호출 형태를 보존해 GPT 코드를 바꾸지 않고 Gemini를 연결한다.
class GeminiStructuredClient:
    """Gemini 구조화 출력을 OpenAI Responses API 모양으로 변환한다."""

    def __init__(self) -> None:
        self.responses = self

    def create(
        self,
        *,
        model: str,
        input: str,
        tools: list[Mapping[str, Any]],
        tool_choice: Mapping[str, Any],
        instructions: str,
    ) -> Any:
        if len(tools) != 1:
            raise ValueError("구조화 출력 도구는 정확히 하나여야 합니다.")

        tool = tools[0]
        tool_name = str(tool.get("name", "")).strip()
        selected_tool_name = str(tool_choice.get("name", "")).strip()
        schema = tool.get("parameters")
        if not tool_name or selected_tool_name != tool_name:
            raise ValueError("선택한 구조화 출력 도구 이름이 올바르지 않습니다.")
        if not isinstance(schema, Mapping):
            raise ValueError("구조화 출력 도구에 JSON 스키마가 필요합니다.")

        # 여러 경험을 한 번에 정리하면 경험별 상황·행동·성과·근거가 모두
        # JSON으로 반환되어 4,000토큰을 쉽게 넘을 수 있다. 응답이 중간에
        # 잘려 스키마 오류가 나지 않도록 구조화 출력 전용 한도를 넉넉히 둔다.
        structured_output_tokens = int(
            os.getenv("AI_STRUCTURED_OUTPUT_MAX_TOKENS", "65536")
        )
        model_client = ChatGoogleGenerativeAI(
            model=model,
            api_key=_required_api_key("GEMINI_API_KEY"),
            max_tokens=structured_output_tokens,
            temperature=0,
        )
        structured_model = model_client.with_structured_output(
            dict(schema),
            method="json_schema",
        )
        result = structured_model.invoke(
            [
                SystemMessage(content=instructions),
                HumanMessage(content=input),
            ]
        )
        if not isinstance(result, Mapping):
            raise ValueError("Gemini 구조화 출력이 JSON 객체가 아닙니다.")

        function_call = SimpleNamespace(
            type="function_call",
            name=tool_name,
            arguments=json.dumps(result, ensure_ascii=False),
        )
        return SimpleNamespace(output=[function_call])


# 10. 구조화 출력 클라이언트 생성
def create_structured_client(
    provider: str | None = None,
) -> Any:
    active_provider = get_ai_provider(provider)
    if active_provider == "gemini":
        return GeminiStructuredClient()
    return OpenAI(api_key=_required_api_key("OPENAI_API_KEY"))


# 11. Provider별 RAG 인덱스 버전
# 서로 다른 임베딩 모델로 생성한 벡터가 같은 컬렉션에서 섞이지 않게 한다.
def get_experience_index_version(
    provider: str | None = None,
) -> str:
    active_provider = get_ai_provider(provider)
    if active_provider == "gemini":
        return "experience-index-gemini-v1"
    return "experience-index-openai-v2"


# 12. API 키 검증
# 모델 호출 직전에 누락된 환경 변수 이름을 명확히 알려준다.
def _required_api_key(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name}가 .env에 설정되지 않았습니다.")
    return value


__all__ = [
    "AIProvider",
    "DEFAULT_AI_PROVIDER",
    "DEFAULT_GEMINI_EMBEDDING_MODEL",
    "DEFAULT_GEMINI_MODEL",
    "DEFAULT_OPENAI_EMBEDDING_MODEL",
    "DEFAULT_OPENAI_MODEL",
    "DEFAULT_CHAT_TEMPERATURE",
    "GeminiStructuredClient",
    "create_chat_model",
    "create_embeddings",
    "create_structured_client",
    "get_ai_provider",
    "get_chat_temperature",
    "get_chat_model_name",
    "get_embedding_model_name",
    "get_experience_index_version",
]
