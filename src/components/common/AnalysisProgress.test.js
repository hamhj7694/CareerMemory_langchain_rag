import { describe, expect, it } from 'vitest';
import { getEstimatedProgress } from './analysisProgressModel.js';

describe('AI 분석 진행률 표시', () => {
  it('처리 시간이 늘어나면 진행률도 증가한다', () => {
    expect(getEstimatedProgress(0)).toBeLessThan(getEstimatedProgress(10));
    expect(getEstimatedProgress(10)).toBeLessThan(getEstimatedProgress(30));
  });

  it('서버 응답 전에는 완료로 오해하지 않도록 92%를 넘지 않는다', () => {
    expect(getEstimatedProgress(300)).toBe(92);
  });
});
