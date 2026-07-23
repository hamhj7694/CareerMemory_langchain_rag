import { v2ChatApi } from './v2ChatApi.js';

let jobSequence = 1;
const jobs = new Map();
const requirementLinks = new Map();
const evidence = new Map();

const now = () => new Date().toISOString();
const clone = (value) => structuredClone(value);

const toExperience = (item) => ({
  id: item.id,
  domainId: item.domain?.id,
  domainName: item.domain?.name,
  projectId: item.project?.id,
  projectName: item.project?.name,
  organization: item.project?.organization || '',
  period: item.period || {},
  title: item.title,
  summary: item.summary || '',
  situation: item.situation || '',
  actions: item.actions || [],
  results: item.results || [],
  role: item.role || '',
  facts: item.facts || [],
  skills: item.skills || [],
  missingInformation: item.missing_information || [],
  sourceRefs: item.source_ids || [],
  evidenceCount: item.evidence_count ?? item.source_ids?.length ?? 0,
  visibility: 'visible',
  createdAt: item.created_at,
  updatedAt: item.updated_at,
  version: item.version,
});

const ensureEvidence = (experience) => {
  (experience.source_ids || []).forEach((sourceId, index) => {
    if (!evidence.has(sourceId)) evidence.set(sourceId, {
      id: sourceId,
      rawId: `RAW-${sourceId}`,
      sourceType: index ? 'file' : 'text',
      text: experience.summary || `${experience.title}의 원본 근거`,
      filename: index ? `${experience.title}-근거-${index}.txt` : undefined,
      capturedAt: experience.created_at,
      linkedFacts: (experience.facts || []).map((fact) => ({ fact, quote: fact })),
    });
  });
};

const experienceScore = (requirement, experience) => {
  const terms = `${requirement.text} ${(requirement.keywords || []).join(' ')}`.toLowerCase().split(/\s+/).filter((term) => term.length > 1);
  const haystack = `${experience.title} ${experience.summary} ${(experience.skills || []).join(' ')} ${(experience.actions || []).join(' ')} ${(experience.results || []).join(' ')}`.toLowerCase();
  return terms.reduce((score, term) => score + (haystack.includes(term) ? 1 : 0), 0);
};

const seedJob = {
  jobId: 'JOB-001', companyName: '넥스트랩', roleName: '서비스 기획자', postingTitle: '서비스 기획자 경력 채용', sourceUrl: 'https://example.com/jobs/service-planner', postingContent: '데이터 기반 서비스 개선 및 개발·디자인 조직과 협업',
  requirements: [
    { id: 'REQ-001', type: 'responsibility', text: '데이터 기반 서비스 개선', importance: 'required', keywords: ['데이터', '서비스 개선'] },
    { id: 'REQ-002', type: 'collaboration', text: '개발·디자인 조직과 협업', importance: 'preferred', keywords: ['협업'] },
  ],
  warnings: [], analyzedAt: now(),
};
jobs.set(seedJob.jobId, seedJob);

export const unifiedMockApi = {
  async getExperience(experienceId) { return toExperience(await v2ChatApi.getExperience(experienceId)); },
  async updateExperience(experienceId, patch) {
    return toExperience(await v2ChatApi.updateExperience(experienceId, { base_version: patch.version, changes: patch.changes }));
  },
  async getExperienceTree() {
    const structure = await v2ChatApi.listStructure();
    return {
      domains: structure.domains.map((domain) => ({
        id: domain.id, name: domain.name,
        experienceCount: domain.projects.reduce((sum, project) => sum + project.experiences.length, 0),
        projects: domain.projects.map((project) => ({ id: project.id, name: project.name, organization: project.organization || '', experienceCount: project.experiences.length, experiences: project.experiences.map(toExperience) })),
      })),
      totalExperienceCount: structure.domains.reduce((sum, domain) => sum + domain.projects.reduce((count, project) => count + project.experiences.length, 0), 0),
    };
  },
  async getExperienceSources(experienceId) {
    const item = await v2ChatApi.getExperience(experienceId); ensureEvidence(item);
    return { experienceId, sources: (item.source_ids || []).map((id) => clone(evidence.get(id))).filter(Boolean) };
  },
  async updateEvidence(sourceId, changes) {
    const current = evidence.get(sourceId) || { id: sourceId, sourceType: 'text', text: '' };
    const updated = { ...current, ...changes, updatedAt: now() }; evidence.set(sourceId, updated); return clone(updated);
  },
  async removeEvidence(sourceId) { evidence.delete(sourceId); return { sourceId, deleted: true }; },
  async analyzeJob(input) {
    const jobId = `JOB-MOCK-${++jobSequence}`;
    const lines = input.postingContent.split(/\n+/).map((line) => line.trim()).filter(Boolean);
    const requirements = (lines.length > 1 ? lines : [input.postingContent, '유관 부서와 원활한 협업']).slice(0, 5).map((text, index) => ({ id: `REQ-${jobId}-${index + 1}`, type: index ? 'qualification' : 'responsibility', text, importance: index ? 'preferred' : 'required', keywords: text.split(/[\s,·]+/).filter((word) => word.length > 1).slice(0, 5) }));
    const job = { jobId, companyName: input.companyName || '', roleName: input.roleName || '', postingTitle: input.postingTitle || '', sourceUrl: input.sourceUrl || '', postingContent: input.postingContent, requirements, warnings: [], analyzedAt: now() };
    jobs.set(jobId, job); return clone(job);
  },
  async getJob(jobId) {
    const job = jobs.get(jobId); if (!job) throw new Error('공고를 찾을 수 없습니다.'); return clone(job);
  },
  async matchJob(jobId, { requirementIds = [] } = {}) {
    const job = jobs.get(jobId); if (!job) throw new Error('공고를 찾을 수 없습니다.');
    const { items } = await v2ChatApi.listExperiences();
    const targets = requirementIds.length ? job.requirements.filter((item) => requirementIds.includes(item.id)) : job.requirements;
    const matches = targets.map((requirement, requirementIndex) => {
      const ranked = items.map((experience) => ({ experience, score: experienceScore(requirement, experience) })).sort((a, b) => b.score - a.score);
      const recommended = ranked.filter((item) => item.score > 0).slice(0, 3);
      const selected = recommended.length ? recommended : (requirementIndex === 0 && ranked[0] ? [ranked[0]] : []);
      const linkKey = `${jobId}:${requirement.id}`;
      if (!requirementLinks.has(linkKey)) requirementLinks.set(linkKey, new Set(selected.map((item) => item.experience.id)));
      return { requirementId: requirement.id, requirementText: requirement.text, status: selected.length ? 'direct' : 'noEvidence', reason: '', linkedExperienceIds: [...requirementLinks.get(linkKey)], experiences: selected.map(({ experience, score }) => ({ ...toExperience(experience), experienceId: experience.id, score, evidence: (experience.source_ids || []).map((sourceId) => ({ sourceId })) })), missingInformation: [] };
    });
    return { jobId, matches, failures: [] };
  },
  async setRequirementLink(jobId, requirementId, experienceId, linked) {
    const key = `${jobId}:${requirementId}`; const ids = requirementLinks.get(key) || new Set();
    linked ? ids.add(experienceId) : ids.delete(experienceId); requirementLinks.set(key, ids);
    return { jobId, requirementId, experienceId, linked, source: 'user', updatedAt: now() };
  },
};
