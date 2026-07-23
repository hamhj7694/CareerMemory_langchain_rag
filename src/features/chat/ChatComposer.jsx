import { useId, useRef } from 'react';

const ACCEPTED_TYPES = ['application/pdf', 'text/plain'];
const MAX_FILE_COUNT = 5;
const MAX_FILE_BYTES = 25 * 1024 * 1024;
const MAX_TOTAL_BYTES = 100 * 1024 * 1024;

const fileKey = (file) => `${file.name}-${file.size}-${file.lastModified}`;

export function ChatComposer({ mode, onModeChange, text, onTextChange, files, onFilesChange, onSubmit, busy }) {
  const inputId = useId();
  const fileInput = useRef(null);
  const addFiles = (event) => {
    const incoming = [...(event.target.files ?? [])];
    const valid = incoming.filter((file) => ACCEPTED_TYPES.includes(file.type) && file.size <= MAX_FILE_BYTES);
    const unique = [...files, ...valid].filter((file, index, all) => all.findIndex((item) => fileKey(item) === fileKey(file)) === index);
    const next = [];
    let bytes = 0;
    for (const file of unique.slice(0, MAX_FILE_COUNT)) {
      if (bytes + file.size <= MAX_TOTAL_BYTES) {
        next.push(file);
        bytes += file.size;
      }
    }
    onFilesChange(next);
    event.target.value = '';
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      onSubmit();
    }
  };

  return <div className="v2-composer">
    {files.length > 0 && <ul className="v2-attachments" aria-label="첨부 파일">
      {files.map((file) => <li key={fileKey(file)}>
        <span aria-hidden="true">▧</span>
        <span><strong>{file.name}</strong><small>{(file.size / 1024 / 1024).toFixed(1)}MiB</small></span>
        <button type="button" onClick={() => onFilesChange(files.filter((item) => item !== file))} aria-label={`${file.name} 제거`}>×</button>
      </li>)}
    </ul>}
    <label className="sr-only" htmlFor={inputId}>Career Memory와 대화하기</label>
    <textarea
      id={inputId}
      rows="2"
      value={text}
      onChange={(event) => onTextChange(event.target.value)}
      onKeyDown={handleKeyDown}
      placeholder={mode === 'experience' ? '정리하고 싶은 경험을 자유롭게 적어 주세요.' : mode === 'job' ? '채용공고 원문을 붙여 넣어 주세요.' : '경험을 이야기하거나 커리어에 관해 질문해 보세요.'}
    />
    <div className="v2-composer__tools">
      <div className="v2-mode-switch" aria-label="대화 유형">
        {[
          ['auto', '자동'],
          ['experience', '경험 정리'],
          ['job', '공고 분석'],
        ].map(([value, label]) => <button type="button" key={value} aria-pressed={mode === value} onClick={() => onModeChange(value)}>{label}</button>)}
      </div>
      <div className="v2-composer__actions">
        <input ref={fileInput} className="sr-only" type="file" multiple accept=".pdf,.txt,application/pdf,text/plain" onChange={addFiles} />
        <button type="button" className="v2-icon-button" onClick={() => fileInput.current?.click()} disabled={busy || files.length >= MAX_FILE_COUNT} aria-label="파일 첨부">＋</button>
        <button type="button" className="v2-send-button" onClick={onSubmit} disabled={busy || (!text.trim() && files.length === 0)} aria-label="메시지 보내기">{busy ? '…' : '↑'}</button>
      </div>
    </div>
    <small className="v2-composer__hint">Enter로 전송 · PDF/TXT 최대 5개 · 파일당 25MiB</small>
  </div>;
}
