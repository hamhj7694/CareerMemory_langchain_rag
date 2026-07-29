import { v2ChatApi } from './v2ChatApi.js';
import { toExperience } from '../features/experience/model/experienceMapper.js';

let jobSequence = 1;
const jobs = new Map();
const requirementLinks = new Map();
const evidence = new Map();

const now = () => new Date().toISOString();
const clone = (value) => structuredClone(value);
const unique = (values) => [...new Set(values.filter(Boolean))];

const toSourceRef = (source) => ({
  id: source.id,
  raw_id: source.rawId || `RAW-${source.id}`,
  source_type: source.sourceType,
  title: source.filename || (source.sourceType === 'text' ? '텍스트 입력' : '첨부 파일'),
  filename: source.filename,
  mime_type: source.mimeType || '',
  size_bytes: source.sizeBytes || 0,
  raw_bytes: source.rawBytes || null,
  text: source.text || '',
  captured_at: source.capturedAt || now(),
  uploaded_at: source.uploadedAt,
  linked_facts: source.linkedFacts || [],
});

const evidenceLines = (sources) => unique(sources.flatMap((source) => {
  const linkedFacts = (source.linkedFacts || []).map((link) => link.fact);
  const textLines = String(source.text || '').split(/\r?\n|(?<=[.!?])\s+/).map((line) => line.trim()).filter(Boolean);
  return [...linkedFacts, ...textLines];
}));

const ensureEvidence = (experience) => {
  (experience.source_refs || []).forEach((source) => {
    if (!source?.id) return;
    evidence.set(source.id, {
      id: source.id,
      rawId: source.raw_id || `RAW-${source.id}`,
      sourceType: source.source_type || (source.filename ? 'file' : 'text'),
      text: source.text || '',
      filename: source.filename || source.title,
      mimeType: source.mime_type || source.mimeType || '',
      sizeBytes: source.size_bytes || source.sizeBytes || 0,
      rawBytes: source.raw_bytes || source.rawBytes || null,
      unavailable: Boolean(source.unavailable),
      capturedAt: source.captured_at,
      uploadedAt: source.uploaded_at,
      linkedFacts: source.linked_facts || [],
    });
  });
  (experience.source_ids || []).forEach((sourceId) => {
    if (!evidence.has(sourceId)) {
      const capturedAt = experience.created_at || now();
      evidence.set(sourceId, {
        id: sourceId,
        rawId: `RAW-${sourceId}`,
        sourceType: 'unknown',
        text: '',
        filename: '원본 정보 없음',
        unavailable: true,
        capturedAt,
        uploadedAt: undefined,
        linkedFacts: [],
      });
    }
  });
};

const experienceScore = (requirement, experience) => {
  const terms = `${requirement.text} ${(requirement.keywords || []).join(' ')}`.toLowerCase().split(/\s+/).filter((term) => term.length > 1);
  const haystack = `${experience.title} ${experience.summary} ${(experience.skills || []).join(' ')} ${(experience.actions || []).join(' ')} ${(experience.results || []).join(' ')}`.toLowerCase();
  return terms.reduce((score, term) => score + (haystack.includes(term) ? 1 : 0), 0);
};

const toRequirement = (jobId, text, index) => {
  const sourceExcerpt = String(text || '').trim();
  const keywords = sourceExcerpt.split(/[\s,·/]+/).map((word) => word.replace(/[^\p{L}\p{N}]/gu, '')).filter((word) => word.length > 1).slice(0, 5);
  const title = sourceExcerpt.length > 34 ? `${sourceExcerpt.slice(0, 34).trim()}…` : sourceExcerpt;
  const keywordSummary = keywords.slice(0, 3).join('·');
  const needsReview = sourceExcerpt.length < 8;
  return {
    id: `REQ-${jobId}-${index + 1}`,
    order: index + 1,
    type: index ? 'qualification' : 'responsibility',
    text: title,
    title: title || '요구사항 제목 없음',
    summary: keywordSummary ? `${keywordSummary} 관련 역량을 실제 업무에서 활용한 경험을 요구합니다.` : '공고에서 요구하는 실무 경험과 역량을 확인해 주세요.',
    sourceExcerpt,
    importance: index ? 'preferred' : 'required',
    keywords,
    confidence: needsReview ? 0.35 : 0.82,
    needsReview,
    sourceLocator: { source: 'posting_content', line: index + 1 },
  };
};

