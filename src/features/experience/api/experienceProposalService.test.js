import { describe, expect, it } from 'vitest';
import { buildLocalExperienceAnalysis, markProposalExperienceSaved } from './experienceProposalService.js';

describe('experience proposal service', () => {
  it('returns the same proposal contract that a future AI adapter must follow', () => {
    const result = buildLocalExperienceAnalysis({
      content: '서비스 지표를 분석했습니다.',
      fileNames: ['성과.txt'],
      uploadedAttachments: [{
        id: 'ATT-1',
        filename: '성과.txt',
        mime_type: 'text/plain',
        size_bytes: 20,
        created_at: '2026-07-25T00:00:00.000Z',
        raw_text: '전환율을 개선했습니다.',
      }],
      domain: { id: 'DOM-1', name: '직장 경험' },
      project: { id: 'PROJ-1', name: '서비스 개선' },
      context: { domainId: 'DOM-1', projectId: 'PROJ-1' },
    });

    expect(result.draft).toMatchObject({ domainName: '직장 경험', projectName: '서비스 개선' });
    expect(result.proposal.kind).toBe('experience');
    expect(result.proposal.experiences).toHaveLength(2);
    expect(result.proposal.experiences[0].source_ref_ids).toHaveLength(2);
  });

  it('marks only the approved draft as saved without changing sibling drafts', () => {
    const proposal = { version: 1, experiences: [{ draft_id: 'D-1' }, { draft_id: 'D-2' }], rawPayload: {} };
    const next = markProposalExperienceSaved(proposal, 1, { id: 'EXP-2', created_at: '2026-07-25T00:00:00.000Z' });

    expect(next.experiences[0].approved).toBeUndefined();
    expect(next.experiences[1]).toMatchObject({ approved: true, savedExperienceId: 'EXP-2' });
  });
});
