import { describe, expect, it } from 'vitest';
import { createEmptyExperience, toExperience, toExperienceChanges } from './experienceMapper.js';
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
});