const seedJob = {
  jobId: 'JOB-001', companyName: '넥스트랩', roleName: '서비스 기획자', postingTitle: '서비스 기획자 경력 채용', sourceUrl: 'https://example.com/jobs/service-planner', postingContent: '데이터 기반 서비스 개선 및 개발·디자인 조직과 협업',
  requirements: [
    { id: 'REQ-001', order: 1, type: 'responsibility', text: '데이터 기반 서비스 개선', title: '데이터 기반 서비스 개선', summary: '서비스 지표를 분석하고 개선안을 실행한 경험을 요구합니다.', sourceExcerpt: '데이터 기반으로 서비스 지표와 사용자 흐름을 분석하고 개선 과제를 도출한 경험', importance: 'required', keywords: ['데이터', '서비스 개선'], confidence: 0.92, needsReview: false, sourceLocator: { source: 'posting_content', line: 1 } },
    { id: 'REQ-002', order: 2, type: 'collaboration', text: '개발·디자인 조직과 협업', title: '개발·디자인 조직과 협업', summary: '여러 직군과 요구사항을 조율하며 제품을 완성한 경험을 우대합니다.', sourceExcerpt: '개발·디자인 조직과 원활하게 협업하고 요구사항을 조율할 수 있는 분', importance: 'preferred', keywords: ['협업'], confidence: 0.9, needsReview: false, sourceLocator: { source: 'posting_content', line: 2 } },
  ],
  warnings: [], analyzedAt: now(),
};
jobs.set(seedJob.jobId, seedJob);

