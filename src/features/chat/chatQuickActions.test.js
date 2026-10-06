import { describe, expect, it } from 'vitest';
import { CHAT_QUICK_ACTIONS, GENERAL_CHAT_MODE } from './chatQuickActions.js';

describe('chat question modes', () => {
  it('provides the four selectable modes without injecting prompt text', () => {
    expect(CHAT_QUICK_ACTIONS.map((action) => action.id)).toEqual([
      'experience',
      'job',
      'document_feedback',
      'interview',
    ]);
    expect(CHAT_QUICK_ACTIONS.every((action) => action.placeholder && !action.prompt)).toBe(true);
    expect(GENERAL_CHAT_MODE.id).toBe('general');
  });
});
