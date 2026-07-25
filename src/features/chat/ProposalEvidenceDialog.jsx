import { useEffect, useState } from 'react';
import { sourceApi } from '../../api/sourceApi.js';
import { EvidenceWorkspace } from '../evidence/components/EvidenceWorkspace.jsx';
import { downloadEvidenceFile, openEvidenceFile } from '../evidence/model/evidenceFileAccess.js';
import { splitProposalSources } from './proposalMapper.js';

export function ProposalEvidenceDialog({ sources, onClose }) {
  const groups = splitProposalSources(sources);
  const [selectedId, setSelectedId] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const closeOnEscape = (event) => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);
  const openFile = async (source) => {
    setError('');
    try { await openEvidenceFile(source, sourceApi.download); }
    catch (reason) { setError(reason.message || '파일을 열지 못했습니다.'); }
  };
  const downloadFile = async (source) => {
    setError('');
    try { await downloadEvidenceFile(source, sourceApi.download); }
    catch (reason) { setError(reason.message || '파일을 다운로드하지 못했습니다.'); }
  };

  return <div className="v2-related-evidence-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="v2-related-evidence-dialog" role="dialog" aria-modal="true" aria-labelledby="v2-related-evidence-title">
      <header>
        <div><span className="v2-eyebrow">Evidence</span><h2 id="v2-related-evidence-title">관련 근거</h2><p>총 {groups.totalCount}개 · 대화·텍스트 {groups.conversationCount}개 · 파일 {groups.fileCount}개</p></div>
        <button type="button" onClick={onClose} aria-label="관련 근거 창 닫기">×</button>
      </header>
      <EvidenceWorkspace
        sources={groups.all}
        selectedId={selectedId}
        onSelect={setSelectedId}
        mode="readonly"
        description={(source) => source.type === 'file' ? '파일 원본을 열거나 다운로드할 수 있습니다.' : '초안 작성에 사용된 원본 내용을 확인할 수 있습니다.'}
        onOpenFile={openFile}
        onDownload={downloadFile}
        error={error}
      />
      <footer><button type="button" onClick={onClose}>닫기</button></footer>
    </section>
  </div>;
}