export const unifiedMockApi = {
  async getExperience(experienceId) { return toExperience(await v2ChatApi.getExperience(experienceId)); },
  async createExperience(input) { return toExperience(await v2ChatApi.createExperience(input)); },
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
    const updated = { ...current, ...changes, updatedAt: now() };
    evidence.set(sourceId, updated);
    const { items } = await v2ChatApi.listExperiences();
    const updatedExperiences = [];
    for (const item of items.filter((experience) => (experience.source_ids || []).includes(sourceId))) {
      const sourceRefs = (item.source_refs || []).map((source) => source?.id === sourceId ? {
        ...source,
        text: updated.text || '',
        filename: updated.filename,
        mime_type: updated.mimeType || source.mime_type,
        size_bytes: updated.sizeBytes || source.size_bytes,
        raw_bytes: updated.rawBytes || source.raw_bytes,
        updated_at: updated.updatedAt,
      } : source);
      const saved = await v2ChatApi.updateExperience(item.id, {
        base_version: item.version,
        changes: { source_refs: sourceRefs },
      });
      updatedExperiences.push(toExperience(saved));
    }
    return clone({ ...updated, experiences: updatedExperiences });
  },
  async addTextEvidence(experienceId, { text, title }) {
    const experience = await v2ChatApi.getExperience(experienceId);
    ensureEvidence(experience);
    const createdAt = now();
    const source = {
      id: `SRC-LOCAL-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      rawId: `RAW-LOCAL-${Date.now()}`,
      sourceType: 'text',
      text: text.trim(),
      filename: title?.trim() || '',
      capturedAt: createdAt,
      linkedFacts: [],
    };
    evidence.set(source.id, source);
    const sourceIds = [...(experience.source_ids || []), source.id];
    const sourceRefs = [...(experience.source_refs || []), toSourceRef(source)];
    const updated = await v2ChatApi.updateExperience(experienceId, {
      base_version: experience.version,
      changes: {
        source_ids: sourceIds,
        source_refs: sourceRefs,
        evidence_count: sourceIds.length,
        evidence_status: 'verified',
      },
    });
    return {
      experience: toExperience(updated),
      sources: sourceIds.map((id) => clone(evidence.get(id))).filter(Boolean),
      addedSourceIds: [source.id],
    };
  },
  async addFileEvidence(experienceId, files) {
    const experience = await v2ChatApi.getExperience(experienceId);
    ensureEvidence(experience);
    const attachments = await v2ChatApi.uploadAttachments(files);
    const added = attachments.map((attachment) => ({
      id: attachment.id,
      rawId: `RAW-${attachment.id}`,
      sourceType: 'file',
      text: attachment.raw_text || '',
      filename: attachment.filename,
      mimeType: attachment.mime_type,
      sizeBytes: attachment.size_bytes,
      rawBytes: attachment.raw_bytes,
      capturedAt: attachment.created_at,
      uploadedAt: attachment.created_at,
      linkedFacts: [],
    }));
    added.forEach((source) => evidence.set(source.id, source));
    const sourceIds = [...(experience.source_ids || []), ...added.map((source) => source.id)];
    const sourceRefs = [...(experience.source_refs || []), ...added.map(toSourceRef)];
    const updated = await v2ChatApi.updateExperience(experienceId, {
      base_version: experience.version,
      changes: {
        source_ids: sourceIds,
        source_refs: sourceRefs,
        evidence_count: sourceIds.length,
        evidence_status: 'verified',
      },
    });
    return {
      experience: toExperience(updated),
      sources: sourceIds.map((id) => clone(evidence.get(id))).filter(Boolean),
      addedSourceIds: added.map((source) => source.id),
    };
  },
  async unlinkEvidence(experienceId, sourceId) {
    const experience = await v2ChatApi.getExperience(experienceId);
    const sourceIds = (experience.source_ids || []).filter((id) => id !== sourceId);
    if (sourceIds.length === (experience.source_ids || []).length) throw new Error('현재 경험에 연결된 근거가 아닙니다.');
    ensureEvidence(experience);
    const remainingSources = sourceIds.map((id) => evidence.get(id)).filter(Boolean);
    const supportedFacts = new Set(remainingSources.flatMap((source) => (source.linkedFacts || []).map((link) => link.fact)));
    const unsupportedFacts = (experience.facts || []).filter((fact) => !supportedFacts.has(fact));
    const factEvidenceStatus = Object.fromEntries((experience.facts || []).map((fact) => [fact, supportedFacts.has(fact) ? 'supported' : 'needs_evidence']));
    const updated = await v2ChatApi.updateExperience(experienceId, {
      base_version: experience.version,
      changes: {
        source_ids: sourceIds,
        source_refs: (experience.source_refs || []).filter((source) => source?.id !== sourceId),
        evidence_count: sourceIds.length,
        evidence_status: sourceIds.length ? 'verified' : 'missing',
        fact_evidence_status: factEvidenceStatus,
      },
    });
    return {
      experience: toExperience(updated),
      sources: remainingSources.map(clone),
      unlinkedSourceId: sourceId,
      sourceDeleted: false,
      unsupportedFacts,
    };
  },
  async reorganizeExperienceFromEvidence(experienceId) {
    const experience = await v2ChatApi.getExperience(experienceId);
    ensureEvidence(experience);
    const sources = (experience.source_ids || []).map((id) => evidence.get(id)).filter(Boolean);
    if (!sources.length) throw new Error('다시 정리할 원본 근거가 없습니다.');
    const lines = evidenceLines(sources);
    const numericResults = lines.filter((line) => /\d|%|증가|감소|개선|달성|단축|절감/.test(line));
    const titleBase = String(experience.title || '경험').replace(/(?:\s*-\s*새 정리본)+$/, '');
    const summary = lines.slice(0, 3).join('\n') || experience.summary || '현재 원본 근거를 기준으로 다시 정리한 경험입니다.';
    const created = await v2ChatApi.createExperience({
      project_id: experience.project_id || experience.project?.id,
      title: `${titleBase} - 새 정리본`,
      summary,
      role: experience.role || '',
      situation: lines[0] || experience.situation || '',
      actions: lines.length ? lines.slice(0, Math.min(5, lines.length)) : (experience.actions || []),
      results: numericResults.length ? numericResults.slice(0, 5) : (experience.results || []),
      skills: experience.skills || [],
      facts: lines.length ? lines.slice(0, 10) : (experience.facts || []),
      source_ids: sources.map((source) => source.id),
      source_refs: sources.map(toSourceRef),
      status: 'confirmed',
      reorganized_from_experience_id: experienceId,
      reorganized_at: now(),
    });
    return {
      experience: toExperience(created),
      sourceExperienceId: experienceId,
      sources: sources.map(clone),
    };
  },
  async removeEvidence(sourceId) { evidence.delete(sourceId); return { sourceId, deleted: true }; },
  async analyzeJob(input) {
    const jobId = `JOB-MOCK-${++jobSequence}`;
    const lines = input.postingContent.split(/\n+/).map((line) => line.trim()).filter(Boolean);
    const requirements = (lines.length > 1 ? lines : [input.postingContent, '유관 부서와 원활한 협업']).slice(0, 5).map((text, index) => toRequirement(jobId, text, index));
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
      return { requirementId: requirement.id, requirementText: requirement.text, status: selected.length ? 'direct' : 'noEvidence', reason: '', linkedExperienceIds: [...requirementLinks.get(linkKey)], experiences: selected.map(({ experience, score }) => ({ ...toExperience(experience), experienceId: experience.id, linkSource: 'ai', linkStatus: 'suggested', score, evidence: (experience.source_ids || []).map((sourceId) => ({ sourceId })) })), missingInformation: [] };
    });
    return { jobId, matches, failures: [] };
  },
  async setRequirementLink(jobId, requirementId, experienceId, linked) {
    const key = `${jobId}:${requirementId}`; const ids = requirementLinks.get(key) || new Set();
    linked ? ids.add(experienceId) : ids.delete(experienceId); requirementLinks.set(key, ids);
    return { jobId, requirementId, experienceId, linked, source: 'user', updatedAt: now() };
  },
};
