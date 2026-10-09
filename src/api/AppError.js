import { toUserFacingErrorMessage } from './userFacingError.js';

export class AppError extends Error {
  constructor({ code, message, status = 0, fieldErrors = [], requestId = '', retryable = false, retryAfterSeconds, details, cause }) {
    super(message, { cause });
    this.name = 'AppError';
    this.code = code;
    this.status = status;
    this.fieldErrors = fieldErrors;
    this.requestId = requestId;
    this.retryable = retryable;
    this.retryAfterSeconds = retryAfterSeconds;
    this.details = details;
  }
}

export function normalizeApiError(payload, status) {
  const error = payload?.error;
  if (!error) {
    return new AppError({
      code: 'INVALID_RESPONSE',
      message: toUserFacingErrorMessage({ code: 'INVALID_RESPONSE', status }),
      status,
    });
  }
  const code = error.code || 'UNKNOWN_ERROR';
  const rawMessage = error.message || '';
  return new AppError({
    code,
    message: toUserFacingErrorMessage(
      { code, message: rawMessage, status },
      '요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.',
    ),
    status,
    fieldErrors: error.field_errors || [],
    requestId: error.request_id || '',
    retryable: Boolean(error.retryable),
    retryAfterSeconds: error.retry_after_seconds,
    details: error.details,
  });
}
