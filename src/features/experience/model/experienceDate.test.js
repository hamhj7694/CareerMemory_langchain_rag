import { describe, expect, it } from 'vitest';
import { formatExperienceSavedDateTime } from './experienceDate.js';

describe('formatExperienceSavedDateTime', () => {
  it('저장 날짜에 시와 분을 함께 표시한다', () => {
    const formatted = formatExperienceSavedDateTime(new Date(2026, 6, 27, 14, 5));

    expect(formatted).toMatch(/2026.*7.*27/);
    expect(formatted).toMatch(/2:05|14:05/);
  });

  it('시간이 없는 과거 날짜 값에는 임의의 시간을 붙이지 않는다', () => {
    const formatted = formatExperienceSavedDateTime('2026-07-27');

    expect(formatted).toMatch(/2026.*7.*27/);
    expect(formatted).not.toMatch(/:/);
  });

  it('비어 있거나 잘못된 값은 표시하지 않는다', () => {
    expect(formatExperienceSavedDateTime('')).toBe('');
    expect(formatExperienceSavedDateTime('not-a-date')).toBe('');
  });
});
