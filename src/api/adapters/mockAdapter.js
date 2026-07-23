import { AppError, normalizeApiError } from '../AppError.js';
import { getMockScenario, mockRoutes } from '../../mocks/scenarioLoader.js';

const customHandlers = new Map();
const handlerKey = (method, path) => `${method.toUpperCase()} ${path}`;

export function registerMockHandler(method, path, handler) {
  customHandlers.set(handlerKey(method, path), handler);
}

export function clearMockHandlers() {
  customHandlers.clear();
}

export function hasMockHandler(method, path) {
  return customHandlers.has(handlerKey(method, path));
}

function matchRoute(method, path) {
  return mockRoutes.find((route) => route.method === method.toUpperCase() && route.pattern.test(path));
}

function waitForLatency(latencyMs, signal) {
  if (!latencyMs) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      signal?.removeEventListener('abort', abort);
      resolve();
    }, latencyMs);
    function abort() {
      clearTimeout(timeoutId);
      reject(new AppError({ code: 'REQUEST_ABORTED', message: '요청이 취소되었습니다.' }));
    }
    signal?.addEventListener('abort', abort, { once: true });
  });
}

export function createMockAdapter({ latencyMs = 250, scenario } = {}) {
  const fixture = getMockScenario(scenario);

  return {
    async request(request) {
      const method = (request.method || 'GET').toUpperCase();
      if (request.signal?.aborted) {
        throw new AppError({ code: 'REQUEST_ABORTED', message: '요청이 취소되었습니다.' });
      }

      const customHandler = customHandlers.get(handlerKey(method, request.path));
      await waitForLatency(latencyMs, request.signal);
      if (customHandler) return structuredClone(await customHandler(request));

      if (/^\/api\/sources\/[^/]+$/.test(request.path) && method === 'PATCH') {
        return { id: request.path.split('/').pop(), source_type: 'text', text: request.body?.changes?.text || '' };
      }
      if (/^\/api\/sources\/[^/]+$/.test(request.path) && method === 'DELETE') {
        return { source_id: request.path.split('/').pop(), deleted: true };
      }

      const route = matchRoute(method, request.path);
      if (!route || !fixture[route.key]) {
        throw new AppError({
          code: 'MOCK_NOT_IMPLEMENTED',
          message: `Mock 응답이 준비되지 않았습니다: ${method} ${request.path}`,
        });
      }

      const response = structuredClone(fixture[route.key]);
      if (response.status < 200 || response.status >= 300) {
        throw normalizeApiError(response.body, response.status);
      }
      return response.body;
    },
  };
}
