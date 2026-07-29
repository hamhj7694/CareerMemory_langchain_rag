import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { request } = vi.hoisted(() => ({
  request: vi.fn(async (input) => input),
}));

vi.mock('./adapters/httpAdapter.js', () => ({
  createHttpAdapter: () => ({ request }),
}));

import { v2ChatHttpApi } from './v2ChatHttpApi.js';
import { clearCsrfToken, setCsrfToken } from '../auth/authSession.js';

describe('실제 대화 HTTP API', () => {
  beforeEach(() => {
    request.mockReset();
    request.mockImplementation(async (input) => input);
  });

  afterEach(() => {
    clearCsrfToken();
    vi.unstubAllGlobals();
  });

  it('대화 생성 요청에 client_request_id를 보충한다', async () => {
    await v2ChatHttpApi.createConversation({ title: '실제 대화' });

    expect(request).toHaveBeenCalledWith(expect.objectContaining({
      path: '/api/v2/conversations',
      method: 'POST',
      body: {
        title: '실제 대화',
        client_request_id: expect.any(String),
      },
    }));
    expect(request.mock.calls[0][0].body.client_request_id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
  });

  it('메시지를 FastAPI의 비스트리밍 주소로 전송한다', async () => {
    await v2ChatHttpApi.sendMessage('CONV-001', {
      content: '안녕하세요',
      intent: 'auto',
      attachment_ids: [],
      client_request_id: 'request-fixed',
    });

    expect(request).toHaveBeenCalledWith({
      path: '/api/v2/conversations/CONV-001/messages',
      method: 'POST',
      body: {
        content: '안녕하세요',
        intent: 'auto',
        attachment_ids: [],
        context: {
          experience_ids: [],
          job_id: null,
          selected_proposal_id: null,
        },
        response_mode: 'complete',
        client_request_id: 'request-fixed',
      },
    });
  });

  it('next_cursor를 따라 세션의 전체 메시지를 불러온다', async () => {
    request
      .mockResolvedValueOnce({
        items: [{ id: 'MSG-1' }, { id: 'MSG-2' }],
        total_count: 3,
        next_cursor: '2',
      })
      .mockResolvedValueOnce({
        items: [{ id: 'MSG-3' }],
        total_count: 3,
        next_cursor: null,
      });

    const result = await v2ChatHttpApi.listMessages('CONV-001', {
      limit: 2,
    });

    expect(request).toHaveBeenNthCalledWith(1, {
      path: '/api/v2/conversations/CONV-001/messages',
      query: { cursor: undefined, limit: 2 },
    });
    expect(request).toHaveBeenNthCalledWith(2, {
      path: '/api/v2/conversations/CONV-001/messages',
      query: { cursor: '2', limit: 2 },
    });
    expect(result).toEqual({
      items: [{ id: 'MSG-1' }, { id: 'MSG-2' }, { id: 'MSG-3' }],
      total_count: 3,
      next_cursor: null,
    });
  });

  it('SSE 응답 조각을 순서대로 JSON 이벤트로 변환한다', async () => {
    setCsrfToken('csrf-test-token');
    const encoder = new TextEncoder();
    const fetchMock = vi.fn(async () => new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(
            'event: message.accepted\nid: 1\ndata: {"type":"message.accepted","sequence":1,"assistant_message_id":"MSG-AI"}\n\n'
          ));
          controller.enqueue(encoder.encode(
            'event: assistant.delta\nid: 2\ndata: {"type":"assistant.delta","sequence":2,"message_id":"MSG-AI","delta":"안녕"}\n\n'
          ));
          controller.enqueue(encoder.encode(
            'event: message.completed\nid: 3\ndata: {"type":"message.completed","sequence":3,"message":{"id":"MSG-AI","content":"안녕"}}\n\n'
          ));
          controller.close();
        },
      }),
      {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      },
    ));
    vi.stubGlobal('fetch', fetchMock);

    const events = [];
    for await (const event of v2ChatHttpApi.streamMessage('CONV-001', {
      content: '인사해줘',
      intent: 'auto',
      client_request_id: 'request-fixed',
    })) {
      events.push(event);
    }

    expect(events.map((event) => event.type)).toEqual([
      'message.accepted',
      'assistant.delta',
      'message.completed',
    ]);
    expect(events[1].delta).toBe('안녕');
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:5173/api/v2/conversations/CONV-001/messages/stream',
      expect.objectContaining({
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
          'X-CSRF-Token': 'csrf-test-token',
        },
        credentials: 'include',
      }),
    );
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual(
      expect.objectContaining({
        content: '인사해줘',
        response_mode: 'stream',
        client_request_id: 'request-fixed',
      }),
    );
  });

  it('URL에 들어가는 대화 ID를 안전하게 인코딩한다', async () => {
    await v2ChatHttpApi.getConversation('CONV/한글');

    expect(request).toHaveBeenCalledWith({
      path: '/api/v2/conversations/CONV%2F%ED%95%9C%EA%B8%80',
    });
  });

  it('대화 제목 변경에 현재 버전과 요청 UUID를 보낸다', async () => {
    await v2ChatHttpApi.updateConversation('CONV-001', {
      title: '변경한 제목',
      base_version: 3,
    });

    expect(request).toHaveBeenCalledWith(expect.objectContaining({
      path: '/api/v2/conversations/CONV-001',
      method: 'PATCH',
      body: expect.objectContaining({
        title: '변경한 제목',
        base_version: 3,
        client_request_id: expect.any(String),
      }),
    }));
  });

  it('대화 삭제에 현재 버전을 보낸다', async () => {
    await v2ChatHttpApi.deleteConversation('CONV-001', { version: 4 });

    expect(request).toHaveBeenCalledWith(expect.objectContaining({
      path: '/api/v2/conversations/CONV-001',
      method: 'DELETE',
      body: {
        version: 4,
        client_request_id: expect.any(String),
      },
    }));
  });
});
