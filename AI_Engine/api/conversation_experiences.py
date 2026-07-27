"""커리어 챗의 경험 정리 입력을 기존 경험정리 AI와 연결한다."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from AI_Engine.api.conversations import create_resource_id, get_conversation_or_404
from AI_Engine.api.experience_extractions import get_experience_ai
from AI_Engine.auth.dependencies import get_current_user, require_csrf_user
from AI_Engine.database.connection import get_database_session
from AI_Engine.database.models import (
    Attachment,
    JobAnalysisRecord,
    Message,
    User,
    utc_now,
)
from AI_Engine.experience_ai import ExperienceAI, ExperienceAIInputError, ExperienceAIOutputError
from AI_Engine.experience_file_text import extract_experience_file_texts
from AI_Engine.job_file_text import JobFile, JobFileExtractionError, JobFileInputError, MAX_JOB_FILE_BYTES
from AI_Engine.schemas import (
    EvidenceSource,
    EvidenceSourceType,
    ExperienceExtractionInputType,
    ExperienceExtractionRequest,
)


router = APIRouter(prefix="/api/v2/conversations", tags=["conversation-experiences"])


class ConversationProposalUpdate(BaseModel):
    version: int
    payload: dict
    approved_experience_indexes: list[int] = Field(default_factory=list)
    status: str = "edited"


class ConversationJobRecord(BaseModel):
    client_request_id: str
    job_id: str
    content: str = ""
    filenames: list[str] = Field(default_factory=list)


class ConversationExtractionCreate(BaseModel):
    client_request_id: str


def _proposal_from_result(result) -> dict:
    experiences = [draft.model_dump(mode="json") for draft in result.experience_drafts]
    source_by_id = {
        source.id: source.model_dump(mode="json") for source in result.sources
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
    }


def _proposal_action(proposal: dict) -> dict:
    return {"type": "experience_proposal", "proposal": proposal}


def _unprocessed_user_messages(conversation, database: Session) -> list[Message]:
    """마지막 정리 이후 사용자 발화 중 공고 원문이 아닌 메시지만 가져온다."""

    return list(database.scalars(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.role == "user",
            Message.status == "completed",
            Message.sequence > conversation.last_successful_extraction_sequence,
            Message.requested_intent != "job",
        )
        .order_by(Message.sequence)
    ))


@router.get("/{conversation_id}/experience-extraction-status")
def get_chat_extraction_status(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
):
    """상단 경험 정리 버튼에 아직 처리하지 않은 대화 개수를 반환한다."""

    conversation = get_conversation_or_404(conversation_id, current_user.id, database)
    messages = _unprocessed_user_messages(conversation, database)
    return {
        "conversation_id": conversation.id,
        "unprocessed_message_count": len(messages),
        "unprocessed_attachment_count": len({
            attachment_id
            for message in messages
            for attachment_id in message.attachment_ids
        }),
        "last_successful_extraction_sequence": conversation.last_successful_extraction_sequence,
        "last_extraction_at": conversation.last_extraction_at,
    }


@router.post("/{conversation_id}/experience-extractions")
def extract_recent_chat_experiences(
    conversation_id: str,
    request: ConversationExtractionCreate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
    experience_ai: ExperienceAI = Depends(get_experience_ai),
):
    """마지막 정리 이후 사용자 발화를 기존 ExperienceAI로 구조화한다."""

    conversation = get_conversation_or_404(conversation_id, current_user.id, database)
    existing_assistant = database.scalar(select(Message).where(
        Message.client_request_id == request.client_request_id,
        Message.role == "assistant",
    ))
    if existing_assistant is not None:
        action = next(
            (item for item in existing_assistant.actions if item.get("type") == "experience_proposal"),
            None,
        )
        if action is None:
            raise HTTPException(status_code=409, detail="저장된 대화 경험 분석 결과를 찾지 못했습니다.")
        return {
            "run": action["proposal"].get("extraction_run", {"id": "replayed"}),
            "message": existing_assistant,
            "proposal": action["proposal"],
        }

    messages = _unprocessed_user_messages(conversation, database)
    if not messages:
        raise HTTPException(status_code=409, detail="새로 정리할 대화내용이 없습니다.")
    sources = [
        EvidenceSource(
            id=f"source-{message.id}",
            type=EvidenceSourceType.MESSAGE_TEXT,
            title=f"대화 메시지 {message.sequence}",
            message_id=message.id,
            text=message.content,
        )
        for message in messages
        if message.content.strip()
    ]
    attachment_ids = list(dict.fromkeys(
        attachment_id
        for message in messages
        for attachment_id in message.attachment_ids
    ))
    if attachment_ids:
        attachments = list(database.scalars(
            select(Attachment).where(
                Attachment.user_id == current_user.id,
                Attachment.id.in_(attachment_ids),
            )
        ))
        attachment_by_id = {item.id: item for item in attachments}
        missing_attachment_ids = [
            attachment_id for attachment_id in attachment_ids
            if attachment_id not in attachment_by_id
        ]
        if missing_attachment_ids:
            raise HTTPException(
                status_code=422,
                detail="경험 정리에 사용할 첨부 파일을 찾을 수 없습니다.",
            )
        sources.extend([
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
        ])
    if not sources:
        raise HTTPException(status_code=422, detail="분석 가능한 대화내용이 없습니다.")

    try:
        result = experience_ai.organize(
            ExperienceExtractionRequest(
                client_request_id=request.client_request_id,
                input_type=ExperienceExtractionInputType.CONVERSATION,
                conversation_id=conversation.id,
                from_sequence=messages[0].sequence,
                to_sequence=messages[-1].sequence,
                message_ids=[message.id for message in messages],
                attachment_ids=attachment_ids,
            ),
            sources=sources,
        )
    except ExperienceAIInputError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ExperienceAIOutputError as error:
        raise HTTPException(status_code=502, detail="대화내용을 경험 초안으로 정리하지 못했습니다.") from error

    proposal = _proposal_from_result(result)
    proposal["analysis_scope"] = {
        "message_count": len(messages),
        "attachment_count": len({
            attachment_id for message in messages for attachment_id in message.attachment_ids
        }),
        "from_sequence": messages[0].sequence,
        "to_sequence": messages[-1].sequence,
    }
    proposal["extraction_run"] = result.run.model_dump(mode="json")
    assistant_message = Message(
        id=create_resource_id("MSG"),
        conversation_id=conversation.id,
        client_request_id=request.client_request_id,
        sequence=conversation.message_count + 1,
        role="assistant",
        status="completed",
        content=f"최근 대화 {len(messages)}개에서 경험 초안 {len(result.experience_drafts)}개를 정리했습니다.",
        requested_intent="experience",
        resolved_intents=["experience"],
        proposal_ids=[proposal["id"]],
        actions=[_proposal_action(proposal)],
        completed_at=utc_now(),
    )
    database.add(assistant_message)
    conversation.message_count += 1
    conversation.pending_proposal_count += 1
    conversation.last_successful_extraction_sequence = messages[-1].sequence
    conversation.last_extraction_at = utc_now()
    conversation.last_message_preview = assistant_message.content
    conversation.version += 1
    database.commit()
    return {"run": result.run, "message": assistant_message, "proposal": proposal}


@router.post("/{conversation_id}/experience-analysis")
async def analyze_chat_experience(
    conversation_id: str,
    client_request_id: str = Form(...),
    text: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
    experience_ai: ExperienceAI = Depends(get_experience_ai),
):
    """채팅 입력을 메시지로 남기고 동일한 경험정리 AI 결과를 제안 카드로 저장한다."""

    conversation = get_conversation_or_404(conversation_id, current_user.id, database)
    existing_user = database.scalar(select(Message).where(
        Message.client_request_id == client_request_id,
        Message.role == "user",
    ))
    if existing_user is not None:
        existing_assistant = database.scalar(select(Message).where(
            Message.conversation_id == conversation_id,
            Message.sequence == existing_user.sequence + 1,
            Message.role == "assistant",
        ))
        if existing_assistant is None:
            raise HTTPException(status_code=409, detail="같은 경험 분석 요청이 아직 처리 중입니다.")
        action = next(
            (item for item in existing_assistant.actions if item.get("type") == "experience_proposal"),
            None,
        )
        if action is None:
            raise HTTPException(status_code=409, detail="저장된 경험 분석 결과를 찾지 못했습니다.")
        return {
            "user_message": existing_user,
            "assistant_message": existing_assistant,
            "proposal": action["proposal"],
            "run": {"id": "replayed"},
        }
    uploaded_files: list[JobFile] = []
    for uploaded in files:
        content = await uploaded.read(MAX_JOB_FILE_BYTES + 1)
        uploaded_files.append(JobFile(
            filename=uploaded.filename or "이름 없는 파일",
            mime_type=(uploaded.content_type or "").lower(),
            content=content,
        ))
        await uploaded.close()

    try:
        extracted_files = extract_experience_file_texts(uploaded_files)
        sources: list[EvidenceSource] = []
        attachment_ids: list[str] = []
        for extracted in extracted_files:
            attachment_id = f"chat-attachment-{uuid4()}"
            attachment_ids.append(attachment_id)
            sources.append(EvidenceSource(
                id=f"source-{attachment_id}",
                type=EvidenceSourceType.FILE,
                title=extracted.filename,
                attachment_id=attachment_id,
                filename=extracted.filename,
                mime_type=extracted.mime_type,
                text=extracted.text,
            ))
        result = experience_ai.organize(
            ExperienceExtractionRequest(
                client_request_id=client_request_id,
                input_type=ExperienceExtractionInputType.DIRECT_INPUT,
                text=text.strip() or None,
                attachment_ids=attachment_ids,
            ),
            sources=sources,
        )
    except (JobFileInputError, ValueError, ExperienceAIInputError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (JobFileExtractionError, ExperienceAIOutputError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    proposal = _proposal_from_result(result)
    user_sequence = conversation.message_count + 1
    proposal["analysis_scope"] = {
        "message_count": 1,
        "attachment_count": len(attachment_ids),
        "from_sequence": user_sequence,
        "to_sequence": user_sequence,
    }
    user_message = Message(
        id=create_resource_id("MSG"),
        conversation_id=conversation.id,
        client_request_id=client_request_id,
        sequence=user_sequence,
        role="user",
        status="completed",
        content=text.strip() or "첨부한 자료로 경험을 정리해 주세요.",
        requested_intent="experience",
        resolved_intents=["experience"],
        attachment_ids=attachment_ids,
        completed_at=utc_now(),
    )
    assistant_message = Message(
        id=create_resource_id("MSG"),
        conversation_id=conversation.id,
        sequence=user_sequence + 1,
        role="assistant",
        status="completed",
        content=f"입력한 내용에서 경험 초안 {len(result.experience_drafts)}개를 정리했습니다. 저장 전 내용을 확인해 주세요.",
        requested_intent="experience",
        resolved_intents=["experience"],
        proposal_ids=[proposal["id"]],
        actions=[_proposal_action(proposal)],
        completed_at=utc_now(),
    )
    database.add_all([user_message, assistant_message])
    conversation.message_count = user_sequence + 1
    conversation.pending_proposal_count += 1
    conversation.last_successful_extraction_sequence = user_sequence
    conversation.last_extraction_at = utc_now()
    conversation.last_message_preview = assistant_message.content
    conversation.version += 1
    database.commit()
    return {
        "user_message": user_message,
        "assistant_message": assistant_message,
        "proposal": proposal,
        "run": result.run,
    }


@router.patch("/{conversation_id}/messages/{message_id}/experience-proposal")
def update_chat_experience_proposal(
    conversation_id: str,
    message_id: str,
    request: ConversationProposalUpdate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    """채팅 메시지에 저장된 경험 제안의 수정·승인 상태를 갱신한다."""

    conversation = get_conversation_or_404(conversation_id, current_user.id, database)
    message = database.get(Message, message_id)
    if message is None or message.conversation_id != conversation_id or message.role != "assistant":
        raise HTTPException(status_code=404, detail="경험 제안 메시지를 찾을 수 없습니다.")
    action = next((item for item in message.actions if item.get("type") == "experience_proposal"), None)
    if action is None:
        raise HTTPException(status_code=404, detail="저장된 경험 제안을 찾을 수 없습니다.")
    current = action["proposal"]
    if current.get("version") != request.version:
        raise HTTPException(status_code=409, detail="경험 제안이 변경되었습니다. 새로고침해 주세요.")
    proposal = {
        **current,
        "version": request.version + 1,
        "payload": request.payload,
        "approved_experience_indexes": request.approved_experience_indexes,
        "status": request.status,
    }
    message.actions = [_proposal_action(proposal)]
    if current.get("status") not in {"approved", "rejected"} and request.status in {"approved", "rejected"}:
        conversation.pending_proposal_count = max(0, conversation.pending_proposal_count - 1)
    if request.status == "rejected":
        # 완전히 버린 초안의 원본 대화는 다시 상단 정리 버튼의 대상이 된다.
        active_sequences: list[int] = []
        assistant_messages = database.scalars(select(Message).where(
            Message.conversation_id == conversation.id,
            Message.role == "assistant",
        ))
        for assistant in assistant_messages:
            for stored_action in assistant.actions:
                stored = stored_action.get("proposal", {})
                if stored.get("status") == "rejected" or stored.get("id") == proposal.get("id"):
                    continue
                scope = stored.get("analysis_scope", {})
                if isinstance(scope.get("to_sequence"), int):
                    active_sequences.append(scope["to_sequence"])
        conversation.last_successful_extraction_sequence = max(active_sequences, default=0)
    database.commit()
    return proposal


@router.post("/{conversation_id}/job-analysis-record")
def record_chat_job_analysis(
    conversation_id: str,
    request: ConversationJobRecord,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    """공고 AI 분석 완료 사실과 결과 페이지 연결을 현재 대화에 기록한다."""

    conversation = get_conversation_or_404(conversation_id, current_user.id, database)
    job = database.get(JobAnalysisRecord, request.job_id)
    if job is None or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="채용공고 분석 결과를 찾을 수 없습니다.")

    existing_user = database.scalar(select(Message).where(
        Message.client_request_id == request.client_request_id,
        Message.role == "user",
    ))
    if existing_user is not None:
        existing_assistant = database.scalar(select(Message).where(
            Message.conversation_id == conversation_id,
            Message.sequence == existing_user.sequence + 1,
            Message.role == "assistant",
        ))
        return {"user_message": existing_user, "assistant_message": existing_assistant}

    user_sequence = conversation.message_count + 1
    content = request.content.strip() or "첨부한 채용공고를 분석해 주세요."
    user_message = Message(
        id=create_resource_id("MSG"),
        conversation_id=conversation.id,
        client_request_id=request.client_request_id,
        sequence=user_sequence,
        role="user",
        status="completed",
        content=content,
        requested_intent="job",
        resolved_intents=["job"],
        attachment_ids=[],
        actions=[{"type": "input_files", "filenames": request.filenames}],
        completed_at=utc_now(),
    )
    assistant_message = Message(
        id=create_resource_id("MSG"),
        conversation_id=conversation.id,
        sequence=user_sequence + 1,
        role="assistant",
        status="completed",
        content=f"채용공고 요구사항 {len(job.requirements)}개와 보유 경험 매칭을 완료했습니다.",
        requested_intent="job",
        resolved_intents=["job"],
        actions=[{"type": "open_job_analysis", "job_id": job.id}],
        completed_at=utc_now(),
    )
    database.add_all([user_message, assistant_message])
    conversation.message_count = user_sequence + 1
    conversation.last_message_preview = assistant_message.content
    conversation.version += 1
    database.commit()
    return {"user_message": user_message, "assistant_message": assistant_message}


__all__ = ["router"]
