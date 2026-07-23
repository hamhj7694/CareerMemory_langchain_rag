export function createClientRequestId() {
  return globalThis.crypto?.randomUUID?.() ?? `req-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
