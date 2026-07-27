import { useState } from 'react';
import { ExperienceDraftEditor } from './ExperienceDraftEditor.jsx';

export function InlineProposalCard({ proposal, onApprove, onReject, onDiscardRemainingExperiences, onChange, onRemoveExperience, onEditingChange, showBatchActions = false }) {
  const [editing, setEditing] = useState(false);
  const [editingIndex, setEditingIndex] = useState(null);
  const [draft, setDraft] = useState(() => proposal ? structuredClone(proposal) : {});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [collapsedDomains, setCollapsedDomains] = useState(() => new Set());

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
  const discardRemainingExperiences = async () => {
    const pendingCount = (activeDraft.experiences || []).filter((item) => !item.approved).length;
    if (!pendingCount || !window.confirm('저장하지 않은 경험 초안을 모두 삭제할까요? 이미 저장된 경험은 유지됩니다.')) return;
    setSaving(true); setError('');
    try {
      const nextProposal = onDiscardRemainingExperiences
        ? await onDiscardRemainingExperiences(activeDraft)
        : await onReject(activeDraft);
      if (nextProposal) setDraft(nextProposal);
    }
    catch (reason) { setError(reason?.message ?? '남은 초안을 삭제하지 못했습니다.'); }
    finally { setSaving(false); }
  };
  const closeEmptyDraft = async () => {
    if (saving) return;
    setSaving(true);
    setError('');
    try {
      await onReject(activeDraft);
    } catch (reason) {
      setError(reason?.message ?? '초안을 닫지 못했습니다.');
    } finally {
      setSaving(false);
    }
  };
  const saveAllExperiences = async () => {
    const pendingIndexes = (activeDraft.experiences || []).map((item, index) => ({ item, index })).filter(({ item }) => !item.approved).map(({ index }) => index);
    if (!pendingIndexes.length || !window.confirm(`저장하지 않은 경험 초안 ${pendingIndexes.length}개를 모두 저장할까요?`)) return;
    setSaving(true); setError('');
    try {
      let current = activeDraft;
      for (const index of pendingIndexes) {
        const item = current.experiences?.[index];
        if (!item || item.approved) continue;
        const sourceIndex = item.sourceIndex ?? index;
        const draftId = item.draft_id;
        const nextProposal = await onApprove({ ...current, selection: { experience_indexes: [sourceIndex], ...(draftId ? { draft_id: draftId } : {}) } });
        if (!nextProposal) return;
        current = nextProposal;
        setDraft(nextProposal);
      }
    } catch (reason) { setError(reason?.message ?? '경험 초안을 모두 저장하지 못했습니다.'); }
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

  const experienceDrafts = Array.isArray(activeDraft.experiences) ? activeDraft.experiences : [activeDraft];
  const pendingExperienceCount = experienceDrafts.filter((item) => !item.approved).length;
  const domainGroups = experienceDrafts.reduce((groups, item, index) => {
    const domainName = String(item.domain || '미분류 경험').trim() || '미분류 경험';
    const domainKey = domainName.normalize('NFKC').replace(/\s+/g, ' ').toLocaleLowerCase('ko-KR');
    const current = groups.find((group) => group.key === domainKey);
    if (current) current.entries.push({ item, index });
    else groups.push({ key: domainKey, name: domainName, entries: [{ item, index }] });
    return groups;
  }, []);
  const toggleDomain = (domainKey) => {
    setCollapsedDomains((current) => {
      const next = new Set(current);
      if (next.has(domainKey)) next.delete(domainKey);
      else next.add(domainKey);
      return next;
    });
  };
  return <section className="v2-inline-proposal is-experience">
    <div className="v2-inline-proposal__heading"><span>경험 초안 · {experienceDrafts.length}개{activeDraft.analysisScope && <small>대화 {activeDraft.analysisScope.message_count}개 · 파일 {activeDraft.analysisScope.attachment_count}개 기준</small>}</span><em>{editing ? '수정 모드' : 'AI 초안'}</em></div>
    {experienceDrafts.length
      ? <div className="v2-experience-draft-list">{domainGroups.map((group) => {
          const domainCollapsed = collapsedDomains.has(group.key);
          return <section className={`v2-draft-domain-group ${domainCollapsed ? 'is-collapsed' : ''}`} key={group.key}>
            <header onClick={() => toggleDomain(group.key)}><span>경험 분류</span><strong>{group.name}</strong><small>{group.entries.length}개 프로젝트·활동</small><button type="button" aria-label={`${group.name} ${domainCollapsed ? '펼치기' : '접기'}`} aria-expanded={!domainCollapsed} onClick={(event) => { event.stopPropagation(); toggleDomain(group.key); }}>{domainCollapsed ? '⌄' : '⌃'}</button></header>
            {!domainCollapsed && <div>{group.entries.map(({ item, index }) => <ExperienceDraftEditor key={`${item.draft_id || item.sourceIndex || 'draft'}-${index}`} grouped collapseKey={`${proposal.id}:${item.draft_id || item.sourceIndex || `draft-${index}`}`} item={item} index={index} approved={item.approved} saving={saving} editing={editingIndex === index} onUpdate={updateExperience} onEdit={() => beginExperienceEditing(index)} onSave={saveExperience} onCancel={cancelExperienceEditing} onDelete={() => removeExperience(index)} onApprove={() => approveExperience(index)} />)}</div>}
          </section>;
        })}</div>
      : <div className="v2-draft-zero-state"><strong>정리할 경험 후보를 찾지 못했습니다.</strong><p>대화에 프로젝트, 역할, 행동이나 결과를 조금 더 구체적으로 남긴 뒤 다시 정리해 주세요.</p><button type="button" disabled={saving} onClick={closeEmptyDraft}>{saving ? '닫는 중…' : '초안 닫기'}</button></div>}
    {error && <p className="v2-proposal-error" role="alert">{error}</p>}
    {showBatchActions && experienceDrafts.length > 0 && <footer className="v2-draft-batch-footer">
      <span>저장하지 않은 초안 {pendingExperienceCount}개</span>
      <div>
        <button type="button" className="is-danger" disabled={!pendingExperienceCount || saving || editingIndex !== null} onClick={discardRemainingExperiences}>나머지 삭제</button>
        <button type="button" className="is-primary" disabled={!pendingExperienceCount || saving || editingIndex !== null} onClick={saveAllExperiences}>{saving ? '처리 중…' : '전체 저장'}</button>
      </div>
    </footer>}
  </section>;
}
