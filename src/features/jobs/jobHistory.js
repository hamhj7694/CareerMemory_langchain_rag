import { getUserStorageKey } from '../../auth/authSession.js';

const STORAGE_KEY = 'career-memory.job-analysis-history.v1';

const read = () => {
  try {
    const userKey = getUserStorageKey(STORAGE_KEY);
    const storedValue = window.localStorage.getItem(userKey);
    const value = JSON.parse(storedValue || '[]');
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
};

const write = (items) => {
  try { window.localStorage.setItem(getUserStorageKey(STORAGE_KEY), JSON.stringify(items)); } catch { /* storage can be unavailable */ }
  return items;
};

export const jobHistory = {
  list() { return read().sort((a, b) => new Date(b.analyzedAt) - new Date(a.analyzedAt)); },
  save(job, input = {}) {
    const jobId = job.jobId || job.id;
    const record = {
      ...job,
      jobId,
      companyName: job.companyName || input.companyName || '',
      roleName: job.roleName || input.roleName || '',
      postingTitle: job.postingTitle || input.postingTitle || '',
      sourceUrl: job.sourceUrl || input.sourceUrl || '',
      postingContent: job.postingContent || input.postingContent || '',
      analyzedAt: job.analyzedAt || new Date().toISOString(),
    };
    const next = [record, ...read().filter((item) => item.jobId !== jobId)];
    write(next);
    return record;
  },
  remove(jobId) { return write(read().filter((item) => item.jobId !== jobId)); },
};
