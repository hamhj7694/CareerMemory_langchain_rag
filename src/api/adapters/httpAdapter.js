import { AppError, normalizeApiError } from '../AppError.js';
import { toWireModel } from '../modelMapper.js';
import { getCsrfToken } from '../../auth/authSession.js';

function buildUrl(baseUrl, path, query) {
  const url = new URL(`${baseUrl}${path}`);
  Object.entries(query || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
  });
  return url.toString();
}

export function createHttpAdapter({ baseUrl, timeoutMs, fetchImpl = fetch }) {
  return {
    async request({ path, method = 'GET', query, body, headers = {}, signal }) {
      const timeoutController = new AbortController();
      const timeoutId = setTimeout(() => timeoutController.abort('timeout'), timeoutMs);
      const combinedSignal = signal ? AbortSignal.any([signal, timeoutController.signal]) : timeoutController.signal;
      const isFormData = body instanceof FormData;

      try {
        const csrfToken = getCsrfToken();
        const csrfHeaders = method === 'GET' || !csrfToken
          ? {}
          : { 'X-CSRF-Token': csrfToken };
        const response = await fetchImpl(buildUrl(baseUrl, path, query), {
          method,
          credentials: 'include',
          headers: isFormData
            ? { ...csrfHeaders, ...headers }
            : { 'Content-Type': 'application/json', ...csrfHeaders, ...headers },
          body: body === undefined ? undefined : isFormData ? body : JSON.stringify(toWireModel(body)),
          signal: combinedSignal,
        });
        const payload = response.status === 204 ? undefined : await response.json().catch(() => undefined);
        if (!response.ok) throw normalizeApiError(payload, response.status);
        if (response.status !== 204 && payload === undefined) {
          throw new AppError({ code: 'INVALID_RESPONSE', message: '서버 응답 형식이 올바르지 않습니다.', status: response.status });
        }
        return payload;
      } catch (error) {
        if (error instanceof AppError) throw error;
        if (error?.name === 'AbortError') {
          const timedOut = timeoutController.signal.aborted && !signal?.aborted;
          throw new AppError({
            code: timedOut ? 'AI_PROCESSING_TIMEOUT' : 'REQUEST_ABORTED',
            message: timedOut ? '처리 시간이 초과되었습니다. 다시 시도해 주세요.' : '요청이 취소되었습니다.',
            retryable: timedOut,
            cause: error,
          });
        }
        throw new AppError({ code: 'NETWORK_ERROR', message: '서버에 연결할 수 없습니다.', retryable: true, cause: error });
      } finally {
        clearTimeout(timeoutId);
      }
    },
  };
}
