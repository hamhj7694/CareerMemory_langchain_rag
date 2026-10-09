import { describe, expect, it } from 'vitest';
import { normalizeApiError } from './AppError.js';

describe('API 오류 공개 문구', () => {
  it('AI 제공자의 내부 오류 대신 사용자 안내를 제공한다', () => {
    const error = normalizeApiError({
      error: {
        code: 'AI_PROVIDER_ERROR',
        message: 'OpenAI provider returned HTTP 502 with invalid JSON',
        request_id: 'REQ-1',
        retryable: true,
      },
    }, 502);

    expect(error.message).toBe('AI 응답을 받아오지 못했어요. 잠시 후 다시 시도해 주세요.');
    expect(error.requestId).toBe('REQ-1');
    expect(error.retryable).toBe(true);
  });

  it('사용자가 바로 수정할 수 있는 입력 오류는 유지한다', () => {
    const error = normalizeApiError({
      error: {
        code: 'VALIDATION_ERROR',
        message: '채용공고 원문을 입력해 주세요.',
      },
    }, 422);

    expect(error.message).toBe('채용공고 원문을 입력해 주세요.');
  });
});

