import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { v2ChatApi } from '../../../api/v2ChatApi.js';
import { discardPendingProposalAttachments } from '../../experience/api/experienceProposalService.js';
import { mergeEvidenceFileSelections } from './evidenceFileSelection.js';

function textFile(name, content) {
  const bytes = new TextEncoder().encode(content);
  return {
    name,
    type: 'text/plain',
    size: bytes.byteLength,
    lastModified: 1,
    text: async () => content,
    arrayBuffer: async () => bytes.slice().buffer,
  };
}

describe('evidence file duplicate selection', () => {
  beforeEach(() => v2ChatApi.reset());
  afterEach(() => v2ChatApi.reset());

  it('reuses an existing attachment when its content hash is identical', async () => {
    const firstSelection = await mergeEvidenceFileSelections([], [textFile('성과.txt', '전환율 18% 향상')], v2ChatApi.preflightAttachments);
    const [stored] = await v2ChatApi.uploadAttachments(firstSelection.files);
    const duplicateSelection = await mergeEvidenceFileSelections([], [textFile('성과.txt', '전환율 18% 향상')], v2ChatApi.preflightAttachments);
    const [reused] = await v2ChatApi.uploadAttachments(duplicateSelection.files);

    expect(duplicateSelection.files[0]).toMatchObject({
      duplicateStatus: 'reused',
      existingAttachmentId: stored.id,
    });
    expect(reused).toMatchObject({ id: stored.id, reused: true });

    await discardPendingProposalAttachments({
      experiences: [{ approved: false, source_refs: [{ id: stored.id, source_type: 'file', reused: true }] }],
    });
    const afterDiscard = await mergeEvidenceFileSelections([], [textFile('성과.txt', '전환율 18% 향상')], v2ChatApi.preflightAttachments);
    expect(afterDiscard.files[0].existingAttachmentId).toBe(stored.id);
  });

  it('keeps the same filename with different content as a new version', async () => {
    const firstSelection = await mergeEvidenceFileSelections([], [textFile('성과.txt', '기존 내용')], v2ChatApi.preflightAttachments);
    const [stored] = await v2ChatApi.uploadAttachments(firstSelection.files);
    const revisedSelection = await mergeEvidenceFileSelections([], [textFile('성과.txt', '수정된 내용')], v2ChatApi.preflightAttachments);
    const [revised] = await v2ChatApi.uploadAttachments(revisedSelection.files);

    expect(revisedSelection.files[0]).toMatchObject({
      duplicateStatus: 'new-version',
      previousAttachmentId: stored.id,
    });
    expect(revised.id).not.toBe(stored.id);
    expect(revised.original_attachment_id).toBe(stored.id);
  });
});
