import { apiConfig } from './config.js';
import { createHttpAdapter } from './adapters/httpAdapter.js';

const http = createHttpAdapter({
  baseUrl: apiConfig.baseUrl,
  timeoutMs: apiConfig.jobAnalysisTimeoutMs,
});

export const chatAnalysisApi = {
  getStatus(conversationId) {
    return http.request({
      path: `/api/v2/conversations/${encodeURIComponent(conversationId)}/analysis-status`,
    });
  },

  analyze(conversationId, input) {
    return http.request({
      path: `/api/v2/conversations/${encodeURIComponent(conversationId)}/analyses`,
      method: 'POST',
      body: input,
    });
  },
};
