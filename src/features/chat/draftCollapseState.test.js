import { beforeEach, describe, expect, it } from 'vitest';
import {
  readDraftCollapseState,
  resetDraftCollapseMemoryForTests,
  writeDraftCollapseState,
} from './draftCollapseState.js';

function createStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
}

describe('chat draft collapse state', () => {
  beforeEach(() => resetDraftCollapseMemoryForTests());

  it('restores the latest collapsed and expanded values from storage', () => {
    const storage = createStorage();

    writeDraftCollapseState('proposal:domain:work', true, storage);
    resetDraftCollapseMemoryForTests();
    expect(readDraftCollapseState('proposal:domain:work', false, storage)).toBe(true);

    writeDraftCollapseState('proposal:domain:work', false, storage);
    resetDraftCollapseMemoryForTests();
    expect(readDraftCollapseState('proposal:domain:work', true, storage)).toBe(false);
  });

  it('falls back safely when storage is unavailable', () => {
    const blockedStorage = {
      getItem: () => { throw new Error('blocked'); },
      setItem: () => { throw new Error('blocked'); },
    };

    expect(readDraftCollapseState('proposal:project:draft', true, blockedStorage)).toBe(true);
    writeDraftCollapseState('proposal:project:draft', false, blockedStorage);
    expect(readDraftCollapseState('proposal:project:draft', true, blockedStorage)).toBe(false);
  });
});

