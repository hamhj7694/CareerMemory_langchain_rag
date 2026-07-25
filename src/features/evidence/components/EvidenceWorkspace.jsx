import { EVIDENCE_TYPES, toEvidenceViews } from '../model/evidenceMapper.js';
import { EvidenceSourceIcon } from './EvidenceSourceIcon.jsx';
import './evidence-workspace.css';

const formatDate = (value) => {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
};

const formatBytes = (value) => {
  if (!Number.isFinite(value) || value <= 0) return '';
  if (value < 1024 * 1024) return `${Math.ceil(value / 1024)}KiB`;
  return `${(value / 1024 / 1024).toFixed(1)}MiB`;
};

function evidenceMetadata(source) {
  const date = formatDate(source.uploadedAt || source.capturedAt);
  if (source.type === EVIDENCE_TYPES.FILE) return [formatBytes(source.sizeBytes), date].filter(Boolean).join(' · ');
  return date;
}

export function EvidenceReadonlyContent({ source, onOpenFile, onDownload }) {
  if (source.type === EVIDENCE_TYPES.FILE) {
    return (
      <div className="evidence-file-card">
        <div><strong>{source.filename || source.title}</strong><span>{evidenceMetadata(source) || '파일 정보 없음'}</span></div>
        <div>
          <button type="button" disabled={source.unavailable || !onOpenFile} onClick={() => onOpenFile?.(source)}>{source.unavailable ? '원본 없음' : '파일 보기'}</button>
          <button type="button" disabled={source.unavailable || !onDownload} onClick={() => onDownload?.(source)}>다운로드</button>
        </div>
      </div>
    );
  }
  if (source.type === EVIDENCE_TYPES.CONVERSATION || source.type === EVIDENCE_TYPES.TEXT) {
    return <label>{source.type === EVIDENCE_TYPES.CONVERSATION ? '원본 대화' : '원본 텍스트'}<textarea className="evidence-original-text" rows="6" value={source.text} readOnly /></label>;
  }
  return <div className="evidence-empty"><p>복구할 수 있는 원본 데이터가 없습니다.</p></div>;
}

export function EvidenceLinkedContent({ source }) {
  return (
    <section className="evidence-linked-content">
      <h4>연결된 내용</h4>
      {source.linkedFacts.length
        ? source.linkedFacts.map((fact, index) => <blockquote key={`${fact.fact || fact.text || 'content'}-${index}`}><strong>{fact.fact || fact.text || '연결된 내용'}</strong>{fact.quote && <p>“{fact.quote}”</p>}</blockquote>)
        : <p className="evidence-linked-content__empty">연결된 내용이 없습니다.</p>}
    </section>
  );
}

export function EvidenceWorkspace({
  sources,
  selectedId,
  onSelect,
  mode = 'readonly',
  className = '',
  sidebarFooter,
  description,
  renderActions,
  renderContent,
  onOpenFile,
  onDownload,
  notice,
  error,
}) {
  const evidenceSources = toEvidenceViews(sources);
  const effectiveId = evidenceSources.some((source) => source.id === selectedId) ? selectedId : evidenceSources[0]?.id;
  const selected = evidenceSources.find((source) => source.id === effectiveId);

  return (
    <div className={`evidence-workspace is-${mode} ${className}`.trim()}>
      <nav aria-label="근거 목록">
        <div className="evidence-source-list">
          {!evidenceSources.length && <p className="evidence-list-empty">연결된 근거가 없습니다.</p>}
          {evidenceSources.map((source) => (
            <button type="button" key={source.id} className={effectiveId === source.id ? 'selected' : ''} onClick={() => onSelect?.(source.id)}>
              <EvidenceSourceIcon type={source.type} className={`source-type-icon is-${source.type}`} />
              <span><strong>{source.title}</strong><small>{evidenceMetadata(source) || `${source.linkedFacts.length}개 내용 연결`}</small></span>
            </button>
          ))}
        </div>
        {sidebarFooter}
      </nav>
      <main>
        {selected ? <>
          <div className="evidence-detail-heading">
            <div><h3>{selected.title}</h3><p>{typeof description === 'function' ? description(selected) : description}</p></div>
            {renderActions?.(selected)}
          </div>
          {renderContent
            ? renderContent(selected)
            : <EvidenceReadonlyContent source={selected} onOpenFile={onOpenFile} onDownload={onDownload} />}
          <EvidenceLinkedContent source={selected} />
          {notice && <p className="source-notice" role="status">{notice}</p>}
          {error && <p className="inline-error" role="alert">{error}</p>}
        </> : <div className="evidence-empty"><div>{notice && <p className="source-notice" role="status">{notice}</p>}<p>목록에서 근거를 선택하세요.</p></div></div>}
      </main>
    </div>
  );
}
