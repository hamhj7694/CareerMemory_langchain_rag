import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { JobPostingSourcePanel } from './JobPostingSourcePanel.jsx';

const job = {
  postingTitle: '서비스 기획자 채용',
  companyName: '커리어 메모리',
  roleName: '서비스 기획자',
  sourceUrl: 'https://example.com/jobs/1',
  postingContent: '데이터를 분석하고 개선 과제를 도출합니다.\n유관 부서와 협업합니다.',
};

describe('JobPostingSourcePanel', () => {
  it('keeps the original posting collapsed by default', () => {
    const html = renderToStaticMarkup(
      <JobPostingSourcePanel job={job} expanded={false} onToggle={() => {}} />,
    );

    expect(html).toContain('입력한 공고 원본');
    expect(html).toContain('원본 보기');
    expect(html).not.toContain('채용공고 원문</h3>');
  });

  it('shows every submitted source field when expanded', () => {
    const html = renderToStaticMarkup(
      <JobPostingSourcePanel job={job} expanded onToggle={() => {}} />,
    );

    expect(html).toContain('서비스 기획자 채용');
    expect(html).toContain('커리어 메모리');
    expect(html).toContain('https://example.com/jobs/1');
    expect(html).toContain('유관 부서와 협업합니다.');
    expect(html).toContain('원본 접기');
  });
});
