import { groupEvidence } from '../evidence/model/evidenceMapper.js';
import { toExperienceContent } from '../experience/model/experienceContent.js';

const list = (value) => Array.isArray(value) ? value : [];
const structureName = (value) => typeof value === 'string' ? value : value?.name || '';

export function splitProposalSources(sourceRefs) {
  const grouped = groupEvidence(sourceRefs);
  const conversations = [...grouped.conversations, ...grouped.texts, ...grouped.unknown];
  return {
    ...grouped,
    conversations,
    conversationCount: conversations.length,
  };
}

function toExperienceDraftView(item, index, approvedIndexes) {
  const sourceRefs = list(item.source_refs || item.sourceRefs);
  const sourceRefIds = list(item.source_ref_ids || item.sourceRefIds);
  const missingInformation = list(item.missing_information || item.missingInformation);
  const content = toExperienceContent(item);
  return {
    ...item,
    ...content,
    draft_id: item.draft_id || item.draftId || `draft-${index}`,
    domain: structureName(item.domain),
    project: structureName(item.project),
    evidenceCount: sourceRefIds.length || sourceRefs.length,
    source_ref_ids: sourceRefIds,
    source_refs: sourceRefs,
    fieldCitations: item.field_citations || item.fieldCitations || {},
    confidence: item.confidence,
    missingInformation,
    skillGroups: list(item.skill_groups || item.skillGroups),
    needsConfirmation: missingInformation.length > 0,
    sourceIndex: item.sourceIndex ?? index,
    approved: Boolean(item.approved || approvedIndexes.has(index)),
    savedExperienceId: item.saved_experience_id || item.savedExperienceId || null,
    savedAt: item.saved_at || item.savedAt || null,
  };
}

export function toProposalView(proposal) {
  if (!proposal) return null;
  const payload = proposal.payload || proposal.rawPayload || {};
  const kind = proposal.kind || (proposal.type === 'analyze_job' ? 'job' : 'experience');

  if (kind === 'job') {
    const jobDraft = payload.job_draft || {};
    return {
      ...proposal,
      id: proposal.id,
      version: proposal.version,
      kind: 'job',
      title: proposal.title || '',
      summary: proposal.summary || '',
      postingTitle: proposal.postingTitle ?? jobDraft.posting_title ?? '',
      companyName: proposal.companyName ?? jobDraft.company_name ?? '',
      roleName: proposal.roleName ?? jobDraft.role_name ?? '',
      sourceUrl: proposal.sourceUrl ?? jobDraft.source_url ?? '',
      postingContent: proposal.postingContent ?? jobDraft.posting_content ?? '',
      rawPayload: payload,
    };
  }

  const sourceExperiences = list(proposal.experiences).length ? proposal.experiences : list(payload.experiences);
  const approvedIndexes = new Set(proposal.approvedExperienceIndexes || proposal.approved_experience_indexes || []);
  const experiences = sourceExperiences.map((item, index) => toExperienceDraftView(item, index, approvedIndexes));
  const first = experiences[0];
  return {
    ...proposal,
    id: proposal.id,
    version: proposal.version || 1,
    kind: 'experience',
    title: first?.title || proposal.title || '경험 구조화 제안',
    domain: first?.domain || structureName(payload.domain),
    project: first?.project || structureName(payload.project),
    role: first?.role || '',
    summary: first?.summary || proposal.summary || '',
    situation: first?.situation || '',
    actions: first?.actions || [],
    results: first?.results || [],
    facts: first?.facts || [],
    skills: first?.skills || [],
    evidenceCount: first?.evidenceCount || 0,
    needsConfirmation: Boolean(first?.needsConfirmation),
    experiences,
    approvedExperienceIndexes: [...approvedIndexes],
    extractionRunId: proposal.extraction_run_id || proposal.extractionRunId,
    analysisScope: proposal.analysis_scope || proposal.analysisScope,
    rawPayload: payload,
  };
}

export function createLocalExperienceProposal({ id, version = 1, title = '경험 구조화 제안', experiences, analysisScope }) {
  const rawExperiences = list(experiences).map((item) => ({
    ...item,
    domain: typeof item.domain === 'string' ? { name: item.domain } : item.domain || { name: '' },
    project: typeof item.project === 'string' ? { name: item.project } : item.project || { name: '' },
    source_ref_ids: list(item.source_ref_ids || item.sourceRefIds),
    source_refs: list(item.source_refs || item.sourceRefs),
    missing_information: list(item.missing_information || item.missingInformation),
    skill_groups: list(item.skill_groups || item.skillGroups),
  }));
  return toProposalView({
    id,
    version,
    type: 'create_experiences',
    status: 'pending',
    title,
    analysis_scope: analysisScope,
    payload: {
      domain: rawExperiences[0]?.domain || { name: '' },
      project: rawExperiences[0]?.project || { name: '' },
      experiences: rawExperiences,
    },
  });
}

export function applyProposalPanelChanges(proposal, panel) {
  const payload = structuredClone(proposal.rawPayload || {});
  if (panel.kind === 'job') {
    payload.job_draft = {
      ...(payload.job_draft || {}),
      posting_title: panel.postingTitle,
      company_name: panel.companyName,
      role_name: panel.roleName,
      source_url: panel.sourceUrl,
      posting_content: panel.postingContent,
    };
    return payload;
  }

  payload.domain = { ...(payload.domain || {}), name: panel.domain };
  payload.project = { ...(payload.project || {}), name: panel.project };
  const panels = list(panel.experiences).length ? panel.experiences : [panel];
  payload.experiences = panels.map((item, index) => ({
    ...(payload.experiences?.[index] || {}),
    draft_id: item.draft_id,
    title: item.title,
    domain: { ...(payload.experiences?.[index]?.domain || {}), name: item.domain },
    project: { ...(payload.experiences?.[index]?.project || {}), name: item.project },
    role: item.role,
    summary: item.summary,
    situation: item.situation,
    actions: list(item.actions),
    results: list(item.results),
    facts: list(item.facts),
    skills: list(item.skills),
    missing_information: list(item.missingInformation || item.missing_information),
    source_ref_ids: list(item.source_ref_ids),
    source_refs: list(item.source_refs),
    field_citations: item.fieldCitations || item.field_citations || {},
    confidence: item.confidence,
    skill_groups: list(item.skillGroups || item.skill_groups),
    saved_experience_id: item.savedExperienceId || item.saved_experience_id || undefined,
    saved_at: item.savedAt || item.saved_at || undefined,
  }));
  return payload;
}
