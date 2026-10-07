"""Integrated conversation analysis for experience drafts and job postings."""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from AI_Engine.analysis_metrics import (
    ANALYSIS_ARCHITECTURE_VERSION,
    AnalysisMetricsCollector,
    capture_analysis_metrics,
)
from AI_Engine.api.conversation_experiences import (
    _proposal_action,
    _proposal_from_result,
    _unprocessed_user_messages as _unprocessed_experience_messages,
)
from AI_Engine.api.conversation_jobs import (
    JOB_SCAN_ACTION,
    _sources_for_messages as _job_sources_for_messages,
    _unprocessed_user_messages as _unprocessed_job_messages,
    get_conversation_job_discovery_ai,
)
from AI_Engine.api.conversations import create_resource_id, get_conversation_or_404
from AI_Engine.api.experience_extractions import get_experience_ai
from AI_Engine.api.jobs import JobAnalyzeBody, analyze_job
from AI_Engine.auth.dependencies import get_current_user, require_csrf_user
from AI_Engine.chat_context import combined_token_count
from AI_Engine.conversation_analysis_workflow import ConversationAnalysisWorkflow
from AI_Engine.conversation_content_router import (
    AssistantConversationContext,
    CONTENT_ROUTER_PROMPT_VERSION,
    CONTENT_ROUTER_TOOL_NAME,
    ConversationContentRouterAI,
    ConversationRouteSource,
    RoutedConversationContent,
    conservative_fallback_route,
    route_source_id,
)
from AI_Engine.conversation_job_extraction import (
    ConversationJobCandidate,
    job_content_fingerprint,
    job_contents_match,
)
from AI_Engine.conversation_job_workflow import (
    ConversationJobDiscoveryAI,
    JOB_DISCOVERY_PROMPT_VERSION,
    JOB_DISCOVERY_TOOL_NAME,
    JobWorkflowResolution,
)
from AI_Engine.database.connection import get_database_session
from AI_Engine.database.models import (
    Attachment,
    Conversation,
    JobAnalysisRecord,
    Message,
    User,
    utc_now,
)
from AI_Engine.database.schemas import MessageResponse
from AI_Engine.experience_ai import ExperienceAI
from AI_Engine.llm_provider import get_ai_provider, get_chat_model_name
from AI_Engine.schemas import (
    EvidenceSource,
    EvidenceSourceType,
    ExperienceExtractionInputType,
    ExperienceExtractionRequest,
)


router = APIRouter(
    prefix="/api/v2/conversations",
    tags=["conversation-analysis"],
)
COMBINED_ANALYSIS_ACTION = "conversation_combined_analysis"


class ConversationAnalysisCreate(BaseModel):
    client_request_id: str = Field(min_length=1, max_length=80)


@lru_cache(maxsize=1)
def get_conversation_content_router_ai() -> ConversationContentRouterAI:
    return ConversationContentRouterAI()


def _assistant_context_excerpt(text: str, *, maximum_characters: int = 600) -> str:
    """Keep only question lines that can resolve the next short user reply."""

    question_lines = [
        line.strip()
        for line in text.splitlines()
        if "?" in line and line.strip()
    ]
    if not question_lines:
        return ""
    return "\n".join(question_lines[-3:])[-maximum_characters:]


def _needs_assistant_context(user_text: str) -> bool:
    """Detect a short value-only answer whose subject may live in a question."""

    normalized = user_text.strip()
    return bool(
        normalized
        and len(normalized) <= 200
        and re.search(
            r"\d|%|퍼센트|시간|분|초|개월|년|건|명|회|배",
            normalized,
            re.IGNORECASE,
        )
    )


