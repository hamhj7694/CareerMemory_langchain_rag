import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { EvidenceReadonlyContent, EvidenceWorkspace } from '../../features/evidence/components/EvidenceWorkspace.jsx';
import { EVIDENCE_TYPES, toEvidenceViews } from '../../features/evidence/model/evidenceMapper.js';
import './source-manager.css';

export function SourceManagerModal({
  open,
  sources = [],
  busy,
  error,
  notice,
  onClose,
  onSave,
  onUnlink,
  onOpenFile,
  onDownload,
  onAddText,
  onAddFiles,
  onReorganize,
}) {
  const titleId = useId();
  const fileInputRef = useRef(null);
  const [selectedId, setSelectedId] = useState(null);
  const [drafts, setDrafts] = useState({});
  const [addMode, setAddMode] = useState('');
  const [newTextTitle, setNewTextTitle] = useState('');
  const [newText, setNewText] = useState('');
  const [evidenceChanged, setEvidenceChanged] = useState(false);
  const [localAction, setLocalAction] = useState('');
  const evidenceSources = toEvidenceViews(sources);
  const effectiveId = evidenceSources.some((source) => source.id === selectedId) ? selectedId : evidenceSources[0]?.id;
  const selected = evidenceSources.find((source) => source.id === effectiveId);
  const editText = selected ? (drafts[selected.id] ?? selected.text ?? '') : '';
  const hasTextChanges = selected?.sourceType === 'text' && editText !== (selected.text ?? '');
  const pendingTextChanges = evidenceSources.filter((source) => (
    source.sourceType === 'text'
    && Object.hasOwn(drafts, source.id)
    && drafts[source.id] !== (source.text ?? '')
  ));
  const hasAnyTextChanges = pendingTextChanges.length > 0;
  const hasInvalidTextChanges = pendingTextChanges.some((source) => !drafts[source.id]?.trim());
  const canReorganize = (evidenceChanged || hasAnyTextChanges) && !hasInvalidTextChanges && evidenceSources.length > 0 && !busy && !localAction;
  const closeModal = useCallback(() => {
    setSelectedId(null);
    setDrafts({});
    setAddMode('');
    setNewTextTitle('');
    setNewText('');
    setEvidenceChanged(false);
    setLocalAction('');
    onClose();
  }, [onClose]);
  const resetText = () => {
    if (!selected) return;
    setDrafts((current) => {
      const next = { ...current };
      delete next[selected.id];
      return next;
    });
  };
  useEffect(() => {
    if (!open) return undefined;
    const escape = (event) => { if (event.key === 'Escape') closeModal(); };
    document.addEventListener('keydown', escape);
    return () => document.removeEventListener('keydown', escape);
  }, [open, closeModal]);
  if (!open) return null;

  const saveSelectedText = async () => {
    if (!selected || !editText.trim()) return false;
    setLocalAction('saving-text');
    try {
      const saved = await onSave(selected, editText.trim());
      if (saved === false) return false;
      setDrafts((current) => {
        const next = { ...current };
        delete next[selected.id];
        return next;
      });
      setEvidenceChanged(true);
      return true;
    } finally {
      setLocalAction('');
    }
  };

  const unlinkSelected = async () => {
    if (!selected) return;
    setLocalAction('unlinking');
    try {
      const unlinked = await onUnlink(selected);
      if (unlinked !== false) setEvidenceChanged(true);
    } finally {
      setLocalAction('');
    }
  };

  const addTextSource = async () => {
    if (!newText.trim()) return;
    setLocalAction('adding-text');
    try {
      const added = await onAddText({ title: newTextTitle.trim(), text: newText.trim() });
      if (added === false) return;
      setEvidenceChanged(true);
      setAddMode('');
      setNewTextTitle('');
      setNewText('');
      if (added?.addedSourceIds?.[0]) setSelectedId(added.addedSourceIds[0]);
    } finally {
      setLocalAction('');
    }
  };

  const addFileSources = async (files) => {
    if (!files.length) return;
    setLocalAction('adding-files');
    try {
      const added = await onAddFiles(files);
      if (added === false) return;
      setEvidenceChanged(true);
      if (added?.addedSourceIds?.[0]) setSelectedId(added.addedSourceIds[0]);
    } finally {
      setLocalAction('');
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const reorganize = async () => {
    if (!canReorganize) return;
    setLocalAction('reorganizing');
    try {
      for (const source of pendingTextChanges) {
        const text = drafts[source.id]?.trim();
        if (!text) return;
        const saved = await onSave(source, text);
        if (saved === false) return;
      }
      const reorganized = await onReorganize();
      if (reorganized === false) return;
      setEvidenceChanged(false);
      setDrafts({});
    } finally {
      setLocalAction('');
    }
  };

  return <div className="modal-backdrop source-manager-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) closeModal(); }}>
    <section className="source-manager" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <header><div><span className="eyebrow">EVIDENCE</span><h2 id={titleId}>원본 근거 관리</h2></div><button type="button" className="source-close" onClick={closeModal} aria-label="원본 근거 창 닫기">×</button></header>
      <EvidenceWorkspace
        className="source-manager-body"
        sources={evidenceSources}
        selectedId={effectiveId}
        onSelect={setSelectedId}
        mode="manage"
        description={(source) => source.type === EVIDENCE_TYPES.FILE ? '파일 원본을 열거나 다운로드하고 연결된 내용을 확인하세요.' : source.type === EVIDENCE_TYPES.TEXT ? '직접 작성한 텍스트 원본은 수정해 저장할 수 있습니다.' : source.type === EVIDENCE_TYPES.CONVERSATION ? '대화 원문과 연결된 내용을 확인하세요.' : '이전 목데이터에는 원본 파일이나 텍스트가 저장되어 있지 않습니다.'}
        renderActions={(source) => <div className="source-detail-actions">
          <button type="button" className="source-unlink" disabled={busy || Boolean(localAction)} onClick={unlinkSelected}>경험에서 연결 해제</button>
          {source.sourceType === 'text' && <>
            <button type="button" className="ui-button ui-button--secondary" disabled={busy || !hasTextChanges} onClick={resetText}>되돌리기</button>
            <button type="button" className="ui-button" disabled={busy || Boolean(localAction) || !hasTextChanges || !editText.trim()} onClick={saveSelectedText}>{localAction === 'saving-text' ? '저장 중…' : '변경 저장'}</button>
          </>}
        </div>}
        renderContent={(source) => source.sourceType === 'text'
          ? <label>원본 텍스트<textarea className="evidence-original-text source-original-text" rows="6" value={editText} onChange={(event) => setDrafts((current) => ({ ...current, [source.id]: event.target.value }))} /></label>
          : <EvidenceReadonlyContent source={source} onOpenFile={onOpenFile} onDownload={onDownload} />}
        onOpenFile={onOpenFile}
        onDownload={onDownload}
        notice={notice}
        error={error}
        sidebarFooter={<div className="source-nav-actions">
            <strong>근거 추가</strong>
            <div>
              <button type="button" disabled={busy || Boolean(localAction)} onClick={() => setAddMode(addMode === 'text' ? '' : 'text')}>+ 텍스트 작성</button>
              <button type="button" disabled={busy || Boolean(localAction)} onClick={() => fileInputRef.current?.click()}>+ 파일 업로드</button>
              <input ref={fileInputRef} className="sr-only" type="file" accept=".pdf,.txt,text/plain,application/pdf" multiple onChange={(event) => addFileSources([...event.target.files])} />
            </div>
            {addMode === 'text' && <div className="source-add-text">
              <label>근거 이름 <input value={newTextTitle} placeholder="선택 입력" onChange={(event) => setNewTextTitle(event.target.value)} /></label>
              <label>원본 텍스트 <textarea rows="5" value={newText} placeholder="경험의 근거가 되는 원문을 입력해 주세요." onChange={(event) => setNewText(event.target.value)} /></label>
              <div><button type="button" onClick={() => setAddMode('')}>취소</button><button type="button" className="is-primary" disabled={!newText.trim() || Boolean(localAction)} onClick={addTextSource}>{localAction === 'adding-text' ? '추가 중…' : '추가'}</button></div>
            </div>}
            <button
              type="button"
              className="source-reorganize"
              disabled={!canReorganize}
              title={!evidenceSources.length ? '다시 정리할 근거가 없습니다.' : hasInvalidTextChanges ? '비어 있는 텍스트 근거를 되돌리거나 내용을 입력해 주세요.' : !(evidenceChanged || hasAnyTextChanges) ? '근거를 추가·수정하거나 연결 해제하면 활성화됩니다.' : ''}
              onClick={reorganize}
            >
              {localAction === 'reorganizing' ? '새 정리본 생성 중…' : '현재 근거로 상세내용 다시 정리하기'}
            </button>
          </div>}
      />
    </section>
  </div>;
}
