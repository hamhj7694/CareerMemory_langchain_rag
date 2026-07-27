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
  async getSources(experienceId, options = {}) {
    const legacyPath = `/api/experiences/${idPath(experienceId)}/sources`;
    if (apiMode === 'mock' && !hasMockHandler('GET', legacyPath)) {
      return unifiedMockApi.getExperienceSources(experienceId);
    }

    // v2 경험 응답이 source_refs를 함께 제공하므로 별도의 구형 sources API를 호출하지 않는다.
    const experience = await apiRequest({
      path: `/api/v2/experiences/${idPath(experienceId)}`,
      ...options,
    });
    const sourceRefs = Array.isArray(experience.sourceRefs) ? experience.sourceRefs : [];
    const sourceIds = Array.isArray(experience.sourceIds) ? experience.sourceIds : [];
    const sourcesById = new Map();

    sourceRefs.forEach((source, index) => {
      const normalized = typeof source === 'string'
        ? { id: source, type: 'unknown', unavailable: true }
        : source;
      const id = normalized?.id || normalized?.sourceId || sourceIds[index];
      if (id) sourcesById.set(id, { ...normalized, id });
    });
    sourceIds.forEach((id) => {
      if (!sourcesById.has(id)) {
        sourcesById.set(id, {
          id,
          type: 'unknown',
          title: '원본 정보 없음',
          unavailable: true,
        });
      }
    });

    return {
      experienceId,
      sources: [...sourcesById.values()],
    };
  },
  chat(message, context = {}, options = {}) { return apiRequest({ path: '/api/chat/experiences', method: 'POST', body: { message, clientRequestId: createClientRequestId(), ...context }, ...options }); },
};
