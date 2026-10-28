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
  listRecoverable() {
    return http.request({
      path: '/api/v2/analysis-runs?target_type=experience_extraction&unclaimed_only=true&limit=1',
    });
  },
  discard(runId) {
    return http.request({
      path: `/api/v2/analysis-runs/${encodeURIComponent(runId)}/discard`,
      method: 'POST',
    });
  },
  analyzeDirectInput({ text, files = [], clientRequestId, domainId, projectId } = {}) {
    if (files.length) {
      const body = new FormData();
      body.append('client_request_id', clientRequestId || createRequestId());
      body.append('text', text || '');
      if (domainId) body.append('preferred_domain_id', domainId);
      if (projectId) body.append('preferred_project_id', projectId);
      files.forEach((item) => body.append('files', item.file || item));
      return http.request({
        path: '/api/v2/experience-extractions/direct-input-files-v2',
        method: 'POST',
        body,
      });
    }
    return http.request({
      path: '/api/v2/experience-extractions/direct-input-v2',
      method: 'POST',
      body: {
        client_request_id: clientRequestId || createRequestId(),
        input_type: 'direct_input',
        text,
        attachment_ids: [],
        preferred_domain_id: domainId || null,
        preferred_project_id: projectId || null,
      },
    });
  },
  updateUnitsProposal(analysisRunId, input) {
    return http.request({
      path: `/api/v2/experience-extractions/${encodeURIComponent(analysisRunId)}/experience-units-proposal`,
      method: 'PATCH',
      body: input,
    });
  },
  approveExperienceUnit(analysisRunId, input) {
    return http.request({
      path: `/api/v2/experience-extractions/${encodeURIComponent(analysisRunId)}/experience-units-proposal/approve`,
      method: 'POST',
      body: input,
    });
  },
  getUnitsProposalSpans(analysisRunId) {
    return http.request({
      path: `/api/v2/experience-extractions/${encodeURIComponent(analysisRunId)}/experience-units-proposal/spans`,
    });
  },
};
