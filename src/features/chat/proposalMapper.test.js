import { describe, expect, it } from 'vitest';
import { applyProposalPanelChanges, createLocalExperienceProposal, splitProposalSources, toProposalView } from './proposalMapper.js';

const sources = [
  { id: 'SRC-MSG-1', source_type: 'message_text', title: '대화 원문', text: '첫 번째 대화' },
  { id: 'SRC-FILE-1', source_type: 'file', filename: '성과.txt', text: '파일 내용' },
];

const rawExperience = {
  draft_id: 'DRF-1',
  domain: { id: 'DOM-1', name: '직장 경험' },
  project: { id: 'PROJ-1', name: '전환 개선' },
  title: '지원 전환율 개선',
  summary: '전환 흐름을 개선했습니다.',
  situation: '',
  actions: ['퍼널을 분석했습니다.'],
  results: ['전환율을 높였습니다.'],
  role: '서비스 기획',
  facts: ['전환율 향상'],
  skills: ['데이터 분석'],
  missing_information: ['정확한 기간 확인'],
  source_ref_ids: sources.map((source) => source.id),
  source_refs: sources,
};

describe('proposal mapper', () => {
  it('normalizes API and local experience proposals into the same view shape', () => {
    const apiView = toProposalView({
      id: 'PRP-API',
      version: 1,
      type: 'create_experiences',
      payload: { domain: rawExperience.domain, project: rawExperience.project, experiences: [rawExperience] },
    });
    const localView = createLocalExperienceProposal({
      id: 'PRP-LOCAL',
      experiences: [{ ...rawExperience, domain: '직장 경험', project: '전환 개선' }],
    });

    expect(localView.experiences[0]).toMatchObject({
      domain: apiView.experiences[0].domain,
      project: apiView.experiences[0].project,
      title: apiView.experiences[0].title,
      source_ref_ids: apiView.experiences[0].source_ref_ids,
      missingInformation: apiView.experiences[0].missingInformation,
    });
    expect(localView.rawPayload.experiences[0].domain).toEqual({ name: '직장 경험' });
    expect(localView.rawPayload.experiences[0].project).toEqual({ name: '전환 개선' });
  });

  it('counts unique conversation and file evidence separately', () => {
    const summary = splitProposalSources([...sources, sources[0]]);

    expect(summary.totalCount).toBe(2);
    expect(summary.conversationCount).toBe(1);
    expect(summary.fileCount).toBe(1);
  });

  it('keeps evidence and missing information when an edited panel is mapped back', () => {
    const proposal = toProposalView({
      id: 'PRP-1',
      version: 1,
      type: 'create_experiences',
      payload: { experiences: [rawExperience] },
    });
    const panel = {
      ...proposal,
      experiences: [{ ...proposal.experiences[0], title: '수정된 경험' }],
    };

    const payload = applyProposalPanelChanges(proposal, panel);

    expect(payload.experiences[0].title).toBe('수정된 경험');
    expect(payload.experiences[0].source_refs).toEqual(sources);
    expect(payload.experiences[0].missing_information).toEqual(['정확한 기간 확인']);
  });

  it('preserves the confirmed experience id used for idempotent draft saving', () => {
    const proposal = toProposalView({
      id: 'PRP-SAVED',
      version: 2,
      type: 'create_experiences',
      approved_experience_indexes: [0],
      payload: {
        experiences: [{
          ...rawExperience,
          saved_experience_id: 'EXP-SAVED',
          saved_at: '2026-07-27T12:00:00+00:00',
        }],
      },
    });

    expect(proposal.experiences[0]).toMatchObject({
      approved: true,
      savedExperienceId: 'EXP-SAVED',
      savedAt: '2026-07-27T12:00:00+00:00',
    });
    expect(applyProposalPanelChanges(proposal, proposal).experiences[0]).toMatchObject({
      saved_experience_id: 'EXP-SAVED',
      saved_at: '2026-07-27T12:00:00+00:00',
    });
  });
});
