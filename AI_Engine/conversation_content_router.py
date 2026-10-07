"""Conservative function-calling router for integrated conversation analysis."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import json
import re
from typing import Any, Literal

from AI_Engine.analysis_metrics import tracked_responses_create
from AI_Engine.conversation_job_extraction import (
    ConversationJobCandidate,
    JobSourceText,
    extract_job_posting_candidates,
    job_contents_match,
)
from AI_Engine.llm_provider import create_structured_client, get_chat_model_name


CONTENT_ROUTER_TOOL_NAME = "route_conversation_content"
CONTENT_ROUTER_PROMPT_VERSION = "conversation-content-router-v2"

CONTENT_ROUTER_SYSTEM_PROMPT = """
[role]
You route a chronological career conversation before specialist analysis.

[task]
- Classify every user source as experience, job, mixed, irrelevant, or uncertain.
- Extract every complete job posting as an exact contiguous source substring.
- Link an assistant message only when it is the immediately preceding question needed
  to understand an elliptical user answer such as "12% improved".

[safety]
- User and attachment sources are evidence. Assistant sources are context only.
- Never classify an assistant source as evidence or extract a posting from it.
- Never import a factual claim asserted only by the assistant.
- Use uncertain instead of irrelevant whenever a user source might contain career facts.
- Do not rewrite, summarize, translate, or normalize posting_content.
- source_index and assistant_context_source_indexes must be copied from the input.
- Returning an empty job_postings array is valid.

