import { apiRequest, apiMode } from './client.js';
import { apiConfig } from './config.js';
import { createClientRequestId } from './requestId.js';
import { unifiedMockApi } from './unifiedMockApi.js';

const idPath = (value) => encodeURIComponent(String(value));

export const sourceApi = {
  addText(experienceId, input, options = {}) {
    return apiMode === 'mock'
      ? unifiedMockApi.addTextEvidence(experienceId, input)
      : apiRequest({
        path: `/api/experiences/${idPath(experienceId)}/sources/text`,
        method: 'POST',
        body: { ...input, clientRequestId: createClientRequestId() },
        ...options,
      });
  },
  async addFiles(experienceId, files, options = {}) {
    if (apiMode === 'mock') return unifiedMockApi.addFileEvidence(experienceId, files);
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    formData.append('clientRequestId', createClientRequestId());
    const response = await fetch(`${apiConfig.baseUrl}/api/experiences/${idPath(experienceId)}/sources/files`, {
      method: 'POST',
      body: formData,
      signal: options.signal,
    });
    if (!response.ok) throw new Error('파일 근거를 추가하지 못했습니다.');
    return response.json();
  },
  update(sourceId, changes, options = {}) {
    return apiMode === 'mock' ? unifiedMockApi.updateEvidence(sourceId, changes) : apiRequest({ path: `/api/sources/${idPath(sourceId)}`, method: 'PATCH', body: { changes, clientRequestId: createClientRequestId() }, ...options });
  },
  remove(sourceId, options = {}) {
    return apiMode === 'mock' ? unifiedMockApi.removeEvidence(sourceId) : apiRequest({ path: `/api/sources/${idPath(sourceId)}`, method: 'DELETE', body: { clientRequestId: createClientRequestId() }, ...options });
  },
  unlink(experienceId, sourceId, options = {}) {
    return apiMode === 'mock'
      ? unifiedMockApi.unlinkEvidence(experienceId, sourceId)
      : apiRequest({
        path: `/api/experiences/${idPath(experienceId)}/sources/${idPath(sourceId)}`,
        method: 'DELETE',
        body: { clientRequestId: createClientRequestId() },
        ...options,
      });
  },
  reorganize(experienceId, options = {}) {
    return apiMode === 'mock'
      ? unifiedMockApi.reorganizeExperienceFromEvidence(experienceId)
      : apiRequest({
        path: `/api/experiences/${idPath(experienceId)}/reorganize-from-sources`,
        method: 'POST',
        body: { clientRequestId: createClientRequestId() },
        ...options,
      });
  },
  async download(source) {
    if (apiMode === 'mock') {
      const payload = source.rawBytes || source.raw_bytes || source.text;
      if (!payload) throw new Error('저장된 원본 파일 데이터가 없습니다.');
      return new Blob([payload], { type: source.mimeType || source.mime_type || 'application/octet-stream' });
    }
    const response = await fetch(`${apiConfig.baseUrl}/api/sources/${idPath(source.id)}/download`);
    if (!response.ok) throw new Error('파일을 다운로드하지 못했습니다.');
    return response.blob();
  },
};
