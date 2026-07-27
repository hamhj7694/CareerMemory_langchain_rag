import { describe, expect, it } from 'vitest';
import { toEmbeddedProposalView, toUiMessage } from '../features/chat/chatMessageMapper.js';

function messageWithProposal(status = 'pending') {
  return {
    id: 'MSG-AI-1',
    conversation_id: 'CONV-1',
    role: 'assistant',
    status: 'completed',
    content: '경험 초안 0개를 정리했습니다.',
    proposal_ids: ['PROPOSAL-1'],
    actions: [{
      type: 'experience_proposal',
      proposal: {
        id: 'PROPOSAL-1',
        version: 1,
        type: 'create_experiences',
        status,
        payload: { experiences: [] },
      },
    }],
  };
}

describe('ChatPage 메시지 제안 복원', () => {
  it('방금 생성된 서버 제안에 메시지와 대화 식별자를 연결한다', () => {
    const message = toUiMessage(messageWithProposal());

    expect(message.proposalIds).toEqual(['PROPOSAL-1']);
    expect(message.embeddedProposals[0]).toMatchObject({
      id: 'PROPOSAL-1',
      chatMessageId: 'MSG-AI-1',
      conversationId: 'CONV-1',
    });
  });

  it('거절된 내장 제안은 proposal_ids가 남아 있어도 다시 노출하지 않는다', () => {
    const message = toUiMessage(messageWithProposal('rejected'));

    expect(message.proposalIds).toEqual([]);
    expect(message.embeddedProposals).toEqual([]);
  });
});

describe('streamed proposal server identifiers', () => {
  it('attaches the message and conversation identifiers required by save and delete', () => {
    const message = messageWithProposal();
    const proposal = toEmbeddedProposalView(message.actions[0].proposal, {
      messageId: message.id,
      conversationId: message.conversation_id,
    });

    expect(proposal).toMatchObject({
      id: 'PROPOSAL-1',
      chatMessageId: 'MSG-AI-1',
      conversationId: 'CONV-1',
    });
  });
});
