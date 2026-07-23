import { afterEach, describe, expect, it } from 'vitest';
import { clearMockHandlers, registerMockHandler } from './adapters/mockAdapter.js';
import { coverLetterApi } from './coverLetterApi.js';
import { experienceApi } from './experienceApi.js';
import { jobApi } from './jobApi.js';

afterEach(() => clearMockHandlers());

function capture(method, path, response = {}) {
  let request;
  registerMockHandler(method, path, (value) => { request = value; return response; });
  return () => request;
}

describe('domain API request contracts', () => {
  it('sends commit project experiences and save metadata', async () => {
    const read = capture('POST', '/api/experiences/commit', { experience_ids: [] });
    await experienceApi.commit({ rawId: 'RAW-1', draftId: 'DRF-1', saveMode: 'new_project', domainName: '직장', project: { name: 'A', experiences: [{ title: '성과' }] } });
    expect(read().body).toMatchObject({ saveMode: 'new_project', project: { experiences: [{ title: '성과' }] } });
    expect(read().body.clientRequestId).toBeTruthy();
  });

  it('sends versioned experience changes', async () => {
    const read = capture('PATCH', '/api/experiences/EXP-1', { id: 'EXP-1' });
    await experienceApi.update('EXP-1', { version: 3, changes: { title: '수정' } });
    expect(read().body).toMatchObject({ version: 3, changes: { title: '수정' } });
    expect(read().body.clientRequestId).toBeTruthy();
  });

  it('uses message and client id for experience chat', async () => {
    const read = capture('POST', '/api/chat/experiences', { answer: '' });
    await experienceApi.chat('질문');
    expect(read().body.message).toBe('질문');
    expect(read().body.clientRequestId).toBeTruthy();
    expect(read().body.question).toBeUndefined();
  });

  it('sends match and cover-letter mutation metadata', async () => {
    const match = capture('POST', '/api/jobs/JOB-1/match', { matches: [], failures: [] });
    await jobApi.match('JOB-1');
    expect(match().body).toMatchObject({ requirementIds: [] });
    expect(match().body.clientRequestId).toBeTruthy();

    const revise = capture('POST', '/api/cover-letters/revise', { document_id: 'DOC-1' });
    await coverLetterApi.revise({ documentId: 'DOC-1', baseVersion: 2, revisionType: 'shorten', content: '본문' });
    expect(revise().body).toMatchObject({ baseVersion: 2, revisionType: 'shorten' });
    expect(revise().body.clientRequestId).toBeTruthy();
  });
});
