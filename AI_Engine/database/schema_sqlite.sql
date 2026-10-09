-- CareerMemory SQLite schema-only dump
-- Contains DDL only. No user data or ontology seed rows are included.
-- Apply this file only to a new, empty SQLite database.

PRAGMA foreign_keys = ON;
BEGIN TRANSACTION;

CREATE TABLE users (
    id VARCHAR(50) NOT NULL,
    username VARCHAR(30),
    email VARCHAR(320) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    password_hash VARCHAR(500) NOT NULL,
    recovery_question VARCHAR(50),
    recovery_answer_hash VARCHAR(500),
    recovery_failed_attempts INTEGER NOT NULL,
    recovery_locked_until DATETIME,
    is_active BOOLEAN NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE ontology_concepts (
    id VARCHAR(100) NOT NULL,
    concept_type VARCHAR(50) NOT NULL,
    canonical_name VARCHAR(200) NOT NULL,
    normalization_key VARCHAR(250) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    ontology_version VARCHAR(100) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_ontology_concepts_type_key
        UNIQUE (concept_type, normalization_key),
    CONSTRAINT ck_ontology_concepts_status
        CHECK (status IN ('active', 'deprecated'))
);

CREATE TABLE conversations (
    id VARCHAR(50) NOT NULL,
    user_id VARCHAR(50),
    client_request_id VARCHAR(100) NOT NULL,
    title VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL,
    last_message_preview VARCHAR(300),
    message_count INTEGER NOT NULL,
    pending_proposal_count INTEGER NOT NULL,
    last_successful_extraction_sequence INTEGER NOT NULL,
    last_extraction_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    version INTEGER NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_conversations_status
        CHECK (status IN ('active', 'archived')),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    UNIQUE (client_request_id)
);

CREATE TABLE attachments (
    id VARCHAR(50) NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    filename VARCHAR(300) NOT NULL,
    normalized_filename VARCHAR(300) NOT NULL,
    mime_type VARCHAR(150) NOT NULL,
    size_bytes INTEGER NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    content BLOB NOT NULL,
    extracted_text TEXT NOT NULL,
    parse_status VARCHAR(20) NOT NULL,
    parse_error TEXT,
    parser_version VARCHAR(100) NOT NULL,
    original_attachment_id VARCHAR(50),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    extraction_metadata JSON NOT NULL DEFAULT '{}',
    storage_backend VARCHAR(30) NOT NULL DEFAULT 'database',
    storage_key TEXT,
    media_kind VARCHAR(30) NOT NULL DEFAULT 'document',
    duration_ms INTEGER,
    PRIMARY KEY (id),
    CONSTRAINT uq_attachments_user_content_hash
        UNIQUE (user_id, content_hash),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (original_attachment_id)
        REFERENCES attachments (id) ON DELETE SET NULL
);

CREATE TABLE auth_sessions (
    id VARCHAR(50) NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    token_hash VARCHAR(64) NOT NULL,
    csrf_token VARCHAR(100) NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    revoked_at DATETIME,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE conversation_memories (
    conversation_id VARCHAR(50) NOT NULL,
    summary_text TEXT NOT NULL,
    through_sequence INTEGER NOT NULL,
    estimated_tokens INTEGER NOT NULL,
    model_version VARCHAR(100) NOT NULL,
    prompt_version VARCHAR(100) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    version INTEGER NOT NULL,
    PRIMARY KEY (conversation_id),
    FOREIGN KEY (conversation_id)
        REFERENCES conversations (id) ON DELETE CASCADE
);

CREATE TABLE messages (
    id VARCHAR(50) NOT NULL,
    conversation_id VARCHAR(50) NOT NULL,
    client_request_id VARCHAR(100),
    sequence INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    requested_intent VARCHAR(30) NOT NULL,
    resolved_intents JSON NOT NULL,
    attachment_ids JSON NOT NULL,
    citations JSON NOT NULL,
    proposal_ids JSON NOT NULL,
    actions JSON NOT NULL,
    error JSON,
    created_at DATETIME NOT NULL,
    completed_at DATETIME,
    PRIMARY KEY (id),
    CONSTRAINT ck_messages_role
        CHECK (role IN ('user', 'assistant', 'system')),
    CONSTRAINT ck_messages_status
        CHECK (status IN (
            'queued', 'processing', 'streaming',
            'completed', 'failed', 'cancelled'
        )),
    CONSTRAINT uq_messages_conversation_sequence
        UNIQUE (conversation_id, sequence),
    FOREIGN KEY (conversation_id)
        REFERENCES conversations (id) ON DELETE CASCADE,
    UNIQUE (client_request_id)
);

CREATE TABLE experience_domains (
    id VARCHAR(50) NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    deleted_at DATETIME,
    version INTEGER NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_experience_domains_user_name UNIQUE (user_id, name),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE experience_projects (
    id VARCHAR(50) NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    domain_id VARCHAR(50) NOT NULL,
    name VARCHAR(150) NOT NULL,
    organization VARCHAR(200) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    deleted_at DATETIME,
    version INTEGER NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_experience_projects_domain_name UNIQUE (domain_id, name),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (domain_id)
        REFERENCES experience_domains (id) ON DELETE CASCADE
);

CREATE TABLE experiences (
    id VARCHAR(50) NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    project_id VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    summary TEXT NOT NULL,
    situation TEXT NOT NULL,
    actions JSON NOT NULL,
    results JSON NOT NULL,
    role VARCHAR(200) NOT NULL,
    skills JSON NOT NULL,
    facts JSON NOT NULL,
    period JSON NOT NULL,
    missing_information JSON NOT NULL,
    source_ids JSON NOT NULL,
    source_refs JSON NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    deleted_at DATETIME,
    version INTEGER NOT NULL,
    skill_mentions JSON NOT NULL DEFAULT '[]',
    metrics JSON NOT NULL DEFAULT '[]',
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (project_id)
        REFERENCES experience_projects (id) ON DELETE CASCADE
);

CREATE TABLE experience_draft_trash (
    id VARCHAR(50) NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    title VARCHAR(200) NOT NULL,
    reason TEXT NOT NULL,
    draft JSON NOT NULL,
    original_text TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE experience_draft_trash_files (
    id VARCHAR(50) NOT NULL,
    trash_id VARCHAR(50) NOT NULL,
    filename VARCHAR(300) NOT NULL,
    mime_type VARCHAR(150) NOT NULL,
    size_bytes INTEGER NOT NULL,
    content BLOB NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (trash_id)
        REFERENCES experience_draft_trash (id) ON DELETE CASCADE
);

CREATE TABLE job_analyses (
    id VARCHAR(50) NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    client_request_id VARCHAR(100) NOT NULL,
    company_name VARCHAR(200) NOT NULL,
    role_name VARCHAR(200) NOT NULL,
    posting_title VARCHAR(300) NOT NULL,
    source_url TEXT,
    posting_content TEXT NOT NULL,
    requirements JSON NOT NULL,
    experience_links JSON NOT NULL,
    warnings JSON NOT NULL,
    versions JSON NOT NULL,
    analyzed_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE file_processing_jobs (
    id VARCHAR(50) NOT NULL,
    attachment_id VARCHAR(50) NOT NULL,
    job_type VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempt_count INTEGER NOT NULL,
    max_attempts INTEGER NOT NULL,
    available_at DATETIME NOT NULL,
    lease_until DATETIME,
    worker_id VARCHAR(100),
    processor_version VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    error_code VARCHAR(100),
    error_message TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    completed_at DATETIME,
    PRIMARY KEY (id),
    FOREIGN KEY (attachment_id)
        REFERENCES attachments (id) ON DELETE CASCADE
);

CREATE TABLE transcription_segments (
    id VARCHAR(50) NOT NULL,
    attachment_id VARCHAR(50) NOT NULL,
    sequence INTEGER NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    speaker VARCHAR(100),
    text TEXT NOT NULL,
    confidence FLOAT,
    provider VARCHAR(50) NOT NULL,
    model VARCHAR(100) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_transcription_segments_attachment_sequence
        UNIQUE (attachment_id, sequence),
    FOREIGN KEY (attachment_id)
        REFERENCES attachments (id) ON DELETE CASCADE
);

CREATE TABLE ontology_aliases (
    id VARCHAR(100) NOT NULL,
    concept_id VARCHAR(100) NOT NULL,
    alias VARCHAR(200) NOT NULL,
    locale VARCHAR(20) NOT NULL,
    normalization_key VARCHAR(250) NOT NULL,
    provenance VARCHAR(100) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_ontology_aliases_key_locale
        UNIQUE (normalization_key, locale),
    FOREIGN KEY (concept_id)
        REFERENCES ontology_concepts (id) ON DELETE CASCADE
);

CREATE TABLE ontology_relations (
    id VARCHAR(120) NOT NULL,
    source_concept_id VARCHAR(100) NOT NULL,
    relation_type VARCHAR(30) NOT NULL,
    target_concept_id VARCHAR(100) NOT NULL,
    matching_policy VARCHAR(30) NOT NULL,
    provenance VARCHAR(100) NOT NULL,
    ontology_version VARCHAR(100) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_ontology_relations_edge
        UNIQUE (source_concept_id, relation_type, target_concept_id),
    CONSTRAINT ck_ontology_relations_type
        CHECK (relation_type IN (
            'alias_of', 'related_to', 'broader_than', 'narrower_than'
        )),
    CONSTRAINT ck_ontology_relations_policy
        CHECK (matching_policy IN (
            'satisfies', 'candidate_only', 'explicit_only'
        )),
    CONSTRAINT ck_ontology_relations_no_self_edge
        CHECK (source_concept_id <> target_concept_id),
    FOREIGN KEY (source_concept_id)
        REFERENCES ontology_concepts (id) ON DELETE CASCADE,
    FOREIGN KEY (target_concept_id)
        REFERENCES ontology_concepts (id) ON DELETE CASCADE
);

CREATE TABLE evidence_documents (
    id VARCHAR(100) NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    source_record_id VARCHAR(100) NOT NULL,
    legacy_source_ref_id VARCHAR(100),
    title VARCHAR(300) NOT NULL,
    original_text TEXT,
    storage_key TEXT,
    content_hash VARCHAR(64) NOT NULL,
    parser_version VARCHAR(100) NOT NULL,
    parse_status VARCHAR(20) NOT NULL,
    evidence_version VARCHAR(100) NOT NULL,
    is_stale BOOLEAN NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_evidence_documents_source_hash
        UNIQUE (user_id, source_type, source_record_id, content_hash),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE evidence_chunks (
    id VARCHAR(120) NOT NULL,
    document_id VARCHAR(100) NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    start_offset INTEGER NOT NULL,
    end_offset INTEGER NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    chunker_version VARCHAR(100) NOT NULL,
    is_stale BOOLEAN NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_evidence_chunks_document_index_hash
        UNIQUE (document_id, chunk_index, content_hash),
    FOREIGN KEY (document_id)
        REFERENCES evidence_documents (id) ON DELETE CASCADE
);

CREATE TABLE evidence_experience_links (
    id VARCHAR(120) NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    experience_id VARCHAR(50) NOT NULL,
    document_id VARCHAR(100) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_evidence_experience_links_pair
        UNIQUE (experience_id, document_id),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (experience_id)
        REFERENCES experiences (id) ON DELETE CASCADE,
    FOREIGN KEY (document_id)
        REFERENCES evidence_documents (id) ON DELETE CASCADE
);

CREATE TABLE embedding_records (
    id VARCHAR(120) NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    target_type VARCHAR(50) NOT NULL,
    target_id VARCHAR(120) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    model VARCHAR(150) NOT NULL,
    dimensions INTEGER,
    content_hash VARCHAR(64) NOT NULL,
    index_version VARCHAR(100) NOT NULL,
    collection_name VARCHAR(150) NOT NULL,
    vector_id VARCHAR(150) NOT NULL,
    status VARCHAR(20) NOT NULL,
    indexed_at DATETIME NOT NULL,
    stale_at DATETIME,
    PRIMARY KEY (id),
    CONSTRAINT uq_embedding_records_target_version_hash
        UNIQUE (
            target_type, target_id, provider, model,
            index_version, content_hash
        ),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_attachments_user_filename
    ON attachments (user_id, normalized_filename);
CREATE INDEX ix_attachments_user_id ON attachments (user_id);
CREATE INDEX ix_auth_sessions_expires_at ON auth_sessions (expires_at);
CREATE UNIQUE INDEX ix_auth_sessions_token_hash
    ON auth_sessions (token_hash);
CREATE INDEX ix_auth_sessions_user_id ON auth_sessions (user_id);
CREATE INDEX ix_conversations_status_updated
    ON conversations (status, updated_at);
CREATE INDEX ix_conversations_user_id ON conversations (user_id);
CREATE INDEX ix_embedding_records_status ON embedding_records (status);
CREATE INDEX ix_embedding_records_user_id ON embedding_records (user_id);
CREATE INDEX ix_embedding_records_user_status
    ON embedding_records (user_id, target_type, status);
CREATE INDEX ix_evidence_chunks_content_hash
    ON evidence_chunks (content_hash);
CREATE INDEX ix_evidence_chunks_document_current
    ON evidence_chunks (document_id, is_stale, chunk_index);
CREATE INDEX ix_evidence_chunks_document_id
    ON evidence_chunks (document_id);
CREATE INDEX ix_evidence_chunks_is_stale ON evidence_chunks (is_stale);
CREATE INDEX ix_evidence_documents_content_hash
    ON evidence_documents (content_hash);
CREATE INDEX ix_evidence_documents_is_stale
    ON evidence_documents (is_stale);
CREATE INDEX ix_evidence_documents_legacy_source_ref_id
    ON evidence_documents (legacy_source_ref_id);
CREATE INDEX ix_evidence_documents_user_id
    ON evidence_documents (user_id);
CREATE INDEX ix_evidence_documents_user_source
    ON evidence_documents (user_id, source_type, source_record_id);
CREATE INDEX ix_evidence_experience_links_document_id
    ON evidence_experience_links (document_id);
CREATE INDEX ix_evidence_experience_links_experience_id
    ON evidence_experience_links (experience_id);
CREATE INDEX ix_evidence_experience_links_user_document
    ON evidence_experience_links (user_id, document_id);
CREATE INDEX ix_evidence_experience_links_user_id
    ON evidence_experience_links (user_id);
CREATE INDEX ix_experience_domains_user_id
    ON experience_domains (user_id);
CREATE INDEX ix_experience_draft_trash_files_trash_id
    ON experience_draft_trash_files (trash_id);
CREATE INDEX ix_experience_draft_trash_user_id
    ON experience_draft_trash (user_id);
CREATE INDEX ix_experience_projects_domain_id
    ON experience_projects (domain_id);
CREATE INDEX ix_experience_projects_user_id
    ON experience_projects (user_id);
CREATE INDEX ix_experiences_project_id ON experiences (project_id);
CREATE INDEX ix_experiences_user_id ON experiences (user_id);
CREATE INDEX ix_file_processing_jobs_attachment_id
    ON file_processing_jobs (attachment_id);
CREATE INDEX ix_file_processing_jobs_status_available
    ON file_processing_jobs (status, available_at);
CREATE INDEX ix_job_analyses_client_request_id
    ON job_analyses (client_request_id);
CREATE INDEX ix_job_analyses_user_id ON job_analyses (user_id);
CREATE INDEX ix_messages_conversation_created
    ON messages (conversation_id, created_at);
CREATE INDEX ix_ontology_aliases_concept_id
    ON ontology_aliases (concept_id);
CREATE INDEX ix_ontology_concepts_concept_type
    ON ontology_concepts (concept_type);
CREATE INDEX ix_ontology_concepts_ontology_version
    ON ontology_concepts (ontology_version);
CREATE INDEX ix_ontology_concepts_status ON ontology_concepts (status);
CREATE INDEX ix_ontology_relations_ontology_version
    ON ontology_relations (ontology_version);
CREATE INDEX ix_ontology_relations_source_concept_id
    ON ontology_relations (source_concept_id);
CREATE INDEX ix_ontology_relations_target_concept_id
    ON ontology_relations (target_concept_id);
CREATE INDEX ix_transcription_segments_attachment_id
    ON transcription_segments (attachment_id);
CREATE UNIQUE INDEX ix_users_email ON users (email);
CREATE UNIQUE INDEX ix_users_username ON users (username);

COMMIT;
