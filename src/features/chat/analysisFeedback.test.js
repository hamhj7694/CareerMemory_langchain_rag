import { describe, expect, it } from 'vitest';
import { conversationAnalysisNotice } from './analysisFeedback.js';

describe('conversationAnalysisNotice', () => {
  it('distinguishes a failed extraction from an empty successful result', () => {
    expect(conversationAnalysisNotice({ experience_count: 0, job_count: 0, failures: [] }))
      .toContain('찾지 못했어요');
    expect(conversationAnalysisNotice({
      experience_count: 0,
      job_count: 0,
      failures: [{ stage: 'analyze_experiences', label: '경험 분석', code: 'invalid_output' }],
    })).toBe('경험 분석 단계에서 오류가 발생했어요. AI가 반환한 초안을 검증하지 못했어요. 프로젝트별로 나눠 다시 시도해 주세요.');
  });

  it('keeps successful counts visible when another stage fails', () => {
    expect(conversationAnalysisNotice({
      experience_count: 2,
      job_count: 0,
      failures: [{ label: '채용공고 분석', code: 'provider_limit' }],
    })).toContain('경험 초안 2개를 분석했어요. 채용공고 분석 단계에서 오류가 발생했어요.');
  });
});
