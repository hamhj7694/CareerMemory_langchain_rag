import { describe, expect, it } from 'vitest';
import { EVIDENCE_TYPES, groupEvidence, toEvidenceView } from './evidenceMapper.js';

describe('evidence view model', () => {
  it('normalizes API snake case and UI camel case into one shape', () => {
    const source = toEvidenceView({
      id: 'SRC-1',
      source_type: 'file',
      filename: '성과.pdf',
      size_bytes: 1024,
      uploaded_at: '2026-07-25T00:00:00.000Z',
      linked_facts: [{ fact: '전환율 향상' }],
    });

    expect(source).toMatchObject({
      id: 'SRC-1',
      type: EVIDENCE_TYPES.FILE,
      title: '성과.pdf',
      sizeBytes: 1024,
      uploadedAt: '2026-07-25T00:00:00.000Z',
      linkedFacts: [{ fact: '전환율 향상' }],
    });
  });

  it('separates conversation, manual text, and files while deduplicating ids', () => {
    const sources = [
      { id: 'MSG-1', source_type: 'message_text' },
      { id: 'TXT-1', sourceType: 'text' },
      { id: 'FILE-1', kind: 'file', filename: '근거.txt' },
      { id: 'FILE-1', source_type: 'file', filename: '근거.txt' },
    ];
    const grouped = groupEvidence(sources);

    expect(grouped.totalCount).toBe(3);
    expect(grouped.conversationCount).toBe(1);
    expect(grouped.textCount).toBe(1);
    expect(grouped.fileCount).toBe(1);
  });

  it('preserves the source chat message id used for returning to the original conversation', () => {
    const source = toEvidenceView({
      id: 'SRC-MSG-1',
      source_type: 'message_text',
      message_id: 'MSG-1',
      conversation_id: 'CONV-1',
    });

    expect(source).toMatchObject({
      type: EVIDENCE_TYPES.CONVERSATION,
      messageId: 'MSG-1',
      conversationId: 'CONV-1',
    });
  });
});
