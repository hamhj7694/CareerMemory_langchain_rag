import { apiRequest } from './client.js';

export const inputApi = {
  parseText(content, clientRequestId, options = {}) {
    return apiRequest({ path: '/api/inputs/text', method: 'POST', body: { content, clientRequestId }, ...options });
  },
  parseFile(file, clientRequestId, options = {}) {
    const body = new FormData();
    body.append('file', file);
    body.append('client_request_id', clientRequestId);
    return apiRequest({ path: '/api/inputs/file', method: 'POST', body, ...options });
  },
  parseFiles(files, clientRequestId, options = {}) {
    const body = new FormData();
    files.forEach((file) => body.append('files', file));
    body.append('client_request_id', clientRequestId);
    return apiRequest({ path: '/api/inputs/file', method: 'POST', body, ...options });
  },
};
