import { beforeEach, describe, expect, it, vi } from 'vitest';

const { request } = vi.hoisted(() => ({
  request: vi.fn(async (input) => input),
}));

vi.mock('./adapters/httpAdapter.js', () => ({
  createHttpAdapter: () => ({ request }),
}));

import { chatAnalysisApi } from './chatAnalysisApi.js';

describe('conversation integrated analysis API', () => {
  beforeEach(() => request.mockClear());

  it('loads the combined pending status', async () => {
    await chatAnalysisApi.getStatus('CONV-1');

    expect(request).toHaveBeenCalledWith({
      path: '/api/v2/conversations/CONV-1/analysis-status',
    });
  });

  it('starts experience and job analysis with one request', async () => {
    await chatAnalysisApi.analyze('CONV-1', {
      client_request_id: 'request-1',
    });

    expect(request).toHaveBeenCalledWith({
      path: '/api/v2/conversations/CONV-1/analyses',
      method: 'POST',
      body: { client_request_id: 'request-1' },
    });
  });
});
