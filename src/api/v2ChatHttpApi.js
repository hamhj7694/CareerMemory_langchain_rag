import { apiConfig } from './config.js';
import { createHttpAdapter } from './adapters/httpAdapter.js';
import { normalizeApiError } from './AppError.js';
import { toWireModel } from './modelMapper.js';
import { getCsrfToken } from '../auth/authSession.js';

// 1. 실제 HTTP 요청 도구
// 공통 Adapter가 base URL, JSON 변환, timeout, 오류 형식을 한곳에서 처리한다.
const http = createHttpAdapter({
  baseUrl: apiConfig.baseUrl,
  timeoutMs: apiConfig.timeoutMs,
});

// 2. 요청 UUID 생성
// 같은 사용자 동작을 수동 재시도할 때는 호출부에서 기존 UUID를 다시 전달할 수 있다.
function createRequestId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();

  // HTTP 접속 등으로 randomUUID를 사용할 수 없는 브라우저에서도
  // FastAPI UUID 검증을 통과하는 표준 UUID v4 모양을 만든다.
  const randomHex = () => Math.floor(Math.random() * 16).toString(16);
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (token) => {
    const randomValue = Number.parseInt(randomHex(), 16);
    const value = token === 'x' ? randomValue : (randomValue & 0x3) | 0x8;
    return value.toString(16);
  });
}

// 3. 대화 생성
// 화면은 제목만 전달해도 되며, 백엔드 멱등성에 필요한 UUID는 이 계층에서 보충한다.
export function createConversation(input = {}) {
  return http.request({
    path: '/api/v2/conversations',
    method: 'POST',
    body: {
      title: input.title || '새 대화',
      client_request_id: input.client_request_id || createRequestId(),
    },
  });
}

// 4. 대화 목록과 상세
export function listConversations({ status = 'active', cursor, limit = 20 } = {}) {
  return http.request({
    path: '/api/v2/conversations',
    query: { status, cursor, limit },
  });
}

export function getConversation(conversationId) {
  return http.request({
    path: `/api/v2/conversations/${encodeURIComponent(conversationId)}`,
  });
}

// 5. 대화 제목 변경과 삭제
// 화면이 가진 version을 함께 보내 오래된 화면이 최신 데이터를 덮어쓰지 못하게 한다.
export function updateConversation(conversationId, changes = {}) {
  return http.request({
    path: `/api/v2/conversations/${encodeURIComponent(conversationId)}`,
    method: 'PATCH',
    body: {
      title: changes.title,
      status: changes.status,
      base_version: changes.base_version,
      client_request_id: changes.client_request_id || createRequestId(),
    },
  });
}

export function deleteConversation(conversationId, options = {}) {
  return http.request({
    path: `/api/v2/conversations/${encodeURIComponent(conversationId)}`,
    method: 'DELETE',
    body: {
      version: options.version,
      client_request_id: options.client_request_id || createRequestId(),
    },
  });
}

// 6-1. 메시지 이력 한 페이지
// FastAPI의 cursor를 그대로 사용해 지정한 위치의 메시지만 가져온다.
function listMessagePage(conversationId, { cursor, limit }) {
  return http.request({
    path: `/api/v2/conversations/${encodeURIComponent(conversationId)}/messages`,
    query: { cursor, limit },
  });
}

// 6-2. 세션의 전체 메시지 이력
// next_cursor가 없어질 때까지 다음 페이지를 읽어 오래된 대화도 빠뜨리지 않는다.
export async function listMessages(conversationId, { limit = 100 } = {}) {
  const items = [];
  const visitedCursors = new Set();
  let cursor;
  let totalCount;

  do {
    const page = await listMessagePage(conversationId, { cursor, limit });
    items.push(...(page.items || []));
    totalCount = page.total_count ?? items.length;

    const nextCursor = page.next_cursor;
    if (!nextCursor || visitedCursors.has(nextCursor)) {
      cursor = null;
    } else {
      visitedCursors.add(nextCursor);
      cursor = nextCursor;
    }
  } while (cursor);

  return {
    items,
    total_count: totalCount ?? items.length,
    next_cursor: null,
  };
}

// 7. 일반 대화 메시지 전송
// 현재 실제 백엔드는 텍스트 기반 auto 모드만 화면에서 사용한다.
export function sendMessage(conversationId, input = {}) {
  return http.request({
    path: `/api/v2/conversations/${encodeURIComponent(conversationId)}/messages`,
    method: 'POST',
    body: {
      content: input.content || '',
      intent: input.intent || 'auto',
      attachment_ids: input.attachment_ids || [],
      context: input.context || {
        experience_ids: [],
        job_id: null,
        selected_proposal_id: null,
      },
      response_mode: 'complete',
      client_request_id: input.client_request_id || createRequestId(),
    },
  });
}

// 8. 실시간 대화 메시지 전송
// fetch의 응답 본문을 직접 읽어 SSE의 data JSON을 이벤트 하나씩 화면에 전달한다.
export async function* streamMessage(conversationId, input = {}) {
  const response = await fetch(
    `${apiConfig.baseUrl}/api/v2/conversations/${encodeURIComponent(conversationId)}/messages/stream`,
    {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        'X-CSRF-Token': getCsrfToken(),
      },
      body: JSON.stringify(toWireModel({
        content: input.content || '',
        intent: input.intent || 'auto',
        attachment_ids: input.attachment_ids || [],
        context: input.context || {
          experience_ids: [],
          job_id: null,
          selected_proposal_id: null,
        },
        response_mode: 'stream',
        client_request_id: input.client_request_id || createRequestId(),
      })),
      signal: input.signal,
    },
  );

  if (!response.ok) {
    const payload = await response.json().catch(() => undefined);
    throw normalizeApiError(payload, response.status);
  }
  if (!response.body) {
    throw normalizeApiError({
      error: {
        code: 'INVALID_RESPONSE',
        message: '스트리밍 응답 본문이 없습니다.',
      },
    }, response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n');
    const frames = buffer.split('\n\n');
    buffer = frames.pop() || '';

    for (const frame of frames) {
      const data = frame
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
        .join('\n');
      if (data) yield JSON.parse(data);
    }
    if (done) break;
  }
}

export const v2ChatHttpApi = {
  createConversation,
  listConversations,
  getConversation,
  updateConversation,
  deleteConversation,
  listMessages,
  sendMessage,
  streamMessage,
};
