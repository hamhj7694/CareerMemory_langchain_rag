import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { experienceExtractionApi } from '../api/experienceExtractionApi.js';
import { experienceTrashApi } from '../api/experienceTrashApi.js';
import { ExperienceProposalModal } from '../features/experience/components/ExperienceProposalModal.jsx';
import {
  buildExperienceAnalysisFromResult,
  markProposalExperienceSaved,
  saveProposalExperience,
} from '../features/experience/api/experienceProposalService.js';
import { listToText, textToMarkdownLines, textToSkills } from '../features/experience/model/experienceContent.js';
import '../features/memory-v2/memory-manager.css';

const editableDraft = (draft = {}) => ({
  ...draft,
  domain: typeof draft.domain === 'string' ? draft.domain : draft.domain?.name || '미분류 경험',
  project: typeof draft.project === 'string' ? draft.project : draft.project?.name || '프로젝트·활동 미분류',
  title: draft.title || '',
  summary: draft.summary || '',
  situation: draft.situation || '',
  role: draft.role || '',
  actions: draft.actions || [],
  results: draft.results || [],
  facts: draft.facts || [],
  skills: draft.skills || [],
});

export function ExperienceTrashPage() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState('');
  const [editingId, setEditingId] = useState('');
  const [form, setForm] = useState(null);
  const [busyId, setBusyId] = useState('');
  const [analysisProposal, setAnalysisProposal] = useState(null);
  const [analysisSourceItem, setAnalysisSourceItem] = useState(null);
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [analysisEditing, setAnalysisEditing] = useState(false);

  const load = async () => {
    setStatus('loading'); setError('');
    try {
      const result = await experienceTrashApi.list();
      setItems(result.items || []);
      setStatus('ready');
    } catch (reason) {
      setError(reason?.message || '쓰레기통을 불러오지 못했습니다.');
      setStatus('error');
    }
  };

  useEffect(() => {
    let active = true;
    experienceTrashApi.list().then((result) => {
      if (!active) return;
      setItems(result.items || []);
      setStatus('ready');
    }, (reason) => {
      if (!active) return;
      setError(reason?.message || '쓰레기통을 불러오지 못했습니다.');
      setStatus('error');
    });
    return () => { active = false; };
  }, []);

  const startEditing = (item) => {
    setEditingId(item.id);
    setForm(editableDraft(item.draft));
  };

  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  const saveEdit = async (itemId) => {
    setBusyId(itemId); setError('');
    try {
      const saved = await experienceTrashApi.update(itemId, form);
      setItems((current) => current.map((item) => item.id === itemId ? saved : item));
      setEditingId(''); setForm(null);
    } catch (reason) {
      setError(reason?.message || '초안 수정을 저장하지 못했습니다.');
    } finally { setBusyId(''); }
  };

  const permanentlyDelete = async (item) => {
    if (!window.confirm(`‘${item.title}’ 초안을 완전히 삭제할까요?\n이 작업은 되돌릴 수 없습니다.`)) return;
    setBusyId(item.id); setError('');
    try {
      await experienceTrashApi.remove(item.id);
      setItems((current) => current.filter((entry) => entry.id !== item.id));
    } catch (reason) {
      setError(reason?.message || '초안을 완전히 삭제하지 못했습니다.');
    } finally { setBusyId(''); }
  };

  const saveAsExperience = async (item) => {
    setBusyId(item.id); setError('');
    try {
      if (!Object.keys(item.draft || {}).length) {
        throw new Error('원문은 경험 분석을 거쳐 초안으로 만든 뒤 저장해 주세요.');
      }
      await saveProposalExperience(item.draft);
      await experienceTrashApi.remove(item.id);
      setItems((current) => current.filter((entry) => entry.id !== item.id));
    } catch (reason) {
      setError(reason?.message || '초안을 내 경험으로 저장하지 못했습니다.');
    } finally { setBusyId(''); }
  };

  // 분석 실패 당시 원문만 남은 항목은 곧바로 경험으로 저장하지 않는다.
  // AI 초안으로 변환한 뒤 사용자가 내용과 분류를 검토할 수 있는 화면을 연다.
  const analyzeOriginal = async (item) => {
    if (!item.original_text?.trim()) return;
    setBusyId(item.id); setError('');
    try {
      const result = await experienceExtractionApi.analyzeDirectInput({
        text: item.original_text,
        files: await Promise.all(
          (item.files || []).map((file) => experienceTrashApi.downloadFile(item.id, file)),
        ),
      });
      const proposal = buildExperienceAnalysisFromResult({ result }).proposal;
      if (!proposal.experiences?.length) {
        throw new Error('원문에서 정리할 경험을 찾지 못했습니다.');
      }
      setAnalysisSourceItem(item);
      setAnalysisProposal(proposal);
    } catch (reason) {
      setError(reason?.message || '원문을 경험 초안으로 분석하지 못했습니다.');
    } finally { setBusyId(''); }
  };

  const removeAnalyzedOriginal = async () => {
    if (!analysisSourceItem) return;
    await experienceTrashApi.remove(analysisSourceItem.id);
    setItems((current) => current.filter((item) => item.id !== analysisSourceItem.id));
    setAnalysisSourceItem(null);
  };

  const approveAnalyzedDraft = async (proposal) => {
    const requestedDraftId = proposal.selection?.draft_id;
    const draftIndex = requestedDraftId
      ? proposal.experiences?.findIndex((item) => item.draft_id === requestedDraftId)
      : -1;
    const index = draftIndex >= 0
      ? draftIndex
      : (proposal.selection?.experience_indexes?.[0] ?? 0);
    const item = proposal.experiences?.[index];
    if (!item || item.approved) return proposal;

    setAnalysisBusy(true); setError('');
    try {
      const saved = await saveProposalExperience(item);
      const nextProposal = markProposalExperienceSaved(proposal, index, saved);
      setAnalysisProposal(nextProposal);
      if (nextProposal.experiences.every((entry) => entry.approved)) {
        await removeAnalyzedOriginal();
      }
      return nextProposal;
    } finally { setAnalysisBusy(false); }
  };

  const saveAllAnalyzedDrafts = async () => {
    const pending = analysisProposal?.experiences
      ?.map((item, index) => ({ item, index }))
      .filter(({ item }) => !item.approved) || [];
    if (!pending.length || analysisBusy) return;
    setAnalysisBusy(true); setError('');
    try {
      let nextProposal = analysisProposal;
      for (const { item, index } of pending) {
        const saved = await saveProposalExperience(item);
        nextProposal = markProposalExperienceSaved(nextProposal, index, saved);
      }
      setAnalysisProposal(nextProposal);
      await removeAnalyzedOriginal();
    } catch (reason) {
      setError(reason?.message || '분석한 경험 초안을 모두 저장하지 못했습니다.');
    } finally { setAnalysisBusy(false); }
  };

  const removeAnalyzedDraft = async (proposal, sourceIndex) => {
    const experiences = (proposal.experiences || []).filter(
      (item, index) => index !== sourceIndex || item.approved,
    );
    if (!experiences.length) {
      setAnalysisProposal(null);
      return null;
    }
    const nextProposal = {
      ...proposal,
      version: (proposal.version || 0) + 1,
      experiences,
    };
    setAnalysisProposal(nextProposal);
    return nextProposal;
  };

  return <section className="mv2-trash-page">
    <header className="mv2-trash-page__header">
      <div><span className="mv2-kicker">DRAFT TRASH</span><h1>쓰레기통</h1><p>삭제되었거나 저장에 실패한 경험 초안을 확인하고 다시 저장할 수 있습니다.</p></div>
      <Link className="mv2-button mv2-button--secondary" to="/memory">경험 관리로 돌아가기</Link>
    </header>
    {error && <div className="mv2-sync-error" role="alert"><span>{error}</span><button onClick={() => setError('')}>닫기</button></div>}
    {status === 'loading' && <p className="mv2-sync-status">쓰레기통을 불러오는 중입니다…</p>}
    {status === 'error' && <button className="mv2-button" onClick={load}>다시 시도</button>}
    {status === 'ready' && !items.length && <div className="mv2-trash-empty"><span aria-hidden="true">✓</span><h2>쓰레기통이 비어 있습니다</h2><p>삭제되거나 저장에 실패한 경험 초안이 없습니다.</p></div>}
    {status === 'ready' && items.length > 0 && <div className="mv2-trash-list">{items.map((item) => {
      const hasDraft = Object.keys(item.draft || {}).length > 0;
      const draft = editingId === item.id ? form : editableDraft(item.draft);
      const editing = editingId === item.id;
      const busy = busyId === item.id;
      return <article className="mv2-trash-card" key={item.id}>
        <header><div><span className={`mv2-trash-status is-${item.status}`}>{item.status === 'failed' ? '저장 실패' : '삭제한 초안'}</span><h2>{draft.title || item.title}</h2><p>{item.reason || '보관된 경험 초안'}</p></div><time>{new Date(item.created_at).toLocaleString('ko-KR')}</time></header>
        {editing ? <div className="mv2-trash-form">
          <label>경험 분류<input value={draft.domain} onChange={(event) => update('domain', event.target.value)} /></label>
          <label>프로젝트·활동<input value={draft.project} onChange={(event) => update('project', event.target.value)} /></label>
          <label className="is-wide">제목<input value={draft.title} onChange={(event) => update('title', event.target.value)} /></label>
          <label className="is-wide">핵심 요약<textarea rows="3" value={draft.summary} onChange={(event) => update('summary', event.target.value)} /></label>
          <label className="is-wide">상황<textarea rows="3" value={draft.situation} onChange={(event) => update('situation', event.target.value)} /></label>
          <label>역할<input value={draft.role} onChange={(event) => update('role', event.target.value)} /></label>
          <label>핵심 역량<textarea rows="3" value={listToText(draft.skills)} onChange={(event) => update('skills', textToSkills(event.target.value))} /></label>
          <label className="is-wide">주요 행동<textarea rows="4" value={listToText(draft.actions)} onChange={(event) => update('actions', textToMarkdownLines(event.target.value))} /></label>
          <label className="is-wide">주요 성과<textarea rows="3" value={listToText(draft.results)} onChange={(event) => update('results', textToMarkdownLines(event.target.value))} /></label>
        </div> : <div className="mv2-trash-summary">
          {hasDraft
            ? <><p><strong>{draft.domain}</strong> · {draft.project}</p><p>{draft.summary || '요약이 없는 초안입니다.'}</p></>
            : <><p className="mv2-trash-original">{item.original_text || '입력한 텍스트가 없습니다.'}</p>{item.files?.length > 0 && <ul className="mv2-experience-intake__files">{item.files.map((file) => <li key={file.id}><span><strong>{file.filename}</strong><small>{(file.size_bytes / 1024 / 1024).toFixed(1)}MB · 보관된 원본 파일</small></span></li>)}</ul>}</>}
        </div>}
        <footer>
          <button type="button" className="mv2-button mv2-button--danger" disabled={busy} onClick={() => permanentlyDelete(item)}>완전 삭제</button>
          <div>{editing
            ? <><button type="button" className="mv2-button mv2-button--secondary" disabled={busy} onClick={() => { setEditingId(''); setForm(null); }}>취소</button><button type="button" className="mv2-button mv2-button--secondary" disabled={busy} onClick={() => saveEdit(item.id)}>수정 저장</button></>
            : hasDraft && <button type="button" className="mv2-button mv2-button--secondary" disabled={busy} onClick={() => startEditing(item)}>내용 확인·수정</button>}
            {hasDraft
              ? <button type="button" className="mv2-button mv2-button--primary" disabled={busy} onClick={() => saveAsExperience(item)}>{busy ? '저장 중…' : '내 경험으로 저장'}</button>
              : <button type="button" className="mv2-button mv2-button--primary" disabled={busy || !item.original_text} onClick={() => analyzeOriginal(item)}>{busy ? '분석 중…' : '경험 분석하기'}</button>}
          </div>
        </footer>
      </article>;
    })}</div>}
    <ExperienceProposalModal
      open={Boolean(analysisProposal)}
      proposal={analysisProposal}
      busy={analysisBusy}
      editing={analysisEditing}
      pendingCount={analysisProposal?.experiences?.filter((item) => !item.approved).length || 0}
      onClose={() => { if (!analysisBusy) { setAnalysisProposal(null); setAnalysisSourceItem(null); } }}
      onApprove={approveAnalyzedDraft}
      onChange={async (proposal) => { setAnalysisProposal(proposal); return proposal; }}
      onRemove={removeAnalyzedDraft}
      onEditingChange={setAnalysisEditing}
      onDiscardRemaining={() => { setAnalysisProposal(null); setAnalysisSourceItem(null); }}
      onSaveAll={saveAllAnalyzedDrafts}
    />
  </section>;
}

export default ExperienceTrashPage;
