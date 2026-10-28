import { toExperienceContent, toExperienceContentChanges } from './experienceContent.js';
import { sanitizeExperienceContentBlocks } from './experienceDetailModel.js';

const list = (value) => Array.isArray(value) ? value.filter(Boolean) : [];

export function toExperience(item = {}) {
  const domain = item.domain || {};
  const project = item.project || {};
  const sourceReferences = list(item.sourceRefs || item.source_refs);
  const sourceIds = item.evidenceIds || item.source_ids || sourceReferences.map((source) => typeof source === 'string' ? source : source.id).filter(Boolean);
  const content = toExperienceContent(item);
  return {
    ...content,
    id: item.id || '',
    version: item.version ?? 0,
    status: item.status || 'confirmed',
    domainId: item.domainId || item.domain_id || domain.id || '',
    domainName: item.domainName || domain.name || '',
    projectId: item.projectId || item.project_id || project.id || '',
    projectName: item.projectName || project.name || '',
    organization: item.organization || project.organization || '',
    period: item.period || {},
    roles: list(item.roles || item.role_tags),
    skillLinks: list(item.skillLinks || item.skill_links),
    skillMentions: list(item.skillMentions || item.skill_mentions),
    skillGroups: list(item.skillGroups || item.skill_groups),
    metrics: list(item.metrics),
    fieldCitations: item.fieldCitations || item.field_citations || {},
    confidence: item.confidence ?? null,
    draftId: item.draftId || item.draft_id || null,
    analysisRunId: item.analysisRunId || item.analysis_run_id || null,
    analysisRun: item.analysisRun || item.analysis_run || null,
    contentDocument: item.contentDocument || item.content_document || null,
    contentBlocks: sanitizeExperienceContentBlocks(item.contentBlocks || item.content_blocks || item.contentDocument?.blocks || item.content_document?.blocks),
    extensions: item.extensions && typeof item.extensions === 'object' ? item.extensions : {},
    factEvidenceStatus: item.factEvidenceStatus || item.fact_evidence_status || {},
    missingInformation: list(item.missingInformation || item.missing_information),
    evidenceIds: list(sourceIds),
    sourceRefs: sourceReferences.length ? sourceReferences : list(sourceIds),
    evidenceCount: item.evidenceCount ?? item.evidence_count ?? sourceIds.length,
    visibility: item.visibility || 'visible',
    createdAt: item.createdAt || item.created_at || '',
    updatedAt: item.updatedAt || item.updated_at || '',
  };
}

export function toExperienceCreateInput(experience) {
  return {
    ...toExperienceContentChanges(experience),
    project_id: experience.projectId,
    skill_links: list(experience.skillLinks),
    skill_mentions: list(experience.skillMentions),
    skill_groups: list(experience.skillGroups),
    metrics: list(experience.metrics),
    field_citations: experience.fieldCitations || {},
    confidence: experience.confidence ?? null,
    draft_id: experience.draftId || null,
    analysis_run_id: experience.analysisRunId || null,
    content_blocks: list(experience.contentBlocks),
    extensions: experience.extensions || {},
    period: experience.period || {},
    missing_information: list(experience.missingInformation),
    source_ids: list(experience.evidenceIds),
    source_refs: list(experience.sourceRefs),
    status: experience.status || 'confirmed',
  };
}

export function toExperienceChanges(experience) {
  return {
    ...toExperienceContentChanges(experience),
    skill_links: list(experience.skillLinks),
    skill_mentions: list(experience.skillMentions),
    skill_groups: list(experience.skillGroups),
    metrics: list(experience.metrics),
    field_citations: experience.fieldCitations || {},
    confidence: experience.confidence ?? null,
    draft_id: experience.draftId || null,
    analysis_run_id: experience.analysisRunId || null,
    content_blocks: list(experience.contentBlocks).filter((block) => block.origin !== 'system_projection'),
    extensions: experience.extensions || {},
    period: experience.period || {},
    missing_information: list(experience.missingInformation),
    source_ids: list(experience.evidenceIds),
    source_refs: list(experience.sourceRefs),
    status: experience.status || 'confirmed',
  };
}

export function createEmptyExperience(overrides = {}) {
  return toExperience({ status: 'draft', ...overrides });
}
