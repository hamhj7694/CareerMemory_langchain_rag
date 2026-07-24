const list = (value) => Array.isArray(value) ? value.filter(Boolean) : [];

export function toExperience(item = {}) {
  const domain = item.domain || {};
  const project = item.project || {};
  const sourceReferences = list(item.sourceRefs || item.source_refs);
  const sourceIds = item.evidenceIds || item.source_ids || sourceReferences.map((source) => typeof source === 'string' ? source : source.id).filter(Boolean);
  return {
    id: item.id || '',
    version: item.version ?? 0,
    status: item.status || 'confirmed',
    domainId: item.domainId || item.domain_id || domain.id || '',
    domainName: item.domainName || domain.name || '',
    projectId: item.projectId || item.project_id || project.id || '',
    projectName: item.projectName || project.name || '',
    organization: item.organization || project.organization || '',
    period: item.period || {},
    title: item.title || '',
    summary: item.summary || '',
    role: item.role || '',
    roles: list(item.roles || item.role_tags),
    situation: item.situation || '',
    actions: list(item.actions),
    results: list(item.results),
    skills: list(item.skills),
    skillLinks: list(item.skillLinks || item.skill_links),
    facts: list(item.facts),
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
    project_id: experience.projectId,
    title: experience.title,
    summary: experience.summary,
    role: experience.role,
    situation: experience.situation,
    actions: list(experience.actions),
    results: list(experience.results),
    skills: list(experience.skills),
    skill_links: list(experience.skillLinks),
    facts: list(experience.facts),
    missing_information: list(experience.missingInformation),
    source_ids: list(experience.evidenceIds),
    source_refs: list(experience.sourceRefs),
    status: experience.status || 'confirmed',
  };
}

export function toExperienceChanges(experience) {
  return {
    title: experience.title,
    summary: experience.summary,
    role: experience.role,
    situation: experience.situation,
    actions: list(experience.actions),
    results: list(experience.results),
    skills: list(experience.skills),
    skill_links: list(experience.skillLinks),
    facts: list(experience.facts),
    missing_information: list(experience.missingInformation),
    source_ids: list(experience.evidenceIds),
    source_refs: list(experience.sourceRefs),
    status: experience.status || 'confirmed',
  };
}

export function createEmptyExperience(overrides = {}) {
  return toExperience({ status: 'draft', ...overrides });
}
