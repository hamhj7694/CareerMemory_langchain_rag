import { apiConfig } from './config.js';
import { createHttpAdapter } from './adapters/httpAdapter.js';

const http = createHttpAdapter({
  baseUrl: apiConfig.baseUrl,
  // 경험 구조화는 일반 API보다 오래 걸릴 수 있어 별도 제한 시간을 사용한다.
  // 파일별 청크 요약 뒤 최종 경험 구조화를 연속 실행하므로 충분한 처리 시간을 둔다.
  timeoutMs: Math.max(apiConfig.timeoutMs, 300_000),
});

function createRequestId() {
  return globalThis.crypto?.randomUUID?.()
    ?? `direct-input-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export const experienceExtractionApi = {
  analyzeDirectInput({ text, files = [], clientRequestId } = {}) {
    if (files.length) {
      const body = new FormData();
      body.append('client_request_id', clientRequestId || createRequestId());
      body.append('text', text || '');
      files.forEach((item) => body.append('files', item.file || item));
      return http.request({
        path: '/api/v2/experience-extractions/direct-input-files',
        method: 'POST',
        body,
      });
    }
    return http.request({
      path: '/api/v2/experience-extractions/direct-input',
      method: 'POST',
      body: {
        client_request_id: clientRequestId || createRequestId(),
        input_type: 'direct_input',
        text,
        attachment_ids: [],
      },
    });
  },
};
