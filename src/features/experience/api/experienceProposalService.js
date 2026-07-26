import { v2ChatApi } from '../../../api/v2ChatApi.js';
import { createLocalExperienceProposal } from '../../chat/proposalMapper.js';
import { createEmptyExperience } from '../model/experienceMapper.js';

const isFileSource = (source = {}) => source.source_type === 'file' || source.kind === 'file' || source.sourceType === 'file';

function proposalSources(uploadedAttachments, originalText) {
  return [
    ...(originalText.trim() ? [{
      id: `LOCAL-TEXT-${Date.now()}`,
      source_type: 'text',
      title: '직접 입력 원문',
      text: originalText.trim(),
      captured_at: new Date().toISOString(),
      linked_facts: [],
    }] : []),
    ...uploadedAttachments.map((file) => ({
      id: file.id,
      source_type: 'file',
      title: file.filename,
      filename: file.filename,
      mime_type: file.mime_type,
      size_bytes: file.size_bytes,
      content_hash: file.content_hash,
      original_attachment_id: file.original_attachment_id,
      reused: Boolean(file.reused),
      raw_bytes: file.raw_bytes,
      uploaded_at: file.created_at,
      captured_at: file.created_at,
      text: file.raw_text || '',
      linked_facts: [],
    })),
  ];
}

function proposalFromDraft(draft, uploadedAttachments, originalText) {
  const sourceRefs = proposalSources(uploadedAttachments, originalText);
  const sourceIds = sourceRefs.map((source) => source.id);
  const experience = {
    draft_id: `DRAFT-${Date.now()}-1`,
    title: draft.title,
    domain: draft.domainName,
    project: draft.projectName,
    role: draft.role,
    summary: draft.summary,
    situation: draft.situation,
    actions: draft.actions || [],
    results: draft.results || [],
    facts: draft.facts || [],
    skills: draft.skills || [],
    evidenceCount: sourceIds.length,
    source_ref_ids: sourceIds,
    source_refs: sourceRefs,
    missing_information: [],
  };

  // 실제 AI 연결 전 다중 초안 UI와 부분 저장 흐름을 검증하기 위한 두 번째 목 초안이다.
  const mockExperience = {
    ...experience,
    draft_id: `DRAFT-${Date.now()}-2`,
    domain: '사이드 프로젝트',
    project: '새 프로젝트·활동 2',
    title: `${draft.title || '새 경험'} 2`,
    summary: draft.summary || '두 번째 경험 초안입니다.',
  };
  return createLocalExperienceProposal({
    id: `LOCAL-PROPOSAL-${Date.now()}`,
    title: '경험 AI 분석 결과',
    experiences: [experience, mockExperience],
  });
}

/**
 * 현재는 결정론적 목 분석기다. AI 엔진 연결 시 이 함수의 반환 계약만 유지하고
 * 내부를 API 호출로 교체하면 화면과 저장 흐름은 변경하지 않아도 된다.
 */
export function buildLocalExperienceAnalysis({ content, fileNames, uploadedAttachments, domain, project, context }) {
  const originalText = content;
  const extractedFileText = uploadedAttachments.map((file) => file.raw_text?.trim()).filter(Boolean).join('\n\n');
  const combinedContent = [content, extractedFileText].filter(Boolean).join('\n\n');
  const sourceText = [combinedContent, fileNames.length ? `첨부 파일: ${fileNames.join(', ')}` : ''].filter(Boolean).join('\n\n');
  const firstLine = sourceText.split('\n').map((line) => line.trim()).find(Boolean) || '새 경험';
  const draft = createEmptyExperience({
    domainId: context.domainId || '',
    domainName: domain?.name || '',
    projectId: context.projectId || '',
    projectName: project?.name || '',
    organization: project?.organization || '',
    title: firstLine.replace(/^[-*#\d.)\s]+/, '').slice(0, 60) || '새 경험',
    summary: sourceText,
    situation: sourceText,
    actions: sourceText ? [sourceText] : [],
    results: [],
    facts: [],
    status: 'draft',
  });
  return { draft, proposal: proposalFromDraft(draft, uploadedAttachments, originalText) };
}

/**
 * 실제 경험정리 AI 결과를 기존 경험 구조화 제안 화면이 사용하는 형태로 변환한다.
 * 원본 근거는 초안마다 복사하지 않고 source_ref_id를 기준으로 연결한다.
 */
export function buildExperienceAnalysisFromResult({ result, domain, project }) {
  const sourceById = new Map((result.sources || []).map((source) => [
    source.id,
    {
      ...source,
      source_type: source.type,
      captured_at: result.run?.completed_at,
      linked_facts: [],
    },
  ]));
  const experiences = (result.experience_drafts || []).map((draft) => ({
    ...draft,
    domain: domain
      ? { id: domain.id, name: domain.name }
      : draft.domain,
    project: project
      ? {
          id: project.id,
          name: project.name,
          organization: project.organization || draft.project?.organization || '',
        }
      : draft.project,
    source_refs: (draft.source_ref_ids || [])
      .map((sourceId) => sourceById.get(sourceId))
      .filter(Boolean),
  }));

  return {
    draft: experiences[0] || null,
    proposal: createLocalExperienceProposal({
      id: result.run?.id || `AI-PROPOSAL-${Date.now()}`,
      title: '경험 AI 분석 결과',
      experiences,
    }),
  };
}

export async function saveProposalExperience(item) {
  if (item.savedExperienceId) return v2ChatApi.getExperience(item.savedExperienceId);
  const domain = typeof item.domain === 'string' ? { name: item.domain } : item.domain;
  const project = typeof item.project === 'string' ? { name: item.project } : item.project;
  return v2ChatApi.createExperience({
    ...item,
    domain: domain || { name: '새 경험 분류' },
    project: project || { name: '새 프로젝트' },
    source_ids: item.source_ref_ids || item.source_ids || [],
    source_refs: item.source_refs || [],
  });
}

export function markProposalExperienceSaved(proposal, index, saved) {
  const experiences = (proposal.experiences || []).map((item, itemIndex) => itemIndex === index
    ? { ...item, approved: true, savedExperienceId: saved.id, savedAt: saved.created_at }
    : item);
  return { ...proposal, version: (proposal.version || 0) + 1, experiences, rawPayload: { ...(proposal.rawPayload || {}), experiences } };
}

export async function discardPendingProposalAttachments(proposal) {
  const experiences = proposal?.experiences || [];
  const retainedSourceIds = new Set(experiences.filter((item) => item.approved).flatMap((item) => item.source_ref_ids || item.source_ids || []));
  const pendingFileIds = new Set(experiences.filter((item) => !item.approved).flatMap((item) => (item.source_refs || [])
    .filter(isFileSource)
    .filter((source) => !source.reused)
    .map((source) => source.id)).filter(Boolean));
  await Promise.all([...pendingFileIds].filter((id) => !retainedSourceIds.has(id)).map((id) => v2ChatApi.deleteAttachment(id).catch(() => null)));
}
