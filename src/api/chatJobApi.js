import { apiConfig } from './config.js';
import { createHttpAdapter } from './adapters/httpAdapter.js';

const http = createHttpAdapter({
  baseUrl: apiConfig.baseUrl,
  timeoutMs: apiConfig.jobAnalysisTimeoutMs,
});

export const chatJobApi = {
  getExtractionStatus(conversationId) {
    return http.request({
      path: `/api/v2/conversations/${encodeURIComponent(conversationId)}/job-extraction-status`,
    });
  },

  extractFromConversation(conversationId, input) {
    return http.request({
      path: `/api/v2/conversations/${encodeURIComponent(conversationId)}/job-extractions`,
      method: 'POST',
      body: input,
    });
  },

  record(conversationId, input) {
    return http.request({
      path: `/api/v2/conversations/${encodeURIComponent(conversationId)}/job-analysis-record`,
      method: 'POST',
      body: input,
    });
  },
};
