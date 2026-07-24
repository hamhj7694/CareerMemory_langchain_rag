import { describe, expect, it } from 'vitest';
import { buildSkillProfile, getSkillGroup, listExperienceRoles } from './skillModel.js';

describe('skill model', () => {
  it('normalizes experience skills into groups and links', () => {
    const profile = buildSkillProfile([{ id: 'EXP-1', role: '서비스 기획', skills: ['데이터 분석', 'UX 기획'], evidenceIds: ['SRC-1'] }]);
    expect(profile.totalLinks).toBe(2);
    expect(profile.links).toHaveLength(2);
    expect(profile.groups.map((group) => group.name)).toEqual(['데이터·분석', '기획·제품']);
    expect(profile.groups[0].experienceIds).toEqual(['EXP-1']);
  });

  it('prefers an explicit AI-provided group over fallback rules', () => {
    expect(getSkillGroup('데이터 분석', { id: 'custom', name: 'AI 분류' })).toMatchObject({ id: 'custom', name: 'AI 분류', source: 'ai' });
  });

  it('collects roles without duplicates', () => {
    expect(listExperienceRoles([{ role: '서비스 기획', roles: ['팀 리드'] }, { role: '서비스 기획' }])).toEqual(['서비스 기획', '팀 리드']);
  });
});
