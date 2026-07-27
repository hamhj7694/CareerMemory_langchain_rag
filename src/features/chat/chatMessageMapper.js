import { toProposalView } from './proposalMapper.js';

export function toEmbeddedProposalView(proposal, { messageId, conversationId } = {}) {
  const view = toProposalView(proposal);
  if (!view) return null;
  return {
    ...view,
    chatMessageId: messageId,
    conversationId,
  };
}

export function toUiMessage(message) {
  const actions = message.actions || [];
  const hasEmbeddedProposalAction = actions
    .some((action) => action.type === 'experience_proposal');
  const embeddedProposals = actions
    .filter((action) => action.type === 'experience_proposal' && action.proposal)
    .map((action) => toEmbeddedProposalView(action.proposal, {
      messageId: message.id,
      conversationId: message.conversation_id || message.conversationId,
    }))
    .filter(Boolean)
    .filter((proposal) => proposal.status !== 'rejected');
  const inputFiles = actions
    .find((action) => action.type === 'input_files')?.filenames || [];
  const jobAnalysisId = actions
    .find((action) => action.type === 'open_job_analysis')?.job_id
    ?? actions.find((action) => action.type === 'open_job_analysis')?.jobId;
  const attachmentRefs = message.attachment_refs || message.attachmentRefs || [];
  const attachmentIds = message.attachment_ids || message.attachmentIds || [];
  return {
    id: message.id,
    sequence: message.sequence,
    role: message.role,
    content: message.content,
    status: message.status,
    error: message.error,
    attachments: attachmentRefs.length
      ? attachmentRefs.map((attachment) => attachment.filename || attachment.id)
      : attachmentIds.length ? attachmentIds : inputFiles,
    evidence: message.citations?.map((citation, index) => ({
      id: citation.source_ref_id ?? citation.source_id ?? `${message.id}-${index}`,
      label: citation.label || citation.title || String(index + 1),
    })) ?? [],
    // 메시지 안에 제안 본문이 있으면 그 상태가 authoritative source다.
    // 거절된 제안의 proposal_ids가 서버 감사 이력에 남아 있더라도 화면에서
    // 다시 별도 제안 API로 조회하지 않도록 활성 제안만 노출한다.
    proposalIds: hasEmbeddedProposalAction
      ? embeddedProposals.map((proposal) => proposal.id)
      : (message.proposal_ids ?? message.proposalIds ?? []),
    embeddedProposals,
    jobAnalysisId,
  };
}
