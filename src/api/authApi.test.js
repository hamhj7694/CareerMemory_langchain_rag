import { beforeEach, describe, expect, it, vi } from 'vitest';

const { request } = vi.hoisted(() => ({
  request: vi.fn(async (input) => input),
}));

vi.mock('./adapters/httpAdapter.js', () => ({
  createHttpAdapter: () => ({ request }),
}));

import { authApi } from './authApi.js';

describe('간편 시작 API', () => {
  beforeEach(() => request.mockClear());

  it('입력 없이 독립된 게스트 공간을 요청한다', async () => {
    await authApi.startGuest();

    expect(request).toHaveBeenCalledWith({
      path: '/api/v2/auth/guest',
      method: 'POST',
    });
  });

  it('간단 아이디와 PIN으로 기록 공간을 열거나 만든다', async () => {
    const input = { identifier: '함형준', pin: '123456' };

    await authApi.startSimple(input);

    expect(request).toHaveBeenCalledWith({
      path: '/api/v2/auth/simple',
      method: 'POST',
      body: input,
    });
  });

  it('게스트 기록을 같은 사용자 공간에서 간단 프로필로 전환한다', async () => {
    const input = {
      identifier: 'my_memory',
      pin: '654321',
      display_name: '내 커리어',
      recovery_question: 'recovery_keyword',
      recovery_answer: '나만의 단어',
    };

    await authApi.claimGuest(input);

    expect(request).toHaveBeenCalledWith({
      path: '/api/v2/auth/simple/claim',
      method: 'PUT',
      body: input,
    });
  });

  it('아이디에 저장된 PIN 복구 질문을 요청한다', async () => {
    const input = { identifier: 'my_memory' };

    await authApi.getSimplePinRecoveryQuestion(input);

    expect(request).toHaveBeenCalledWith({
      path: '/api/v2/auth/simple/pin/recovery-question',
      method: 'POST',
      body: input,
    });
  });

  it('복구 답변으로 새 PIN 설정을 요청한다', async () => {
    const input = {
      identifier: 'my_memory',
      recovery_answer: '나만의 단어',
      pin: '123456',
      pin_confirm: '123456',
    };

    await authApi.resetSimplePin(input);

    expect(request).toHaveBeenCalledWith({
      path: '/api/v2/auth/simple/pin/reset',
      method: 'POST',
      body: input,
    });
  });

  // 기존 API는 이전 데이터와의 호환을 위해 남겨 둔다.
  it('기존 계정의 저장된 복구 질문을 불러올 수 있다', async () => {
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
