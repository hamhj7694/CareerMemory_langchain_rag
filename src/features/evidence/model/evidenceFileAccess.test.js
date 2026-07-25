import { describe, expect, it } from 'vitest';
import { evidenceBlob } from './evidenceFileAccess.js';

describe('evidence file access', () => {
  it('opens local draft file bytes without requiring a persisted source endpoint', async () => {
    const bytes = new TextEncoder().encode('초안 파일 원문');
    const blob = await evidenceBlob({
      raw_bytes: bytes.buffer,
      mime_type: 'text/plain',
    });

    expect(await blob.text()).toBe('초안 파일 원문');
  });

  it('falls back to a source loader after persistence', async () => {
    const blob = await evidenceBlob(
      { id: 'SRC-1', mimeType: 'text/plain' },
      async () => new Blob(['저장된 원문'], { type: 'text/plain' }),
    );

    expect(await blob.text()).toBe('저장된 원문');
  });
});
