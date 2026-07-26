import { InlineProposalCard } from './InlineProposalCard.jsx';
import { MarkdownMessage } from './MarkdownMessage.jsx';

const STARTERS = [
  { mode: 'experience', title: '프로젝트 경험 정리', description: '정리되지 않은 이야기를 경력 자산으로 만들어요.' },
  { mode: 'experience', title: '파일에서 성과 찾기', description: 'PDF나 TXT를 올려 경험과 수치를 찾아요.' },
  { mode: 'auto', title: '내 경험에 질문', description: '저장된 경험과 원본 근거에서 답을 찾아요.' },
  { mode: 'job', title: '채용공고와 비교', description: '공고 요구사항과 내 경험을 근거별로 비교해요.' },
];

export function MessageThread({ messages, proposals, busy, busyLabel = '답변을 준비하고 있어요.', onStarter, onEvidence, onApproveProposal, onRejectProposal, onDiscardRemainingProposalExperiences, onChangeProposal, onRemoveProposalExperience }) {
  if (messages.length === 0) return <div className="v2-chat-empty">
    <span className="v2-chat-empty__mark" aria-hidden="true">CM</span>
    <h1>당신의 경험을 이야기해 주세요</h1>
    <p>대화하고 자료를 더할수록, 흩어진 기억이 근거 있는 경력 자산으로 정리됩니다.</p>
    <div className="v2-starters">
      {STARTERS.map((starter) => <button type="button" key={starter.title} onClick={() => onStarter(starter)}>
        <strong>{starter.title}</strong><span>{starter.description}</span>
      </button>)}
    </div>
  </div>;

  return <div className="v2-message-list" aria-live="polite">
    {messages.map((message) => <article key={message.id} className={`v2-message v2-message--${message.role}`}>
      <div className="v2-message__meta">{message.role === 'assistant' ? 'Career Memory' : '나'}</div>
      {message.role === 'assistant'
        ? <MarkdownMessage content={message.content} />
        : <p>{message.content}</p>}
      {message.status === 'failed' && <small className="v2-message__failed">전송되지 않았습니다. 입력창에서 다시 전송해 주세요.</small>}
      {message.attachments?.length > 0 && <div className="v2-message__files">{message.attachments.map((file) => <span key={file}>▧ {file}</span>)}</div>}
      {message.evidence?.length > 0 && !message.proposalIds?.length && <div className="v2-message__links">
        {message.evidence.map((item) => <button type="button" key={item.id} onClick={() => onEvidence(item)}>근거 {item.label}</button>)}
      </div>}
      {message.proposalIds?.map((proposalId) => {
        const proposal = proposals[proposalId];
        if (!proposal) return null;
        {/* 제안 버전이 갱신되어도 카드 컴포넌트를 재마운트하지 않아
            각 경험 분류의 접힘/펼침 상태를 유지합니다. */}
        return <InlineProposalCard key={proposalId} proposal={proposal} onApprove={onApproveProposal} onReject={onRejectProposal} onDiscardRemainingExperiences={onDiscardRemainingProposalExperiences} onChange={onChangeProposal} onRemoveExperience={onRemoveProposalExperience} showBatchActions />;
      })}
    </article>)}
    {busy && <article className="v2-message v2-message--assistant v2-message--thinking" role="status"><div className="v2-message__meta">Career Memory</div><p><span /> {busyLabel}</p></article>}
  </div>;
}
