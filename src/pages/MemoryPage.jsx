import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { experienceApi } from '../api/experienceApi.js';
import { inputApi } from '../api/inputApi.js';
import EmptyState from '../components/common/EmptyState.jsx';
import ErrorState from '../components/common/ErrorState.jsx';
import LoadingState from '../components/common/LoadingState.jsx';
import '../styles/memory.css';
import '../styles/memory-workspace.css';
import { useDirtyBlocker } from '../hooks/useDirtyBlocker.js';
import { projectCandidateId } from '../utils/contractFields.js';

const newId = () => globalThis.crypto?.randomUUID?.() ?? `req-${Date.now()}`;
const listText = (value) => Array.isArray(value) ? value.join('\n') : (value ?? '');
const lines = (value) => value.split('\n').map((item) => item.trim()).filter(Boolean);
const MAX_FILE_COUNT = 5;
const MAX_FILE_BYTES = 25 * 1024 * 1024;
const MAX_TOTAL_BYTES = 100 * 1024 * 1024;

function ExperienceTree({ tree, highlightId }) {
  if (!tree?.domains?.length) return <EmptyState title="저장된 경험이 없습니다" description="첫 경험을 입력해 나만의 커리어 메모리를 시작해 보세요." />;
  return <div className="memory-tree">{tree.domains.map((domain) => (
    <details key={domain.id} open>
      <summary>{domain.name}<span>{domain.experienceCount}</span></summary>
      {domain.projects?.map((project) => <details key={project.id} open>
        <summary>{project.name}<small>{project.organization}</small></summary>
        <ul>{project.experiences?.map((experience) => <li key={experience.id} className={experience.id === highlightId ? 'is-new' : ''}>
          <Link to={`/memory/${experience.id}`}><strong>{experience.title}</strong><span>{experience.summary}</span></Link>
        </li>)}</ul>
      </details>)}
    </details>
  ))}</div>;
}

function ReviewForm({ initial, busy, error, onCommit, onCancel }) {
  const first = initial.project?.experiences?.[0] ?? {};
  const [draft, setDraft] = useState({
    draftId: initial.draftId, rawId: initial.rawId, domainName: initial.domainName ?? '',
    project: { ...(initial.project ?? { name: '', organization: '', period: {} }), experiences: [{ ...first, actions: first.actions ?? [], results: first.results ?? [], facts: first.facts ?? [], skills: first.skills ?? [] }] },
    projectSelection: initial.projectCandidates?.length ? 'new' : 'new',
  });
  const experience = draft.project.experiences[0];
  const setRoot = (key, value) => setDraft((old) => ({ ...old, [key]: value }));
  const setProject = (key, value) => setDraft((old) => ({ ...old, project: { ...old.project, [key]: value } }));
  const setExperience = (key, value) => setDraft((old) => ({ ...old, project: { ...old.project, experiences: [{ ...old.project.experiences[0], [key]: value }] } }));
  const submit = (event) => {
    event.preventDefault();
    const existing = draft.projectSelection !== 'new';
    onCommit({
      rawId: draft.rawId,
      draftId: draft.draftId,
      saveMode: existing ? 'existing_project' : 'new_project',
      targetProjectId: existing ? draft.projectSelection : undefined,
      domainName: draft.domainName,
      project: draft.project,
    });
  };
  return <form className="review-form" onSubmit={submit}>
    <div className="section-heading"><div><span className="eyebrow">AI 초안</span><h2>구조화 결과를 확인해 주세요</h2></div><p>사실과 다른 내용을 수정한 뒤 저장하세요.</p></div>
    {error && <p className="inline-error" role="alert">{error}</p>}
    <fieldset disabled={busy}><legend>분류와 프로젝트</legend>
      <label>큰 영역명<input required value={draft.domainName} onChange={(e) => setRoot('domainName', e.target.value)} /></label>
      <div className="field-row"><label>프로젝트명<input required value={draft.project.name ?? ''} onChange={(e) => setProject('name', e.target.value)} /></label><label>소속<input value={draft.project.organization ?? ''} onChange={(e) => setProject('organization', e.target.value)} /></label></div>
      {initial.projectCandidates?.length > 0 && <label>프로젝트 연결<select value={draft.projectSelection} onChange={(e) => setRoot('projectSelection', e.target.value)}><option value="new">새 프로젝트로 저장</option>{initial.projectCandidates.map((item) => <option key={projectCandidateId(item)} value={projectCandidateId(item)}>{item.name}</option>)}</select></label>}
    </fieldset>
    <fieldset disabled={busy}><legend>세부 경험</legend>
      <label>제목<input required value={experience.title ?? ''} onChange={(e) => setExperience('title', e.target.value)} /></label>
      <label>한 줄 요약<textarea required rows="2" value={experience.summary ?? ''} onChange={(e) => setExperience('summary', e.target.value)} /></label>
      <label>상황<textarea rows="3" value={experience.situation ?? ''} onChange={(e) => setExperience('situation', e.target.value)} /></label>
      <label>행동 <small>한 줄에 하나씩</small><textarea rows="4" value={listText(experience.actions)} onChange={(e) => setExperience('actions', lines(e.target.value))} /></label>
      <label>결과 <small>한 줄에 하나씩</small><textarea rows="3" value={listText(experience.results)} onChange={(e) => setExperience('results', lines(e.target.value))} /></label>
      <div className="field-row"><label>역할<input value={experience.role ?? ''} onChange={(e) => setExperience('role', e.target.value)} /></label><label>역량 <small>한 줄에 하나씩</small><textarea rows="2" value={listText(experience.skills)} onChange={(e) => setExperience('skills', lines(e.target.value))} /></label></div>
    </fieldset>
    <div className="sticky-actions"><button type="button" className="ui-button ui-button--secondary" onClick={onCancel} disabled={busy}>취소</button><button className="ui-button" disabled={busy}>{busy ? '저장하는 중…' : '경험 저장'}</button></div>
  </form>;
}