def _routing_sources(
    conversation: Conversation,
    user_messages: list[Message],
    job_sources,
    database: Session,
) -> list[ConversationRouteSource]:
    """Build chronological router input while keeping assistant text non-evidence."""

    if not user_messages:
        return []
    sequence_by_message = {
        message.id: message.sequence for message in user_messages
    }
    sources = [
        ConversationRouteSource(
            source_id=route_source_id(source),
            message_id=source.message_id,
            role="user",
            text=source.text,
            sequence=sequence_by_message[source.message_id],
            attachment_id=source.attachment_id,
            title=source.title,
        )
        for source in job_sources
    ]
    first_sequence = min(sequence_by_message.values())
    last_sequence = max(sequence_by_message.values())
    assistants = database.scalars(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.role == "assistant",
            Message.status == "completed",
            Message.sequence >= max(0, first_sequence - 1),
            Message.sequence <= last_sequence,
        )
        .order_by(Message.sequence)
    ).all()
    user_by_sequence = {
        message.sequence: message for message in user_messages
    }
    for message in assistants:
        next_user = user_by_sequence.get(message.sequence + 1)
        if next_user is None or not _needs_assistant_context(next_user.content):
            continue
        excerpt = _assistant_context_excerpt(message.content)
        if not excerpt:
            continue
        sources.append(ConversationRouteSource(
            source_id=f"message:{message.id}",
            message_id=message.id,
            role="assistant",
            text=excerpt,
            sequence=message.sequence,
            title=f"대화 메시지 {message.sequence}",
        ))
    return sorted(sources, key=lambda item: (item.sequence, item.source_id))


def _route_id_for_evidence(
    source: EvidenceSource,
    messages: list[Message],
) -> str | None:
    if source.message_id:
        return f"message:{source.message_id}"
    if source.attachment_id:
        owner = next(
            (
                message
                for message in messages
                if source.attachment_id in (message.attachment_ids or [])
            ),
            None,
        )
        if owner is not None:
            return (
                f"message:{owner.id}:attachment:{source.attachment_id}"
            )
    return None


def _combined_action(message: Message) -> dict[str, Any] | None:
    return next(
        (
            action
            for action in (message.actions or [])
            if isinstance(action, dict)
            and action.get("type") == COMBINED_ANALYSIS_ACTION
        ),
        None,
    )


def _proposal_from_message(message: Message) -> dict[str, Any] | None:
    action = next(
        (
            item
            for item in (message.actions or [])
            if isinstance(item, dict)
            and item.get("type") == "experience_proposal"
        ),
        None,
    )
    return action.get("proposal") if action else None


def _response_from_message(
    message: Message,
    action: dict[str, Any],
    *,
    replayed: bool,
) -> dict[str, Any]:
    return {
        "run": action.get("run", {}),
        "message": MessageResponse.model_validate(message),
        "proposal": _proposal_from_message(message),
        "job_ids": action.get("job_ids", []),
        "replayed": replayed,
    }


def _prior_job_contents(
    messages: list[Message],
    user_id: str,
    database: Session,
) -> dict[str, list[str]]:
    job_ids_by_message: dict[str, list[str]] = {}
    all_job_ids: set[str] = set()
    for message in messages:
        job_ids = [
            str(job_id)
            for action in (message.actions or [])
            if isinstance(action, dict) and action.get("type") == JOB_SCAN_ACTION
            for job_id in (action.get("job_ids") or [])
        ]
        job_ids_by_message[message.id] = job_ids
        all_job_ids.update(job_ids)
    if not all_job_ids:
        return {message.id: [] for message in messages}
    jobs = database.scalars(
        select(JobAnalysisRecord).where(
            JobAnalysisRecord.user_id == user_id,
            JobAnalysisRecord.id.in_(all_job_ids),
        )
    ).all()
    content_by_id = {job.id: job.posting_content for job in jobs}
    return {
        message.id: [
            content_by_id[job_id]
            for job_id in job_ids_by_message[message.id]
            if job_id in content_by_id
        ]
        for message in messages
    }


def _without_job_postings(text: str, posting_contents: list[str]) -> str:
    remaining = text
    for posting_content in sorted(
        {item for item in posting_contents if item.strip()},
        key=len,
        reverse=True,
    ):
        remaining = remaining.replace(posting_content, "\n")
    remaining = re.sub(r"\n[ \t]+\n", "\n\n", remaining)
    remaining = re.sub(r"\n{3,}", "\n\n", remaining)
    return remaining.strip()