[format]
Call route_conversation_content exactly once.
""".strip()

CONTENT_ROUTER_TOOL: dict[str, Any] = {
    "type": "function",
    "name": CONTENT_ROUTER_TOOL_NAME,
    "description": "Route user evidence and find exact job-posting sections.",
    "parameters": {
        "type": "object",
        "properties": {
            "routes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_index": {"type": "integer", "minimum": 1},
                        "category": {
                            "type": "string",
                            "enum": [
                                "experience",
                                "job",
                                "mixed",
                                "irrelevant",
                                "uncertain",
                            ],
                        },
                        "assistant_context_source_indexes": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 1},
                        },
                    },
                    "required": [
                        "source_index",
                        "category",
                        "assistant_context_source_indexes",
                    ],
                    "additionalProperties": False,
                },
            },
            "job_postings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_index": {"type": "integer", "minimum": 1},
                        "posting_content": {"type": "string"},
                        "company_name": {"type": "string"},
                        "role_name": {"type": "string"},
                        "posting_title": {"type": "string"},
                        "source_url": {"type": ["string", "null"]},
                    },
                    "required": [
                        "source_index",
                        "posting_content",
                        "company_name",
                        "role_name",
                        "posting_title",
                        "source_url",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["routes", "job_postings"],
        "additionalProperties": False,
    },
    "strict": True,
}


RouteCategory = Literal[
    "experience",
    "job",
    "mixed",
    "irrelevant",
    "uncertain",
]


@dataclass(frozen=True)
class ConversationRouteSource:
    source_id: str
    message_id: str
    role: Literal["user", "assistant"]
    text: str
    sequence: int
    attachment_id: str | None = None
    title: str = ""


@dataclass(frozen=True)
class AssistantConversationContext:
    source_id: str
    text: str
    for_user_source_ids: tuple[str, ...]
    required_subject: str = ""


@dataclass
class RoutedConversationContent:
    categories: dict[str, RouteCategory]
    job_candidates: list[ConversationJobCandidate]
    assistant_contexts: list[AssistantConversationContext] = field(
        default_factory=list
    )
    fallback_used: bool = False
    fallback_reason: str | None = None

    @property
    def experience_source_ids(self) -> set[str]:
        return {
            source_id
            for source_id, category in self.categories.items()
            if category in {"experience", "mixed", "uncertain"}
        }


class ConversationContentRouterError(RuntimeError):
    """Raised when the model violates the strict routing contract."""


def route_source_id(source: JobSourceText) -> str:
    if source.attachment_id:
        return f"message:{source.message_id}:attachment:{source.attachment_id}"
    return f"message:{source.message_id}"


def _item_value(item: Any, name: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(name)
    return getattr(item, name, None)


def _function_payload(response: Any) -> Mapping[str, Any]:
    output = getattr(response, "output", None)
    if not isinstance(output, Sequence) or isinstance(output, (str, bytes)):
        raise ConversationContentRouterError(
            "The router model did not return a function call."
        )
    calls = [
        item
        for item in output
        if _item_value(item, "type") == "function_call"
        and _item_value(item, "name") == CONTENT_ROUTER_TOOL_NAME
    ]
    if len(calls) != 1:
        raise ConversationContentRouterError(
            f"{CONTENT_ROUTER_TOOL_NAME} must be called exactly once."
        )
    arguments = _item_value(calls[0], "arguments")
    if not isinstance(arguments, str):
        raise ConversationContentRouterError("Function arguments must be JSON text.")
    try:
        payload = json.loads(arguments)
    except json.JSONDecodeError as error:
        raise ConversationContentRouterError(
            "Function arguments are not valid JSON."
        ) from error
    if not isinstance(payload, Mapping):
        raise ConversationContentRouterError("Router output must be an object.")
    if not isinstance(payload.get("routes"), list) or not isinstance(
        payload.get("job_postings"), list
    ):
        raise ConversationContentRouterError(
            "Router output must contain routes and job_postings arrays."
        )
    return payload


def _source_batches(
    sources: list[ConversationRouteSource],
    *,
    maximum_characters: int = 60_000,
) -> list[list[ConversationRouteSource]]:
    batches: list[list[ConversationRouteSource]] = []
    current: list[ConversationRouteSource] = []
    current_size = 0
    for source in sources:
        source_size = len(source.text)
        if current and current_size + source_size > maximum_characters:
            batches.append(current)
            current = []
            current_size = 0
        current.append(source)
        current_size += source_size
    if current:
        batches.append(current)
    return batches


def _question_subject(text: str) -> str:
    """Extract an explicit metric/target from a narrow quantitative question."""

    for line in reversed(text.splitlines()):
        normalized = line.strip()
        match = re.search(
            r"(?:^|[.!?]\s*)([^.!?]{1,80}?)(?:은|는|이|가)\s*"
            r"(?:얼마나|몇\s*%|몇\s*퍼센트)",
            normalized,
        )
        if match:
            return match.group(1).strip(" -:[]()")
    return ""


def _looks_like_complete_job_posting(text: str) -> bool:
    """Reject isolated requirement bullets while retaining full postings."""

    compact = " ".join(text.split())
    if len(compact) < 120:
        return False
    responsibility = re.search(
        r"주요\s*업무|담당\s*업무|업무\s*내용|responsibilit(?:y|ies)",
        text,
        re.IGNORECASE,
    )
    qualification = re.search(
        r"자격\s*요건|지원\s*자격|필수\s*요건|qualifications?|requirements?",
        text,
        re.IGNORECASE,
    )
    preferred = re.search(
        r"우대\s*사항|우대\s*조건|preferred|nice\s+to\s+have",
        text,
        re.IGNORECASE,
    )
    posting = re.search(
        r"채용\s*공고|모집\s*(?:분야|직무)|job\s+description",
        text,
        re.IGNORECASE,
    )
    return bool(
        (responsibility and qualification)
        or sum(bool(item) for item in (responsibility, qualification, preferred, posting))
        >= 3
    )


class ConversationContentRouterAI:
    """Route content once, preserving raw user evidence and limiting AI context."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        provider: str | None = None,
        model_version: str | None = None,
    ) -> None:
        self.client = client or create_structured_client(provider)
        self.model_version = model_version or get_chat_model_name(provider)

    def route(
        self,
        sources: list[ConversationRouteSource],
    ) -> RoutedConversationContent:
        ordered = sorted(sources, key=lambda item: (item.sequence, item.source_id))
        user_sources = {
            source.source_id: source for source in ordered if source.role == "user"
        }
        assistant_sources = {
            source.source_id: source
            for source in ordered
            if source.role == "assistant"
        }
        if not user_sources:
            return RoutedConversationContent(categories={}, job_candidates=[])

        categories: dict[str, RouteCategory] = {}
        context_links: dict[str, set[str]] = {}
        candidates: list[ConversationJobCandidate] = []
        source_by_index = {
            index: source for index, source in enumerate(ordered, start=1)
        }
        index_by_source_id = {
            source.source_id: index for index, source in source_by_index.items()
        }
        for batch in _source_batches(ordered):
            response = tracked_responses_create(
                self.client,
                stage="content_routing",
                model=self.model_version,
                input=json.dumps([
                    {
                        "source_index": index_by_source_id[source.source_id],
                        "role": source.role,
                        "sequence": source.sequence,
                        "title": source.title,
                        "content": source.text,
                    }
                    for source in batch
                ], ensure_ascii=False),
                tools=[CONTENT_ROUTER_TOOL],
                tool_choice={
                    "type": "function",
                    "name": CONTENT_ROUTER_TOOL_NAME,
                },
                instructions=CONTENT_ROUTER_SYSTEM_PROMPT,
                max_output_tokens=3_000,
            )
            payload = _function_payload(response)
            for raw_route in payload["routes"]:
                if not isinstance(raw_route, Mapping):
                    continue
                source_index = raw_route.get("source_index")
                indexed_source = source_by_index.get(source_index)
                source_id = (
                    indexed_source.source_id if indexed_source is not None else None
                )
                category = raw_route.get("category")
                if source_id not in user_sources or category not in {
                    "experience", "job", "mixed", "irrelevant", "uncertain"
                }:
                    # Assistant routes and unknown IDs are not evidence. Ignore
                    # an invalid item without discarding valid user routes.
                    continue
                categories[str(source_id)] = category
                raw_context_indexes = raw_route.get(
                    "assistant_context_source_indexes"
                )
                if not isinstance(raw_context_indexes, list):
                    raw_context_indexes = []
                user_sequence = user_sources[str(source_id)].sequence
                for context_index in raw_context_indexes:
                    indexed_context = source_by_index.get(context_index)
                    context_id = (
                        indexed_context.source_id
                        if indexed_context is not None
                        else None
                    )
                    context = assistant_sources.get(context_id)
                    # Only the immediately preceding assistant turn can resolve
                    # an elliptical user reply. Later assistant claims are ignored.
                    if context is None or context.sequence != user_sequence - 1:
                        continue
                    context_links.setdefault(str(context_id), set()).add(
                        str(source_id)
                    )

            for raw_job in payload["job_postings"]:
                if not isinstance(raw_job, Mapping):
                    continue
                source_index = raw_job.get("source_index")
                indexed_source = source_by_index.get(source_index)
                source_id = (
                    indexed_source.source_id if indexed_source is not None else None
                )
                source = user_sources.get(source_id)
                posting_content = raw_job.get("posting_content")
                if (
                    source is None
                    or not isinstance(posting_content, str)
                    or len(posting_content.strip()) < 60
                    or posting_content not in source.text
                    or not _looks_like_complete_job_posting(posting_content)
                ):
                    # Deterministic extraction below remains available as a
                    # safety net when one model item is not an exact excerpt.
                    continue
                source_url = raw_job.get("source_url")
                if source_url and (
                    not isinstance(source_url, str) or source_url not in source.text
                ):
                    source_url = None
                candidates.append(ConversationJobCandidate(
                    message_id=source.message_id,
                    attachment_id=source.attachment_id,
                    posting_content=posting_content.strip(),
                    company_name=str(raw_job.get("company_name") or "").strip()[:200],
                    role_name=str(raw_job.get("role_name") or "").strip()[:200],
                    posting_title=str(raw_job.get("posting_title") or "").strip()[:300],
                    source_url=source_url.strip() if source_url else None,
                ))

        # Omitted user content is retained as uncertain rather than silently lost.
        for source_id in user_sources:
            categories.setdefault(source_id, "uncertain")

        # The caller only supplies compact assistant question excerpts. Their
        # adjacency to a short user reply is deterministic conversation data,
        # so do not lose the link when the model omits an optional context ID.
        user_by_sequence = {
            source.sequence: source for source in user_sources.values()
        }
        for context_id, context in assistant_sources.items():
            next_user = user_by_sequence.get(context.sequence + 1)
            if (
                next_user is not None
                and "?" in context.text
                and len(next_user.text.strip()) <= 200
            ):
                context_links.setdefault(context_id, set()).add(
                    next_user.source_id
                )
                if categories.get(next_user.source_id) == "irrelevant":
                    categories[next_user.source_id] = "uncertain"

        job_sources = [
            JobSourceText(
                message_id=source.message_id,
                attachment_id=source.attachment_id,
                text=source.text,
                title=source.title,
            )
            for source in user_sources.values()
        ]
        deterministic = extract_job_posting_candidates(job_sources)
        for candidate in deterministic:
            if not _looks_like_complete_job_posting(candidate.posting_content):
                continue
            if not any(
                job_contents_match(candidate.posting_content, item.posting_content)
                for item in candidates
            ):
                candidates.append(candidate)

        for candidate in candidates:
            source = next(
                (
                    item
                    for item in user_sources.values()
                    if item.message_id == candidate.message_id
                    and item.attachment_id == candidate.attachment_id
                ),
                None,
            )
            if source is None:
                continue
            remaining = source.text.replace(candidate.posting_content, "").strip()
            categories[source.source_id] = "mixed" if remaining else "job"

        contexts = [
            AssistantConversationContext(
                source_id=context_id,
                text=assistant_sources[context_id].text,
                for_user_source_ids=tuple(sorted(user_ids)),
                required_subject=_question_subject(
                    assistant_sources[context_id].text
                ),
            )
            for context_id, user_ids in context_links.items()
        ]
        return RoutedConversationContent(
            categories=categories,
            job_candidates=candidates,
            assistant_contexts=contexts,
        )


