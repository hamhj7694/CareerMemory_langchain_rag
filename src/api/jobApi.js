import { apiMode, apiRequest } from './client.js';
import { apiConfig } from './config.js';
import { unifiedMockApi } from './unifiedMockApi.js';
import { hasMockHandler } from './adapters/mockAdapter.js';
import { createClientRequestId } from './requestId.js';

const idPath = (value) => encodeURIComponent(String(value));
const withJobAnalysisTimeout = (options = {}) => ({
  ...options,
  timeoutMs: Math.max(
    Number(options.timeoutMs) || 0,
    apiConfig.jobAnalysisTimeoutMs,
  ),
});

export const jobApi = {
  list(options = {}) { const path = '/api/jobs'; return apiMode === 'mock' ? Promise.resolve({ items: [] }) : apiRequest({ path, ...options }); },
  extractFiles(files, options = {}) {
    const body = new FormData();
    files.forEach((file) => body.append('files', file.file || file));
    return apiRequest({
      path: '/api/jobs/extract-text',
      method: 'POST',
      body,
      ...withJobAnalysisTimeout(options),
    });
  },
  analyze(input, options = {}) {
    const path = '/api/jobs/analyze';
    if (apiMode === 'mock' && !hasMockHandler('POST', path)) {
      return unifiedMockApi.analyzeJob(input);
    }
    const { clientRequestId, ...payload } = input;
    return apiRequest({
      path,
      method: 'POST',
      body: {
        ...payload,
        clientRequestId: clientRequestId || createClientRequestId(),
      },
      ...withJobAnalysisTimeout(options),
    });
  },
  get(jobId, options = {}) { const path = `/api/jobs/${idPath(jobId)}`; return apiMode === 'mock' && !hasMockHandler('GET', path) ? unifiedMockApi.getJob(jobId) : apiRequest({ path, ...options }); },
  match(jobId, input = {}, options = {}) { const path = `/api/jobs/${idPath(jobId)}/match`; return apiMode === 'mock' && !hasMockHandler('POST', path) ? unifiedMockApi.matchJob(jobId, input) : apiRequest({ path, method: 'POST', body: { requirementIds: [], clientRequestId: createClientRequestId(), ...input }, ...withJobAnalysisTimeout(options) }); },
  rematch(jobId, requirementIds = [], options = {}) { const path = `/api/jobs/${idPath(jobId)}/match`; return apiMode === 'mock' && !hasMockHandler('POST', path) ? unifiedMockApi.matchJob(jobId, { requirementIds }) : apiRequest({ path, method: 'POST', body: { requirementIds, refresh: true, clientRequestId: createClientRequestId() }, ...withJobAnalysisTimeout(options) }); },
  setRequirementLink(jobId, requirementId, experienceId, linked, options = {}) { return apiMode === 'mock' ? unifiedMockApi.setRequirementLink(jobId, requirementId, experienceId, linked) : apiRequest({ path: `/api/jobs/${idPath(jobId)}/requirements/${idPath(requirementId)}/experience-links/${idPath(experienceId)}`, method: linked ? 'PUT' : 'DELETE', body: { clientRequestId: createClientRequestId() }, ...options }); },
  remove(jobId, options = {}) { const path = `/api/jobs/${idPath(jobId)}`; return apiMode === 'mock' ? Promise.resolve(undefined) : apiRequest({ path, method: 'DELETE', ...options }); },
};
