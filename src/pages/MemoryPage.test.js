import { describe, expect, it } from 'vitest';
import { projectCandidateId } from '../utils/contractFields.js';

describe('projectCandidateId', () => {
  it('uses the camelized projectId contract field', () => {
    expect(projectCandidateId({ projectId: 'PROJ-1' })).toBe('PROJ-1');
  });
});
