import { describe, expect, it } from 'vitest';
import {
  createEmptyExperience,
  toExperience,
  toExperienceChanges,
  toExperienceCreateInput,
} from './experienceMapper.js';
import { selectExperienceCard, selectExperiencePreview } from './experienceSelectors.js';

describe('experience model', () => {
  it('API 응답을 하나의 정규 경험으로 변환한다', () => {
    const experience = toExperience({
      id: 'EXP-1',
      domain: { id: 'DOM-1', name: '직장 경험' },
      project: { id: 'PROJ-1', name: '서비스 개선', organization: 'ABC' },
      title: '지원 전환율 개선',
      source_ids: ['SRC-1'],
    });
    expect(experience).toMatchObject({
      id: 'EXP-1',
      domainId: 'DOM-1',
      projectId: 'PROJ-1',
      projectName: '서비스 개선',
      evidenceIds: ['SRC-1'],
    });
    expect(experience.actions).toEqual([]);
  });

  it('미리보기와 카드는 같은 경험에서 파생된다', () => {
    const experience = toExperience({ id: 'EXP-1', title: '지원 전환율 개선', summary: '요약', skills: ['데이터 분석', 'UX 기획', 'A/B 테스트'] });
    expect(selectExperiencePreview(experience).summary).toBe('요약');
    expect(selectExperienceCard(experience).skills).toEqual(['데이터 분석', 'UX 기획']);
  });

  it('빈 초안도 전체 상세 필드를 가진다', () => {
    const draft = createEmptyExperience();
    expect(draft.status).toBe('draft');
    expect(toExperienceChanges(draft)).toMatchObject({ actions: [], results: [], facts: [], skills: [] });
  });

  it('근거와 확장 블록을 API 왕복 과정에서 보존한다', () => {
    const raw = {
      id: 'EXP-lossless',
      title: '무손실 경험',
      facts: ['응답시간 50% 단축'],
      skill_mentions: [{ raw_text: '페스트API', canonical_skill_id: 'skill-fastapi' }],
      skill_groups: [{ name: '백엔드', skill_names: ['FastAPI'] }],
      field_citations: { 'facts.0': [{ source_ref_id: 'SRC-1', quote: '응답시간 50% 단축' }] },
      fact_evidence_status: { '응답시간 50% 단축': 'supported' },
      content_blocks: [
        { id: 'BLOCK-1', type: 'custom', data: { value: '스키마 밖 정보' }, origin: 'user' },
        { id: 'BLOCK-core', type: 'summary', data: { text: 'projection' }, origin: 'system_projection' },
      ],
      extensions: { future_field: '보존됨' },
      confidence: 0.91,
      analysis_run_id: 'ANALYSIS-1',
    };

    const experience = toExperience(raw);
    expect(experience).toMatchObject({
      confidence: 0.91,
      analysisRunId: 'ANALYSIS-1',
      factEvidenceStatus: { '응답시간 50% 단축': 'supported' },
      extensions: { future_field: '보존됨' },
    });
    expect(experience.contentBlocks[0].data.value).toBe('스키마 밖 정보');

    const createInput = toExperienceCreateInput(experience);
    expect(createInput.field_citations['facts.0'][0].source_ref_id).toBe('SRC-1');
    expect(createInput.content_blocks[0].type).toBe('custom');
    expect(createInput.extensions.future_field).toBe('보존됨');
    expect(toExperienceChanges(experience).content_blocks).toEqual([
      expect.objectContaining({ id: 'BLOCK-1', origin: 'user' }),
    ]);
  });
});
