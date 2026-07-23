import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { experienceApi } from './experienceApi.js';
import { jobApi } from './jobApi.js';
import { resetMockV2Store } from './v2/mockV2Store.js';
import { v2ChatApi } from './v2ChatApi.js';

describe('unified frontend mock data', () => {
  beforeEach(() => resetMockV2Store());
  afterEach(() => resetMockV2Store());

  it('shares the latest experience across management, detail, and job matching', async () => {
    const current = await v2ChatApi.getExperience('exp-platform-conversion');
    await v2ChatApi.updateExperience(current.id, { base_version: current.version, changes: { title: '통합 경험 제목', skills: ['데이터 분석'] } });

    const detail = await experienceApi.get(current.id);
    expect(detail.title).toBe('통합 경험 제목');

    const result = await jobApi.match('JOB-001');
    const matched = result.matches.flatMap((match) => match.experiences).find((item) => item.experienceId === current.id);
    expect(matched?.title).toBe('통합 경험 제목');
  });

  it('persists requirement-experience links in the shared relation store', async () => {
    await jobApi.match('JOB-001');
    await jobApi.setRequirementLink('JOB-001', 'REQ-002', 'exp-platform-conversion', true);
    const result = await jobApi.match('JOB-001');
    const requirement = result.matches.find((match) => match.requirementId === 'REQ-002');
    expect(requirement.linkedExperienceIds).toContain('exp-platform-conversion');
  });
});
