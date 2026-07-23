import { describe, expect, it } from 'vitest';
import { failureRequirementIds } from '../utils/contractFields.js';

describe('failureRequirementIds', () => {
  it('maps camelized PartialFailure itemId for retry', () => {
    expect(failureRequirementIds([{ itemId: 'REQ-1' }, { requirementId: 'REQ-2' }, { id: 'REQ-3' }]))
      .toEqual(['REQ-1', 'REQ-2', 'REQ-3']);
  });
});
