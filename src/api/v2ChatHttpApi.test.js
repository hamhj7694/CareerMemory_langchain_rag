import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { request } = vi.hoisted(() => ({
  request: vi.fn(async (input) => input),
}));

vi.mock('./adapters/httpAdapter.js', () => ({
  createHttpAdapter: () => ({ request }),
}));

import { v2ChatHttpApi } from './v2ChatHttpApi.js';
import { apiConfig } from './config.js';
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

  it('대화 검색어를 목록 API에 전달한다', async () => {
    await v2ChatHttpApi.listConversations({ query: '전환율 개선', limit: 100 });

    expect(request).toHaveBeenCalledWith({
      path: '/api/v2/conversations',
      query: {
        status: 'active',
        cursor: undefined,
        limit: 100,
        query: '전환율 개선',
      },
    });
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
        mode_hint: 'general',
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

  it('선택한 질문 모드를 메시지 요청과 분리해 전달한다', async () => {
    await v2ChatHttpApi.sendMessage('CONV-001', {
      content: '이 문장을 검토해 주세요.',
      mode_hint: 'document_feedback',
      client_request_id: 'request-mode',
    });

    expect(request.mock.calls[0][0].body).toMatchObject({
      content: '이 문장을 검토해 주세요.',
      intent: 'auto',
      mode_hint: 'document_feedback',
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
      `${apiConfig.baseUrl}/api/v2/conversations/CONV-001/messages/stream`,
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
        mode_hint: 'general',
        response_mode: 'stream',
        client_request_id: 'request-fixed',
      }),
    );
  });

  it('새 사용자 메시지로 취소된 스트림을 정상 종료 이벤트로 처리한다', async () => {
    const encoder = new TextEncoder();
    const fetchMock = vi.fn(async () => new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(
            'event: message.cancelled\ndata: {"type":"message.cancelled","sequence":2,"message_id":"MSG-OLD","error":{"code":"superseded_by_user"}}\n\n'
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
      content: '이어서 말할게',
      reconnect_attempts: 1,
    })) {
      events.push(event);
    }

    expect(events).toEqual([
      expect.objectContaining({
        type: 'message.cancelled',
        message_id: 'MSG-OLD',
      }),
    ]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('SSE가 완료 전에 끊기면 같은 요청 ID로 재연결해 저장된 스냅샷을 받는다', async () => {
    const encoder = new TextEncoder();
    const responseFromFrames = (frames) => new Response(
      new ReadableStream({
        start(controller) {
          frames.forEach((frame) => controller.enqueue(encoder.encode(frame)));
          controller.close();
        },
      }),
      {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      },
    );
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(responseFromFrames([
        'event: message.accepted\ndata: {"type":"message.accepted","sequence":1,"assistant_message_id":"MSG-AI"}\n\n',
        'event: assistant.delta\ndata: {"type":"assistant.delta","sequence":2,"message_id":"MSG-AI","delta":"일부"}\n\n',
      ]))
      .mockResolvedValueOnce(responseFromFrames([
        'event: message.accepted\ndata: {"type":"message.accepted","sequence":1,"assistant_message_id":"MSG-AI"}\n\n',
        'event: assistant.snapshot\ndata: {"type":"assistant.snapshot","sequence":2,"message_id":"MSG-AI","content":"전체 답변"}\n\n',
        'event: message.completed\ndata: {"type":"message.completed","sequence":3,"message":{"id":"MSG-AI","content":"전체 답변"}}\n\n',
      ]));
    vi.stubGlobal('fetch', fetchMock);

    const events = [];
    for await (const event of v2ChatHttpApi.streamMessage('CONV-001', {
      content: '재연결해줘',
      intent: 'auto',
      client_request_id: 'request-reconnect',
      reconnect_attempts: 1,
    })) {
      events.push(event);
    }

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(events.map((event) => event.type)).toEqual([
      'message.accepted',
      'assistant.delta',
      'message.accepted',
      'assistant.snapshot',
      'message.completed',
    ]);
    expect(events[3].content).toBe('전체 답변');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).client_request_id)
      .toBe('request-reconnect');
    expect(JSON.parse(fetchMock.mock.calls[1][1].body).client_request_id)
      .toBe('request-reconnect');
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

  it('실패한 첨부는 사용자가 재시도할 때 저장된 원본을 다시 처리한다', async () => {
    request.mockResolvedValueOnce({
      id: 'ATT/1',
      filename: 'scan.png',
      status: 'ready',
    });

    const result = await v2ChatHttpApi.processAttachment('ATT/1');

    expect(request).toHaveBeenCalledWith({
      path: '/api/v2/attachments/ATT%2F1/process',
      method: 'POST',
    });
    expect(result).toMatchObject({ status: 'ready' });
  });

  it('상태 카드용 업로드는 실패 응답을 그대로 반환할 수 있다', async () => {
    request.mockResolvedValueOnce({
      id: 'ATT-FAILED',
      filename: 'scan.png',
      status: 'failed',
      parse_error: 'OCR 실행 환경이 없습니다.',
    });

    const result = await v2ChatHttpApi.uploadAttachments([
      { file: new File(['image'], 'scan.png', { type: 'image/png' }) },
    ], { throwOnFailure: false });

    expect(result[0]).toMatchObject({ status: 'failed' });
  });

  it('공통 업로드 경로에서 열한 번째 파일을 서버 호출 전에 거부한다', async () => {
    const files = Array.from({ length: 11 }, (_, index) => (
      new File(['x'], `${index}.txt`, { type: 'text/plain' })
    ));

    await expect(v2ChatHttpApi.uploadAttachments(files)).rejects.toThrow('최대 10개');
    expect(request).not.toHaveBeenCalled();
  });

  it('첨부 원본은 저장됐지만 파싱이 실패하면 메시지 전송 전에 이유를 알린다', async () => {
    request.mockResolvedValueOnce({
      id: 'ATT-FAILED',
      filename: 'scan.png',
      status: 'failed',
      parse_error: 'Tesseract 실행 파일을 찾을 수 없습니다.',
    });

    await expect(v2ChatHttpApi.uploadAttachments([
      {
        file: new File(['image'], 'scan.png', { type: 'image/png' }),
        contentHash: 'a'.repeat(64),
      },
    ])).rejects.toThrow(
      'scan.png: 이미지의 글자를 읽지 못했어요. 더 선명한 이미지로 다시 시도하거나 PDF·텍스트 파일을 첨부해 주세요.',
    );
  });
});
