"""대화와 메시지를 저장하는 SQLAlchemy 테이블 모델."""

from __future__ import annotations

# 1. Python 기본 기능
from datetime import datetime, timezone

# 2. SQLAlchemy 컬럼과 관계 기능
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from AI_Engine.database.connection import Base


# 3. UTC 시간 생성
# 모든 서버 시간은 지역에 관계없이 비교 가능한 UTC 기준으로 저장한다.
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# 4. 사용자 테이블
class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    username: Mapped[str | None] = mapped_column(
        String(30),
        unique=True,
        nullable=True,
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    recovery_question: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    recovery_answer_hash: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    recovery_failed_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    recovery_locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user",
    )
    experience_domains: Mapped[list["ExperienceDomain"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    experience_draft_trash: Mapped[list["ExperienceDraftTrash"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    job_analyses: Mapped[list["JobAnalysisRecord"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


# 5. 로그인 세션 테이블
class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    csrf_token: Mapped[str] = mapped_column(String(100), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user: Mapped[User] = relationship(back_populates="sessions")


# 6. 대화 테이블
# 채팅방 제목과 상태뿐 아니라 목록 화면에 필요한 집계값도 함께 저장한다.
class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_conversations_status",
        ),
        Index("ix_conversations_status_updated", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    # 기존 로컬 단일 사용자 DB와 호환하기 위해 컬럼 자체는 nullable로 둔다.
    # 새 API로 생성되는 모든 대화에는 현재 로그인 사용자의 ID가 반드시 들어간다.
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    client_request_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="새 대화",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
    )
    last_message_preview: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )
    message_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    pending_proposal_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    last_successful_extraction_sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    last_extraction_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.sequence",
    )
    user: Mapped[User | None] = relationship(back_populates="conversations")


# 7. 메시지 테이블
# AI 연결 전에도 사용자·assistant 메시지의 순서와 처리 상태를 일관되게 저장할 수 있다.
class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="ck_messages_role",
        ),
        CheckConstraint(
            "status IN "
            "('queued', 'processing', 'streaming', 'completed', "
            "'failed', 'cancelled')",
            name="ck_messages_status",
        ),
        UniqueConstraint(
            "conversation_id",
            "sequence",
            name="uq_messages_conversation_sequence",
        ),
        Index(
            "ix_messages_conversation_created",
            "conversation_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    client_request_id: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
        nullable=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    requested_intent: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="auto",
    )
    resolved_intents: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    attachment_ids: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    citations: Mapped[list[dict[str, object]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    proposal_ids: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    actions: Mapped[list[dict[str, object]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    error: Mapped[dict[str, object] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    conversation: Mapped[Conversation] = relationship(
        back_populates="messages",
    )


# 8. 경험 관리 테이블
class ExperienceDomain(Base):
    __tablename__ = "experience_domains"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_experience_domains_user_name"),
    )

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    user: Mapped[User] = relationship(back_populates="experience_domains")
    projects: Mapped[list["ExperienceProject"]] = relationship(
        back_populates="domain", cascade="all, delete-orphan"
    )


class ExperienceProject(Base):
    __tablename__ = "experience_projects"
    __table_args__ = (
        UniqueConstraint("domain_id", "name", name="uq_experience_projects_domain_name"),
    )

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    domain_id: Mapped[str] = mapped_column(
        ForeignKey("experience_domains.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    organization: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    domain: Mapped[ExperienceDomain] = relationship(back_populates="projects")
    experiences: Mapped[list["Experience"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Experience(Base):
    __tablename__ = "experiences"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("experience_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    situation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    results: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    role: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    skills: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    facts: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    period: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    missing_information: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_refs: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="confirmed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    project: Mapped[ExperienceProject] = relationship(back_populates="experiences")


class ExperienceDraftTrash(Base):
    """삭제되었거나 저장에 실패한 AI 경험 초안을 사용자별로 보관한다."""

    __tablename__ = "experience_draft_trash"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="deleted")
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="제목 없는 초안")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    draft: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    original_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user: Mapped[User] = relationship(back_populates="experience_draft_trash")
    files: Mapped[list["ExperienceDraftTrashFile"]] = relationship(
        back_populates="trash_item",
        cascade="all, delete-orphan",
    )


class ExperienceDraftTrashFile(Base):
    """재분석할 수 있도록 쓰레기통에 보관하는 원본 첨부파일."""

    __tablename__ = "experience_draft_trash_files"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    trash_id: Mapped[str] = mapped_column(
        ForeignKey("experience_draft_trash.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(150), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    trash_item: Mapped[ExperienceDraftTrash] = relationship(back_populates="files")


class JobAnalysisRecord(Base):
    """로그인 사용자가 실행한 채용공고 분석 결과를 보관한다."""

    __tablename__ = "job_analyses"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_request_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    company_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    role_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    posting_title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    posting_content: Mapped[str] = mapped_column(Text, nullable=False)
    # AI가 만든 요구사항과 RAG 연결은 구조가 중첩되어 JSON으로 그대로 보관한다.
    requirements: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    experience_links: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    versions: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    user: Mapped[User] = relationship(back_populates="job_analyses")


__all__ = [
    "AuthSession",
    "Conversation",
    "Experience",
    "ExperienceDomain",
    "ExperienceDraftTrash",
    "ExperienceProject",
    "JobAnalysisRecord",
    "Message",
    "User",
    "utc_now",
]
