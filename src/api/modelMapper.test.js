import { describe, expect, it } from 'vitest';
import { toScreenModel, toWireModel } from './modelMapper.js';

describe('API model mapper', () => {
  it('recursively maps wire keys to screen-model keys', () => {
    expect(toScreenModel({ raw_id: 'raw-1', source_refs: [{ source_id: 'src-1' }] })).toEqual({
      rawId: 'raw-1',
      sourceRefs: [{ sourceId: 'src-1' }],
    });
  });

  it('recursively maps screen-model keys to wire keys', () => {
    expect(toWireModel({ clientRequestId: 'request-1', selectedExperienceIds: ['exp-1'] })).toEqual({
      client_request_id: 'request-1',
      selected_experience_ids: ['exp-1'],
    });
  });
});
