import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { MarkdownMessage } from './MarkdownMessage.jsx';

describe('AI 답변 Markdown 렌더링', () => {
  it('강조와 목록을 실제 HTML 요소로 변환한다', () => {
    const html = renderToStaticMarkup(
      <MarkdownMessage content={'**중요**\n\n- 첫 번째\n- 두 번째'} />,
    );

    expect(html).toContain('<strong>중요</strong>');
    expect(html).toContain('<ul>');
    expect(html).toContain('<li>첫 번째</li>');
    expect(html).not.toContain('**중요**');
  });

  it('모델이 보낸 HTML과 스크립트를 실행 가능한 요소로 만들지 않는다', () => {
    const html = renderToStaticMarkup(
      <MarkdownMessage content={'<script>alert("위험")</script>\n\n안전한 답변'} />,
    );

    expect(html).not.toContain('<script>');
    expect(html).not.toContain('alert(');
    expect(html).toContain('안전한 답변');
  });

  it('외부 링크에 새 탭 보안 속성을 추가한다', () => {
    const html = renderToStaticMarkup(
      <MarkdownMessage content="[공식 문서](https://example.com)" />,
    );

    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noreferrer"');
  });
});
