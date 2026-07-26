import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearCurrentUserId,
  setCurrentUserId,
} from '../../auth/authSession.js';
import { jobHistory } from './jobHistory.js';

describe('사용자별 채용공고 분석 기록', () => {
  let values;

  beforeEach(() => {
    values = new Map();
    vi.stubGlobal('window', {
      localStorage: {
        getItem: (key) => values.get(key) ?? null,
        setItem: (key, value) => values.set(key, value),
      },
    });
  });

  afterEach(() => {
    clearCurrentUserId();
    vi.unstubAllGlobals();
  });

  it('서로 다른 계정의 기록을 같은 브라우저에서도 분리한다', () => {
    setCurrentUserId('USER-A');
    jobHistory.save({ jobId: 'JOB-A', companyName: 'A 회사' });

    setCurrentUserId('USER-B');
    expect(jobHistory.list()).toEqual([]);
    jobHistory.save({ jobId: 'JOB-B', companyName: 'B 회사' });

    setCurrentUserId('USER-A');
    expect(jobHistory.list().map((job) => job.jobId)).toEqual(['JOB-A']);
    setCurrentUserId('USER-B');
    expect(jobHistory.list().map((job) => job.jobId)).toEqual(['JOB-B']);
  });
});
