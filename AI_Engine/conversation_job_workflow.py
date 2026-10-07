"""LangGraph workflow and function-calling discovery for conversation jobs."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from AI_Engine.analysis_metrics import tracked_responses_create
from AI_Engine.conversation_job_extraction import (
    ConversationJobCandidate,
    JobSourceText,
    extract_job_posting_candidates,
    job_contents_match,
)
from AI_Engine.llm_provider import create_structured_client, get_chat_model_name


JOB_DISCOVERY_TOOL_NAME = "discover_conversation_job_postings"
JOB_DISCOVERY_PROMPT_VERSION = "conversation-job-discovery-v1"

JOB_DISCOVERY_SYSTEM_PROMPT = """
[role]
You identify complete job postings contained in conversation messages and attachments.

[task]
- Return every distinct job posting found in the supplied sources.
- If one source contains multiple postings, return each posting separately.
- Ignore career advice, interview questions, resumes, personal experiences, and ordinary chat.

[constraints]
- source_id must be copied from the supplied source.
- posting_content must be an exact, contiguous substring of that source's content.
- Never invent, summarize, translate, or rewrite posting_content.
- Metadata must come from the posting. Use an empty string or null when unknown.
- Returning an empty postings array is valid when no posting is present.

[format]
Call discover_conversation_job_postings exactly once.
""".strip()

JOB_DISCOVERY_TOOL: dict[str, Any] = {
    "type": "function",
    "name": JOB_DISCOVERY_TOOL_NAME,
    "description": "Find exact job-posting sections in conversation sources.",
    "parameters": {
        "type": "object",
        "properties": {
            "postings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string"},
                        "posting_content": {"type": "string"},
                        "company_name": {"type": "string"},
                        "role_name": {"type": "string"},
                        "posting_title": {"type": "string"},
                        "source_url": {"type": ["string", "null"]},
                    },
                    "required": [
                        "source_id",
                        "posting_content",
                        "company_name",
                        "role_name",
                        "posting_title",
                        "source_url",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["postings"],
        "additionalProperties": False,
    },
    "strict": True,
}


class ConversationJobDiscoveryError(RuntimeError):
    """Raised when the discovery model violates its strict output contract."""


def job_source_id(source: JobSourceText) -> str:
    if source.attachment_id:
        return f"message:{source.message_id}:attachment:{source.attachment_id}"
    return f"message:{source.message_id}"


def _item_value(item: Any, name: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(name)
    return getattr(item, name, None)


def _function_postings(response: Any) -> list[Mapping[str, Any]]:
    output = getattr(response, "output", None)
    if not isinstance(output, Sequence) or isinstance(output, (str, bytes)):
        raise ConversationJobDiscoveryError(
            "The discovery model did not return a function call."
        )
    calls = [
        item
        for item in output
        if _item_value(item, "type") == "function_call"
        and _item_value(item, "name") == JOB_DISCOVERY_TOOL_NAME
    ]
    if len(calls) != 1:
        raise ConversationJobDiscoveryError(
            f"{JOB_DISCOVERY_TOOL_NAME} must be called exactly once."
        )
    arguments = _item_value(calls[0], "arguments")
    if not isinstance(arguments, str):
        raise ConversationJobDiscoveryError("Function arguments must be JSON text.")
    try:
        payload = json.loads(arguments)
    except json.JSONDecodeError as error:
        raise ConversationJobDiscoveryError(
            "Function arguments are not valid JSON."
        ) from error
    postings = payload.get("postings") if isinstance(payload, Mapping) else None
    if not isinstance(postings, list) or not all(
        isinstance(item, Mapping) for item in postings
    ):
        raise ConversationJobDiscoveryError("postings must be an array of objects.")
    return postings


def _source_batches(
    sources: list[JobSourceText],
    *,
    maximum_characters: int = 60_000,
    maximum_sources: int = 8,
) -> list[list[JobSourceText]]:
    """Keep model requests bounded without splitting an individual source."""

    batches: list[list[JobSourceText]] = []
    current: list[JobSourceText] = []
    current_size = 0
    for source in sources:
        source_size = len(source.text)
        if current and (
            len(current) >= maximum_sources
            or current_size + source_size > maximum_characters
        ):
            batches.append(current)
            current = []
            current_size = 0
        current.append(source)
        current_size += source_size
    if current:
        batches.append(current)
    return batches


class ConversationJobDiscoveryAI:
    """Use strict function calling to locate postings before analysis."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        provider: str | None = None,
        model_version: str | None = None,
    ) -> None:
        self.client = client or create_structured_client(provider)
        self.model_version = model_version or get_chat_model_name(provider)

    def discover(
        self,
        sources: list[JobSourceText],
    ) -> list[ConversationJobCandidate]:
        if not sources:
            return []

        source_by_id = {job_source_id(source): source for source in sources}
        discovered: list[ConversationJobCandidate] = []
        for batch in _source_batches(sources):
            model_sources = [
                {
                    "source_id": job_source_id(source),
                    "title": source.title,
                    "content": source.text,
                }
                for source in batch
            ]
            response = tracked_responses_create(
                self.client,
                stage="job_discovery",
                model=self.model_version,
                input=json.dumps(model_sources, ensure_ascii=False),
                tools=[JOB_DISCOVERY_TOOL],
                tool_choice={
                    "type": "function",
                    "name": JOB_DISCOVERY_TOOL_NAME,
                },
                instructions=JOB_DISCOVERY_SYSTEM_PROMPT,
            )
            for raw in _function_postings(response):
                source_id = raw.get("source_id")
                posting_content = raw.get("posting_content")
                source = source_by_id.get(source_id) if isinstance(source_id, str) else None
                if source is None:
                    raise ConversationJobDiscoveryError(
                        "The model returned an unknown source_id."
                    )
                if (
                    not isinstance(posting_content, str)
                    or len(posting_content.strip()) < 60
                    or posting_content not in source.text
                ):
                    raise ConversationJobDiscoveryError(
                        "The model returned posting content that is not an exact source excerpt."
                    )
                source_url = raw.get("source_url")
                if source_url is not None and not isinstance(source_url, str):
                    raise ConversationJobDiscoveryError("source_url must be text or null.")
                if source_url and source_url not in source.text:
                    source_url = None
                discovered.append(ConversationJobCandidate(
                    message_id=source.message_id,
                    attachment_id=source.attachment_id,
                    posting_content=posting_content.strip(),
                    company_name=str(raw.get("company_name") or "").strip()[:200],
                    role_name=str(raw.get("role_name") or "").strip()[:200],
                    posting_title=str(raw.get("posting_title") or "").strip()[:300],
                    source_url=source_url.strip() if source_url else None,
                ))

        # Deterministic candidates remain as a safety net. AI candidates come
        # first so their richer metadata wins during the graph's dedupe node.
        return [*discovered, *extract_job_posting_candidates(sources)]


