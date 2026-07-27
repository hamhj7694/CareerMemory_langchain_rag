"""Execute the dedicated AI selected by the chat ``auto`` intent router."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from AI_Engine.database.models import Attachment, Conversation, Message, User, utc_now
from AI_Engine.schemas import (
    EvidenceSource,
    EvidenceSourceType,
    ExperienceExtractionInputType,
    ExperienceExtractionRequest,
)


@dataclass(frozen=True)
class AutomaticRouteResult:
    """Persisted assistant result produced by a dedicated auto route."""

    message: Message
    proposal: dict | None = None


def get_experience_ai():
    """Resolve the API singleton lazily to avoid an API-router import cycle."""

    from AI_Engine.api.experience_extractions import (
        get_experience_ai as resolve_experience_ai,
    )

    return resolve_experience_ai()


def analyze_job(*args, **kwargs):
    """Resolve the job analysis endpoint lazily to avoid an API-router import cycle."""

    from AI_Engine.api.jobs import analyze_job as run_job_analysis

    return run_job_analysis(*args, **kwargs)


def execute_automatic_route(
    route: str,
    *,
    database: Session,
    conversation: Conversation,
    current_user: User,
    user_message: Message,
) -> AutomaticRouteResult | None:
    """Run the selected non-chat AI. Plain chat returns ``None``."""

    if route == "experience_extraction":
        return _execute_experience(
            database=database,
            conversation=conversation,
            current_user=current_user,
            user_message=user_message,
        )
    if route == "job_analysis":
        return _execute_job(
            database=database,
            conversation=conversation,
            current_user=current_user,
            user_message=user_message,
        )
    return None


def _load_attachments(
    database: Session,
    user_id: str,
    attachment_ids: list[str],
) -> list[Attachment]:
    if not attachment_ids:
        return []
    attachments = list(
        database.scalars(
            select(Attachment).where(
                Attachment.user_id == user_id,
                Attachment.id.in_(attachment_ids),
            )
        )
    )
    attachment_by_id = {attachment.id: attachment for attachment in attachments}
    return [
        attachment_by_id[attachment_id]
        for attachment_id in attachment_ids
        if attachment_id in attachment_by_id
    ]


def _experience_sources(
    user_message: Message,
    attachments: list[Attachment],
) -> list[EvidenceSource]:
    sources: list[EvidenceSource] = []
    if user_message.content.strip():
        sources.append(
            EvidenceSource(
                id=f"source-{user_message.id}",
                type=EvidenceSourceType.MESSAGE_TEXT,
                title=f"대화 메시지 {user_message.sequence}",
                message_id=user_message.id,
                text=user_message.content,
            )
        )
    sources.extend(
        EvidenceSource(
            id=f"source-{attachment.id}",
            type=EvidenceSourceType.FILE,
            title=attachment.filename,
            attachment_id=attachment.id,
            filename=attachment.filename,
            mime_type=attachment.mime_type,
            uploaded_at=attachment.created_at,
            content_hash=attachment.content_hash,
            text=attachment.extracted_text,
        )
        for attachment in attachments
        if attachment.extracted_text.strip()
    )
    return sources


def _proposal_from_extraction(result) -> dict:
    experiences = [
        draft.model_dump(mode="json")
        for draft in result.experience_drafts
    ]
    source_by_id = {
        source.id: source.model_dump(mode="json")
        for source in result.sources
    }
    for experience in experiences:
        experience["source_refs"] = [
            source_by_id[source_id]
            for source_id in experience.get("source_ref_ids", [])
            if source_id in source_by_id
        ]
    return {
        "id": f"CHAT-PROPOSAL-{uuid4()}",
        "version": 1,
        "type": "create_experiences",
        "status": "pending",
        "title": "경험 AI 분석 결과",
        "approved_experience_indexes": [],
        "payload": {"experiences": experiences},
        "extraction_run": result.run.model_dump(mode="json"),
    }


def _execute_experience(
    *,
    database: Session,
    conversation: Conversation,
    current_user: User,
    user_message: Message,
) -> AutomaticRouteResult:
    attachments = _load_attachments(
        database,
        current_user.id,
        user_message.attachment_ids,
    )
    sources = _experience_sources(user_message, attachments)
    if not sources:
        raise ValueError("경험을 정리할 텍스트나 파일 내용이 없습니다.")

    result = get_experience_ai().organize(
        ExperienceExtractionRequest(
            client_request_id=user_message.client_request_id or user_message.id,
            input_type=ExperienceExtractionInputType.DIRECT_INPUT,
            text=user_message.content.strip() or None,
            attachment_ids=user_message.attachment_ids,
        ),
        sources=sources,
    )
    proposal = _proposal_from_extraction(result)
    proposal["analysis_scope"] = {
        "message_count": 1,
        "attachment_count": len(user_message.attachment_ids),
        "from_sequence": user_message.sequence,
        "to_sequence": user_message.sequence,
    }

    assistant = Message(
        id=f"MSG-{uuid4()}",
        conversation_id=conversation.id,
        sequence=user_message.sequence + 1,
        role="assistant",
        status="completed",
        content=(
            f"입력한 내용에서 경험 초안 {len(result.experience_drafts)}개를 "
            "정리했습니다. 저장 전에 내용을 확인해 주세요."
        ),
        requested_intent="auto",
        resolved_intents=["experience_extraction"],
        proposal_ids=[proposal["id"]],
        actions=[{"type": "experience_proposal", "proposal": proposal}],
        completed_at=utc_now(),
    )
    database.add(assistant)
    conversation.message_count = assistant.sequence
    conversation.pending_proposal_count += 1
    conversation.last_successful_extraction_sequence = user_message.sequence
    conversation.last_extraction_at = utc_now()
    conversation.last_message_preview = assistant.content
    conversation.version += 1
    database.commit()
    database.refresh(assistant)
    return AutomaticRouteResult(message=assistant, proposal=proposal)


def _execute_job(
    *,
    database: Session,
    conversation: Conversation,
    current_user: User,
    user_message: Message,
) -> AutomaticRouteResult:
    from AI_Engine.api.jobs import JobAnalyzeBody

    attachments = _load_attachments(
        database,
        current_user.id,
        user_message.attachment_ids,
    )
    posting_content = "\n\n".join(
        value
        for value in [
            user_message.content.strip(),
            *[
                attachment.extracted_text.strip()
                for attachment in attachments
            ],
        ]
        if value
    )
    if not posting_content:
        raise ValueError("분석할 채용공고 원문이 없습니다.")

    analyzed = analyze_job(
        JobAnalyzeBody(
            client_request_id=user_message.client_request_id or user_message.id,
            posting_content=posting_content,
        ),
        current_user=current_user,
        database=database,
    )
    requirement_count = len(analyzed.get("requirements", []))
    assistant = Message(
        id=f"MSG-{uuid4()}",
        conversation_id=conversation.id,
        sequence=user_message.sequence + 1,
        role="assistant",
        status="completed",
        content=(
            f"채용공고 요구사항 {requirement_count}개와 보유 경험 매칭을 "
            "완료했습니다."
        ),
        requested_intent="auto",
        resolved_intents=["job_analysis"],
        actions=[
            {
                "type": "open_job_analysis",
                "job_id": analyzed["jobId"],
            }
        ],
        completed_at=utc_now(),
    )
    database.add(assistant)
    conversation.message_count = assistant.sequence
    conversation.last_message_preview = assistant.content
    conversation.version += 1
    database.commit()
    database.refresh(assistant)
    return AutomaticRouteResult(message=assistant)


__all__ = ["AutomaticRouteResult", "execute_automatic_route"]
