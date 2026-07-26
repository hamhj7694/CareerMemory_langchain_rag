import { createHttpAdapter } from './adapters/httpAdapter.js';
import { apiConfig } from './config.js';

// 경험 관리 화면에서 사용하는 실제 FastAPI 요청 도구입니다.
const http = createHttpAdapter({
  baseUrl: apiConfig.baseUrl,
  timeoutMs: apiConfig.timeoutMs,
});

const pathId = (value) => encodeURIComponent(value);

export const experienceLibraryHttpApi = {
  listStructure() {
    return http.request({ path: '/api/v2/experience-structure' });
  },

  listExperiences() {
    return http.request({ path: '/api/v2/experiences' });
  },

  getExperience(experienceId) {
    return http.request({ path: `/api/v2/experiences/${pathId(experienceId)}` });
  },

  createExperience(input) {
    return http.request({
      path: '/api/v2/experiences',
      method: 'POST',
      body: input,
    });
  },

  updateExperience(experienceId, input) {
    return http.request({
      path: `/api/v2/experiences/${pathId(experienceId)}`,
      method: 'PATCH',
      body: input,
    });
  },

  deleteExperience(experienceId, input = {}) {
    return http.request({
      path: `/api/v2/experiences/${pathId(experienceId)}`,
      method: 'DELETE',
      body: input,
    });
  },

  createDomain(input) {
    return http.request({
      path: '/api/v2/experience-domains',
      method: 'POST',
      body: input,
    });
  },

  updateDomain(domainId, input) {
    const { base_version, ...changes } = input;
    return http.request({
      path: `/api/v2/experience-domains/${pathId(domainId)}`,
      method: 'PATCH',
      body: { base_version, changes },
    });
  },

  deleteDomain(domainId, input = {}) {
    return http.request({
      path: `/api/v2/experience-domains/${pathId(domainId)}`,
      method: 'DELETE',
      body: input,
    });
  },

  createProject(input) {
    return http.request({
      path: '/api/v2/experience-projects',
      method: 'POST',
      body: input,
    });
  },

  updateProject(projectId, input) {
    const { base_version, ...changes } = input;
    return http.request({
      path: `/api/v2/experience-projects/${pathId(projectId)}`,
      method: 'PATCH',
      body: { base_version, changes },
    });
  },

  deleteProject(projectId, input = {}) {
    return http.request({
      path: `/api/v2/experience-projects/${pathId(projectId)}`,
      method: 'DELETE',
      body: input,
    });
  },

  bulkMoveExperiences(input) {
    return http.request({
      path: '/api/v2/experiences/bulk-move',
      method: 'POST',
      body: input,
    });
  },
};
