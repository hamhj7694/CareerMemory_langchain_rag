import { describe, expect, it } from 'vitest';
import { applyExperienceUnitsChanges, applyProposalPanelChanges, createLocalExperienceProposal, splitProposalSources, toProposalView } from './proposalMapper.js';

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

  it('keeps each draft metadata attached by draft id after editing or reordering', () => {
    const secondExperience = {
      ...rawExperience,
      draft_id: 'DRF-2',
      title: '두 번째 경험',
      domain: { id: 'DOM-2', name: '교육 경험' },
      project: { id: 'PROJ-2', name: '분석 교육' },
      source_ref_ids: ['SRC-SECOND'],
      source_refs: [{ id: 'SRC-SECOND', source_type: 'message_text', text: '두 번째 근거' }],
    };
    const proposal = toProposalView({
      id: 'PRP-REORDER',
      version: 1,
      type: 'create_experiences',
      payload: { experiences: [rawExperience, secondExperience] },
    });
    const reorderedPanel = {
      ...proposal,
      experiences: [
        { ...proposal.experiences[1], title: '수정한 두 번째 경험' },
        { ...proposal.experiences[0], title: '수정한 첫 번째 경험' },
      ],
    };

    const payload = applyProposalPanelChanges(proposal, reorderedPanel);

    expect(payload.experiences[0]).toMatchObject({
      draft_id: 'DRF-2',
      title: '수정한 두 번째 경험',
      source_ref_ids: ['SRC-SECOND'],
    });
    expect(payload.experiences[0].domain).toMatchObject({ id: 'DOM-2', name: '교육 경험' });
    expect(payload.experiences[1]).toMatchObject({
      draft_id: 'DRF-1',
      title: '수정한 첫 번째 경험',
      source_ref_ids: ['SRC-MSG-1', 'SRC-FILE-1'],
    });
    expect(payload.experiences[1].domain).toMatchObject({ id: 'DOM-1', name: '직장 경험' });
  });

  it('maps the v2 unit contract and keeps immutable trace fields when edited', () => {
    const proposal = toProposalView({
      id: 'UNITS-1',
      version: 1,
      contract_version: 'experience-units-v2',
      coverage: { processing_status: 'complete' },
      units: [{
        unit_id: 'UNIT-1',
        domain: { name: 'AI' },
        project: { name: 'Career Memory' },
        title: '기존 제목',
        actions: ['설계'],
        results: ['단축'],
        source_ref_ids: ['SRC-1'],
        source_refs: [{ id: 'SRC-1', message_id: 'MSG-1' }],
        primary_span_ids: ['SPAN-1'],
        context_span_ids: ['SPAN-H'],
        field_span_ids: { actions: ['SPAN-1'] },
      }],
    });
    const edited = { ...proposal, units: [{ ...proposal.units[0], title: '수정 제목' }] };
    const wireUnits = applyExperienceUnitsChanges(proposal, edited);

    expect(proposal).toMatchObject({ kind: 'experience-units', contractVersion: 'experience-units-v2' });
    expect(wireUnits[0]).toMatchObject({
      unit_id: 'UNIT-1',
      title: '수정 제목',
      source_ref_ids: ['SRC-1'],
      primary_span_ids: ['SPAN-1'],
      context_span_ids: ['SPAN-H'],
    });
  });

  it('does not truncate a large v2 unit collection while mapping and editing', () => {
    const sourceUnits = Array.from({ length: 80 }, (_, index) => ({
      unit_id: `UNIT-${index + 1}`,
      title: `경험 ${index + 1}`,
      domain: { name: '개발 경험' },
      project: { name: `프로젝트 ${Math.floor(index / 10) + 1}` },
      actions: [`행동 ${index + 1}`],
      results: [`결과 ${index + 1}`],
      primary_span_ids: [`SPAN-${index + 1}`],
      context_span_ids: [`HEADING-${Math.floor(index / 10) + 1}`],
      source_ref_ids: [`SOURCE-${index + 1}`],
    }));
    const proposal = toProposalView({
      id: 'UNITS-LARGE',
      version: 1,
      contract_version: 'experience-units-v2',
      coverage: { processing_status: 'complete', experience_span_count: 80 },
      units: sourceUnits,
    });

    expect(proposal.units).toHaveLength(80);
    expect(proposal.units.at(-1)).toMatchObject({
      unitId: 'UNIT-80',
      title: '경험 80',
      primarySpanIds: ['SPAN-80'],
    });

    const wireUnits = applyExperienceUnitsChanges(proposal, {
      ...proposal,
      units: proposal.units.map((unit, index) => (
        index === 79 ? { ...unit, title: '수정한 마지막 경험' } : unit
      )),
    });

    expect(wireUnits).toHaveLength(80);
    expect(wireUnits.at(-1)).toMatchObject({
      unit_id: 'UNIT-80',
      title: '수정한 마지막 경험',
      primary_span_ids: ['SPAN-80'],
      source_ref_ids: ['SOURCE-80'],
    });
  });
});
