import { useState } from 'react';
import { v2ChatApi } from '../../../api/v2ChatApi.js';
import { EVIDENCE_FILE_LIMITS, evidenceFileKey, evidenceFileStatusLabel, mergeEvidenceFileSelections } from '../../evidence/model/evidenceFileSelection.js';

export function ExperienceIntakeModal({ open, onClose, onAnalyze, busy = false }) {
  const [content, setContent] = useState('');
  const [files, setFiles] = useState([]);
  const [fileError, setFileError] = useState('');
  const [fileNotice, setFileNotice] = useState('');
  const [analysisError, setAnalysisError] = useState('');
  const [checkingFiles, setCheckingFiles] = useState(false);

  if (!open) return null;

  const canAnalyze = Boolean(content.trim() || files.length > 0) && !checkingFiles;
  const addFiles = async (event) => {
    const incoming = Array.from(event.target.files || []);
    event.target.value = '';
    if (!incoming.length) return;
    setCheckingFiles(true); setFileError(''); setFileNotice('');
    try {
      const result = await mergeEvidenceFileSelections(files, incoming, v2ChatApi.preflightAttachments);
      setFiles(result.files);
      setFileError(result.error);
      setFileNotice(result.notice);
    } catch (reason) {
      setFileError(reason?.message || '파일의 중복 여부를 확인하지 못했습니다.');
    } finally {
      setCheckingFiles(false);
    }
  };
  const submit = async (event) => {
    event.preventDefault();
    if (!canAnalyze || busy) return;
    setAnalysisError('');
    try {
      await onAnalyze({ content: content.trim(), files });
      setContent(''); setFiles([]); setFileError(''); setFileNotice('');
    } catch (reason) {
      setAnalysisError(reason?.message || '경험을 정리하지 못했습니다. 다시 시도해 주세요.');
    }
  };
  const close = () => {
    if (busy || checkingFiles) return;
    setContent(''); setFiles([]); setFileError(''); setFileNotice(''); setAnalysisError('');
    onClose();
  };

  return (
    <div className="mv2-modal-backdrop" role="presentation">
      <section className="mv2-modal mv2-experience-intake" role="dialog" aria-modal="true" aria-labelledby="experience-intake-title">
        <header>
          <div>
            <span className="mv2-kicker">EXPERIENCE AI</span>
            <h2 id="experience-intake-title">경험정리 AI</h2>
            <p>경험을 자유롭게 적으면 AI가 핵심 내용과 역할, 행동, 성과를 분석합니다.</p>
          </div>
          <button type="button" className="mv2-icon-button" onClick={close} aria-label="닫기" disabled={busy || checkingFiles}>×</button>
        </header>
        <form onSubmit={submit}>
          <div className="mv2-experience-intake__body">
            <label>
              경험 내용
              <textarea value={content} onChange={(event) => setContent(event.target.value)} rows="9" placeholder="프로젝트, 업무, 상황, 행동, 결과를 자유롭게 적어 주세요." disabled={busy} />
            </label>
            <label className="mv2-file-picker">
              <span>파일 근거 추가</span>
              <input type="file" multiple accept=".pdf,.txt,application/pdf,text/plain" onChange={addFiles} disabled={busy || checkingFiles || files.length >= EVIDENCE_FILE_LIMITS.maxCount} />
              <small>{checkingFiles ? '기존 근거와 중복 여부를 확인하고 있습니다…' : 'PDF·TXT를 최대 5개까지 선택할 수 있습니다.'}</small>
            </label>
            {files.length > 0 && <ul className="mv2-experience-intake__files">{files.map((file) => <li key={evidenceFileKey(file)}><span><strong>{file.name}</strong><small>{evidenceFileStatusLabel(file)}</small></span><button type="button" onClick={() => setFiles((current) => current.filter((item) => item !== file))} aria-label={`${file.name} 제거`}>×</button></li>)}</ul>}
            {fileError && <p className="mv2-experience-intake__file-error" role="alert">{fileError}</p>}
            {fileNotice && <p className="mv2-experience-intake__file-notice" role="status">{fileNotice}</p>}
            {analysisError && <p className="mv2-experience-intake__file-error" role="alert">{analysisError}</p>}
            <p className="mv2-experience-intake__notice">입력한 원문에서 확인되는 내용만 AI가 경험 초안으로 정리합니다.</p>
          </div>
          <footer>
            <button type="button" className="mv2-button mv2-button--secondary" onClick={close} disabled={busy || checkingFiles}>취소</button>
            <button type="submit" className="mv2-button" disabled={!canAnalyze || busy}>{busy ? '정리 중…' : '경험 정리하기'}</button>
          </footer>
        </form>
      </section>
    </div>
  );
}
