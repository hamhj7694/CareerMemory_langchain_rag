import { createHttpAdapter } from './adapters/httpAdapter.js';
import { apiConfig } from './config.js';
import { getCsrfToken } from '../auth/authSession.js';

const http = createHttpAdapter({
  baseUrl: apiConfig.baseUrl,
  timeoutMs: apiConfig.timeoutMs,
});

const pathId = (value) => encodeURIComponent(value);

export const experienceTrashApi = {
  list() {
    return http.request({ path: '/api/v2/experience-draft-trash' });
  },

  create(input) {
    return http.request({
      path: '/api/v2/experience-draft-trash',
      method: 'POST',
      body: input,
    });
  },

  createWithFiles(input, files = []) {
    const body = new FormData();
    body.append('status', input.status);
    body.append('reason', input.reason || '');
    body.append('draft_json', JSON.stringify(input.draft || {}));
    body.append('original_text', input.original_text || '');
    files.forEach((item) => body.append('files', item.file || item));
    return http.request({
      path: '/api/v2/experience-draft-trash/with-files',
      method: 'POST',
      body,
    });
  },

  async downloadFile(itemId, file) {
    const response = await fetch(
      `${apiConfig.baseUrl}/api/v2/experience-draft-trash/${pathId(itemId)}/files/${pathId(file.id)}`,
      { credentials: 'include', headers: getCsrfToken() ? { 'X-CSRF-Token': getCsrfToken() } : {} },
    );
    if (!response.ok) throw new Error('보관된 원본 파일을 불러오지 못했습니다.');
    return new File([await response.blob()], file.filename, { type: file.mime_type });
  },

  update(itemId, draft) {
    return http.request({
      path: `/api/v2/experience-draft-trash/${pathId(itemId)}`,
      method: 'PATCH',
      body: { draft },
    });
  },

  remove(itemId) {
    return http.request({
      path: `/api/v2/experience-draft-trash/${pathId(itemId)}`,
      method: 'DELETE',
      body: { confirm: true },
    });
  },
};
