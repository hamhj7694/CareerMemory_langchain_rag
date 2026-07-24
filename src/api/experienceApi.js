import { apiMode, apiRequest } from './client.js';
import { unifiedMockApi } from './unifiedMockApi.js';
import { hasMockHandler } from './adapters/mockAdapter.js';
import { createClientRequestId } from './requestId.js';

const idPath = (value) => encodeURIComponent(String(value));

export const experienceApi = {
  commit(draft, options = {}) { return apiRequest({ path: '/api/experiences/commit', method: 'POST', body: { clientRequestId: createClientRequestId(), ...draft }, ...options }); },
  create(draft, options = {}) { const path = '/api/experiences'; return apiMode === 'mock' && !hasMockHandler('POST', path) ? unifiedMockApi.createExperience(draft) : apiRequest({ path, method: 'POST', body: { clientRequestId: createClientRequestId(), ...draft }, ...options }); },
  getTree(options = {}) { const path = '/api/experiences/tree'; return apiMode === 'mock' && !hasMockHandler('GET', path) ? unifiedMockApi.getExperienceTree() : apiRequest({ path, ...options }); },
  get(experienceId, options = {}) { const path = `/api/experiences/${idPath(experienceId)}`; return apiMode === 'mock' && !hasMockHandler('GET', path) ? unifiedMockApi.getExperience(experienceId) : apiRequest({ path, ...options }); },
  update(experienceId, patch, options = {}) { const path = `/api/experiences/${idPath(experienceId)}`; return apiMode === 'mock' && !hasMockHandler('PATCH', path) ? unifiedMockApi.updateExperience(experienceId, patch) : apiRequest({ path, method: 'PATCH', body: { clientRequestId: createClientRequestId(), ...patch }, ...options }); },
  getSources(experienceId, options = {}) { const path = `/api/experiences/${idPath(experienceId)}/sources`; return apiMode === 'mock' && !hasMockHandler('GET', path) ? unifiedMockApi.getExperienceSources(experienceId) : apiRequest({ path, ...options }); },
  chat(message, context = {}, options = {}) { return apiRequest({ path: '/api/chat/experiences', method: 'POST', body: { message, clientRequestId: createClientRequestId(), ...context }, ...options }); },
};
