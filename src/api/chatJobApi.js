import { apiConfig } from './config.js';
import { createHttpAdapter } from './adapters/httpAdapter.js';

const http = createHttpAdapter({
  baseUrl: apiConfig.baseUrl,
  timeoutMs: apiConfig.timeoutMs,
});

export const chatJobApi = {
  record(conversationId, input) {
    return http.request({
      path: `/api/v2/conversations/${encodeURIComponent(conversationId)}/job-analysis-record`,
      method: 'POST',
      body: input,
    });
  },
};
