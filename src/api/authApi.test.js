import { beforeEach, describe, expect, it, vi } from 'vitest';

const { request } = vi.hoisted(() => ({
  request: vi.fn(async (input) => input),
}));

vi.mock('./adapters/httpAdapter.js', () => ({
  createHttpAdapter: () => ({ request }),
}));

import { authApi } from './authApi.js';

describe('password recovery API', () => {
  beforeEach(() => request.mockClear());

  it('loads the one recovery question stored for the account identity', async () => {
    await authApi.getRecoveryQuestion({
      email: 'user@example.com',
      username: 'test_user',
    });

    expect(request).toHaveBeenCalledWith({
      path: '/api/v2/auth/password/recovery-question',
      method: 'POST',
      body: {
        email: 'user@example.com',
        username: 'test_user',
      },
    });
  });
});
