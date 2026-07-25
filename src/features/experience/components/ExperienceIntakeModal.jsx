import { useState } from 'react';

export function ExperienceIntakeModal({ open, onClose, onAnalyze, busy = false }) {
  const [content, setContent] = useState('');
  const [files, setFiles] = useState([]);

  if (!open) return null;

  const canAnalyze = Boolean(content.trim() || files.length > 0);
  const submit = async (event) => {
    event.preventDefault();
    if (!canAnalyze || busy) return;
    await onAnalyze({ content: content.trim(), files });
  };

  return (
    <div className="mv2-modal-backdrop" role="presentation">
      <section className="mv2-modal mv2-experience-intake" role="dialog" aria-modal="true" aria-labelledby="experience-intake-title">
        <header>
          <div>
            <span className="mv2-kicker">EXPERIENCE AI</span>
            <h2 id="experience-intake-title">경험정리 AI</h2>
            <p>경험을 자유롭게 적거나 파일을 넣으면 기존 경험 구조로 정리합니다.</p>
          </div>
          <button type="button" className="mv2-icon-button" onClick={onClose} aria-label="닫기" disabled={busy}>×</button>
        </header>
        <form onSubmit={submit}>
          <div className="mv2-experience-intake__body">
            <label>
              경험 내용
              <textarea value={content} onChange={(event) => setContent(event.target.value)} rows="9" placeholder="프로젝트, 업무, 상황, 행동, 결과를 자유롭게 적어 주세요." disabled={busy} />
            </label>
            <label className="mv2-file-picker">
              <span>파일 근거 추가</span>
              <input type="file" multiple onChange={(event) => setFiles(Array.from(event.target.files || []))} disabled={busy} />
              <small>PDF·TXT 등 여러 파일을 한 번에 선택할 수 있습니다.</small>
            </label>
            {files.length > 0 && <ul className="mv2-experience-intake__files">{files.map((file) => <li key={`${file.name}-${file.lastModified}`}>{file.name}</li>)}</ul>}
            <p className="mv2-experience-intake__notice">현재는 목데이터 분석으로 초안을 만들며, AI 엔진 연결 후 실제 분석 결과로 대체됩니다.</p>
          </div>
          <footer>
            <button type="button" className="mv2-button mv2-button--secondary" onClick={onClose} disabled={busy}>취소</button>
            <button type="submit" className="mv2-button" disabled={!canAnalyze || busy}>{busy ? '정리 중…' : '경험 정리하기'}</button>
          </footer>
        </form>
      </section>
    </div>
  );
}