@dataclass(frozen=True)
class JobWorkflowResolution:
    job_id: str
    created: bool


class JobWorkflowResult(TypedDict):
    candidate: ConversationJobCandidate
    job_id: str
    created: bool


class ConversationJobWorkflowState(TypedDict, total=False):
    sources: list[JobSourceText]
    candidates: list[ConversationJobCandidate]
    unique_candidates: list[ConversationJobCandidate]
    results: list[JobWorkflowResult]
    steps: list[str]


class ConversationJobWorkflow:
    """A real LangGraph workflow with conditional job-analysis routing."""

    def __init__(
        self,
        *,
        discover: Callable[[list[JobSourceText]], list[ConversationJobCandidate]],
        resolve: Callable[[ConversationJobCandidate], JobWorkflowResolution],
    ) -> None:
        self.discover = discover
        self.resolve = resolve
        builder = StateGraph(ConversationJobWorkflowState)
        builder.add_node("discover_postings", self._discover_postings)
        builder.add_node("deduplicate_postings", self._deduplicate_postings)
        builder.add_node("analyze_postings", self._analyze_postings)
        builder.add_node("complete", self._complete)
        builder.add_edge(START, "discover_postings")
        builder.add_edge("discover_postings", "deduplicate_postings")
        builder.add_conditional_edges(
            "deduplicate_postings",
            self._route_after_deduplication,
            {
                "analyze": "analyze_postings",
                "complete": "complete",
            },
        )
        builder.add_edge("analyze_postings", "complete")
        builder.add_edge("complete", END)
        self.graph = builder.compile()

    def invoke(self, sources: list[JobSourceText]) -> ConversationJobWorkflowState:
        return self.graph.invoke({"sources": sources, "steps": []})

    def _discover_postings(
        self,
        state: ConversationJobWorkflowState,
    ) -> ConversationJobWorkflowState:
        return {
            "candidates": self.discover(state.get("sources", [])),
            "steps": [*state.get("steps", []), "discover_postings"],
        }

    @staticmethod
    def _deduplicate_postings(
        state: ConversationJobWorkflowState,
    ) -> ConversationJobWorkflowState:
        unique: list[ConversationJobCandidate] = []
        for candidate in state.get("candidates", []):
            if any(
                job_contents_match(
                    candidate.posting_content,
                    stored.posting_content,
                )
                for stored in unique
            ):
                continue
            unique.append(candidate)
        return {
            "unique_candidates": unique,
            "steps": [*state.get("steps", []), "deduplicate_postings"],
        }

    @staticmethod
    def _route_after_deduplication(
        state: ConversationJobWorkflowState,
    ) -> Literal["analyze", "complete"]:
        return "analyze" if state.get("unique_candidates") else "complete"

    def _analyze_postings(
        self,
        state: ConversationJobWorkflowState,
    ) -> ConversationJobWorkflowState:
        results: list[JobWorkflowResult] = []
        for candidate in state.get("unique_candidates", []):
            resolved = self.resolve(candidate)
            results.append({
                "candidate": candidate,
                "job_id": resolved.job_id,
                "created": resolved.created,
            })
        return {
            "results": results,
            "steps": [*state.get("steps", []), "analyze_postings"],
        }

    @staticmethod
    def _complete(
        state: ConversationJobWorkflowState,
    ) -> ConversationJobWorkflowState:
        return {"steps": [*state.get("steps", []), "complete"]}


__all__ = [
    "ConversationJobDiscoveryAI",
    "ConversationJobDiscoveryError",
    "ConversationJobWorkflow",
    "ConversationJobWorkflowState",
    "JOB_DISCOVERY_PROMPT_VERSION",
    "JOB_DISCOVERY_TOOL",
    "JOB_DISCOVERY_TOOL_NAME",
    "JobWorkflowResolution",
    "job_source_id",
]
