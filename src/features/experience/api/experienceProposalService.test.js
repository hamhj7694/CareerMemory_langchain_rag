import { describe, expect, it } from 'vitest';
import { buildExperienceAnalysisFromResult } from './experienceProposalService.js';

describe('buildExperienceAnalysisFromResult', () => {
  it('AI가 반환한 경험만 제안으로 만들고 원본 근거를 연결한다', () => {
    const result = {
      run: { id: 'RUN-1', completed_at: '2026-07-26T00:00:00Z' },
      sources: [{
        id: 'SRC-1',
        type: 'manual_text',
        title: '사용자 직접 입력',
        text: '전환율을 개선했다.',
      }],
      experience_drafts: [{
        draft_id: 'DRAFT-1',
        domain: { name: '직장 경험' },
        project: { name: '서비스 개선' },
        title: '전환율 개선',
        summary: '전환율을 개선한 경험',
        source_ref_ids: ['SRC-1'],
      }],
    };

    const analysis = buildExperienceAnalysisFromResult({ result });

    expect(analysis.proposal.experiences).toHaveLength(1);
    expect(analysis.proposal.experiences[0].title).toBe('전환율 개선');
    expect(analysis.proposal.experiences[0].source_refs[0].id).toBe('SRC-1');
  });
});
