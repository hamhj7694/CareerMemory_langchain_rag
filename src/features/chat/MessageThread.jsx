import { InlineProposalCard } from './InlineProposalCard.jsx';
import { MarkdownMessage } from './MarkdownMessage.jsx';

const STARTERS = [
  {
    title: '프로젝트 경험 이야기하기',
    description: '질문을 따라가며 기억을 구체적인 경험으로 풀어내요.',
    prompt: '프로젝트 경험을 이야기하고 싶은데, 어떤 내용부터 말하면 좋을까요?',
  },
  {
    title: '파일에서 성과 찾기',
    description: '자료를 준비하기 전에 어떤 파일과 내용이 필요한지 물어봐요.',
    prompt: '파일에서 제 경험과 성과를 찾고 싶은데, 어떤 자료를 준비하면 좋을까요?',
  },
  {
    title: '내 경험 돌아보기',
    description: '저장된 경험을 바탕으로 강점과 보완점을 함께 살펴봐요.',
    prompt: '저장된 경험을 바탕으로 제 강점과 보완할 점을 함께 살펴봐 주세요.',
  },
  {
    title: '채용공고와 비교 준비하기',
    description: '공고와 경험을 비교하기 위해 필요한 내용을 먼저 확인해요.',
    prompt: '채용공고와 제 경험을 비교하려면 어떤 내용을 준비해야 하나요?',
  },
];

export function MessageThread({ messages, proposals, busy, busyLabel = '답변을 준비하고 있어요.', onStarter, onEvidence, onOpenJobAnalysis, onApproveProposal, onRejectProposal, onDiscardRemainingProposalExperiences, onChangeProposal, onRemoveProposalExperience }) {
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
    {messages.map((message) => <article key={message.id} className={`v2-message v2-message--${message.role}`}>
      <div className="v2-message__meta">{message.role === 'assistant' ? 'Career Memory' : '나'}</div>
      {message.id === streamingMessageId && !message.content
        ? <p className="v2-message--thinking" role="status"><span /> {busyLabel}</p>
        : message.role === 'assistant'
        ? <MarkdownMessage content={message.content} />
        : <p className="v2-message__content">{message.content}</p>}
      {message.status === 'failed' && <small className="v2-message__failed">전송되지 않았습니다. 입력창에서 다시 전송해 주세요.</small>}
      {message.attachments?.length > 0 && <div className="v2-message__files">{message.attachments.map((file) => <span key={file}>▧ {file}</span>)}</div>}
      {message.evidence?.length > 0 && !message.proposalIds?.length && <div className="v2-message__links">
        {message.evidence.map((item) => <button type="button" key={item.id} onClick={() => onEvidence(item)}>근거 {item.label}</button>)}
      </div>}
      {message.jobAnalysisId && <div className="v2-message__links"><button type="button" onClick={() => onOpenJobAnalysis(message.jobAnalysisId)}>공고 분석 결과 보기</button></div>}
      {message.proposalIds?.map((proposalId) => {
        const proposal = proposals[proposalId];
        if (!proposal) return null;
        {/* 제안 버전이 갱신되어도 카드 컴포넌트를 재마운트하지 않아
            각 경험 분류의 접힘/펼침 상태를 유지합니다. */}
        return <InlineProposalCard key={proposalId} proposal={proposal} onApprove={onApproveProposal} onReject={onRejectProposal} onDiscardRemainingExperiences={onDiscardRemainingProposalExperiences} onChange={onChangeProposal} onRemoveExperience={onRemoveProposalExperience} showBatchActions />;
      })}
    </article>)}
    {busy && !streamingMessageId && <article className="v2-message v2-message--assistant v2-message--thinking" role="status"><div className="v2-message__meta">Career Memory</div><p><span /> {busyLabel}</p></article>}
  </div>;
}
