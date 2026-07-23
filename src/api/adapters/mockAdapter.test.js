import { describe, expect, it } from 'vitest';
import { AppError } from '../AppError.js';
import { createMockAdapter } from './mockAdapter.js';
import { availableMockScenarios, mockRoutes } from '../../mocks/scenarioLoader.js';

const samplePath = (path) => path
  .replace('{experienceId}', 'EXP-001')
  .replace('{jobId}', 'JOB-001')
  .replace('{documentId}', 'DOC-001');

describe('mockAdapter', () => {
  it('exposes the four selectable scenarios', () => {
    expect(availableMockScenarios).toEqual(['success', 'empty', 'partial-success', 'error']);
  });

  it('maps every declared API route to a success fixture', async () => {
    const adapter = createMockAdapter({ scenario: 'success', latencyMs: 0 });
    expect(mockRoutes).toHaveLength(15);
    for (const route of mockRoutes) {
      const result = await adapter.request({ method: route.method, path: samplePath(route.path) });
      expect(result, route.api_id).toBeDefined();
    }
  });

  it('matches dynamic resource paths', async () => {
    const adapter = createMockAdapter({ scenario: 'success', latencyMs: 0 });
    await expect(adapter.request({ method: 'GET', path: '/api/experiences/another-id' }))
      .resolves.toMatchObject({ id: 'EXP-001' });
  });

  it('turns non-2xx fixtures into AppError', async () => {
    const adapter = createMockAdapter({ scenario: 'error', latencyMs: 0 });
    await expect(adapter.request({ method: 'POST', path: '/api/inputs/text' }))
      .rejects.toMatchObject({ name: 'AppError', code: 'VALIDATION_ERROR', status: 422 });
  });

  it('rejects unknown routes consistently', async () => {
    const adapter = createMockAdapter({ scenario: 'success', latencyMs: 0 });
    await expect(adapter.request({ method: 'GET', path: '/api/not-found' }))
      .rejects.toBeInstanceOf(AppError);
  });

  it('supports the manifest partial_success alias', async () => {
    const adapter = createMockAdapter({ scenario: 'partial_success', latencyMs: 0 });
    await expect(adapter.request({ method: 'GET', path: '/api/experiences/tree' })).resolves.toBeDefined();
  });

  it('honors AbortSignal while simulating latency', async () => {
    const controller = new AbortController();
    const adapter = createMockAdapter({ scenario: 'success', latencyMs: 100 });
    const pending = adapter.request({ method: 'GET', path: '/api/experiences/tree', signal: controller.signal });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ code: 'REQUEST_ABORTED' });
  });
});