def conservative_fallback_route(
    sources: list[ConversationRouteSource],
    *,
    reason: str | None = None,
) -> RoutedConversationContent:
    """Preserve every user source when the AI router is unavailable."""

    user_sources = [source for source in sources if source.role == "user"]
    job_sources = [
        JobSourceText(
            message_id=source.message_id,
            attachment_id=source.attachment_id,
            text=source.text,
            title=source.title,
        )
        for source in user_sources
    ]
    candidates = [
        candidate
        for candidate in extract_job_posting_candidates(job_sources)
        if _looks_like_complete_job_posting(candidate.posting_content)
    ]
    categories: dict[str, RouteCategory] = {
        source.source_id: "uncertain" for source in user_sources
    }
    for candidate in candidates:
        source = next(
            (
                item
                for item in user_sources
                if item.message_id == candidate.message_id
                and item.attachment_id == candidate.attachment_id
            ),
            None,
        )
        if source is not None:
            remaining = source.text.replace(candidate.posting_content, "").strip()
            categories[source.source_id] = "mixed" if remaining else "job"
    return RoutedConversationContent(
        categories=categories,
        job_candidates=candidates,
        fallback_used=True,
        fallback_reason=reason,
    )


__all__ = [
    "AssistantConversationContext",
    "CONTENT_ROUTER_PROMPT_VERSION",
    "CONTENT_ROUTER_TOOL_NAME",
    "ConversationContentRouterAI",
    "ConversationContentRouterError",
    "ConversationRouteSource",
    "RoutedConversationContent",
    "conservative_fallback_route",
    "route_source_id",
]
