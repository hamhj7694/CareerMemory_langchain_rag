import { apiConfig } from './config.js';
import { createHttpAdapter } from './adapters/httpAdapter.js';
import { createMockAdapter } from './adapters/mockAdapter.js';
import { toScreenModel } from './modelMapper.js';

const adapter = apiConfig.useMock
  ? createMockAdapter({ scenario: apiConfig.mockScenario, latencyMs: apiConfig.mockLatencyMs })
  : createHttpAdapter({ baseUrl: apiConfig.baseUrl, timeoutMs: apiConfig.timeoutMs });

export const apiMode = apiConfig.useMock ? 'mock' : 'http';

export async function apiRequest(request) {
  return toScreenModel(await adapter.request(request));
}
