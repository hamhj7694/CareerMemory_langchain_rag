"""Find and analyze job postings that appeared in an existing conversation."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from AI_Engine.api.conversations import create_resource_id, get_conversation_or_404
from AI_Engine.api.jobs import JobAnalyzeBody, analyze_job
from AI_Engine.auth.dependencies import get_current_user, require_csrf_user
from AI_Engine.conversation_job_extraction import (
    ConversationJobCandidate,
    JobSourceText,
    extract_job_posting_candidates,
    job_content_fingerprint,
    job_contents_match,
)
from AI_Engine.conversation_job_workflow import (
    ConversationJobDiscoveryAI,
    ConversationJobDiscoveryError,
    ConversationJobWorkflow,
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


router = APIRouter(prefix="/api/v2/conversations", tags=["conversation-jobs"])
JOB_SCAN_ACTION = "conversation_job_scan_source"
JOB_EXTRACTION_ACTION = "conversation_job_extraction"


class ConversationJobExtractionCreate(BaseModel):
    client_request_id: str = Field(min_length=1, max_length=80)


@lru_cache(maxsize=1)
def get_conversation_job_discovery_ai() -> ConversationJobDiscoveryAI:
    return ConversationJobDiscoveryAI()


def _was_scanned(message: Message) -> bool:
    return any(
        isinstance(action, dict) and action.get("type") == JOB_SCAN_ACTION
        for action in (message.actions or [])
    )


def _unprocessed_user_messages(
    conversation: Conversation,
    database: Session,
) -> list[Message]:
    messages = database.scalars(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.role == "user",
            Message.status == "completed",
            # Messages created by the dedicated job-analysis flow already point
            # to a saved JobAnalysisRecord and must not be analyzed again.
            Message.requested_intent != "job",
        )
        .order_by(Message.sequence)
    ).all()
    return [message for message in messages if not _was_scanned(message)]


def _sources_for_messages(
    messages: list[Message],
    user_id: str,
    database: Session,
) -> list[JobSourceText]:
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

    sources: list[JobSourceText] = []
    for message in messages:
        if message.content.strip():
            sources.append(JobSourceText(
                message_id=message.id,
                text=message.content,
                title=f"Conversation message {message.sequence}",
            ))
        for attachment_id in message.attachment_ids or []:
            attachment = attachments.get(attachment_id)
            if attachment is None or not attachment.extracted_text.strip():
                continue
            sources.append(JobSourceText(
                message_id=message.id,
                attachment_id=attachment.id,
                text=attachment.extracted_text,
                title=attachment.filename,
            ))
    return sources


def _extraction_action(message: Message) -> dict[str, Any] | None:
    return next(
        (
            action
            for action in (message.actions or [])
            if isinstance(action, dict) and action.get("type") == JOB_EXTRACTION_ACTION
        ),
        None,
    )


def _result_from_action(
    message: Message,
    action: dict[str, Any],
    *,
    replayed: bool,
) -> dict[str, Any]:
    return {
        "run": action.get("run", {}),
        "message": MessageResponse.model_validate(message),
        "job_ids": action.get("job_ids", []),
        "created_job_ids": action.get("created_job_ids", []),
        "existing_job_ids": action.get("existing_job_ids", []),
        "replayed": replayed,
    }


@router.get("/{conversation_id}/job-extraction-status")
def get_conversation_job_extraction_status(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
) -> dict[str, Any]:
    conversation = get_conversation_or_404(conversation_id, current_user.id, database)
    messages = _unprocessed_user_messages(conversation, database)
    sources = _sources_for_messages(messages, current_user.id, database)
    candidates = extract_job_posting_candidates(sources)
    return {
        "conversation_id": conversation.id,
        "unprocessed_message_count": len(messages),
        "unprocessed_attachment_count": len({
            attachment_id
            for message in messages
            for attachment_id in (message.attachment_ids or [])
        }),
        "candidate_count": len({
            job_content_fingerprint(candidate.posting_content)
            for candidate in candidates
        }),
    }


@router.post("/{conversation_id}/job-extractions")
def extract_conversation_jobs(
    conversation_id: str,
    request: ConversationJobExtractionCreate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
    discovery_ai: ConversationJobDiscoveryAI = Depends(
        get_conversation_job_discovery_ai
    ),
) -> dict[str, Any]:
    """Analyze all new job postings in a conversation exactly once."""

    conversation = get_conversation_or_404(conversation_id, current_user.id, database)
    existing_message = database.scalar(
        select(Message).where(
            Message.conversation_id == conversation.id,
            Message.client_request_id == request.client_request_id,
            Message.role == "assistant",
        )
    )
    if existing_message is not None:
        action = _extraction_action(existing_message)
        if action is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The same request ID is already in use.",
            )
        return _result_from_action(existing_message, action, replayed=True)

    messages = _unprocessed_user_messages(conversation, database)
    if not messages:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="There are no new conversation messages to scan.",
        )

    sources = _sources_for_messages(messages, current_user.id, database)
    existing_jobs = database.scalars(
        select(JobAnalysisRecord).where(JobAnalysisRecord.user_id == current_user.id)
    ).all()
    jobs_by_fingerprint = {
        job_content_fingerprint(item.posting_content): item
        for item in existing_jobs
        if item.posting_content.strip()
    }

    def resolve_candidate(
        candidate: ConversationJobCandidate,
    ) -> JobWorkflowResolution:
        fingerprint = job_content_fingerprint(candidate.posting_content)
        item = jobs_by_fingerprint.get(fingerprint)
        if item is None:
            item = next(
                (
                    existing
                    for existing in existing_jobs
                    if job_contents_match(
                        candidate.posting_content,
                        existing.posting_content,
                    )
                ),
                None,
            )
        created = item is None
        if created:
            request_digest = hashlib.sha256(
                f"{request.client_request_id}:{fingerprint}".encode("utf-8")
            ).hexdigest()[:40]
            result = analyze_job(
                body=JobAnalyzeBody(
                    client_request_id=f"chat-job-{request_digest}",
                    company_name=candidate.company_name,
                    role_name=candidate.role_name,
                    posting_title=candidate.posting_title,
                    source_url=candidate.source_url,
                    posting_content=candidate.posting_content,
                ),
                current_user=current_user,
                database=database,
            )
            item = database.get(JobAnalysisRecord, str(result["jobId"]))
            if item is None:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="The analyzed job result was not saved.",
                )
            jobs_by_fingerprint[fingerprint] = item
            existing_jobs.append(item)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The job result could not be resolved.",
            )
        return JobWorkflowResolution(job_id=item.id, created=created)

    workflow = ConversationJobWorkflow(
        discover=discovery_ai.discover,
        resolve=resolve_candidate,
    )
    try:
        workflow_state = workflow.invoke(sources)
    except HTTPException:
        raise
    except ConversationJobDiscoveryError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="채용공고 탐색 결과가 올바르지 않습니다. 다시 시도해 주세요.",
        ) from error
    except Exception as error:
        error_text = str(error).lower()
        if "quota" in error_text or "resource_exhausted" in error_text or "429" in error_text:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="AI 사용 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.",
            ) from error
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="대화에서 채용공고를 찾는 중 AI 호출에 실패했습니다.",
        ) from error

    workflow_results = workflow_state.get("results", [])
    created_job_ids = list(dict.fromkeys(
        result["job_id"] for result in workflow_results if result["created"]
    ))
    existing_job_ids = list(dict.fromkeys(
        result["job_id"] for result in workflow_results if not result["created"]
    ))
    job_ids = list(dict.fromkeys(
        result["job_id"] for result in workflow_results
    ))
    job_ids_by_message: dict[str, list[str]] = {message.id: [] for message in messages}
    for result in workflow_results:
        message_job_ids = job_ids_by_message[result["candidate"].message_id]
        if result["job_id"] not in message_job_ids:
            message_job_ids.append(result["job_id"])

    run_id = f"JOB-RUN-{uuid4()}"
    run = {
        "id": run_id,
        "source_message_ids": [message.id for message in messages],
        "candidate_count": len(workflow_state.get("unique_candidates", [])),
        "created_count": len(created_job_ids),
        "existing_count": len(existing_job_ids),
        "workflow": {
            "engine": "langgraph",
            "steps": workflow_state.get("steps", []),
            "discovery_tool": JOB_DISCOVERY_TOOL_NAME,
            "prompt_version": JOB_DISCOVERY_PROMPT_VERSION,
        },
    }

    if created_job_ids and existing_job_ids:
        content = (
            f"채용공고 {len(created_job_ids)}개를 새로 분석했고, "
            f"이미 분석된 공고 {len(existing_job_ids)}개를 확인했어요."
        )
    elif created_job_ids:
        content = f"채용공고 {len(created_job_ids)}개를 분석했어요."
    elif existing_job_ids:
        content = f"이미 분석된 채용공고 {len(existing_job_ids)}개를 확인했어요."
    else:
        content = "새로 분석할 채용공고를 대화에서 찾지 못했어요."

    actions: list[dict[str, Any]] = [{
        "type": JOB_EXTRACTION_ACTION,
        "run": run,
        "job_ids": job_ids,
        "created_job_ids": created_job_ids,
        "existing_job_ids": existing_job_ids,
    }]
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
        requested_intent="job",
        resolved_intents=["job"],
        actions=actions,
        completed_at=utc_now(),
    )
    database.add(assistant_message)

    for message in messages:
        message.actions = [
            *(message.actions or []),
            {
                "type": JOB_SCAN_ACTION,
                "run_id": run_id,
                "job_ids": job_ids_by_message[message.id],
            },
        ]

    conversation.message_count = assistant_message.sequence
    conversation.last_message_preview = content
    conversation.updated_at = utc_now()
    conversation.version += 1
    database.commit()
    return _result_from_action(assistant_message, actions[0], replayed=False)


__all__ = [
    "ConversationJobExtractionCreate",
    "extract_conversation_jobs",
    "get_conversation_job_discovery_ai",
    "get_conversation_job_extraction_status",
    "router",
]
