const list = (value) => Array.isArray(value) ? value : [];

export const EVIDENCE_TYPES = Object.freeze({
  CONVERSATION: 'conversation',
  TEXT: 'text',
  FILE: 'file',
  UNKNOWN: 'unknown',
});

function evidenceType(source = {}) {
  const rawType = source.type || source.sourceType || source.source_type || source.kind;
  if (rawType === 'file' || rawType === 'pdf' || source.filename) return EVIDENCE_TYPES.FILE;
  if (['message_text', 'chat_range', 'conversation', 'message'].includes(rawType)) return EVIDENCE_TYPES.CONVERSATION;
  if (['text', 'manual_text', 'manual'].includes(rawType)) return EVIDENCE_TYPES.TEXT;
  return EVIDENCE_TYPES.UNKNOWN;
}

export function toEvidenceView(source = {}, index = 0) {
  const type = evidenceType(source);
  const id = source.id || source.sourceId || source.source_id || `evidence-${index}`;
  return {
    ...source,
    id,
    type,
    sourceType: type,
    editable: type === EVIDENCE_TYPES.TEXT,
    title: source.title || source.filename || (type === EVIDENCE_TYPES.CONVERSATION ? '대화 원문' : type === EVIDENCE_TYPES.TEXT ? '텍스트 입력' : type === EVIDENCE_TYPES.FILE ? '첨부 파일' : '원본 정보 없음'),
    filename: source.filename || '',
    text: source.text || source.preview || source.content || '',
    mimeType: source.mimeType || source.mime_type || '',
    sizeBytes: source.sizeBytes ?? source.size_bytes ?? 0,
    capturedAt: source.capturedAt || source.captured_at || source.createdAt || source.created_at || '',
    uploadedAt: source.uploadedAt || source.uploaded_at || '',
    messageId: source.messageId || source.message_id || '',
    conversationId: source.conversationId || source.conversation_id || '',
    linkedFacts: list(source.linkedFacts || source.linked_facts),
    unavailable: Boolean(source.unavailable),
    raw: source,
  };
}

export function toEvidenceViews(sources) {
  const normalized = list(sources).map(toEvidenceView);
  return [...new Map(normalized.map((source) => [source.id, source])).values()];
}

export function groupEvidence(sources) {
  const all = toEvidenceViews(sources);
  const files = all.filter((source) => source.type === EVIDENCE_TYPES.FILE);
  const conversations = all.filter((source) => source.type === EVIDENCE_TYPES.CONVERSATION);
  const texts = all.filter((source) => source.type === EVIDENCE_TYPES.TEXT);
  const unknown = all.filter((source) => source.type === EVIDENCE_TYPES.UNKNOWN);
  return {
    all,
    files,
    conversations,
    texts,
    unknown,
    totalCount: all.length,
    fileCount: files.length,
    conversationCount: conversations.length,
    textCount: texts.length,
    unknownCount: unknown.length,
  };
}
