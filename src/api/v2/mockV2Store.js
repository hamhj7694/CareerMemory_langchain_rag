import { initialExperiences } from '../../mocks/canonicalExperienceSeeds.js';

const now = () => new Date().toISOString();
let sequence = 100;
const id = (prefix) => `${prefix}-${++sequence}`;
const clone = (value) => structuredClone(value);

// 예시 경험은 단위 테스트의 고정 fixture로만 사용합니다.
// 실제 개발 화면과 배포 화면에서는 빈 목록에서 시작해 DB 데이터만 보여 줍니다.
const fixtureExperiences = import.meta.env.MODE === 'test' ? initialExperiences : [];
const domainIds = new Map();
const projectIds = new Map();
const seedDomains = [];
const seedProjects = [];

fixtureExperiences.forEach((item) => {
  if (!domainIds.has(item.domain)) {
    const domainId = `DOM-SEED-${domainIds.size + 1}`;
    domainIds.set(item.domain, domainId);
    seedDomains.push({ id: domainId, name: item.domain, created_at: now(), updated_at: now(), version: 1 });
  }
  const projectKey = `${item.domain}::${item.project}`;
  if (!projectIds.has(projectKey)) {
    const projectId = `PROJ-SEED-${projectIds.size + 1}`;
    projectIds.set(projectKey, projectId);
    seedProjects.push({ id: projectId, domain_id: domainIds.get(item.domain), name: item.project, organization: item.organization || '', created_at: now(), updated_at: now(), version: 1 });
  }
});

const seedExperiences = fixtureExperiences.map((item) => ({
  id: item.id,
  title: item.title,
  summary: item.summary || '',
  domain: { id: domainIds.get(item.domain), name: item.domain },
  project: { id: projectIds.get(`${item.domain}::${item.project}`), name: item.project, organization: item.organization || '' },
  situation: item.situation || '',
  actions: item.actions || [],
  results: item.results || [],
  role: item.role || '',
  facts: item.facts || [],
  skills: item.skills || [],
  period: item.period || '',
  missing_information: item.missing || [],
  evidence_count: item.evidenceCount || 0,
  evidence_status: item.evidenceCount ? 'verified' : 'missing',
  source_ids: Array.from({ length: item.evidenceCount || 0 }, (_, index) => `SRC-${item.id}-${index + 1}`),
  created_at: now(),
  updated_at: now(),
  version: 1,
}));

export const mockV2Store = {
  conversations: [],
  messages: [],
  attachments: [],
  sources: [],
  extractionRuns: [],
  proposals: [],
  domains: clone(seedDomains),
  projects: clone(seedProjects),
  experiences: clone(seedExperiences),
  deleted: { domains: [], projects: [], experiences: [] },
};

export function nextId(prefix) { return id(prefix); }
export function timestamp() { return now(); }
export function snapshot(value) { return clone(value); }

export function resetMockV2Store() {
  mockV2Store.conversations = [];
  mockV2Store.messages = [];
  mockV2Store.attachments = [];
  mockV2Store.sources = [];
  mockV2Store.extractionRuns = [];
  mockV2Store.proposals = [];
  mockV2Store.domains = clone(seedDomains);
  mockV2Store.projects = clone(seedProjects);
  mockV2Store.experiences = clone(seedExperiences);
  mockV2Store.deleted = { domains: [], projects: [], experiences: [] };
}
