import { useState } from 'react';

const lines = (value) => String(value || '').split('\n').map((item) => item.trim()).filter(Boolean);
const joined = (value) => (value || []).join('\n');

function DetailList({ items, empty }) {
  return items?.length ? <ul>{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul> : <p className="v2-draft-empty">{empty}</p>;
}

function ExperienceDraftEditor({ item, index, editing, approved, saving, onUpdate, onEdit, onSave, onCancel, onDelete, onApprove }) {
  const [collapsed, setCollapsed] = useState(false);
  const update = (key, value) => onUpdate(index, key, value);
  return <div className={`v2-draft-structure v2-draft-structure--detail ${editing ? 'is-editing' : ''}`}>
    <header className={`v2-draft-structure__domain-bar ${collapsed ? 'is-collapsed' : ''}`} onClick={() => setCollapsed((value) => !value)}>
      <span>경험 분류</span>
      {editing ? <input aria-label={`경험 분류 ${index + 1}`} value={item.domain || ''} onClick={(event) => event.stopPropagation()} onChange={(event) => update('domain', event.target.value)} /> : <strong>{item.domain || '미분류 경험'}</strong>}
      <div className="v2-draft-structure__actions" onClick={(event) => event.stopPropagation()}>
        {approved ? <strong className="v2-draft-structure__saved">저장되었습니다</strong> : <>{editing ? <><button type="button" onClick={onCancel}>취소</button><button type="button" disabled={saving} onClick={onSave}>{saving ? '저장 중…' : '수정 저장'}</button></> : <button type="button" onClick={onEdit}>수정</button>}<button type="button" className="is-danger" disabled={saving} onClick={onDelete}>삭제</button><button type="button" className="is-primary" disabled={saving} onClick={onApprove}>경험으로 저장</button></>}
      </div>
      <button type="button" className="v2-draft-structure__collapse" aria-label={`${item.domain || '경험 분류'} ${collapsed ? '펼치기' : '접기'}`} aria-expanded={!collapsed} onClick={(event) => { event.stopPropagation(); setCollapsed((value) => !value); }}>{collapsed ? '⌄' : '⌃'}</button>
    </header>
    {!collapsed && <div className="v2-draft-project">
      <div><span>프로젝트·활동</span>{editing ? <input aria-label={`프로젝트·활동 ${index + 1}`} value={item.project || ''} onChange={(event) => update('project', event.target.value)} /> : <strong>{item.project || '새 프로젝트'}</strong>}</div>
      <article className="v2-draft-detail">
        {editing ? <input className="v2-draft-title-input" aria-label={`경험 제목 ${index + 1}`} value={item.title || ''} onChange={(event) => update('title', event.target.value)} /> : <h3>{item.title || '제목 미입력'}</h3>}
        <div className="v2-draft-detail-grid">
          <div className="v2-draft-detail-main">
            <section><h4>요약</h4>{editing ? <textarea rows="3" value={item.summary || ''} onChange={(event) => update('summary', event.target.value)} /> : <p>{item.summary || '정리된 요약이 없습니다.'}</p>}</section>
            <section><h4>상황</h4>{editing ? <textarea rows="3" value={item.situation || ''} onChange={(event) => update('situation', event.target.value)} /> : <p>{item.situation || '확인된 상황이 없습니다.'}</p>}</section>
            <section><h4>행동</h4>{editing ? <textarea rows="4" value={joined(item.actions)} onChange={(event) => update('actions', lines(event.target.value))} placeholder="행동을 줄바꿈으로 구분해 주세요." /> : <DetailList items={item.actions} empty="확인된 행동이 없습니다." />}</section>
            <section><h4>결과</h4>{editing ? <textarea rows="3" value={joined(item.results)} onChange={(event) => update('results', lines(event.target.value))} placeholder="결과를 줄바꿈으로 구분해 주세요." /> : <DetailList items={item.results} empty="확인된 결과가 없습니다." />}</section>
          </div>
          <aside>
            <section><h4>나의 역할</h4>{editing ? <input value={item.role || ''} onChange={(event) => update('role', event.target.value)} /> : <p>{item.role || '확인된 역할이 없습니다.'}</p>}</section>
            <section><h4>역량</h4>{editing ? <textarea rows="3" value={joined(item.skills)} onChange={(event) => update('skills', lines(event.target.value))} placeholder="역량을 줄바꿈으로 구분해 주세요." /> : <div className="v2-skill-list">{item.skills?.length ? item.skills.map((skill) => <span key={skill}>{skill}</span>) : <p className="v2-draft-empty">확인된 역량이 없습니다.</p>}</div>}</section>
            <section><h4>확인된 사실</h4>{editing ? <textarea rows="4" value={joined(item.facts)} onChange={(event) => update('facts', lines(event.target.value))} placeholder="사실을 줄바꿈으로 구분해 주세요." /> : <DetailList items={item.facts} empty="확인된 사실이 없습니다." />}</section>
            <section className="v2-draft-evidence"><h4>원본 근거</h4><p>원본 {item.evidenceCount || item.source_ref_ids?.length || 0}개와 연결됨</p></section>
          </aside>
        </div>
      </article>
    </div>}
  </div>;
}

export function InlineProposalCard({ proposal, onApprove, onReject, onChange, onRemoveExperience, onEditingChange }) {
  const [editing, setEditing] = useState(false);
  const [editingIndex, setEditingIndex] = useState(null);
  const [draft, setDraft] = useState(() => proposal ? structuredClone(proposal) : {});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  if (!proposal) return null;
  const activeDraft = draft && typeof draft === 'object' ? draft : proposal;
  const beginEditing = () => { setDraft(structuredClone(proposal)); setError(''); setEditing(true); onEditingChange?.(true); };
  const update = (key, value) => setDraft((current) => ({ ...(current ?? proposal), [key]: value }));
  const updateExperience = (index, key, value) => setDraft((current) => {
    const experiences = [...(current.experiences || [current])];
    experiences[index] = { ...experiences[index], [key]: value };
    return { ...current, experiences, ...(index === 0 ? { [key]: value } : {}) };
  });
  const beginExperienceEditing = (index) => { setDraft(structuredClone(activeDraft)); setEditingIndex(index); setError(''); onEditingChange?.(true); };
  const saveExperience = async () => {
    setSaving(true); setError('');
    try { const updated = await onChange(activeDraft); setDraft(updated); setEditingIndex(null); onEditingChange?.(false); return updated; }
    catch (reason) { setError(reason?.message ?? '초안을 저장하지 못했습니다.'); return null; }
    finally { setSaving(false); }
  };
  const cancelExperienceEditing = () => { setDraft(structuredClone(proposal)); setEditingIndex(null); setError(''); onEditingChange?.(false); };
  const approveExperience = async (index) => {
    if (!window.confirm('이 경험을 저장할까요?')) return;
    setSaving(true); setError('');
    try {
      const sourceIndex = activeDraft.experiences?.[index]?.sourceIndex ?? index;
      const draftId = activeDraft.experiences?.[index]?.draft_id;
      const nextProposal = await onApprove({ ...activeDraft, selection: { experience_indexes: [sourceIndex], ...(draftId ? { draft_id: draftId } : {}) } });
      if (nextProposal) setDraft(nextProposal);
    } catch (reason) { setError(reason?.message ?? '경험을 저장하지 못했습니다.'); }
    finally { setSaving(false); }
  };
  const removeExperience = async (index) => {
    if (!window.confirm('이 초안을 삭제할까요?')) return;
    const sourceIndex = activeDraft.experiences?.[index]?.sourceIndex ?? index;
    setSaving(true); setError('');
    try {
      // Pass the latest edited snapshot so parent-side deletion cannot restore stale values.
      if (onRemoveExperience) { const nextProposal = await onRemoveExperience(activeDraft, sourceIndex); if (nextProposal) setDraft(nextProposal); return; }
      const experiences = (activeDraft.experiences || []).filter((_, itemIndex) => itemIndex !== index);
      if (!experiences.length) onReject(proposal);
      else setDraft({ ...activeDraft, experiences });
    } catch (reason) { setError(reason?.message ?? '초안을 삭제하지 못했습니다.'); }
    finally { setSaving(false); }
  };
  const save = async () => {
    setSaving(true); setError('');
    try { const updated = await onChange(activeDraft); setDraft(updated); setEditing(false); onEditingChange?.(false); return updated; }
    catch (reason) { setError(reason?.message ?? '초안을 저장하지 못했습니다.'); return null; }
    finally { setSaving(false); }
  };
  const approveJob = async () => {
    setSaving(true); setError('');
    try { const latest = editing ? await onChange(activeDraft) : proposal; if (latest) await onApprove(latest); }
    catch (reason) { setError(reason?.message ?? '공고 분석을 시작하지 못했습니다.'); }
    finally { setSaving(false); }
  };

  if (proposal.kind === 'job') return <section className="v2-inline-proposal is-job">
    <div className="v2-inline-proposal__heading"><span>공고 분석 제안</span><em>AI 초안</em></div>
    {editing ? <div className="v2-proposal-form v2-job-draft-form">
      <label className="is-wide">공고 제목<input value={activeDraft.postingTitle || ''} onChange={(event) => update('postingTitle', event.target.value)} placeholder="예: 2026년 서비스 기획자 채용" /></label>
      <label>회사명<input value={activeDraft.companyName || ''} onChange={(event) => update('companyName', event.target.value)} placeholder="회사명" /></label>
      <label>직무명<input value={activeDraft.roleName || ''} onChange={(event) => update('roleName', event.target.value)} placeholder="직무명" /></label>
      <label className="is-wide">공고 링크<input type="url" value={activeDraft.sourceUrl || ''} onChange={(event) => update('sourceUrl', event.target.value)} placeholder="https://example.com/jobs/123" /></label>
      <label className="is-wide">채용공고 원문<textarea rows="8" value={activeDraft.postingContent || ''} onChange={(event) => update('postingContent', event.target.value)} placeholder="채용공고 원문을 입력해 주세요." /></label>
    </div> : <div className="v2-job-draft-summary"><h3>{proposal.postingTitle || '제목 미입력'}</h3><p>{[proposal.companyName || '회사 미입력', proposal.roleName || '직무 미입력'].join(' · ')}</p><div>{proposal.postingContent || '채용공고 원문이 없습니다.'}</div>{proposal.sourceUrl && <a href={proposal.sourceUrl} target="_blank" rel="noreferrer">원문 공고 열기</a>}</div>}
    {error && <p className="v2-proposal-error" role="alert">{error}</p>}
    <footer><button type="button" className="is-danger" onClick={() => onReject(proposal)}>삭제</button>{editing ? <><button type="button" onClick={() => { setDraft(structuredClone(proposal)); setEditing(false); setError(''); onEditingChange?.(false); }}>취소</button><button type="button" disabled={saving} onClick={save}>{saving ? '저장 중…' : '수정 저장'}</button></> : <button type="button" onClick={beginEditing}>내용 확인·수정</button>}<button type="button" className="is-primary" disabled={saving} onClick={approveJob}>{saving ? '처리 중…' : '분석 시작'}</button></footer>
  </section>;

  const experienceDrafts = activeDraft.experiences?.length ? activeDraft.experiences : [activeDraft];
  return <section className="v2-inline-proposal is-experience">
    <div className="v2-inline-proposal__heading"><span>경험 초안 · {experienceDrafts.length}개</span><em>{editing ? '수정 모드' : 'AI 초안'}</em></div>
    <div className="v2-experience-draft-list">{experienceDrafts.map((item, index) => <ExperienceDraftEditor key={`${item.title || 'draft'}-${index}`} item={item} index={index} approved={item.approved} saving={saving} editing={editingIndex === index} onUpdate={updateExperience} onEdit={() => beginExperienceEditing(index)} onSave={saveExperience} onCancel={cancelExperienceEditing} onDelete={() => removeExperience(index)} onApprove={() => approveExperience(index)} />)}</div>
    {error && <p className="v2-proposal-error" role="alert">{error}</p>}
  </section>;
}
