import { describe, expect, it, vi } from 'vitest';
import { resolveJobAnalysisAttempt } from './jobAnalysisAttempt.js';

const input = {
  companyName: '넥스트랩',
  roleName: '서비스 기획자',
  postingTitle: '서비스 기획자 채용',
  sourceUrl: 'https://example.com/jobs/123',
  postingContent: '사용자 데이터를 분석하고 개선 과제를 도출한 경험',
};

describe('공고 분석 재시도 식별자', () => {
  it('입력 내용이 같으면 동일한 요청 ID를 재사용한다', () => {
    const idFactory = vi.fn(() => 'request-1');
    const first = resolveJobAnalysisAttempt(null, input, idFactory);
    const retry = resolveJobAnalysisAttempt(first, { ...input }, idFactory);

    expect(retry).toBe(first);
    expect(idFactory).toHaveBeenCalledTimes(1);
  });

  it('입력 내용이 바뀌면 새로운 요청 ID를 만든다', () => {
    const idFactory = vi.fn()
      .mockReturnValueOnce('request-1')
      .mockReturnValueOnce('request-2');
    const first = resolveJobAnalysisAttempt(null, input, idFactory);
    const changed = resolveJobAnalysisAttempt(
      first,
      { ...input, postingContent: `${input.postingContent}\n협업 경험` },
      idFactory,
    );

    expect(changed.clientRequestId).toBe('request-2');
    expect(changed.fingerprint).not.toBe(first.fingerprint);
  });
});
