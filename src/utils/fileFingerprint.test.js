import { describe, expect, it } from 'vitest';
import { sha256ArrayBuffer } from './fileFingerprint.js';

describe('fileFingerprint', () => {
  it('서버 content_hash 스키마와 같은 SHA-256 64자리 hex를 반환한다', async () => {
    const buffer = new TextEncoder().encode('career-memory').buffer;
    const fingerprint = await sha256ArrayBuffer(buffer);

    expect(fingerprint).toMatch(/^[a-f0-9]{64}$/);
    expect(fingerprint).not.toContain('sha256:');
  });
});
