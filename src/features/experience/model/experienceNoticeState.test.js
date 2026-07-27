import { describe, expect, it } from 'vitest';
import {
  createExperienceNoticeState,
  markExperienceNoticeRead,
  reconcileExperienceNoticeState,
} from './experienceNoticeState.js';

describe('experience new-card notice state', () => {
  it('treats the first loaded list as an existing baseline', () => {
    expect(reconcileExperienceNoticeState(createExperienceNoticeState(), ['EXP-1', 'EXP-2'])).toEqual({
      initialized: true,
      knownIds: ['EXP-1', 'EXP-2'],
      unreadIds: [],
    });
  });

  it('marks only IDs added after the baseline as unread', () => {
    const baseline = reconcileExperienceNoticeState(createExperienceNoticeState(), ['EXP-1']);
    const updated = reconcileExperienceNoticeState(baseline, ['EXP-1', 'EXP-2']);

    expect(updated.unreadIds).toEqual(['EXP-2']);
  });

  it('keeps an unread card across refreshes until the user reads it', () => {
    const state = {
      initialized: true,
      knownIds: ['EXP-1', 'EXP-2'],
      unreadIds: ['EXP-2'],
    };

    expect(reconcileExperienceNoticeState(state, ['EXP-1', 'EXP-2']).unreadIds).toEqual(['EXP-2']);
    expect(markExperienceNoticeRead(state, 'EXP-2').unreadIds).toEqual([]);
  });

  it('removes deleted experience IDs from the notice state', () => {
    const state = {
      initialized: true,
      knownIds: ['EXP-1', 'EXP-2'],
      unreadIds: ['EXP-2'],
    };

    expect(reconcileExperienceNoticeState(state, ['EXP-1'])).toEqual({
      initialized: true,
      knownIds: ['EXP-1'],
      unreadIds: [],
    });
  });
});
