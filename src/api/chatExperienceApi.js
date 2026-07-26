import { apiConfig } from './config.js';
import { createHttpAdapter } from './adapters/httpAdapter.js';

const http = createHttpAdapter({
  baseUrl: apiConfig.baseUrl,
  timeoutMs: Math.max(apiConfig.timeoutMs, 180_000),
});

export const chatExperienceApi = {
  analyze(conversationId, { text, files = [], clientRequestId }) {
    const body = new FormData();
    body.append('client_request_id', clientRequestId);
    body.append('text', text || '');
    files.forEach((item) => body.append('files', item.file || item));
    return http.request({
      path: `/api/v2/conversations/${encodeURIComponent(conversationId)}/experience-analysis`,
      method: 'POST',
      body,
    });
  },

  updateProposal(conversationId, messageId, input) {
    return http.request({
      path: `/api/v2/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}/experience-proposal`,
      method: 'PATCH',
      body: input,
    });
  },
};
