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
