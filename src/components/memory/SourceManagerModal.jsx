import { useEffect, useId, useState } from 'react';
import { Tag } from '../common/index.js';
import './source-manager.css';

export function SourceManagerModal({ open, sources = [], busy, error, onClose, onSave, onDelete, onDownload }) {
  const titleId = useId();
  const [selectedId, setSelectedId] = useState(null);
  const [drafts, setDrafts] = useState({});
  const effectiveId = sources.some((source) => source.id === selectedId) ? selectedId : sources[0]?.id;
  const selected = sources.find((source) => source.id === effectiveId);
  const editText = selected ? (drafts[selected.id] ?? selected.text ?? '') : '';
  useEffect(() => { if (!open) return undefined; const escape = (event) => { if (event.key === 'Escape') onClose(); }; document.addEventListener('keydown', escape); return () => document.removeEventListener('keydown', escape); }, [open, onClose]);
  if (!open) return null;

  return <div className="modal-backdrop source-manager-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="source-manager" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <header><div><span className="eyebrow">EVIDENCE</span><h2 id={titleId}>원본 근거 관리</h2></div><button type="button" className="source-close" onClick={onClose} aria-label="원본 근거 창 닫기">×</button></header>
      <div className="source-manager-body">
        <nav aria-label="원본 근거 목록">
          {sources.length === 0 && <p className="panel-guide">연결된 원본이 없습니다.</p>}
          {sources.map((source) => <button type="button" key={source.id} className={effectiveId === source.id ? 'selected' : ''} onClick={() => setSelectedId(source.id)}><Tag label={source.sourceType === 'file' ? '파일' : '텍스트'} variant={source.sourceType === 'file' ? 'evidence' : 'ai'} /><span><strong>{source.filename || '텍스트 입력'}</strong><small>{source.page ? `${source.page}쪽 · ` : ''}{source.linkedFacts?.length || 0}개 사실 연결</small></span></button>)}
        </nav>
        <main>{selected ? <>
          <div className="source-detail-heading"><div><h3>{selected.filename || '텍스트 근거'}</h3><p>{selected.sourceType === 'file' ? '파일 원본을 다운로드하거나 연결 사실을 확인하세요.' : '텍스트 원본은 내용을 수정해 저장할 수 있습니다.'}</p></div><button type="button" className="source-delete" disabled={busy} onClick={() => onDelete(selected)}>삭제</button></div>
          {selected.sourceType === 'text' ? <label>원본 텍스트<textarea rows="12" value={editText} onChange={(event) => setDrafts((current) => ({ ...current, [selected.id]: event.target.value }))} /></label> : <div className="file-source-card"><strong>{selected.filename}</strong><span>{selected.page ? `${selected.page}쪽에서 인용` : '업로드 파일'}</span><button type="button" className="ui-button ui-button--secondary" onClick={() => onDownload(selected)}>파일 다운로드</button></div>}
          <section className="linked-facts"><h4>연결된 사실</h4>{selected.linkedFacts?.map((fact) => <blockquote key={fact.fact}><strong>{fact.fact}</strong><p>“{fact.quote}”</p></blockquote>)}</section>
          {error && <p className="inline-error" role="alert">{error}</p>}
          {selected.sourceType === 'text' && <div className="source-actions"><button type="button" className="ui-button" disabled={busy || editText === selected.text || !editText.trim()} onClick={() => onSave(selected, editText.trim())}>{busy ? '저장 중…' : '변경 저장'}</button></div>}
        </> : <div className="source-empty">목록에서 원본을 선택하세요.</div>}</main>
      </div>
    </section>
  </div>;
}