function ExperienceChat() {
  const [question, setQuestion] = useState(''); const [result, setResult] = useState(null); const [status, setStatus] = useState('idle'); const [error, setError] = useState('');
  const ask = async (event) => { event.preventDefault(); if (!question.trim() || status === 'loading') return; setStatus('loading'); setError(''); try { setResult(await experienceApi.chat(question.trim())); setStatus('success'); } catch (e) { setError(e.message); setStatus('error'); } };
  return <section className="chat-panel"><div className="section-heading"><div><span className="eyebrow">경험 검색</span><h2>내 경험에 질문하기</h2><p>저장된 경험과 원본 근거에서 답을 찾습니다.</p></div></div>
    <form className="chat-input" onSubmit={ask}><label className="sr-only" htmlFor="memory-question">질문</label><input id="memory-question" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="예: 데이터로 성과를 개선한 경험이 있어?" /><button className="ui-button" disabled={!question.trim() || status === 'loading'}>{status === 'loading' ? '찾는 중…' : '질문하기'}</button></form>
    {error && <p className="inline-error" role="alert">{error}</p>}
    {result && <div className="chat-answer" aria-live="polite"><span className="eyebrow">AI 답변</span><p>{result.answer}</p>{result.experiences?.length > 0 && <div className="result-cards">{result.experiences.map((item) => <Link key={item.id} to={`/memory/${item.id}`}><strong>{item.title}</strong><span>{item.projectName}</span><p>{item.summary}</p></Link>)}</div>}{result.evidence?.map((item) => <blockquote key={`${item.sourceId}-${item.quote}`}>“{item.quote}” <span>원본 근거</span></blockquote>)}</div>}
  </section>;
}

