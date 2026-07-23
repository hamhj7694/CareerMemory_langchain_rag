import { apiMode, apiRequest } from './client.js';
import { unifiedMockApi } from './unifiedMockApi.js';
import { hasMockHandler } from './adapters/mockAdapter.js';
import { createClientRequestId } from './requestId.js';

const idPath = (value) => encodeURIComponent(String(value));

export const jobApi = {
  analyze(input, options = {}) { const path = '/api/jobs/analyze'; return apiMode === 'mock' && !hasMockHandler('POST', path) ? unifiedMockApi.analyzeJob(input) : apiRequest({ path, method: 'POST', body: { clientRequestId: createClientRequestId(), ...input }, ...options }); },
  get(jobId, options = {}) { const path = `/api/jobs/${idPath(jobId)}`; return apiMode === 'mock' && !hasMockHandler('GET', path) ? unifiedMockApi.getJob(jobId) : apiRequest({ path, ...options }); },
  match(jobId, input = {}, options = {}) { const path = `/api/jobs/${idPath(jobId)}/match`; return apiMode === 'mock' && !hasMockHandler('POST', path) ? unifiedMockApi.matchJob(jobId, input) : apiRequest({ path, method: 'POST', body: { requirementIds: [], clientRequestId: createClientRequestId(), ...input }, ...options }); },
  setRequirementLink(jobId, requirementId, experienceId, linked, options = {}) { return apiMode === 'mock' ? unifiedMockApi.setRequirementLink(jobId, requirementId, experienceId, linked) : apiRequest({ path: `/api/jobs/${idPath(jobId)}/requirements/${idPath(requirementId)}/experience-links/${idPath(experienceId)}`, method: linked ? 'PUT' : 'DELETE', body: { clientRequestId: createClientRequestId() }, ...options }); },
};
