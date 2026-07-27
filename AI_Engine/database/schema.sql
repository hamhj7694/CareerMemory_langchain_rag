-- Career Memory 대화·메시지 테이블 구조
-- 실제 서버는 models.py를 기준으로 테이블을 자동 생성한다.
-- 이 파일은 SQL 테이블과 제약조건을 직접 읽고 확인하기 위한 초기 설계 문서다.

PRAGMA foreign_keys = ON;

-- 1. 사용자
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(50) PRIMARY KEY,
    username VARCHAR(30) UNIQUE,
    email VARCHAR(320) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    password_hash VARCHAR(500) NOT NULL,
    recovery_question VARCHAR(50),
    recovery_answer_hash VARCHAR(500),
    recovery_failed_attempts INTEGER NOT NULL DEFAULT 0,
    recovery_locked_until DATETIME,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

-- 2. 로그인 세션
CREATE TABLE IF NOT EXISTS auth_sessions (
    id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    csrf_token VARCHAR(100) NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    revoked_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- 3. 대화방
-- 목록 화면에서 바로 사용할 제목, 상태, 메시지 수와 갱신 시간을 저장한다.
CREATE TABLE IF NOT EXISTS conversations (
    id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50),
    client_request_id VARCHAR(100) NOT NULL UNIQUE,
    title VARCHAR(200) NOT NULL DEFAULT '새 대화',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    last_message_preview VARCHAR(300),
    message_count INTEGER NOT NULL DEFAULT 0,
    pending_proposal_count INTEGER NOT NULL DEFAULT 0,
    last_successful_extraction_sequence INTEGER NOT NULL DEFAULT 0,
    last_extraction_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT ck_conversations_status
        CHECK (status IN ('active', 'archived')),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_conversations_user_id
    ON conversations (user_id);
CREATE INDEX IF NOT EXISTS ix_conversations_status_updated
    ON conversations (status, updated_at);

-- 4. 대화 메시지
-- 한 대화 안의 메시지 순서와 AI 처리 상태, 화면 표시 데이터를 저장한다.
CREATE TABLE IF NOT EXISTS messages (
    id VARCHAR(50) PRIMARY KEY,
    conversation_id VARCHAR(50) NOT NULL,
    client_request_id VARCHAR(100) UNIQUE,
    sequence INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    requested_intent VARCHAR(30) NOT NULL DEFAULT 'auto',
    resolved_intents JSON NOT NULL,
    attachment_ids JSON NOT NULL,
    citations JSON NOT NULL,
    proposal_ids JSON NOT NULL,
    actions JSON NOT NULL,
    error JSON,
    created_at DATETIME NOT NULL,
    completed_at DATETIME,
    CONSTRAINT fk_messages_conversation
        FOREIGN KEY (conversation_id)
        REFERENCES conversations (id)
        ON DELETE CASCADE,
    CONSTRAINT uq_messages_conversation_sequence
        UNIQUE (conversation_id, sequence),
    CONSTRAINT ck_messages_role
        CHECK (role IN ('user', 'assistant', 'system')),
    CONSTRAINT ck_messages_status
        CHECK (
            status IN (
                'queued',
                'processing',
                'streaming',
                'completed',
                'failed',
                'cancelled'
            )
        )
);

CREATE INDEX IF NOT EXISTS ix_messages_conversation_created
    ON messages (conversation_id, created_at);

-- 5. 대화 요약 메모리
-- 오래된 원문 메시지를 삭제하지 않고 모델 입력에 사용할 파생 요약만 저장한다.
CREATE TABLE IF NOT EXISTS conversation_memories (
    conversation_id VARCHAR(50) PRIMARY KEY,
    summary_text TEXT NOT NULL DEFAULT '',
    through_sequence INTEGER NOT NULL DEFAULT 0,
    estimated_tokens INTEGER NOT NULL DEFAULT 0,
    model_version VARCHAR(100) NOT NULL DEFAULT '',
    prompt_version VARCHAR(100) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (conversation_id)
        REFERENCES conversations (id)
        ON DELETE CASCADE
);

-- 6. 사용자 원본 첨부 파일
-- 해시가 같은 파일은 사용자 안에서 재사용하고 추출 본문은 RAG/대화 문맥에 사용한다.
CREATE TABLE IF NOT EXISTS attachments (
    id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    filename VARCHAR(300) NOT NULL,
    normalized_filename VARCHAR(300) NOT NULL,
    mime_type VARCHAR(150) NOT NULL,
    size_bytes INTEGER NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    content BLOB NOT NULL,
    extracted_text TEXT NOT NULL DEFAULT '',
    parse_status VARCHAR(20) NOT NULL DEFAULT 'ready',
    parse_error TEXT,
    parser_version VARCHAR(100) NOT NULL DEFAULT 'experience-file-parser-v1',
    original_attachment_id VARCHAR(50),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_attachments_user_content_hash
        UNIQUE (user_id, content_hash),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (original_attachment_id)
        REFERENCES attachments (id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_attachments_user_id
    ON attachments (user_id);
CREATE INDEX IF NOT EXISTS ix_attachments_user_filename
    ON attachments (user_id, normalized_filename);
