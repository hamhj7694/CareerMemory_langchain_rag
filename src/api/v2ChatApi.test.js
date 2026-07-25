import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { experienceApi } from './experienceApi.js';
import { v2ChatApi } from './v2ChatApi.js';

describe('career chat extraction flow', () => {
  beforeEach(() => v2ChatApi.reset());
  afterEach(() => v2ChatApi.reset());

  it('structures only unprocessed conversation messages and records an extraction run', async () => {
    const conversation = await v2ChatApi.createConversation({ title: '증분 정리 테스트' });
    await v2ChatApi.sendMessage(conversation.id, {
      content: '지원 단계의 이탈 데이터를 분석하고 입력 흐름을 개선했습니다.',
      intent: 'auto',
      attachment_ids: [],
    });

    const before = await v2ChatApi.getConversationExtractionStatus(conversation.id);
    expect(before.unprocessed_message_count).toBe(1);

    const result = await v2ChatApi.extractConversationExperiences(conversation.id, {
      client_request_id: 'extract-once',
    });

    expect(result.run).toMatchObject({
      status: 'succeeded',
      from_sequence: 1,
      to_sequence: 1,
      message_ids: expect.arrayContaining([expect.any(String)]),
    });
    expect(result.proposal.payload.experiences).toHaveLength(1);
    expect(result.proposal.payload.experiences[0]).toMatchObject({
      draft_id: expect.any(String),
      source_ref_ids: [expect.any(String)],
      field_citations: expect.any(Object),
    });

    const after = await v2ChatApi.getConversationExtractionStatus(conversation.id);
    expect(after.unprocessed_message_count).toBe(0);
    await expect(v2ChatApi.extractConversationExperiences(conversation.id)).rejects.toMatchObject({ code: 'NO_NEW_CONTENT' });
  });

  it('creates multiple stable drafts and supports partial approval', async () => {
    const conversation = await v2ChatApi.createConversation({ title: '복수 경험 테스트' });
    await v2ChatApi.sendMessage(conversation.id, {
      content: '경험 1: 퍼널 분석 프로젝트\n요약: 전환 흐름을 개선했습니다.',
      intent: 'auto',
      attachment_ids: [],
    });
    await v2ChatApi.sendMessage(conversation.id, {
      content: '경험 2: 운영 대시보드 프로젝트\n요약: 운영 지표를 통합했습니다.',
      intent: 'auto',
      attachment_ids: [],
    });

    const extracted = await v2ChatApi.extractConversationExperiences(conversation.id);
    const drafts = extracted.proposal.payload.experiences;
    expect(drafts).toHaveLength(2);
    expect(new Set(drafts.map((draft) => draft.draft_id)).size).toBe(2);

    const first = await v2ChatApi.approveProposal(extracted.proposal.id, {
      base_version: extracted.proposal.version,
      selection: { experience_indexes: [0] },
    });
    expect(first.created.experience_ids).toHaveLength(1);
    expect(first.proposal.status).toBe('edited');
    expect(first.proposal.approved_experience_indexes).toEqual([0]);

    const second = await v2ChatApi.approveProposal(extracted.proposal.id, {
      base_version: first.proposal.version,
      selection: { experience_indexes: [1] },
    });
    expect(second.created.experience_ids).toHaveLength(1);
    expect(second.proposal.status).toBe('approved');
    expect(second.proposal.approved_experience_indexes).toEqual([0, 1]);
  });

  it('keeps approved drafts and discards only the remaining unapproved drafts', async () => {
    const initialExperienceCount = (await v2ChatApi.listExperiences()).items.length;
    const conversation = await v2ChatApi.createConversation({ title: '저장 초안 유지 테스트' });
    await v2ChatApi.sendMessage(conversation.id, {
      content: '경험 1: 퍼널 분석 프로젝트\n요약: 전환 흐름을 개선했습니다.',
      intent: 'auto',
      attachment_ids: [],
    });
    await v2ChatApi.sendMessage(conversation.id, {
      content: '경험 2: 운영 대시보드 프로젝트\n요약: 운영 지표를 통합했습니다.',
      intent: 'auto',
      attachment_ids: [],
    });
    const extracted = await v2ChatApi.extractConversationExperiences(conversation.id);
    const first = await v2ChatApi.approveProposal(extracted.proposal.id, {
      base_version: extracted.proposal.version,
      selection: { experience_indexes: [0] },
    });

    const discarded = await v2ChatApi.discardUnapprovedProposalExperiences(extracted.proposal.id, {
      base_version: first.proposal.version,
    });

    expect(discarded.status).toBe('approved');
    expect(discarded.payload.experiences).toHaveLength(1);
    expect(discarded.approved_experience_indexes).toEqual([0]);
    expect((await v2ChatApi.listExperiences()).items).toHaveLength(initialExperienceCount + 1);
  });

  it('rejects the proposal when discarding all drafts before anything is saved', async () => {
    const initialExperienceCount = (await v2ChatApi.listExperiences()).items.length;
    const conversation = await v2ChatApi.createConversation({ title: '전체 미저장 삭제 테스트' });
    await v2ChatApi.sendMessage(conversation.id, {
      content: '고객 문의 분류 체계를 개선했습니다.',
      intent: 'auto',
      attachment_ids: [],
    });
    const extracted = await v2ChatApi.extractConversationExperiences(conversation.id);

    const discarded = await v2ChatApi.discardUnapprovedProposalExperiences(extracted.proposal.id, {
      base_version: extracted.proposal.version,
    });

    expect(discarded.status).toBe('rejected');
    expect((await v2ChatApi.listExperiences()).items).toHaveLength(initialExperienceCount);
    expect((await v2ChatApi.getConversationExtractionStatus(conversation.id)).unprocessed_message_count).toBe(1);
  });

  it('keeps message and file sources separate in a conversation proposal', async () => {
    const conversation = await v2ChatApi.createConversation({ title: '근거 연결 테스트' });
    const file = {
      name: '성과.txt',
      type: 'text/plain',
      size: 24,
      text: async () => '프로젝트: 운영 개선\n결과: 보고 시간을 30% 단축했습니다.',
      arrayBuffer: async () => new TextEncoder().encode('운영 개선').buffer,
    };
    const [attachment] = await v2ChatApi.uploadAttachments([file]);
    await v2ChatApi.sendMessage(conversation.id, {
      content: '운영 지표를 정리했던 경험도 함께 확인해 주세요.',
      intent: 'auto',
      attachment_ids: [attachment.id],
    });

    const result = await v2ChatApi.extractConversationExperiences(conversation.id);
    const refs = result.proposal.source_refs;
    expect(refs.some((source) => source.source_type === 'message_text')).toBe(true);
    expect(refs.some((source) => source.source_type === 'file' && source.filename === '성과.txt')).toBe(true);
    expect(result.proposal.payload.experiences.some((draft) => {
      const types = draft.source_refs.map((source) => source.source_type);
      return types.includes('message_text') && types.includes('file');
    })).toBe(true);
    expect(result.run.attachment_ids).toEqual([attachment.id]);
  });

  it('keeps the same evidence records after a proposal becomes an experience', async () => {
    const conversation = await v2ChatApi.createConversation({ title: '근거 승인 연결 테스트' });
    const file = {
      name: '승인-근거.txt',
      type: 'text/plain',
      size: 24,
      text: async () => '전환율을 18% 높였습니다.',
      arrayBuffer: async () => new TextEncoder().encode('전환율 18% 향상').buffer,
    };
    const [attachment] = await v2ChatApi.uploadAttachments([file]);
    await v2ChatApi.sendMessage(conversation.id, {
      content: '지원 흐름을 분석하고 개선했습니다.',
      intent: 'auto',
      attachment_ids: [attachment.id],
    });
    const extracted = await v2ChatApi.extractConversationExperiences(conversation.id);
    const approved = await v2ChatApi.approveProposal(extracted.proposal.id, {
      base_version: extracted.proposal.version,
      selection: { experience_indexes: [0] },
    });
    const stored = await experienceApi.getSources(approved.created.experience_ids[0]);

    expect(stored.sources).toHaveLength(2);
    expect(stored.sources.map((source) => source.sourceType)).toEqual(expect.arrayContaining(['message_text', 'file']));
    expect(stored.sources.every((source) => source.filename !== '원본 정보 없음')).toBe(true);
  });

  it('makes rejected proposal messages eligible for a later extraction', async () => {
    const conversation = await v2ChatApi.createConversation({ title: '거절 후 재정리' });
    await v2ChatApi.sendMessage(conversation.id, {
      content: '고객 문의 분류 체계를 개선했습니다.',
      intent: 'auto',
      attachment_ids: [],
    });
    const extracted = await v2ChatApi.extractConversationExperiences(conversation.id);

    await v2ChatApi.rejectProposal(extracted.proposal.id, { base_version: extracted.proposal.version });

    const status = await v2ChatApi.getConversationExtractionStatus(conversation.id);
    expect(status.unprocessed_message_count).toBe(1);
  });
});