def _build_experience_sources(
    messages: list[Message],
    current_candidates: list[ConversationJobCandidate],
    user_id: str,
    database: Session,
) -> list[EvidenceSource]:
    exclusions = _prior_job_contents(messages, user_id, database)
    for candidate in current_candidates:
        exclusions.setdefault(candidate.message_id, []).append(
            candidate.posting_content
        )

    attachment_ids = list(dict.fromkeys(
        attachment_id
        for message in messages
        for attachment_id in (message.attachment_ids or [])
    ))
    attachments: dict[str, Attachment] = {}
    if attachment_ids:
        attachments = {
            item.id: item
            for item in database.scalars(
                select(Attachment).where(
                    Attachment.user_id == user_id,
                    Attachment.id.in_(attachment_ids),
                )
            ).all()
        }
        missing = [
            attachment_id
            for attachment_id in attachment_ids
            if attachment_id not in attachments
        ]
        if missing:
            raise ValueError("경험 분석에 필요한 첨부파일을 찾을 수 없습니다.")

    sources: list[EvidenceSource] = []
    for message in messages:
        posting_contents = exclusions.get(message.id, [])
        message_text = _without_job_postings(
            message.content,
            posting_contents,
        )
        if message_text:
            sources.append(EvidenceSource(
                id=f"source-{message.id}",
                type=EvidenceSourceType.MESSAGE_TEXT,
                title=f"대화 메시지 {message.sequence}",
                message_id=message.id,
                text=message_text,
            ))
    for attachment_id in attachment_ids:
        attachment = attachments[attachment_id]
        posting_contents = [
            posting_content
            for message in messages
            if attachment_id in (message.attachment_ids or [])
            for posting_content in exclusions.get(message.id, [])
        ]
        attachment_text = _without_job_postings(
            attachment.extracted_text,
            posting_contents,
        )
        if not attachment_text:
            continue
        sources.append(EvidenceSource(
            id=f"source-{attachment.id}",
            type=EvidenceSourceType.FILE,
            title=attachment.filename,
            attachment_id=attachment.id,
            filename=attachment.filename,
            mime_type=attachment.mime_type,
            uploaded_at=attachment.created_at,
            content_hash=attachment.content_hash,
            text=attachment_text,
        ))
    return sources


