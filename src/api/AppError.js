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
    return new AppError({ code: 'INVALID_RESPONSE', message: '서버 응답을 처리할 수 없습니다.', status });
  }
  return new AppError({
    code: error.code || 'UNKNOWN_ERROR',
    message: error.message || '요청을 처리하지 못했습니다.',
    status,
    fieldErrors: error.field_errors || [],
    requestId: error.request_id || '',
    retryable: Boolean(error.retryable),
    retryAfterSeconds: error.retry_after_seconds,
    details: error.details,
  });
}
