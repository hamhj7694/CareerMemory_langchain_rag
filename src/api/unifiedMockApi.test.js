import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { experienceApi } from './experienceApi.js';
import { jobApi } from './jobApi.js';
import { sourceApi } from './sourceApi.js';
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

  it('normalizes analyzed requirements into title, summary, and source excerpt fields', async () => {
    const job = await jobApi.analyze({
      postingContent: '퍼널 지표를 분석해 전환율 개선 과제를 도출한 경험\n개발 및 디자인 조직과 협업한 경험',
      companyName: '',
      roleName: '',
    });

    expect(job.requirements).toHaveLength(2);
    expect(job.requirements[0]).toMatchObject({
      order: 1,
      title: expect.any(String),
      summary: expect.any(String),
      sourceExcerpt: '퍼널 지표를 분석해 전환율 개선 과제를 도출한 경험',
      confidence: expect.any(Number),
      needsReview: false,
      sourceLocator: { source: 'posting_content', line: 1 },
    });
  });

  it('marks a requirement with insufficient source text for review', async () => {
    const job = await jobApi.analyze({ postingContent: '기획', companyName: '', roleName: '' });

    expect(job.requirements[0]).toMatchObject({
      order: 1,
      needsReview: true,
      confidence: 0.35,
    });
  });

  it('unlinks evidence from one experience without deleting the source', async () => {
    const before = await experienceApi.get('exp-platform-conversion');
    const sourceId = before.sourceRefs[0];

    const result = await sourceApi.unlink(before.id, sourceId);
    const after = await experienceApi.get(before.id);

    expect(result.sourceDeleted).toBe(false);
    expect(result.unlinkedSourceId).toBe(sourceId);
    expect(after.sourceRefs).not.toContain(sourceId);
    expect(after.evidenceCount).toBe(before.evidenceCount - 1);
    expect(after.factEvidenceStatus).toBeDefined();
  });

  it('adds and edits evidence, then saves a reorganized experience as a new card', async () => {
    const original = await experienceApi.get('exp-platform-conversion');
    const added = await sourceApi.addText(original.id, {
      title: '추가 인터뷰 기록',
      text: '지원 전환 흐름을 다시 분석했습니다.\n전환율을 21% 높였습니다.',
    });
    const addedSourceId = added.addedSourceIds[0];

    expect(added.sources.some((source) => source.id === addedSourceId)).toBe(true);

    await sourceApi.update(addedSourceId, {
      text: '지원 전환 흐름을 다시 분석했습니다.\n전환율을 24% 높였습니다.',
    });
    const latestSources = await experienceApi.getSources(original.id);
    expect(latestSources.sources.find((source) => source.id === addedSourceId)?.text).toContain('24%');

    const reorganized = await sourceApi.reorganize(original.id);
    const saved = await experienceApi.get(reorganized.experience.id);

    expect(saved.id).not.toBe(original.id);
    expect(saved.title).toBe(`${original.title} - 새 정리본`);
    expect(saved.projectId).toBe(original.projectId);
    expect(saved.evidenceIds).toContain(addedSourceId);
    expect(saved.summary).toContain('24%');
  });

  it('keeps the actual uploaded file bytes in newly added evidence', async () => {
    const bytes = new TextEncoder().encode('실제 파일 근거 내용');
    const file = {
      name: 'real-evidence.txt',
      type: 'text/plain',
      size: bytes.byteLength,
      text: async () => '실제 파일 근거 내용',
      arrayBuffer: async () => bytes.buffer.slice(0),
    };

    const added = await sourceApi.addFiles('exp-platform-conversion', [file]);
    const source = added.sources.find((entry) => entry.id === added.addedSourceIds[0]);
    const blob = await sourceApi.download(source);

    expect(source.filename).toBe('real-evidence.txt');
    expect(await blob.text()).toBe('실제 파일 근거 내용');
  });

  it('recovers missing classification names into selectable structure nodes', async () => {
    const created = await v2ChatApi.createExperience({
      title: '분류 연결이 없는 경험',
      summary: '구조 복구 테스트',
      status: 'confirmed',
      source_ids: [],
      source_refs: [],
    });

    const structure = await v2ChatApi.listStructure();
    const fallbackDomain = structure.domains.find((domain) => domain.name === '미분류 경험');
    const fallbackProject = fallbackDomain?.projects.find((project) => project.name === '프로젝트·활동 미분류');
    const detail = await experienceApi.get(created.id);

    expect(fallbackDomain).toBeDefined();
    expect(fallbackProject).toBeDefined();
    expect(detail.domainId).toBe(fallbackDomain.id);
    expect(detail.domainName).toBe('미분류 경험');
    expect(detail.projectId).toBe(fallbackProject.id);
    expect(detail.projectName).toBe('프로젝트·활동 미분류');
  });
});
