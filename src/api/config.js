function readPositiveNumber(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function readApiBaseUrl(value) {
  const configured = String(value || '').trim();
  const localPreviewApi = /^http:\/\/(?:localhost|127\.0\.0\.1):8000$/i.test(configured);
  if (configured === 'same-origin' || (import.meta.env.PROD && localPreviewApi)) {
    return typeof window === 'undefined' ? 'http://localhost:5173' : window.location.origin;
  }
  return (configured || 'http://localhost:8000').replace(/\/$/, '');
}

export const apiConfig = Object.freeze({
  // 단위 테스트는 외부 서버 없이 항상 고정된 Mock 데이터로 실행한다.
  useMock: import.meta.env.MODE === 'test' || import.meta.env.VITE_USE_MOCK !== 'false',
  baseUrl: readApiBaseUrl(import.meta.env.VITE_API_BASE_URL),
  timeoutMs: readPositiveNumber(import.meta.env.VITE_API_TIMEOUT_MS, 30_000),
  mockScenario: import.meta.env.VITE_MOCK_SCENARIO || 'success',
  mockLatencyMs: readPositiveNumber(import.meta.env.VITE_MOCK_LATENCY_MS, 250),
});