export function MemoryPage() {
  const [mode, setMode] = useState('browse'); const [inputType, setInputType] = useState('text'); const [content, setContent] = useState(''); const [files, setFiles] = useState([]);
  const [tree, setTree] = useState(null); const [treeStatus, setTreeStatus] = useState('loading'); const [draft, setDraft] = useState(null); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [highlightId, setHighlightId] = useState('');
  const isDirty = (mode === 'input' && Boolean(content || files.length)) || mode === 'review';
  useDirtyBlocker(isDirty);
  const loadTree = async () => { setTreeStatus('loading'); try { setTree(await experienceApi.getTree()); setTreeStatus('success'); } catch { setTreeStatus('error'); } };
  useEffect(() => {
    let active = true;
    experienceApi.getTree().then((data) => { if (active) { setTree(data); setTreeStatus('success'); } }, () => { if (active) setTreeStatus('error'); });
    return () => { active = false; };
  }, []);
  useEffect(() => { const protect = (e) => { if (isDirty) { e.preventDefault(); e.returnValue = ''; } }; window.addEventListener('beforeunload', protect); return () => window.removeEventListener('beforeunload', protect); }, [isDirty]);
  const validFiles = useMemo(() => files.length > 0 && files.length <= MAX_FILE_COUNT && files.reduce((sum, file) => sum + file.size, 0) <= MAX_TOTAL_BYTES && files.every((file) => ['application/pdf', 'text/plain'].includes(file.type) && file.size <= MAX_FILE_BYTES), [files]);
  const selectFiles = (event) => {
    const selected = [...(event.target.files || [])];
    setFiles((current) => [...current, ...selected].filter((file, index, all) => all.findIndex((item) => item.name === file.name && item.size === file.size) === index).slice(0, MAX_FILE_COUNT));
    event.target.value = '';
  };
  const clearInput = () => { setContent(''); setFiles([]); setError(''); };
  const parse = async (event) => { event.preventDefault(); setError(''); if (inputType === 'text' && !content.trim()) return setError('경험 내용을 입력해 주세요.'); if (inputType === 'file' && !validFiles) return setError('PDF 또는 TXT 파일을 최대 5개까지 선택해 주세요. 파일당 25MiB, 전체 100MiB까지 가능합니다.'); setBusy(true); try { const data = inputType === 'text' ? await inputApi.parseText(content.trim(), newId()) : await inputApi.parseFiles(files, newId()); setDraft(data); setMode('review'); } catch (e) { setError(e.message); } finally { setBusy(false); } };
  const commit = async (value) => { setBusy(true); setError(''); try { const result = await experienceApi.commit(value); setHighlightId(result.experienceIds?.[0] ?? ''); setContent(''); setFiles([]); setDraft(null); await loadTree(); setMode('browse'); } catch (e) { setError(e.message); } finally { setBusy(false); } };
  return <div className="memory-page">
    <nav className="mode-tabs" aria-label="경험 메모리 작업"><button className={mode === 'browse' ? 'active' : ''} onClick={() => setMode('browse')}>저장된 경험</button><button className={mode === 'input' || mode === 'review' ? 'active' : ''} onClick={() => setMode('input')}>새 경험 입력</button><button className={mode === 'chat' ? 'active' : ''} onClick={() => setMode('chat')}>경험 질문</button></nav>
    <section className={`browse-layout mode-${mode}`}>
      <aside><div className="panel-title"><div><span className="eyebrow">Memory</span><h2>경험 구조</h2></div><button className="ui-button" onClick={() => setMode('input')}>+ 새 경험</button></div>{treeStatus === 'loading' ? <LoadingState label="경험을 불러오는 중입니다." /> : treeStatus === 'error' ? <ErrorState title="경험을 불러오지 못했습니다" onRetry={loadTree} /> : <ExperienceTree tree={tree} highlightId={highlightId} />}</aside>
      <div className="memory-workspace">
        {mode === 'browse' && <div className="memory-welcome"><span className="welcome-mark">CM</span><h2>기억을 근거 있는 경력 자산으로</h2><p>왼쪽에서 경험을 선택하거나 새로운 경험을 정리해 보세요.</p><button className="ui-button" onClick={() => setMode('input')}>경험 입력하기</button></div>}
        {mode === 'input' && <form className="input-panel" onSubmit={parse}><div className="section-heading"><div><span className="eyebrow">새 경험</span><h2>정리되지 않은 이야기 그대로 시작하세요</h2></div><p>AI가 프로젝트와 세부 경험으로 구조화합니다.</p></div><div className="segmented" role="group" aria-label="입력 방식"><button type="button" aria-pressed={inputType === 'text'} onClick={() => setInputType('text')}>텍스트</button><button type="button" aria-pressed={inputType === 'file'} onClick={() => setInputType('file')}>파일</button></div>{inputType === 'text' ? <label>경험 내용<textarea rows="14" value={content} onChange={(e) => setContent(e.target.value)} placeholder="어떤 상황에서, 무엇을 맡아, 어떻게 행동했고 어떤 결과가 있었는지 자유롭게 적어주세요." /></label> : <div><label className="file-drop">PDF 또는 TXT 파일 최대 5개<input type="file" multiple accept=".pdf,.txt,application/pdf,text/plain" onChange={selectFiles} /><span>{files.length ? `${files.length}개 선택 · 총 ${(files.reduce((sum, file) => sum + file.size, 0) / 1024 / 1024).toFixed(1)}MiB / 100MiB` : '파일당 25MiB · 전체 100MiB까지 선택할 수 있습니다'}</span></label>{files.length > 0 && <ul className="selected-file-list" aria-label="선택한 파일">{files.map((file) => <li key={`${file.name}-${file.size}`}><span><strong>{file.name}</strong><small>{(file.size / 1024).toFixed(0)}KB</small></span><button type="button" onClick={() => setFiles((current) => current.filter((item) => item !== file))} aria-label={`${file.name} 제거`}>제거</button></li>)}</ul>}</div>}{error && <p className="inline-error" role="alert">{error}</p>}<div className="sticky-actions"><button type="button" className="ui-button ui-button--secondary" onClick={clearInput} disabled={busy || (!content && files.length === 0)}>모두 지우기</button><button className="ui-button" disabled={busy}>{busy ? 'AI가 구조화하는 중…' : '경험 정리하기'}</button></div></form>}
        {mode === 'review' && draft && <ReviewForm initial={draft} busy={busy} error={error} onCommit={commit} onCancel={() => setMode('input')} />}
        {mode === 'chat' && <ExperienceChat />}
      </div>
    </section>
  </div>;
}
