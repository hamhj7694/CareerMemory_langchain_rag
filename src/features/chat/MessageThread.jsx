import { ProposalCard } from './ProposalCard.jsx';
import { MarkdownMessage } from './MarkdownMessage.jsx';
import { CHAT_QUICK_ACTIONS } from './chatQuickActions.js';

export function MessageThread({ messages, proposals, busy, busyLabel = '답변을 준비하고 있어요.', onStarter, onEvidence, onOpenJobAnalysis, onOpenJobAnalyses, onApproveProposal, onRejectProposal, onDiscardRemainingProposalExperiences, onChangeProposal, onRemoveProposalExperience }) {
  if (messages.length === 0) return <div className="v2-chat-empty">
    <span className="v2-chat-empty__mark" aria-hidden="true">CM</span>
    <h1>당신의 경험을 이야기해 주세요</h1>
    <p>대화하고 자료를 더할수록, 흩어진 기억이 근거 있는 경력 자산으로 정리됩니다.</p>
    <div className="v2-starters">
      {CHAT_QUICK_ACTIONS.map((starter) => <button type="button" key={starter.id} onClick={() => onStarter(starter)}>
        <strong>{starter.title}</strong><span>{starter.description}</span>
      </button>)}
    </div>
  </div>;

  // 스트리밍을 시작하면 내용이 비어 있는 AI 메시지가 먼저 만들어집니다.
  // 이 메시지와 별도의 로딩 메시지를 함께 표시하면 이름이 두 번 나오므로,
  // 빈 스트리밍 메시지 자체에 진행 문구를 보여 줍니다.
  const streamingMessageId = busy
    ? messages.findLast((message) => (
        message.role === 'assistant'
        && message.status === 'streaming'
      ))?.id
    : null;

  return <div className="v2-message-list" aria-live="polite">
    {messages.map((message) => <article
      key={message.id}
      data-message-id={message.id}
      data-selectable-text={message.role === 'user' ? 'true' : undefined}
      draggable={false}
      className={`v2-message v2-message--${message.role}`}
    >
      <div className="v2-message__meta">{message.role === 'assistant' ? 'Career Memory' : '나'}</div>
      {message.id === streamingMessageId && !message.content
        ? <p className="v2-message--thinking" role="status"><span /> {busyLabel}</p>
        : message.role === 'assistant'
        ? <MarkdownMessage content={message.content} />
        : <p className="v2-message__content" draggable={false}>{message.content}</p>}
      {message.status === 'failed' && <small className="v2-message__failed">전송되지 않았습니다. 입력창에서 다시 전송해 주세요.</small>}
      {message.attachments?.length > 0 && <div className="v2-message__files">{message.attachments.map((file, index) => {
        const attachment = typeof file === 'string' ? { filename: file } : file;
        const key = attachment.id || attachment.filename || `attachment-${index}`;
        return attachment.downloadUrl
          ? <a key={key} href={attachment.downloadUrl}>▧ {attachment.filename}</a>
          : <span key={key}>▧ {attachment.filename || '첨부 파일'}</span>;
      })}</div>}
      {message.evidence?.length > 0 && !message.proposalIds?.length && <div className="v2-message__links">
        {message.evidence.map((item) => item.quote
          ? <details key={item.id}><summary onClick={() => onEvidence(item)}>근거 {item.label}</summary><blockquote>{item.quote}</blockquote></details>
          : <button type="button" key={item.id} onClick={() => onEvidence(item)}>근거 {item.label}</button>)}
      </div>}
      {message.jobAnalysisIds?.length > 0
        ? <div className="v2-message__links"><button type="button" onClick={() => onOpenJobAnalyses(message.jobAnalysisIds)}>분석 공고 보러가기</button></div>
        : message.jobAnalysisId && <div className="v2-message__links"><button type="button" onClick={() => onOpenJobAnalysis(message.jobAnalysisId)}>공고 분석 결과 보기</button></div>}
      {message.proposalIds?.map((proposalId) => {
        const proposal = proposals[proposalId];
        if (!proposal) return null;
        {/* Legacy 카드는 접힘 상태를 유지하고, V2 카드는 승인·편집 응답을
            로컬 편집 상태에 안전하게 반영하기 위해 버전별로 다시 마운트합니다. */}
        const cardKey = proposal.contractVersion === 'experience-units-v2'
          ? `${proposalId}-${proposal.version}`
          : proposalId;
        return <ProposalCard key={cardKey} proposal={proposal} onApprove={onApproveProposal} onReject={onRejectProposal} onDiscardRemainingExperiences={onDiscardRemainingProposalExperiences} onChange={onChangeProposal} onRemoveExperience={onRemoveProposalExperience} showBatchActions />;
      })}
    </article>)}
    {busy && !streamingMessageId && <article className="v2-message v2-message--assistant v2-message--thinking" role="status"><div className="v2-message__meta">Career Memory</div><p><span /> {busyLabel}</p></article>}
  </div>;
}
