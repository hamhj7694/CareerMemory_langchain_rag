import { apiRequest, apiMode } from './client.js';
import { apiConfig } from './config.js';
import { createHttpAdapter } from './adapters/httpAdapter.js';
import { toScreenModel } from './modelMapper.js';
import { createClientRequestId } from './requestId.js';
import { unifiedMockApi } from './unifiedMockApi.js';
import { v2ChatApi } from './v2ChatApi.js';

const idPath = (value) => encodeURIComponent(String(value));
const aiHttp = createHttpAdapter({
  baseUrl: apiConfig.baseUrl,
  timeoutMs: Math.max(apiConfig.timeoutMs, 180_000),
});

export const sourceApi = {
  addText(experienceId, input, options = {}) {
    return apiMode === 'mock'
      ? unifiedMockApi.addTextEvidence(experienceId, input)
      : apiRequest({
        path: `/api/v2/experiences/${idPath(experienceId)}/sources/text`,
        method: 'POST',
        body: { ...input, clientRequestId: createClientRequestId() },
        ...options,
      });
  },
  async addFiles(experienceId, files, options = {}) {
    if (apiMode === 'mock') return unifiedMockApi.addFileEvidence(experienceId, files);
    const attachments = await v2ChatApi.uploadAttachments(files);
    return apiRequest({
      path: `/api/v2/experiences/${idPath(experienceId)}/sources/files`,
      method: 'POST',
      body: {
        attachmentIds: attachments.map((attachment) => attachment.id),
        clientRequestId: createClientRequestId(),
      },
      ...options,
    });
  },
  update(experienceId, sourceId, changes, options = {}) {
    if (apiMode === 'mock') {
      // 기존 목 API 호출(sourceId, changes)도 유지해 관련 근거 미리보기 테스트를 깨지 않는다.
      if (typeof sourceId === 'object') {
        return unifiedMockApi.updateEvidence(experienceId, sourceId);
      }
      return unifiedMockApi.updateEvidence(sourceId, changes);
    }
    return apiRequest({ path: `/api/v2/experiences/${idPath(experienceId)}/sources/${idPath(sourceId)}`, method: 'PATCH', body: { changes, clientRequestId: createClientRequestId() }, ...options });
  },
  remove(sourceId, options = {}) {
    return apiMode === 'mock' ? unifiedMockApi.removeEvidence(sourceId) : apiRequest({ path: `/api/v2/sources/${idPath(sourceId)}`, method: 'DELETE', body: { clientRequestId: createClientRequestId() }, ...options });
  },
  unlink(experienceId, sourceId, options = {}) {
    return apiMode === 'mock'
      ? unifiedMockApi.unlinkEvidence(experienceId, sourceId)
      : apiRequest({
        path: `/api/v2/experiences/${idPath(experienceId)}/sources/${idPath(sourceId)}`,
        method: 'DELETE',
        body: { clientRequestId: createClientRequestId() },
        ...options,
      });
  },
  reorganize(experienceId, options = {}) {
    if (apiMode === 'mock') {
      return unifiedMockApi.reorganizeExperienceFromEvidence(experienceId);
    }
    return aiHttp.request({
      path: `/api/v2/experiences/${idPath(experienceId)}/reorganize-from-sources`,
      method: 'POST',
      body: { clientRequestId: createClientRequestId() },
      ...options,
    }).then(toScreenModel);
  },
  async download(experienceId, source) {
    const selectedSource = source || experienceId;
    if (apiMode === 'mock') {
      const payload = selectedSource.rawBytes || selectedSource.raw_bytes || selectedSource.text;
      if (!payload) throw new Error('저장된 원본 파일 데이터가 없습니다.');
      return new Blob([payload], { type: selectedSource.mimeType || selectedSource.mime_type || 'application/octet-stream' });
    }
    if (!source) throw new Error('파일이 연결된 경험 정보를 확인할 수 없습니다.');
    const response = await fetch(
      `${apiConfig.baseUrl}/api/v2/experiences/${idPath(experienceId)}/sources/${idPath(selectedSource.id)}/download`,
      { credentials: 'include' },
    );
    if (!response.ok) {
      const payload = await response.json().catch(() => undefined);
      throw new Error(payload?.error?.message || '파일을 다운로드하지 못했습니다.');
    }
    return response.blob();
  },
};
