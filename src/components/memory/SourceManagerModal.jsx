import { useEffect, useId, useState } from 'react';
import './source-manager.css';

function SourceTypeIcon({ type }) {
  const isFile = type === 'file';
  return <span className={`source-type-icon is-${isFile ? 'file' : 'text'}`} title={isFile ? '파일 원본' : '텍스트 원본'}>
    <svg viewBox="0 0 24 24" aria-hidden="true">
      {isFile
        ? <><path d="M6.5 3.5h7l4 4v13h-11z" /><path d="M13.5 3.5v4h4" /></>
        : <><path d="M5 5.5h14M5 9.5h14M5 13.5h10M5 17.5h8" /></>}
    </svg>
    <span className="sr-only">{isFile ? '파일 원본' : '텍스트 원본'}</span>
  </span>;
}

function formatUploadDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return `업로드 ${new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)}`;
}

function fileMetadata(source) {
  const uploadDate = formatUploadDate(
    source.uploadedAt ?? source.uploaded_at ?? source.capturedAt ?? source.captured_at ?? source.createdAt ?? source.created_at,
  );
  return [
    uploadDate,
    source.page ? `${source.page}쪽에서 인용` : '',
  ].filter(Boolean).join(' · ');
}

export function SourceManagerModal({ open, sources = [], busy, error, notice, onClose, onSave, onUnlink, onDownload }) {
  const titleId = useId();
  const [selectedId, setSelectedId] = useState(null);
  const [drafts, setDrafts] = useState({});
  const effectiveId = sources.some((source) => source.id === selectedId) ? selectedId : sources[0]?.id;
  const selected = sources.find((source) => source.id === effectiveId);
  const editText = selected ? (drafts[selected.id] ?? selected.text ?? '') : '';
  const hasTextChanges = selected?.sourceType === 'text' && editText !== (selected.text ?? '');
  const resetText = () => {
    if (!selected) return;
    setDrafts((current) => {
      const next = { ...current };
      delete next[selected.id];
      return next;
    });
  };
  useEffect(() => { if (!open) return undefined; const escape = (event) => { if (event.key === 'Escape') onClose(); }; document.addEventListener('keydown', escape); return () => document.removeEventListener('keydown', escape); }, [open, onClose]);
  if (!open) return null;

  return <div className="modal-backdrop source-manager-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="source-manager" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <header><div><span className="eyebrow">EVIDENCE</span><h2 id={titleId}>원본 근거 관리</h2></div><button type="button" className="source-close" onClick={onClose} aria-label="원본 근거 창 닫기">×</button></header>
      <div className="source-manager-body">
        <nav aria-label="원본 근거 목록">
          {sources.length === 0 && <p className="panel-guide">연결된 원본이 없습니다.</p>}
          {sources.map((source) => <button type="button" key={source.id} className={effectiveId === source.id ? 'selected' : ''} onClick={() => setSelectedId(source.id)}><SourceTypeIcon type={source.sourceType} /><span><strong>{source.filename || '텍스트 입력'}</strong><small>{source.page ? `${source.page}쪽 · ` : ''}{source.linkedFacts?.length || 0}개 사실 연결</small></span></button>)}
        </nav>
        <main>{selected ? <>
          <div className="source-detail-heading">
            <div><h3>{selected.filename || '텍스트 근거'}</h3><p>{selected.sourceType === 'file' ? '파일 원본을 다운로드하거나 연결 사실을 확인하세요.' : '텍스트 원본은 내용을 수정해 저장할 수 있습니다.'}</p></div>
            <div className="source-detail-actions">
              <button type="button" className="source-unlink" disabled={busy} onClick={() => onUnlink(selected)}>경험에서 연결 해제</button>
              {selected.sourceType === 'text' && <>
                <button type="button" className="ui-button ui-button--secondary" disabled={busy || !hasTextChanges} onClick={resetText}>되돌리기</button>
                <button type="button" className="ui-button" disabled={busy || !hasTextChanges || !editText.trim()} onClick={() => onSave(selected, editText.trim())}>{busy ? '저장 중…' : '변경 저장'}</button>
              </>}
            </div>
          </div>
          {selected.sourceType === 'text' ? <label>원본 텍스트<textarea className="source-original-text" rows="6" value={editText} onChange={(event) => setDrafts((current) => ({ ...current, [selected.id]: event.target.value }))} /></label> : <div className="file-source-card"><strong>{selected.filename}</strong><span>{fileMetadata(selected)}</span><button type="button" className="ui-button ui-button--secondary" onClick={() => onDownload(selected)}>파일 다운로드</button></div>}
          <section className="linked-facts"><h4>연결된 사실</h4>{selected.linkedFacts?.map((fact) => <blockquote key={fact.fact}><strong>{fact.fact}</strong><p>“{fact.quote}”</p></blockquote>)}</section>
          {notice && <p className="source-notice" role="status">{notice}</p>}
          {error && <p className="inline-error" role="alert">{error}</p>}
        </> : <div className="source-empty"><div>{notice && <p className="source-notice" role="status">{notice}</p>}<p>목록에서 원본을 선택하세요.</p></div></div>}</main>
      </div>
    </section>
  </div>;
}
