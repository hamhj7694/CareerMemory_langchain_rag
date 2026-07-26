import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// AI 답변 전용 Markdown 렌더러다.
// 사용자 입력은 이 컴포넌트를 거치지 않고 일반 텍스트로 표시한다.
export function MarkdownMessage({ content }) {
  return (
    <div className="v2-message__markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          // 외부 링크가 현재 Career Memory 화면을 덮어쓰지 않도록 새 탭에서 연다.
          a: ({ children, ...properties }) => (
            <a {...properties} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
          // 모델 답변의 이미지 URL을 자동으로 불러오면 사용자 추적에 쓰일 수 있다.
          // 이미지 문법은 네트워크 요청 대신 대체 텍스트만 표시한다.
          img: ({ alt }) => <span>{alt || '이미지'}</span>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
