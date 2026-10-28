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

  it('경험 관리 직접 입력에서도 v2 단위 계약과 기존 경험 업데이트 정보를 유지한다', () => {
    const analysis = buildExperienceAnalysisFromResult({
      result: {
        analysis_record_id: 'ANALYSIS-2',
        proposal: {
          id: 'PROPOSAL-2',
          version: 1,
          contract_version: 'experience-units-v2',
          analysis_run_id: 'ANALYSIS-2',
          coverage: { processing_status: 'complete' },
          units: [{
            unit_id: 'UNIT-2',
            title: '전환율 개선',
            domain: { name: '직장 경험' },
            project: { name: '서비스 개선' },
            skills: ['FastAPI'],
            save_strategy: {
              operation: 'update',
              experience_id: 'EXP-1',
              experience_title: '기존 전환율 개선',
            },
            reused_skills: ['FastAPI'],
          }],
        },
      },
    });

    expect(analysis.proposal).toMatchObject({
      contractVersion: 'experience-units-v2',
      analysisRunId: 'ANALYSIS-2',
    });
    expect(analysis.proposal.units[0]).toMatchObject({
      unitId: 'UNIT-2',
      saveStrategy: { operation: 'update', experience_id: 'EXP-1' },
      reusedSkills: ['FastAPI'],
    });
  });
});
