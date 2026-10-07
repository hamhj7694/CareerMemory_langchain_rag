import { useEffect, useId, useRef, useState } from 'react';
import { v2ChatApi } from '../../api/v2ChatApi.js';
import { filesFromDrop, filesFromPaste, hasFilePayload } from '../evidence/model/attachmentIngress.js';
import { CHAT_ATTACHMENT_LIMITS, EVIDENCE_FILE_ACCEPT, evidenceFileKey, evidenceFileStatusLabel, mergeEvidenceFileSelections } from '../evidence/model/evidenceFileSelection.js';
import { CHAT_QUICK_ACTIONS, GENERAL_CHAT_MODE } from './chatQuickActions.js';

export function ChatComposer({ text, onTextChange, files, onFilesChange, onSubmit, busy, showQuickActions = false, selectedMode = 'general', onModeChange }) {
  const inputId = useId();
  const fileInput = useRef(null);
  const textInput = useRef(null);
  const previousMode = useRef(selectedMode);
  const dragDepth = useRef(0);
  const [fileError, setFileError] = useState('');
  const [fileNotice, setFileNotice] = useState('');
  const [checkingFiles, setCheckingFiles] = useState(false);
  const [draggingFiles, setDraggingFiles] = useState(false);
  const applyAttachmentResult = (selection, attachment) => ({
    ...selection,
    existingAttachmentId: attachment.id,
    serverAttachmentId: attachment.id,
    processingStatus: attachment.status,
    processingJobStatus: attachment.processing_job_status,
    parseError: attachment.parse_error || '',
    qualityScore: attachment.quality_score,
    warnings: attachment.warnings || [],
    uploadedForComposer: !selection.existingAttachmentId && !attachment.reused,
  });
  const addIncomingFiles = async (incoming) => {
    if (!incoming.length) return;
    if (busy || checkingFiles) {
      setFileError('현재 첨부파일을 처리하고 있습니다. 잠시 후 다시 시도해 주세요.');
      return;
    }
    let stagedFiles = files;
    setCheckingFiles(true); setFileError(''); setFileNotice('');
    try {
      const result = await mergeEvidenceFileSelections(
        files,
        incoming,
        v2ChatApi.preflightAttachments,
        CHAT_ATTACHMENT_LIMITS,
      );
      const pending = result.files.filter((file) => !file.processingStatus);
      stagedFiles = result.files.map((file) => (
        pending.includes(file) ? { ...file, processingStatus: 'uploading' } : file
      ));
      onFilesChange(stagedFiles);
      setFileError(result.error);
      setFileNotice(result.notice);
      if (pending.length) {
        const uploaded = await v2ChatApi.uploadAttachments(pending, { throwOnFailure: false });
        let uploadIndex = 0;
        const completed = result.files.map((file) => {
          if (!pending.includes(file)) return file;
          const attachment = uploaded[uploadIndex];
          uploadIndex += 1;
          return applyAttachmentResult(file, attachment);
        });
        onFilesChange(completed);
        const failed = completed.filter((file) => ['failed', 'unsupported'].includes(file.processingStatus));
        if (failed.length) setFileError(failed.map((file) => `${file.name}: ${file.parseError || evidenceFileStatusLabel(file)}`).join(' · '));
      }
    } catch (reason) {
      setFileError(reason?.message || '파일의 중복 여부를 확인하지 못했습니다.');
      onFilesChange(stagedFiles.map((file) => (
        file.processingStatus === 'uploading'
          ? { ...file, processingStatus: 'upload_failed', parseError: reason?.message || '업로드에 실패했습니다.' }
          : file
      )));
    } finally {
      setCheckingFiles(false);
    }
  };
  const addFiles = (event) => {
    const incoming = [...(event.target.files ?? [])];
    event.target.value = '';
    addIncomingFiles(incoming);
  };

  const handlePaste = (event) => {
    const incoming = filesFromPaste(event.clipboardData);
    if (!incoming.length) return;
    if (!event.clipboardData.getData('text/plain')) event.preventDefault();
    addIncomingFiles(incoming);
  };

  const handleDragEnter = (event) => {
    if (!hasFilePayload(event.dataTransfer)) return;
    event.preventDefault();
    dragDepth.current += 1;
    setDraggingFiles(true);
  };

  const handleDragLeave = (event) => {
    if (!hasFilePayload(event.dataTransfer)) return;
    event.preventDefault();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDraggingFiles(false);
  };

  const handleDrop = (event) => {
    if (!hasFilePayload(event.dataTransfer)) return;
    event.preventDefault();
    dragDepth.current = 0;
    setDraggingFiles(false);
    addIncomingFiles(filesFromDrop(event.dataTransfer));
  };

  const attachmentIcon = (file) => {
    if (file.type?.startsWith('image/')) return '▧';
    if (file.type?.startsWith('audio/')) return '♪';
    if (file.type?.startsWith('video/')) return '▶';
    if (/\.(docx?|hwpx?)$/i.test(file.name || '')) return '▤';
    if (/\.(pptx?)$/i.test(file.name || '')) return '▥';
    return '▱';
  };

  const retryFile = async (file) => {
    if (busy || checkingFiles) return;
    setCheckingFiles(true); setFileError('');
    onFilesChange(files.map((item) => (
      item === file ? { ...item, processingStatus: 'processing', parseError: '' } : item
    )));
    try {
      const attachment = file.serverAttachmentId || file.existingAttachmentId
        ? await v2ChatApi.processAttachment(file.serverAttachmentId || file.existingAttachmentId)
        : (await v2ChatApi.uploadAttachments([file], { throwOnFailure: false }))[0];
      const next = files.map((item) => (
        item === file ? applyAttachmentResult(item, attachment) : item
      ));
      onFilesChange(next);
      if (['failed', 'unsupported'].includes(attachment.status)) {
        setFileError(`${file.name}: ${attachment.parse_error || '다시 처리하지 못했습니다.'}`);
      }
    } catch (reason) {
      onFilesChange(files.map((item) => (
        item === file
          ? { ...item, processingStatus: 'upload_failed', parseError: reason?.message || '다시 처리하지 못했습니다.' }
          : item
      )));
      setFileError(reason?.message || '첨부 파일을 다시 처리하지 못했습니다.');
    } finally {
      setCheckingFiles(false);
    }
  };

  const removeFile = async (file) => {
    onFilesChange(files.filter((item) => item !== file));
    if (file.uploadedForComposer && file.serverAttachmentId) {
      try {
        await v2ChatApi.deleteAttachment(file.serverAttachmentId);
      } catch (reason) {
        setFileError(reason?.message || '서버에 임시 저장된 첨부 원본을 정리하지 못했습니다.');
      }
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      const unavailable = files.find((file) => !['ready', 'partial'].includes(file.processingStatus));
      if (unavailable) {
        setFileError(`${unavailable.name}: 첨부 처리가 끝나거나 재시도에 성공한 뒤 전송할 수 있습니다.`);
        return;
      }
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
    <div
      className={`v2-composer ${draggingFiles ? 'is-file-dragging' : ''}`}
      onDragEnter={handleDragEnter}
      onDragOver={(event) => { if (hasFilePayload(event.dataTransfer)) event.preventDefault(); }}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
    {draggingFiles && <div className="v2-composer__drop-target" role="status">여기에 놓아 첨부하세요</div>}
    {files.length > 0 && <ul className="v2-attachments" aria-label="첨부 파일">
      {files.map((file) => <li key={evidenceFileKey(file)} className={`is-${file.processingStatus || 'selected'}`}>
        <span className="v2-attachments__icon" aria-hidden="true">{attachmentIcon(file)}</span>
        <span><strong>{file.name}</strong><small>{(file.size / 1024 / 1024).toFixed(1)}MiB · {evidenceFileStatusLabel(file)}</small>{file.parseError && <em title={file.parseError}>{file.parseError}</em>}</span>
        <span className="v2-attachments__controls">
          {['failed', 'unsupported', 'upload_failed'].includes(file.processingStatus) && <button type="button" className="v2-attachments__retry" onClick={() => retryFile(file)}>재시도</button>}
          <button type="button" onClick={() => removeFile(file)} aria-label={`${file.name} 제거`}>×</button>
        </span>
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
      onPaste={handlePaste}
      placeholder={activeMode.placeholder}
    />
    <div className="v2-composer__tools">
      <div className="v2-composer__actions">
        <input ref={fileInput} className="sr-only" type="file" multiple accept={EVIDENCE_FILE_ACCEPT} onChange={addFiles} />
        <button type="button" className="v2-icon-button" onClick={() => fileInput.current?.click()} disabled={busy || checkingFiles || files.length >= CHAT_ATTACHMENT_LIMITS.maxCount} aria-label="파일 첨부">{checkingFiles ? '…' : '＋'}</button>
        <button type="button" className="v2-send-button" onClick={onSubmit} disabled={busy || checkingFiles || files.some((file) => !['ready', 'partial'].includes(file.processingStatus)) || (!text.trim() && files.length === 0)} aria-label="메시지 보내기">{busy || checkingFiles ? '…' : '↑'}</button>
      </div>
    </div>
    <small className="v2-composer__hint">Enter로 전송 · 붙여넣기/드롭 지원 · 문서·이미지·음성·영상 최대 10개 · 파일당 25MiB·전체 100MiB</small>
    </div>
  </div>;
}
