import { useEffect, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { coverLetterApi } from '../api/index.js';
import { ErrorState, LoadingState, Tag } from '../components/common/index.js';
import './jobs.css';
import { useDirtyBlocker } from '../hooks/useDirtyBlocker.js';

const revisionActions = [
  ['shorten', '짧게'], ['expand', '구체적으로'], ['natural', '자연스럽게'], ['rewrite', '다시 작성'],
];

export function DocumentPage() {
  const { documentId } = useParams(); const location = useLocation(); const navigate = useNavigate();
  const [document, setDocument] = useState(location.state?.document || null); const [content, setContent] = useState(location.state?.document?.content || '');
  const [phase, setPhase] = useState(document ? 'ready' : 'loading'); const [error, setError] = useState(''); const [saved, setSaved] = useState(true);
  const [undoContent, setUndoContent] = useState(null);
  useDirtyBlocker(!saved);

  useEffect(() => { if (document) return; coverLetterApi.get(documentId).then((data) => { setDocument(data); setContent(data.content || ''); setPhase('ready'); }).catch((e) => { setError(e.message); setPhase('error'); }); }, [document, documentId]);
  useEffect(() => { const guard = (event) => { if (!saved) { event.preventDefault(); event.returnValue = ''; } }; window.addEventListener('beforeunload', guard); return () => window.removeEventListener('beforeunload', guard); }, [saved]);

  const revise = async (type) => { setPhase('revising'); setError(''); setUndoContent(content); try { const next = await coverLetterApi.revise({ documentId, baseVersion: document.version, revisionType: type, content }); setDocument(next); setContent(next.content); setSaved(true); setPhase('ready'); } catch (e) { setError(e.message); setPhase('ready'); } };
  const save = async () => { setPhase('saving'); setError(''); try { const next = await coverLetterApi.update(documentId, { version: document.version, changes: { content } }); setDocument(next); setContent(next.content); setSaved(true); setPhase('ready'); } catch (e) { setError(e.message); setPhase('ready'); } };
  const copy = async () => { try { await navigator.clipboard.writeText(content); setError(''); } catch { setError('클립보드에 복사하지 못했습니다. 직접 선택해 복사해 주세요.'); } };
  const undo = () => { if (undoContent == null) return; setContent(undoContent); setUndoContent(null); setSaved(false); };

  if (phase === 'loading') return <LoadingState title="자기소개서를 불러오는 중" />;
  if (phase === 'error') return <ErrorState title="문서를 찾을 수 없습니다" description={error} actionLabel="공고로 돌아가기" onRetry={() => navigate('/jobs')} />;
  if (!document) return null;
  const count = [...content].length; const overLimit = count > document.characterLimit;

  return <section className="feature-page document-page">
    <header className="feature-heading split"><div><span className="eyebrow">COVER LETTER · VERSION {document.version || 1}</span><h1>자기소개서 편집</h1><p>{document.question}</p></div><div className="header-actions"><Tag tone={saved ? 'confirmed' : 'ai'}>{saved ? '저장됨' : '편집 중'}</Tag><button className="ui-button ui-button--secondary" onClick={() => navigate(`/jobs/${document.jobId}`)}>공고로 돌아가기</button></div></header>
    {error && <div className="inline-error" role="alert">{error}</div>}
    <div className="document-workspace">
      <main className="surface editor-panel"><div className="editor-toolbar"><div className="revision-actions" aria-label="AI 수정 명령">{revisionActions.map(([type, label]) => <button key={type} className="tool-button" onClick={() => revise(type)} disabled={phase !== 'ready'}>{label}</button>)}{undoContent != null && <button className="tool-button" onClick={undo}>되돌리기</button>}</div><button className="tool-button" onClick={copy}>복사</button></div>
        <label className="document-editor"><span className="sr-only">자기소개서 본문</span><textarea value={content} onChange={(event) => { setContent(event.target.value); setSaved(false); }} disabled={phase === 'revising'} /></label>
        <footer className="editor-footer"><span className={overLimit ? 'count over' : 'count'}>{count.toLocaleString()} / {document.characterLimit?.toLocaleString()}자</span><button className="ui-button" onClick={save} disabled={saved || phase !== 'ready'}>{phase === 'saving' ? '저장 중…' : '편집 내용 저장'}</button></footer>
      </main>
      <aside className="surface evidence-panel"><div className="section-title"><div><span className="step">✓</span><h2>사용 근거</h2></div></div><p className="panel-guide">AI가 사용한 경험과 원문 근거입니다.</p>
        {document.evidence?.map((item, index) => <blockquote key={`${item.sourceId}-${index}`}><Tag tone="evidence">원본 근거</Tag><p>“{item.quote}”</p><cite>{item.experienceId}</cite></blockquote>)}
        {document.missingInformation?.length > 0 && <div className="warning-box"><strong>확인이 필요한 정보</strong><ul>{document.missingInformation.map((item) => <li key={item}>{item}</li>)}</ul></div>}
        {document.warnings?.map((warning) => <div className="warning-box" key={warning}>{warning}</div>)}
      </aside>
    </div>
  </section>;
}
