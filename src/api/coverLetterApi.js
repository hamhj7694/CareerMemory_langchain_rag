import { apiRequest } from './client.js';
import { createClientRequestId } from './requestId.js';

const idPath = (value) => encodeURIComponent(String(value));

export const coverLetterApi = {
  generate(input, options = {}) { return apiRequest({ path: '/api/cover-letters/generate', method: 'POST', body: { clientRequestId: createClientRequestId(), ...input }, ...options }); },
  revise(input, options = {}) { return apiRequest({ path: '/api/cover-letters/revise', method: 'POST', body: { clientRequestId: createClientRequestId(), ...input }, ...options }); },
  get(documentId, options = {}) { return apiRequest({ path: `/api/documents/${idPath(documentId)}`, ...options }); },
  update(documentId, patch, options = {}) { return apiRequest({ path: `/api/documents/${idPath(documentId)}`, method: 'PATCH', body: { clientRequestId: createClientRequestId(), ...patch }, ...options }); },
};
