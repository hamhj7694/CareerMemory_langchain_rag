import { apiRequest, apiMode } from './client.js';
import { apiConfig } from './config.js';
import { createClientRequestId } from './requestId.js';
import { unifiedMockApi } from './unifiedMockApi.js';

const idPath = (value) => encodeURIComponent(String(value));

export const sourceApi = {
  update(sourceId, changes, options = {}) {
    return apiMode === 'mock' ? unifiedMockApi.updateEvidence(sourceId, changes) : apiRequest({ path: `/api/sources/${idPath(sourceId)}`, method: 'PATCH', body: { changes, clientRequestId: createClientRequestId() }, ...options });
  },
  remove(sourceId, options = {}) {
    return apiMode === 'mock' ? unifiedMockApi.removeEvidence(sourceId) : apiRequest({ path: `/api/sources/${idPath(sourceId)}`, method: 'DELETE', body: { clientRequestId: createClientRequestId() }, ...options });
  },
  async download(source) {
    if (apiMode === 'mock') return new Blob([source.text || 'Mock source file'], { type: 'text/plain;charset=utf-8' });
    const response = await fetch(`${apiConfig.baseUrl}/api/sources/${idPath(source.id)}/download`);
    if (!response.ok) throw new Error('파일을 다운로드하지 못했습니다.');
    return response.blob();
  },
};
