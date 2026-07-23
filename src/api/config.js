function readPositiveNumber(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export const apiConfig = Object.freeze({
  useMock: import.meta.env.VITE_USE_MOCK !== 'false',
  baseUrl: (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, ''),
  timeoutMs: readPositiveNumber(import.meta.env.VITE_API_TIMEOUT_MS, 30_000),
  mockScenario: import.meta.env.VITE_MOCK_SCENARIO || 'success',
  mockLatencyMs: readPositiveNumber(import.meta.env.VITE_MOCK_LATENCY_MS, 250),
});
