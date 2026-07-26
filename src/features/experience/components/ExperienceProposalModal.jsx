import { InlineProposalCard } from '../../chat/InlineProposalCard.jsx';

export function ExperienceProposalModal({
  open,
  proposal,
  busy,
  editing,
  pendingCount,
  onClose,
  onApprove,
  onChange,
  onRemove,
  onEditingChange,
  onDiscardRemaining,
  onSaveAll,
}) {
  if (!open || !proposal) return null;
  return (
    <div className="mv2-modal-backdrop mv2-experience-preview-backdrop">
      <section className="mv2-experience-preview-modal" role="dialog" aria-modal="true" aria-label="경험 AI 분석 결과">
        <header>
          <div><span className="mv2-kicker">EXPERIENCE AI</span><h2>경험 AI 분석 결과</h2><p>AI가 분석한 핵심 내용과 분류를 확인한 뒤 저장해 주세요.</p></div>
          <button type="button" className="mv2-icon-button" onClick={onClose} aria-label="닫기">×</button>
        </header>
        <InlineProposalCard
          key={`${proposal.id}-${proposal.version || 0}`}
          proposal={proposal}
          onApprove={onApprove}
          onReject={onClose}
          onChange={onChange}
          onRemoveExperience={onRemove}
          onEditingChange={onEditingChange}
        />
        <footer className="mv2-experience-preview-footer">
          <span>{pendingCount ? `저장하지 않은 초안 ${pendingCount}개` : '모든 초안이 저장되었습니다.'}</span>
          {pendingCount > 0 && <div>
            <button type="button" className="mv2-button mv2-button--danger" disabled={!pendingCount || busy || editing} onClick={onDiscardRemaining}>나머지 삭제</button>
            <button type="button" className="mv2-button mv2-button--primary" disabled={!pendingCount || busy || editing} onClick={onSaveAll}>{busy ? '전체 저장 중…' : '전체 저장'}</button>
          </div>}
        </footer>
      </section>
    </div>
  );
}
