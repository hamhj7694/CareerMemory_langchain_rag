import { useEffect, useId, useRef, useState } from 'react';
import { v2ChatApi } from '../../api/v2ChatApi.js';
import { EVIDENCE_FILE_LIMITS, evidenceFileKey, evidenceFileStatusLabel, mergeEvidenceFileSelections } from '../evidence/model/evidenceFileSelection.js';
import { CHAT_QUICK_ACTIONS, GENERAL_CHAT_MODE } from './chatQuickActions.js';

export function ChatComposer({ text, onTextChange, files, onFilesChange, onSubmit, busy, showQuickActions = false, selectedMode = 'general', onModeChange }) {
  const inputId = useId();
  const fileInput = useRef(null);
  const textInput = useRef(null);
  const previousMode = useRef(selectedMode);
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

  const activeMode = CHAT_QUICK_ACTIONS.find((action) => action.id === selectedMode)
    || GENERAL_CHAT_MODE;

  useEffect(() => {
    if (previousMode.current === selectedMode) return undefined;
    previousMode.current = selectedMode;
    const frame = window.requestAnimationFrame(() => textInput.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [selectedMode]);

  return <div className="v2-composer-shell">
    {(selectedMode !== GENERAL_CHAT_MODE.id || showQuickActions) && <div className="v2-chat-mode-toolbar">
      {selectedMode !== GENERAL_CHAT_MODE.id && <div className="v2-chat-mode-indicator" aria-label={`현재 질문 모드: ${activeMode.title}`}>
        <span>질문 모드</span>
        <strong>{activeMode.title}</strong>
        <button
          type="button"
          onClick={() => onModeChange?.(GENERAL_CHAT_MODE.id)}
          aria-label="일반 대화 모드로 돌아가기"
          title="모드 해제"
        >×</button>
      </div>}
      {showQuickActions && <nav className="v2-chat-quick-actions" aria-label="질문 모드 선택">
        {CHAT_QUICK_ACTIONS.map((action) => <button
          type="button"
          key={action.id}
          className={selectedMode === action.id ? 'is-active' : ''}
          aria-pressed={selectedMode === action.id}
          disabled={busy}
          onClick={() => onModeChange?.(action.id)}
        >
          {action.title}
        </button>)}
      </nav>}
    </div>}
    <div className="v2-composer">
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
      ref={textInput}
      id={inputId}
      rows="2"
      value={text}
      onChange={(event) => onTextChange(event.target.value)}
      onKeyDown={handleKeyDown}
      placeholder={activeMode.placeholder}
    />
    <div className="v2-composer__tools">
      <div className="v2-composer__actions">
        <input ref={fileInput} className="sr-only" type="file" multiple accept=".pdf,.txt,.png,.jpg,.jpeg,.webp,application/pdf,text/plain,image/png,image/jpeg,image/webp" onChange={addFiles} />
        <button type="button" className="v2-icon-button" onClick={() => fileInput.current?.click()} disabled={busy || checkingFiles || files.length >= EVIDENCE_FILE_LIMITS.maxCount} aria-label="파일 첨부">{checkingFiles ? '…' : '＋'}</button>
        <button type="button" className="v2-send-button" onClick={onSubmit} disabled={busy || checkingFiles || (!text.trim() && files.length === 0)} aria-label="메시지 보내기">{busy || checkingFiles ? '…' : '↑'}</button>
      </div>
    </div>
    <small className="v2-composer__hint">Enter로 전송 · PDF/TXT/이미지 최대 5개 · 파일당 25MiB·전체 100MiB</small>
    </div>
  </div>;
}
