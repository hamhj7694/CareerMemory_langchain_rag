"""커리어 챗의 경험 정리 입력을 기존 경험정리 AI와 연결한다."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from AI_Engine.api.conversations import create_resource_id, get_conversation_or_404
from AI_Engine.api.experience_extractions import (
    _attachment_sources,
    _persist_extraction_result,
    get_experience_ai,
)
from AI_Engine.api.experiences import ExperienceCreate, resolve_project
from AI_Engine.attachment_service import attachment_service
from AI_Engine.auth.dependencies import get_current_user, require_csrf_user
from AI_Engine.database.connection import get_database_session
from AI_Engine.database.models import (
    AnalysisRunRecord,
    Attachment,
    Experience,
    JobAnalysisRecord,
    Message,
    User,
    utc_now,
)
from AI_Engine.evidence_repository import sync_experience_evidence
from AI_Engine.knowledge_documents import (
    begin_analysis_run,
    experience_content_blocks,
    fail_analysis_run,
    link_analysis_target,
    merge_projected_blocks,
    upsert_content_document,
)
from AI_Engine.experience_units import (
    EXPERIENCE_UNITS_ACTION,
    EXPERIENCE_UNITS_SEGMENTER_VERSION,
    build_experience_units_proposal,
    organize_segmented_sources,
    proposal_action as experience_units_action,
    recalculate_proposal_coverage,
    segment_sources,
    source_manifest,
    validate_proposal_invariants,
)
from AI_Engine.experience_unit_storage import (
    annotate_proposal_matches,
    save_experience_unit,
)
from AI_Engine.normalization_backfill import structured_fields_for_experience
from AI_Engine.experience_ai import ExperienceAI, ExperienceAIInputError, ExperienceAIOutputError
from AI_Engine.privacy import guest_private_mode, redact_guest_text, redact_source_texts
from AI_Engine.file_extraction import FileInputError, run_file_extraction
from AI_Engine.job_file_text import (
    MAX_JOB_FILE_BYTES,
    MAX_JOB_FILE_COUNT,
    MAX_JOB_FILES_TOTAL_BYTES,
)
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


class ConversationProposalApprove(BaseModel):
    version: int = Field(ge=1)
    draft_id: str | None = None
    experience_index: int | None = Field(default=None, ge=0)


class ExperienceUnitsProposalUpdate(BaseModel):
    version: int = Field(ge=1)
    units: list[dict]
    coverage: dict
    status: Literal["edited", "rejected"] = "edited"


class ExperienceUnitApprove(BaseModel):
    version: int = Field(ge=1)
    unit_id: str = Field(min_length=1, max_length=100)


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
        experience["analysis_run_id"] = getattr(result, "analysis_record_id", None)
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


def _replace_proposal_action(message: Message, current_action: dict, proposal: dict) -> None:
    """다른 메시지 액션은 유지하고 경험 제안 액션만 교체한다."""

    message.actions = [
        _proposal_action(proposal) if item is current_action else item
        for item in message.actions
    ]


def _replace_units_proposal_action(
    message: Message,
    current_action: dict,
    proposal: dict,
) -> None:
    message.actions = [
        {"type": EXPERIENCE_UNITS_ACTION, "proposal": proposal}
        if item is current_action else item
        for item in message.actions
    ]


def _store_units_proposal_on_run(
    analysis_record: AnalysisRunRecord,
    proposal: dict,
) -> None:
    coverage = proposal.get("coverage") or {}
    analysis_record.output_payload = {
        **(analysis_record.output_payload or {}),
        "proposal": proposal,
        "unit_ids": [unit["unit_id"] for unit in proposal.get("units", [])],
    }
    analysis_record.coverage_report = coverage
    analysis_record.versions = {
        **(analysis_record.versions or {}),
        "contract": "experience-units-v2",
        "segmenter": EXPERIENCE_UNITS_SEGMENTER_VERSION,
    }
    if coverage.get("processing_status") == "partial":
        analysis_record.status = "partial"
    analysis_record.updated_at = utc_now()


def _experience_create_from_draft(draft: dict) -> ExperienceCreate:
    extensions = dict(draft.get("extensions") or {})
    if draft.get("unit_id"):
        extensions["experience_unit_v2"] = {
            "unit_id": draft["unit_id"],
            "contract_version": "experience-units-v2",
            "primary_span_ids": list(draft.get("primary_span_ids") or []),
            "context_span_ids": list(draft.get("context_span_ids") or []),
            "field_span_ids": dict(draft.get("field_span_ids") or {}),
            "fact_ids": list(draft.get("fact_ids") or []),
        }
    return ExperienceCreate(
        project_id=draft.get("project_id"),
        domain=draft.get("domain"),
        project=draft.get("project"),
        title=str(draft.get("title") or "제목 없는 경험").strip(),
        summary=str(draft.get("summary") or ""),
        situation=str(draft.get("situation") or ""),
        actions=list(draft.get("actions") or []),
        results=list(draft.get("results") or []),
        role=str(draft.get("role") or ""),
        skills=list(draft.get("skills") or []),
        skill_mentions=list(draft.get("skill_mentions") or []),
        facts=list(draft.get("facts") or []),
        metrics=list(draft.get("metrics") or []),
        period=draft.get("period"),
        missing_information=list(draft.get("missing_information") or []),
        source_ids=list(draft.get("source_ref_ids") or draft.get("source_ids") or []),
        source_refs=list(draft.get("source_refs") or []),
        draft_id=draft.get("draft_id"),
        field_citations=dict(draft.get("field_citations") or {}),
        skill_groups=list(draft.get("skill_groups") or []),
        confidence=draft.get("confidence"),
        extensions=extensions,
        analysis_run_id=draft.get("analysis_run_id"),
        content_blocks=list(draft.get("content_blocks") or []),
    )


def _hydrate_unit_source_refs(
    database: Session,
    *,
    unit: dict,
    current_user: User,
    conversation_id: str,
) -> list[dict]:
    """V2 메타데이터 참조를 현재 사용자가 소유한 원문으로 복원한다."""

    hydrated: list[dict] = []
    guest = guest_private_mode(current_user)
    for source in unit.get("source_refs") or []:
        item = dict(source)
        message_id = item.get("message_id")
        attachment_id = item.get("attachment_id")
        if message_id:
            message = database.get(Message, message_id)
            if message is None or message.conversation_id != conversation_id:
                raise HTTPException(status_code=422, detail="연결할 수 없는 대화 원문입니다.")
            item["type"] = "message_text"
            item["text"] = redact_guest_text(message.content) if guest else message.content
        elif attachment_id:
            attachment = database.get(Attachment, attachment_id)
            if attachment is None or attachment.user_id != current_user.id:
                raise HTTPException(status_code=422, detail="연결할 수 없는 첨부 원문입니다.")
            item.update({
                "type": "file",
                "filename": attachment.filename,
                "mime_type": attachment.mime_type,
                "text": redact_guest_text(attachment.extracted_text)
                if guest else attachment.extracted_text,
            })
        else:
            raise HTTPException(status_code=422, detail="원문 식별자가 없는 근거입니다.")
        hydrated.append(item)
    return hydrated


def _persist_confirmed_experience(
    database: Session,
    *,
    create_request: ExperienceCreate,
    current_user: User,
    unit_id: str | None = None,
) -> Experience:
    analysis_run = None
    if create_request.analysis_run_id:
        analysis_run = database.scalar(select(AnalysisRunRecord).where(
            AnalysisRunRecord.id == create_request.analysis_run_id,
            AnalysisRunRecord.user_id == current_user.id,
        ))
        if analysis_run is None:
            raise HTTPException(status_code=422, detail="연결할 수 없는 AI 분석 기록입니다.")
    project = resolve_project(create_request, current_user, database)
    period = create_request.period if isinstance(create_request.period, dict) else {}
    skill_mentions, metrics = structured_fields_for_experience(
        create_request.skills,
        create_request.facts,
        skill_mentions=create_request.skill_mentions,
        metrics=create_request.metrics,
        source_refs=create_request.source_refs,
    )
    experience = Experience(
        id=create_resource_id("EXP"), user_id=current_user.id, project_id=project.id,
        title=create_request.title, summary=create_request.summary,
        situation=create_request.situation, actions=create_request.actions,
        results=create_request.results, role=create_request.role,
        skills=create_request.skills, skill_mentions=skill_mentions,
        facts=create_request.facts,
        fact_evidence_status={
            fact: ("supported" if create_request.field_citations.get(f"facts.{index}") else "needs_evidence")
            for index, fact in enumerate(create_request.facts)
        },
        metrics=metrics, period=period,
        missing_information=create_request.missing_information,
        source_ids=create_request.source_ids, source_refs=create_request.source_refs,
        draft_id=create_request.draft_id, field_citations=create_request.field_citations,
        skill_groups=create_request.skill_groups, confidence=create_request.confidence,
        extensions=create_request.extensions,
        analysis_run_id=analysis_run.id if analysis_run else None,
        status="confirmed",
    )
    experience.project = project
    database.add(experience)
    database.flush()
    document = upsert_content_document(
        database, user_id=current_user.id, owner_type="experience",
        owner_id=experience.id, title=experience.title,
        blocks=merge_projected_blocks(experience_content_blocks({
            **create_request.model_dump(mode="json"),
            "skill_mentions": skill_mentions, "metrics": metrics,
            "fact_evidence_status": experience.fact_evidence_status,
        }), create_request.content_blocks),
        extensions=create_request.extensions,
    )
    experience.content_document_id = document.id
    if analysis_run is not None:
        if unit_id:
            link_analysis_target(
                database, analysis_run, unit_id=unit_id,
                target_type="experience", target_id=experience.id, commit=False,
            )
        else:
            analysis_run.target_id = experience.id
    sync_experience_evidence(database, experience)
    return experience


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
            (item for item in existing_assistant.actions if item.get("type") in {EXPERIENCE_UNITS_ACTION, "experience_proposal"}),
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
    text_messages = [
        message for message in messages
        if message.content.strip()
    ]
    sources = [
        EvidenceSource(
            id=f"source-{message.id}",
            type=EvidenceSourceType.MESSAGE_TEXT,
            title=f"대화 메시지 {message.sequence}",
            message_id=message.id,
            text=message.content,
        )
        for message in text_messages
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
    sources = redact_source_texts(sources, guest=guest_private_mode(current_user))
    if not sources:
        raise HTTPException(status_code=422, detail="분석 가능한 대화내용이 없습니다.")
    segmented = segment_sources(
        sources,
        privacy_policy="guest_redacted" if guest_private_mode(current_user) else "registered_full",
    )

    extraction_request = ExperienceExtractionRequest(
        client_request_id=request.client_request_id,
        input_type=ExperienceExtractionInputType.CONVERSATION,
        conversation_id=conversation.id,
        from_sequence=messages[0].sequence,
        to_sequence=messages[-1].sequence,
        # 파일만 첨부한 빈 메시지는 attachment_ids가 원본 근거 계약을 맡는다.
        # 대화 텍스트 근거가 실제로 만들어진 메시지만 message_ids에 기록한다.
        message_ids=[message.id for message in text_messages],
        attachment_ids=attachment_ids,
    )
    analysis_record = begin_analysis_run(
        database,
        user_id=current_user.id,
        client_request_id=request.client_request_id,
        target_type="conversation_experience_extraction",
        input_type=str(ExperienceExtractionInputType.CONVERSATION.value),
        input_payload={
            **extraction_request.model_dump(mode="json", exclude={"text"}),
            "source_manifest": source_manifest(segmented),
            "segmenter_version": EXPERIENCE_UNITS_SEGMENTER_VERSION,
        },
        source_ids=[source.id for source in sources],
    )
    try:
        result = organize_segmented_sources(experience_ai, extraction_request, segmented)
        result = _persist_extraction_result(database, analysis_record, result)
    except ExperienceAIInputError as error:
        fail_analysis_run(database, analysis_record, code="invalid_input", message=str(error))
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ExperienceAIOutputError as error:
        fail_analysis_run(database, analysis_record, code="invalid_ai_output", message=str(error))
        raise HTTPException(status_code=502, detail="대화내용을 경험 초안으로 정리하지 못했습니다.") from error

    proposal = build_experience_units_proposal(
        result,
        segmented,
        analysis_run_id=analysis_record.id,
    )
    proposal = annotate_proposal_matches(
        database, proposal, user_id=current_user.id,
    )
    _store_units_proposal_on_run(analysis_record, proposal)
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
        actions=[experience_units_action(proposal)],
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
            (item for item in existing_assistant.actions if item.get("type") in {EXPERIENCE_UNITS_ACTION, "experience_proposal"}),
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
    if guest_private_mode(current_user):
        text = redact_guest_text(text)
    if len(files) > MAX_JOB_FILE_COUNT:
        raise HTTPException(status_code=422, detail=f"파일은 최대 {MAX_JOB_FILE_COUNT}개까지 선택할 수 있습니다.")
    uploaded_files: list[tuple[str, str, bytes]] = []
    total_bytes = 0
    for uploaded in files:
        content = await uploaded.read(MAX_JOB_FILE_BYTES + 1)
        await uploaded.close()
        total_bytes += len(content)
        uploaded_files.append((
            uploaded.filename or "이름 없는 파일",
            (uploaded.content_type or "").lower(),
            content,
        ))
    if total_bytes > MAX_JOB_FILES_TOTAL_BYTES:
        raise HTTPException(status_code=413, detail="첨부 파일 전체 크기가 허용 범위를 초과합니다.")

    try:
        attachment_ids: list[str] = []
        for filename, mime_type, content in uploaded_files:
            ingested = attachment_service.ingest(
                database,
                user_id=current_user.id,
                filename=filename,
                mime_type=mime_type,
                content=content,
            )
            if ingested.job is not None and ingested.job.status == "queued":
                await run_file_extraction(
                    attachment_service.process_job,
                    database,
                    ingested.job.id,
                )
            database.refresh(ingested.attachment)
            if ingested.attachment.parse_status not in {"ready", "partial"}:
                raise FileInputError(
                    ingested.attachment.parse_error
                    or f"{filename}: 파일 처리에 실패했습니다."
                )
            attachment_ids.append(ingested.attachment.id)
        sources = _attachment_sources(
            database,
            user_id=current_user.id,
            attachment_ids=attachment_ids,
        )
        sources = redact_source_texts(sources, guest=guest_private_mode(current_user))
        if text.strip():
            sources.insert(0, EvidenceSource(
                id=f"source-{client_request_id}",
                type=EvidenceSourceType.MANUAL_TEXT,
                title="사용자 직접 입력",
                manual_input_id=client_request_id,
                text=text,
            ))
        segmented = segment_sources(
            sources,
            privacy_policy="guest_redacted" if guest_private_mode(current_user) else "registered_full",
        )
        extraction_request = ExperienceExtractionRequest(
            client_request_id=client_request_id,
            input_type=ExperienceExtractionInputType.DIRECT_INPUT,
            text=text if text.strip() else None,
            attachment_ids=attachment_ids,
        )
        analysis_record = begin_analysis_run(
            database,
            user_id=current_user.id,
            client_request_id=client_request_id,
            target_type="conversation_experience_extraction",
            input_type=str(ExperienceExtractionInputType.DIRECT_INPUT.value),
            input_payload={
                **extraction_request.model_dump(mode="json", exclude={"text"}),
                "source_manifest": source_manifest(segmented),
                "segmenter_version": EXPERIENCE_UNITS_SEGMENTER_VERSION,
            },
            source_ids=[source.id for source in sources],
        )
        result = organize_segmented_sources(experience_ai, extraction_request, segmented)
        result = _persist_extraction_result(database, analysis_record, result)
    except (FileInputError, ValueError, ExperienceAIInputError) as error:
        if "analysis_record" in locals():
            fail_analysis_run(database, analysis_record, code="invalid_input", message=str(error))
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ExperienceAIOutputError as error:
        if "analysis_record" in locals():
            fail_analysis_run(database, analysis_record, code="invalid_ai_output", message=str(error))
        raise HTTPException(status_code=502, detail=str(error)) from error

    proposal = build_experience_units_proposal(
        result,
        segmented,
        analysis_run_id=analysis_record.id,
    )
    proposal = annotate_proposal_matches(
        database, proposal, user_id=current_user.id,
    )
    _store_units_proposal_on_run(analysis_record, proposal)
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
        content=text if text.strip() else "첨부한 자료로 경험을 정리해 주세요.",
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
        actions=[experience_units_action(proposal)],
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


@router.patch("/{conversation_id}/messages/{message_id}/experience-units-proposal")
def update_experience_units_proposal(
    conversation_id: str,
    message_id: str,
    request: ExperienceUnitsProposalUpdate,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    """V2 경험 단위를 안정 ID 기준으로 수정하며 원문 추적 정보는 잠근다."""

    conversation = get_conversation_or_404(conversation_id, current_user.id, database)
    message = database.get(Message, message_id)
    if message is None or message.conversation_id != conversation_id or message.role != "assistant":
        raise HTTPException(status_code=404, detail="경험 단위 제안 메시지를 찾을 수 없습니다.")
    action = next(
        (item for item in message.actions if item.get("type") == EXPERIENCE_UNITS_ACTION),
        None,
    )
    if action is None:
        raise HTTPException(status_code=404, detail="저장된 경험 단위 제안을 찾을 수 없습니다.")
    current = action["proposal"]
    if current.get("version") != request.version:
        raise HTTPException(status_code=409, detail="경험 제안이 변경되었습니다. 새로고침해 주세요.")
    current_by_id = {unit["unit_id"]: unit for unit in current.get("units", [])}
    for unit in request.units:
        stored = current_by_id.get(unit.get("unit_id"))
        if stored is None:
            raise HTTPException(status_code=422, detail="새 경험 단위 ID를 임의로 추가할 수 없습니다.")
        for key in (
            "analysis_run_id", "source_ref_ids", "source_refs", "primary_span_ids",
            "context_span_ids", "field_span_ids", "saved_experience_id", "saved_at",
            "fact_ids",
        ):
            if unit.get(key) != stored.get(key):
                raise HTTPException(status_code=422, detail=f"{key} 추적 정보는 수정할 수 없습니다.")
    incoming_ids = {unit.get("unit_id") for unit in request.units}
    if any(
        unit.get("saved_experience_id") and unit.get("unit_id") not in incoming_ids
        for unit in current.get("units", [])
    ):
        raise HTTPException(status_code=409, detail="이미 저장된 경험 단위는 삭제할 수 없습니다.")
    proposal = {
        **current,
        "version": request.version + 1,
        "units": deepcopy(request.units),
        "coverage": current.get("coverage", {}),
        "status": request.status,
    }
    proposal = annotate_proposal_matches(
        database, proposal, user_id=current_user.id,
    )
    for updated in proposal.get("units", []):
        stored = current_by_id.get(updated.get("unit_id")) or {}
        if stored.get("saved_experience_id"):
            updated["save_strategy"] = stored.get("save_strategy", {"operation": "create"})
    proposal["coverage"] = recalculate_proposal_coverage(proposal)
    try:
        validate_proposal_invariants(proposal)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    _replace_units_proposal_action(message, action, proposal)
    if current.get("status") not in {"approved", "rejected"} and request.status in {"approved", "rejected"}:
        conversation.pending_proposal_count = max(0, conversation.pending_proposal_count - 1)
    database.commit()
    return proposal


@router.get("/{conversation_id}/messages/{message_id}/experience-units-proposal/spans")
def get_experience_unit_spans(
    conversation_id: str,
    message_id: str,
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
):
    """Return authorized source slices on demand instead of copying full text into units."""

    get_conversation_or_404(conversation_id, current_user.id, database)
    message = database.get(Message, message_id)
    if message is None or message.conversation_id != conversation_id or message.role != "assistant":
        raise HTTPException(status_code=404, detail="경험 단위 제안 메시지를 찾을 수 없습니다.")
    action = next(
        (item for item in message.actions if item.get("type") == EXPERIENCE_UNITS_ACTION),
        None,
    )
    if action is None:
        raise HTTPException(status_code=404, detail="저장된 경험 단위 제안을 찾을 수 없습니다.")
    proposal = action["proposal"]
    span_status = (proposal.get("coverage") or {}).get("span_status") or {}
    values: list[dict] = []
    guest = guest_private_mode(current_user)
    for snapshot in proposal.get("source_snapshots") or []:
        source_text = ""
        if snapshot.get("message_id"):
            source = database.get(Message, snapshot["message_id"])
            if source is None or source.conversation_id != conversation_id:
                raise HTTPException(status_code=422, detail="원문 메시지 연결이 유효하지 않습니다.")
            source_text = source.content
        elif snapshot.get("attachment_id"):
            attachment = database.get(Attachment, snapshot["attachment_id"])
            if attachment is None or attachment.user_id != current_user.id:
                raise HTTPException(status_code=422, detail="원문 첨부 연결이 유효하지 않습니다.")
            source_text = attachment.extracted_text
        if guest:
            source_text = redact_guest_text(source_text)
        expected_hash = snapshot.get("text_hash")
        current_hash = sha256(source_text.encode("utf-8")).hexdigest()
        if expected_hash and current_hash != expected_hash:
            raise HTTPException(
                status_code=409,
                detail="원문이 분석 이후 변경되어 근거 구간을 표시할 수 없습니다.",
            )
        for span in snapshot.get("spans") or []:
            start = int(span.get("char_start") or 0)
            end = int(span.get("char_end") or start)
            values.append({
                "id": span.get("id"),
                "source_id": snapshot.get("source_id"),
                "source_title": snapshot.get("title") or "원문",
                "category": span_status.get(span.get("id"), span.get("category")),
                "char_start": start,
                "char_end": end,
                "text": source_text[start:end],
            })
    return {"items": values, "total_count": len(values)}


@router.post("/{conversation_id}/messages/{message_id}/experience-units-proposal/approve")
def approve_experience_unit(
    conversation_id: str,
    message_id: str,
    request: ExperienceUnitApprove,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    """V2 경험 한 단위를 저장하고 같은 unit_id 재요청은 재생 처리한다."""

    conversation = get_conversation_or_404(conversation_id, current_user.id, database)
    message = database.get(Message, message_id)
    if message is None or message.conversation_id != conversation_id or message.role != "assistant":
        raise HTTPException(status_code=404, detail="경험 단위 제안 메시지를 찾을 수 없습니다.")
    action = next(
        (item for item in message.actions if item.get("type") == EXPERIENCE_UNITS_ACTION),
        None,
    )
    if action is None:
        raise HTTPException(status_code=404, detail="저장된 경험 단위 제안을 찾을 수 없습니다.")
    current = action["proposal"]
    try:
        validate_proposal_invariants(current)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=f"저장된 경험 단위 계약이 손상되었습니다: {error}") from error
    unit = next(
        (item for item in current.get("units", []) if item.get("unit_id") == request.unit_id),
        None,
    )
    if unit is None:
        raise HTTPException(status_code=404, detail="저장할 경험 단위를 찾을 수 없습니다.")
    if unit.get("saved_experience_id"):
        return {
            "proposal": current,
            "created": {"experience_id": unit["saved_experience_id"]},
            "replayed": True,
        }
    if current.get("version") != request.version:
        raise HTTPException(status_code=409, detail="경험 제안이 변경되었습니다. 새로고침해 주세요.")
    if current.get("status") == "rejected":
        raise HTTPException(status_code=409, detail="삭제된 경험 제안은 저장할 수 없습니다.")

    source_refs = _hydrate_unit_source_refs(
        database, unit=unit, current_user=current_user,
        conversation_id=conversation_id,
    )
    experience, operation = save_experience_unit(
        database, unit=unit, source_refs=source_refs,
        current_user=current_user,
    )
    units = deepcopy(current.get("units", []))
    saved_unit = next(item for item in units if item.get("unit_id") == request.unit_id)
    saved_unit["saved_experience_id"] = experience.id
    saved_unit["saved_at"] = utc_now().isoformat()
    saved_unit["status"] = "approved"
    all_approved = all(item.get("saved_experience_id") for item in units)
    proposal = {
        **current,
        "version": request.version + 1,
        "units": units,
        "status": "approved" if all_approved else "edited",
        "coverage": {
            **current.get("coverage", {}),
            "review_status": "approved" if all_approved else "partial",
        },
    }
    _replace_units_proposal_action(message, action, proposal)
    if current.get("status") not in {"approved", "rejected"} and all_approved:
        conversation.pending_proposal_count = max(0, conversation.pending_proposal_count - 1)
    database.commit()
    return {
        "proposal": proposal,
        "created": {"experience_id": experience.id},
        "operation": operation,
        "replayed": False,
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
    _replace_proposal_action(message, action, proposal)
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


@router.post("/{conversation_id}/messages/{message_id}/experience-proposal/approve")
def approve_chat_experience_proposal(
    conversation_id: str,
    message_id: str,
    request: ConversationProposalApprove,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
):
    """초안 한 건의 확정 경험 생성과 제안 상태 갱신을 한 트랜잭션으로 처리한다."""

    conversation = get_conversation_or_404(conversation_id, current_user.id, database)
    message = database.get(Message, message_id)
    if message is None or message.conversation_id != conversation_id or message.role != "assistant":
        raise HTTPException(status_code=404, detail="경험 제안 메시지를 찾을 수 없습니다.")
    action = next((item for item in message.actions if item.get("type") == "experience_proposal"), None)
    if action is None:
        raise HTTPException(status_code=404, detail="저장된 경험 제안을 찾을 수 없습니다.")

    current = action["proposal"]
    payload = deepcopy(current.get("payload") or {})
    drafts = payload.get("experiences")
    if not isinstance(drafts, list):
        raise HTTPException(status_code=422, detail="저장할 경험 초안 형식이 올바르지 않습니다.")

    draft_index = None
    if request.draft_id:
        draft_index = next(
            (index for index, draft in enumerate(drafts) if draft.get("draft_id") == request.draft_id),
            None,
        )
    if draft_index is None:
        draft_index = request.experience_index
    if draft_index is None or draft_index >= len(drafts):
        raise HTTPException(status_code=404, detail="저장할 경험 초안을 찾을 수 없습니다.")

    draft = drafts[draft_index]
    saved_experience_id = draft.get("saved_experience_id")
    approved_indexes = set(current.get("approved_experience_indexes") or [])

    # 응답을 받지 못해 동일 저장을 다시 요청해도 경험을 중복 생성하지 않는다.
    if saved_experience_id or draft_index in approved_indexes:
        return {
            "proposal": current,
            "created": {"experience_id": saved_experience_id},
            "replayed": True,
        }
    if current.get("version") != request.version:
        raise HTTPException(status_code=409, detail="경험 제안이 변경되었습니다. 새로고침해 주세요.")
    if current.get("status") == "rejected":
        raise HTTPException(status_code=409, detail="삭제된 경험 제안은 저장할 수 없습니다.")

    create_request = ExperienceCreate(
        project_id=draft.get("project_id"),
        domain=draft.get("domain"),
        project=draft.get("project"),
        title=str(draft.get("title") or "제목 없는 경험").strip(),
        summary=str(draft.get("summary") or ""),
        situation=str(draft.get("situation") or ""),
        actions=list(draft.get("actions") or []),
        results=list(draft.get("results") or []),
        role=str(draft.get("role") or ""),
        skills=list(draft.get("skills") or []),
        skill_mentions=list(draft.get("skill_mentions") or []),
        facts=list(draft.get("facts") or []),
        metrics=list(draft.get("metrics") or []),
        period=draft.get("period"),
        missing_information=list(draft.get("missing_information") or []),
        source_ids=list(draft.get("source_ref_ids") or draft.get("source_ids") or []),
        source_refs=list(draft.get("source_refs") or []),
        draft_id=draft.get("draft_id"),
        field_citations=dict(draft.get("field_citations") or {}),
        skill_groups=list(draft.get("skill_groups") or []),
        confidence=draft.get("confidence"),
        extensions=dict(draft.get("extensions") or {}),
        analysis_run_id=draft.get("analysis_run_id"),
        content_blocks=list(draft.get("content_blocks") or []),
    )
    analysis_run = None
    if create_request.analysis_run_id:
        analysis_run = database.scalar(select(AnalysisRunRecord).where(
            AnalysisRunRecord.id == create_request.analysis_run_id,
            AnalysisRunRecord.user_id == current_user.id,
        ))
        if analysis_run is None:
            raise HTTPException(status_code=422, detail="연결할 수 없는 AI 분석 기록입니다.")
    project = resolve_project(create_request, current_user, database)
    period = create_request.period if isinstance(create_request.period, dict) else {}
    skill_mentions, metrics = structured_fields_for_experience(
        create_request.skills,
        create_request.facts,
        skill_mentions=create_request.skill_mentions,
        metrics=create_request.metrics,
        source_refs=create_request.source_refs,
    )
    experience = Experience(
        id=create_resource_id("EXP"),
        user_id=current_user.id,
        project_id=project.id,
        title=create_request.title,
        summary=create_request.summary,
        situation=create_request.situation,
        actions=create_request.actions,
        results=create_request.results,
        role=create_request.role,
        skills=create_request.skills,
        skill_mentions=skill_mentions,
        facts=create_request.facts,
        fact_evidence_status={
            fact: (
                "supported"
                if create_request.field_citations.get(f"facts.{index}")
                else "needs_evidence"
            )
            for index, fact in enumerate(create_request.facts)
        },
        metrics=metrics,
        period=period,
        missing_information=create_request.missing_information,
        source_ids=create_request.source_ids,
        source_refs=create_request.source_refs,
        draft_id=create_request.draft_id,
        field_citations=create_request.field_citations,
        skill_groups=create_request.skill_groups,
        confidence=create_request.confidence,
        extensions=create_request.extensions,
        analysis_run_id=analysis_run.id if analysis_run else None,
        status="confirmed",
    )
    experience.project = project
    database.add(experience)
    database.flush()
    document = upsert_content_document(
        database,
        user_id=current_user.id,
        owner_type="experience",
        owner_id=experience.id,
        title=experience.title,
        blocks=merge_projected_blocks(experience_content_blocks({
            **create_request.model_dump(mode="json"),
            "skill_mentions": skill_mentions,
            "metrics": metrics,
            "fact_evidence_status": experience.fact_evidence_status,
        }), create_request.content_blocks),
        extensions=create_request.extensions,
    )
    experience.content_document_id = document.id
    if analysis_run is not None:
        analysis_run.target_id = experience.id
    sync_experience_evidence(database, experience)

    saved_at = utc_now()
    draft["saved_experience_id"] = experience.id
    draft["saved_at"] = saved_at.isoformat()
    approved_indexes.add(draft_index)
    all_approved = len(approved_indexes) >= len(drafts)
    proposal = {
        **current,
        "version": request.version + 1,
        "payload": payload,
        "approved_experience_indexes": sorted(approved_indexes),
        "status": "approved" if all_approved else "edited",
    }
    _replace_proposal_action(message, action, proposal)
    if current.get("status") not in {"approved", "rejected"} and all_approved:
        conversation.pending_proposal_count = max(0, conversation.pending_proposal_count - 1)
    database.commit()
    return {
        "proposal": proposal,
        "created": {"experience_id": experience.id},
        "replayed": False,
    }


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
