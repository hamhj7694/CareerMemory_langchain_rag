const STORAGE_PREFIX = 'career-memory:chat-draft-collapse:v1:';
const memoryState = new Map();

function storageKey(key) {
  return `${STORAGE_PREFIX}${key}`;
}

function browserStorage() {
  try {
    return globalThis.localStorage;
  } catch {
    return null;
  }
}

export function readDraftCollapseState(key, fallback = false, storage = browserStorage()) {
  if (!key) return fallback;
  if (memoryState.has(key)) return memoryState.get(key);
  try {
    const stored = storage?.getItem(storageKey(key));
    if (stored === 'collapsed') return true;
    if (stored === 'expanded') return false;
  } catch {
    // 저장소가 차단된 환경에서는 현재 화면의 메모리 상태만 사용한다.
  }
  return fallback;
}

export function writeDraftCollapseState(key, collapsed, storage = browserStorage()) {
  if (!key) return;
  const next = Boolean(collapsed);
  memoryState.set(key, next);
  try {
    storage?.setItem(storageKey(key), next ? 'collapsed' : 'expanded');
  } catch {
    // localStorage 용량·보안 오류가 나도 접기/펼치기 자체는 계속 동작해야 한다.
  }
}

export function resetDraftCollapseMemoryForTests() {
  memoryState.clear();
}

