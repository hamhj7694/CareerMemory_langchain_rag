import { useId, useRef, useState } from 'react';
import { v2ChatApi } from '../../api/v2ChatApi.js';
import { EVIDENCE_FILE_LIMITS, evidenceFileKey, evidenceFileStatusLabel, mergeEvidenceFileSelections } from '../evidence/model/evidenceFileSelection.js';

export function ChatComposer({ mode, onModeChange, text, onTextChange, files, onFilesChange, onSubmit, busy }) {
  const inputId = useId();
  const fileInput = useRef(null);
  const [fileError, setFileError] = useState('');
  const [fileNotice, setFileNotice] = useState('');
  const [checkingFiles, setCheckingFiles] = useState(false);
  const addFiles = async (event) => {
    const incoming = [...(event.target.files ?? [])];
    event.target.value = '';
    if (!incoming.length) return;
    setCheckingFiles(true); setFileError(''); setFileNotice('');
    try {
      const result = await mergeEvidenceFileSelections(files, incoming, v2ChatApi.preflightAttachments);
      onFilesChange(result.files);
      setFileError(result.error);
      setFileNotice(result.notice);
    } catch (reason) {
      setFileError(reason?.message || '파일의 중복 여부를 확인하지 못했습니다.');
    } finally {
      setCheckingFiles(false);
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      onSubmit();
    }
  };

  return <div className="v2-composer">
    {files.length > 0 && <ul className="v2-attachments" aria-label="첨부 파일">
      {files.map((file) => <li key={evidenceFileKey(file)}>
        <span aria-hidden="true">▧</span>
        <span><strong>{file.name}</strong><small>{(file.size / 1024 / 1024).toFixed(1)}MiB · {evidenceFileStatusLabel(file)}</small></span>
        <button type="button" onClick={() => onFilesChange(files.filter((item) => item !== file))} aria-label={`${file.name} 제거`}>×</button>
      </li>)}
    </ul>}
    {fileError && <p className="v2-composer__error" role="alert">{fileError}</p>}
    {fileNotice && <p className="v2-composer__file-notice" role="status">{fileNotice}</p>}
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
        <input ref={fileInput} className="sr-only" type="file" multiple accept=".pdf,.txt,.png,.jpg,.jpeg,.webp,application/pdf,text/plain,image/png,image/jpeg,image/webp" onChange={addFiles} />
        <button type="button" className="v2-icon-button" onClick={() => fileInput.current?.click()} disabled={busy || checkingFiles || files.length >= EVIDENCE_FILE_LIMITS.maxCount} aria-label="파일 첨부">{checkingFiles ? '…' : '＋'}</button>
        <button type="button" className="v2-send-button" onClick={onSubmit} disabled={busy || checkingFiles || (!text.trim() && files.length === 0)} aria-label="메시지 보내기">{busy || checkingFiles ? '…' : '↑'}</button>
      </div>
    </div>
    <small className="v2-composer__hint">Enter로 전송 · PDF/TXT/이미지 최대 5개 · 전체 14MB</small>
  </div>;
}