def _safe_failures(failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    labels = {
        "discover_jobs": "채용공고 탐색",
        "partition_sources": "대화내용 분류",
        "analyze_jobs": "채용공고 분석",
        "analyze_experiences": "경험 분석",
    }
    return [
        {
            "stage": failure.get("stage", "unknown"),
            "label": labels.get(failure.get("stage"), "분석"),
            **(
                {"source_message_id": failure["source_message_id"]}
                if failure.get("source_message_id")
                else {}
            ),
        }
        for failure in failures
    ]


@router.get("/{conversation_id}/analysis-status")
def get_conversation_analysis_status(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
) -> dict[str, Any]:
    conversation = get_conversation_or_404(conversation_id, current_user.id, database)
    experience_messages = _unprocessed_experience_messages(conversation, database)
    job_messages = _unprocessed_job_messages(conversation, database)
    pending_ids = {message.id for message in [*experience_messages, *job_messages]}
    return {
        "conversation_id": conversation.id,
        "unprocessed_message_count": len(pending_ids),
        "experience_message_count": len(experience_messages),
        "job_message_count": len(job_messages),
        "unprocessed_attachment_count": len({
            attachment_id
            for message in [*experience_messages, *job_messages]
            for attachment_id in (message.attachment_ids or [])
        }),
    }


@router.post("/{conversation_id}/analyses")
def analyze_conversation(
    conversation_id: str,
    request: ConversationAnalysisCreate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
    discovery_ai: ConversationJobDiscoveryAI = Depends(
        get_conversation_job_discovery_ai
    ),
    experience_ai: ExperienceAI = Depends(get_experience_ai),
) -> dict[str, Any]:
    """Analyze new conversation content into experience drafts and saved jobs."""

    conversation = get_conversation_or_404(conversation_id, current_user.id, database)
    existing_message = database.scalar(
        select(Message).where(
            Message.conversation_id == conversation.id,
            Message.client_request_id == request.client_request_id,
            Message.role == "assistant",
        )
    )
    if existing_message is not None:
        action = _combined_action(existing_message)
        if action is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The same request ID is already in use.",
            )
        return _response_from_message(existing_message, action, replayed=True)

    experience_messages = _unprocessed_experience_messages(conversation, database)
    job_messages = _unprocessed_job_messages(conversation, database)
    if not experience_messages and not job_messages:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="새로 분석할 대화내용이 없습니다.",
        )

    all_user_messages = sorted(
        {message.id: message for message in [*experience_messages, *job_messages]}.values(),
        key=lambda message: message.sequence,
    )
    job_sources = _job_sources_for_messages(
        all_user_messages,
        current_user.id,
        database,
    )
    use_content_router = isinstance(discovery_ai, ConversationJobDiscoveryAI)
    routing_sources = (
        _routing_sources(
            conversation,
            all_user_messages,
            job_sources,
            database,
        )
        if use_content_router
        else []
    )
    existing_jobs = list(database.scalars(
        select(JobAnalysisRecord).where(
            JobAnalysisRecord.user_id == current_user.id
        )
    ).all())
    jobs_by_fingerprint = {
        job_content_fingerprint(item.posting_content): item
        for item in existing_jobs
        if item.posting_content.strip()
    }

    def resolve_job(candidate: ConversationJobCandidate) -> JobWorkflowResolution:
        fingerprint = job_content_fingerprint(candidate.posting_content)
        item = jobs_by_fingerprint.get(fingerprint)
        if item is None:
            item = next(
                (
                    stored
                    for stored in existing_jobs
                    if job_contents_match(
                        candidate.posting_content,
                        stored.posting_content,
                    )
                ),
                None,
            )
        created = item is None
        if created:
            request_digest = hashlib.sha256(
                f"{request.client_request_id}:{fingerprint}".encode("utf-8")
            ).hexdigest()[:40]
            analyzed = analyze_job(
                body=JobAnalyzeBody(
                    client_request_id=f"combined-job-{request_digest}",
                    company_name=candidate.company_name,
                    role_name=candidate.role_name,
                    posting_title=candidate.posting_title,
                    source_url=candidate.source_url,
                    posting_content=candidate.posting_content,
                ),
                current_user=current_user,
                database=database,
            )
            item = database.get(JobAnalysisRecord, str(analyzed["jobId"]))
            if item is None:
                raise RuntimeError("분석된 채용공고가 저장되지 않았습니다.")
            existing_jobs.append(item)
            jobs_by_fingerprint[fingerprint] = item
        return JobWorkflowResolution(job_id=item.id, created=created)

    def build_experience_sources(
        candidates: list[ConversationJobCandidate],
    ) -> list[EvidenceSource]:
        return _build_experience_sources(
            experience_messages,
            candidates,
            current_user.id,
            database,
        )

    assistant_contexts: list[AssistantConversationContext] = []

    def build_routed_experience_sources(
        candidates: list[ConversationJobCandidate],
        routed: RoutedConversationContent,
    ) -> list[EvidenceSource]:
        nonlocal assistant_contexts
        sources = _build_experience_sources(
            experience_messages,
            candidates,
            current_user.id,
            database,
        )
        included: list[EvidenceSource] = []
        included_route_ids: set[str] = set()
        for source in sources:
            route_id = _route_id_for_evidence(source, experience_messages)
            # A source omitted from routing is retained conservatively.
            if route_id is None or (
                route_id not in routed.categories
                or route_id in routed.experience_source_ids
            ):
                included.append(source)
                if route_id is not None:
                    included_route_ids.add(route_id)
        assistant_contexts = [
            context
            for context in routed.assistant_contexts
            if set(context.for_user_source_ids) & included_route_ids
        ]
        return included

    def analyze_experiences(sources: list[EvidenceSource]):
        message_ids = list(dict.fromkeys(
            source.message_id
            for source in sources
            if source.message_id
        ))
        attachment_ids = list(dict.fromkeys(
            source.attachment_id
            for source in sources
            if source.attachment_id
        ))
        request_digest = hashlib.sha256(
            f"{request.client_request_id}:experience".encode("utf-8")
        ).hexdigest()[:40]
        organize_kwargs: dict[str, Any] = {"sources": sources}
        if assistant_contexts:
            organize_kwargs["assistant_contexts"] = assistant_contexts
        return experience_ai.organize(
            ExperienceExtractionRequest(
                client_request_id=f"combined-exp-{request_digest}",
                input_type=ExperienceExtractionInputType.CONVERSATION,
                conversation_id=conversation.id,
                from_sequence=experience_messages[0].sequence,
                to_sequence=experience_messages[-1].sequence,
                message_ids=message_ids,
                attachment_ids=attachment_ids,
            ),
            **organize_kwargs,
        )

    content_router = get_conversation_content_router_ai() if use_content_router else None

    def route_content(
        sources: list[ConversationRouteSource],
    ) -> RoutedConversationContent:
        if content_router is None:
            return conservative_fallback_route(sources)
        try:
            return content_router.route(sources)
        except Exception as error:
            # Preserve all user text and use only deterministic job extraction.
            return conservative_fallback_route(
                sources,
                reason=f"{error.__class__.__name__}: {str(error)[:240]}",
            )

    workflow = ConversationAnalysisWorkflow(
        discover_jobs=discovery_ai.discover,
        resolve_job=resolve_job,
        build_experience_sources=build_experience_sources,
        analyze_experiences=analyze_experiences,
        route_content=route_content if use_content_router else None,
        build_routed_experience_sources=(
            build_routed_experience_sources if use_content_router else None
        ),
    )
    run_id = f"ANALYSIS-RUN-{uuid4()}"
    unique_source_texts: dict[str, str] = {}
    for source in job_sources:
        source_key = (
            f"attachment:{source.attachment_id}"
            if source.attachment_id
            else f"message:{source.message_id}"
        )
        unique_source_texts.setdefault(source_key, source.text)
    metrics = AnalysisMetricsCollector(
        run_id=run_id,
        provider=get_ai_provider(),
        model=getattr(
            discovery_ai,
            "model_version",
            getattr(experience_ai, "model_version", get_chat_model_name()),
        ),
        architecture_version=ANALYSIS_ARCHITECTURE_VERSION,
        source_message_count=len({
            message.id for message in [*experience_messages, *job_messages]
        }),
        unique_source_tokens=combined_token_count(
            unique_source_texts.values()
        ),
    )
    with capture_analysis_metrics(metrics):
        state = workflow.invoke(job_sources, routing_sources=routing_sources)

    job_results = state.get("job_results", [])
    job_ids = list(dict.fromkeys(result["job_id"] for result in job_results))
    created_job_ids = list(dict.fromkeys(
        result["job_id"] for result in job_results if result["created"]
    ))
    existing_job_ids = list(dict.fromkeys(
        result["job_id"] for result in job_results if not result["created"]
    ))
    experience_result = state.get("experience_result")
    experience_count = (
        len(experience_result.experience_drafts)
        if experience_result is not None
        else 0
    )
    safe_failures = _safe_failures(state.get("failures", []))
    if safe_failures:
        metrics.status = "partial"
    metrics_payload = metrics.to_dict()

    proposal = None
    if experience_result is not None and experience_count:
        proposal = _proposal_from_result(experience_result)
        proposal["analysis_scope"] = {
            "message_count": len(experience_messages),
            "attachment_count": len({
                source.attachment_id
                for source in state.get("experience_sources", [])
                if source.attachment_id
            }),
            "from_sequence": experience_messages[0].sequence,
            "to_sequence": experience_messages[-1].sequence,
        }
        proposal["extraction_run"] = experience_result.run.model_dump(
            mode="json"
        )

    run = {
        "id": run_id,
        "status": "partial" if safe_failures else "succeeded",
        "source_message_ids": list(dict.fromkeys(
            message.id
            for message in [*experience_messages, *job_messages]
        )),
        "experience_count": experience_count,
        "job_count": len(job_ids),
        "created_job_count": len(created_job_ids),
        "existing_job_count": len(existing_job_ids),
        "failures": safe_failures,
        "metrics": metrics_payload,
        "workflow": {
            "engine": "langgraph",
            "steps": state.get("steps", []),
            "job_discovery_tool": JOB_DISCOVERY_TOOL_NAME,
            "job_discovery_prompt_version": JOB_DISCOVERY_PROMPT_VERSION,
            "content_router_tool": (
                CONTENT_ROUTER_TOOL_NAME if use_content_router else None
            ),
            "content_router_prompt_version": (
                CONTENT_ROUTER_PROMPT_VERSION if use_content_router else None
            ),
            "content_router_fallback_used": bool(
                state.get("content_route")
                and state["content_route"].fallback_used
            ),
            "content_router_fallback_reason": (
                state["content_route"].fallback_reason
                if state.get("content_route")
                else None
            ),
        },
    }

    result_parts = []
    if experience_count:
        result_parts.append(f"경험 초안 {experience_count}개")
    if job_ids:
        result_parts.append(f"채용공고 {len(job_ids)}개")
    if result_parts:
        content = f"대화내용에서 {'와 '.join(result_parts)}를 분석했어요."
    else:
        content = "대화내용에서 새로 정리할 경험이나 채용공고를 찾지 못했어요."
    if safe_failures:
        content += " 일부 분석은 완료하지 못해 다음 요청에서 다시 시도할 수 있어요."

    combined_action = {
        "type": COMBINED_ANALYSIS_ACTION,
        "run": run,
        "job_ids": job_ids,
        "created_job_ids": created_job_ids,
        "existing_job_ids": existing_job_ids,
    }
    actions: list[dict[str, Any]] = [combined_action]
    if proposal is not None:
        actions.append(_proposal_action(proposal))
    if job_ids:
        actions.append({"type": "open_job_analyses", "job_ids": job_ids})
        if len(job_ids) == 1:
            actions.append({"type": "open_job_analysis", "job_id": job_ids[0]})

    assistant_message = Message(
        id=create_resource_id("MSG"),
        conversation_id=conversation.id,
        client_request_id=request.client_request_id,
        sequence=conversation.message_count + 1,
        role="assistant",
        status="completed",
        content=content,
        requested_intent="auto",
        resolved_intents=[
            *(["experience"] if experience_count else []),
            *(["job"] if job_ids else []),
        ],
        proposal_ids=[proposal["id"]] if proposal is not None else [],
        actions=actions,
        completed_at=utc_now(),
    )
    database.add(assistant_message)

    unresolved_job_message_ids = {
        candidate.message_id
        for candidate in state.get("unique_job_candidates", [])
        if not any(
            result["candidate"] is candidate for result in job_results
        )
    }
    job_ids_by_message: dict[str, list[str]] = {
        message.id: [] for message in job_messages
    }
    for result in job_results:
        values = job_ids_by_message.setdefault(
            result["candidate"].message_id,
            [],
        )
        if result["job_id"] not in values:
            values.append(result["job_id"])
    if state.get("job_discovery_succeeded"):
        for message in job_messages:
            if message.id in unresolved_job_message_ids:
                continue
            message.actions = [
                *(message.actions or []),
                {
                    "type": JOB_SCAN_ACTION,
                    "run_id": run_id,
                    "job_ids": job_ids_by_message.get(message.id, []),
                },
            ]

    if state.get("experience_succeeded") and experience_messages:
        conversation.last_successful_extraction_sequence = (
            experience_messages[-1].sequence
        )
        conversation.last_extraction_at = utc_now()
    if proposal is not None:
        conversation.pending_proposal_count += 1
    conversation.message_count = assistant_message.sequence
    conversation.last_message_preview = content
    conversation.updated_at = utc_now()
    conversation.version += 1
    database.commit()
    return _response_from_message(
        assistant_message,
        combined_action,
        replayed=False,
    )


__all__ = [
    "COMBINED_ANALYSIS_ACTION",
    "ConversationAnalysisCreate",
    "analyze_conversation",
    "get_conversation_analysis_status",
    "router",
]
