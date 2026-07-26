import { afterEach, describe, expect, it, vi } from 'vitest';
import { clearCsrfToken, setCsrfToken } from '../../auth/authSession.js';
import { createHttpAdapter } from './httpAdapter.js';

describe('인증 HTTP 어댑터', () => {
  afterEach(() => clearCsrfToken());

  it('쿠키를 포함하고 변경 요청에는 CSRF 헤더를 보낸다', async () => {
    setCsrfToken('csrf-test-token');
    const fetchImpl = vi.fn(async () => new Response(
      JSON.stringify({ saved: true }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    const adapter = createHttpAdapter({
      baseUrl: 'http://localhost:8000',
      timeoutMs: 1000,
      fetchImpl,
    });

    await adapter.request({
      path: '/api/v2/test',
      method: 'POST',
      body: { value: 1 },
    });

    expect(fetchImpl).toHaveBeenCalledWith(
      'http://localhost:8000/api/v2/test',
      expect.objectContaining({
        credentials: 'include',
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
          'X-CSRF-Token': 'csrf-test-token',
        }),
      }),
    );
  });

  it('조회 요청에는 CSRF 헤더를 추가하지 않는다', async () => {
    setCsrfToken('csrf-test-token');
    const fetchImpl = vi.fn(async () => new Response(
      JSON.stringify({ ok: true }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    const adapter = createHttpAdapter({
      baseUrl: 'http://localhost:8000',
      timeoutMs: 1000,
      fetchImpl,
    });

    await adapter.request({ path: '/api/v2/test' });

    expect(fetchImpl.mock.calls[0][1].headers).not.toHaveProperty(
      'X-CSRF-Token'
    );
  });
});
