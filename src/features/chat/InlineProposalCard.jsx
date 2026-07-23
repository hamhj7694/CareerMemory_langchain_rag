import { useState } from 'react';

const lines = (value) => String(value || '').split('\n').map((item) => item.trim()).filter(Boolean);
const joined = (value) => (value || []).join('\n');

function DetailList({ items, empty }) {
  return items?.length ? <ul>{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul> : <p className="v2-draft-empty">{empty}</p>;
}

export function InlineProposalCard({ proposal, onApprove, onReject, onChange }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() => proposal ? { ...proposal } : {});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  if (!proposal) return null;

  const activeDraft = draft && typeof draft === 'object' ? draft : proposal;
  const beginEditing = () => {
    setDraft({ ...proposal });
    setError('');
    setEditing(true);
  };
  const update = (key, value) => setDraft((current) => ({ ...(current ?? proposal), [key]: value }));
  const save = async () => {
    setSaving(true);
    setError('');
    try {
      const updated = await onChange(activeDraft);
      setDraft(updated);
      setEditing(false);
      return updated;
    } catch (reason) {
      setError(reason?.message ?? '초안을 저장하지 못했습니다.');
      return null;
    } finally {
      setSaving(false);
    }
  };
  const approveJob = async () => {
    setSaving(true);
    setError('');
    try {
      const latest = editing ? await onChange(activeDraft) : proposal;
      if (!latest) return;
      await onApprove(latest);
    } catch (reason) {
      setError(reason?.message ?? '공고 분석을 시작하지 못했습니다.');
    } finally {
      setSaving(false);
    }
  };

  if (proposal.kind === 'job') return <section className="v2-inline-proposal is-job">
    <div className="v2-inline-proposal__heading"><span>공고 분석 제안</span><em>AI 초안</em></div>
    {editing ? <div className="v2-proposal-form v2-job-draft-form">
      <label className="is-wide">공고 제목<input value={activeDraft.postingTitle || ''} onChange={(event) => update('postingTitle', event.target.value)} placeholder="예: 2026년 서비스 기획자 채용" /></label>
      <label>회사명<input value={activeDraft.companyName || ''} onChange={(event) => update('companyName', event.target.value)} placeholder="회사명" /></label>
      <label>직무명<input value={activeDraft.roleName || ''} onChange={(event) => update('roleName', event.target.value)} placeholder="직무명" /></label>
      <label className="is-wide">공고 링크<input type="url" value={activeDraft.sourceUrl || ''} onChange={(event) => update('sourceUrl', event.target.value)} placeholder="https://example.com/jobs/123" /></label>
      <label className="is-wide">채용공고 원문<textarea rows="8" value={activeDraft.postingContent || ''} onChange={(event) => update('postingContent', event.target.value)} placeholder="채용공고 원문을 입력해 주세요." /></label>
    </div> : <div className="v2-job-draft-summary">
      <h3>{proposal.postingTitle || '제목 미입력'}</h3>
      <p>{[proposal.companyName || '회사 미입력', proposal.roleName || '직무 미입력'].join(' · ')}</p>
      <div>{proposal.postingContent || '채용공고 원문이 없습니다.'}</div>
      {proposal.sourceUrl && <a href={proposal.sourceUrl} target="_blank" rel="noreferrer">원문 공고 열기</a>}
    </div>}
    {error && <p className="v2-proposal-error" role="alert">{error}</p>}
    <footer>
      <button type="button" className="is-danger" onClick={() => onReject(proposal)}>삭제</button>
      {editing
        ? <><button type="button" onClick={() => { setDraft(proposal); setEditing(false); setError(''); }}>취소</button><button type="button" disabled={saving} onClick={save}>{saving ? '저장 중…' : '수정 저장'}</button></>
        : <button type="button" onClick={beginEditing}>내용 확인·수정</button>}
      <button type="button" className="is-primary" disabled={saving} onClick={approveJob}>{saving ? '처리 중…' : '분석 시작'}</button>
    </footer>
  </section>;

  return <section className="v2-inline-proposal is-experience">
    <div className="v2-inline-proposal__heading"><span>경험 초안</span><em>{editing ? '수정 모드' : 'AI 초안'}</em></div>
    <div className={`v2-draft-structure v2-draft-structure--detail ${editing ? 'is-editing' : ''}`}>
      <header><span>경험 분류</span>{editing ? <input aria-label="경험 분류" value={activeDraft.domain || ''} onChange={(event) => update('domain', event.target.value)} /> : <strong>{proposal.domain || '미분류 경험'}</strong>}</header>
      <div className="v2-draft-project">
        <div><span>프로젝트·활동</span>{editing ? <input aria-label="프로젝트·활동" value={activeDraft.project || ''} onChange={(event) => update('project', event.target.value)} /> : <strong>{proposal.project || '새 프로젝트'}</strong>}</div>
        <article className="v2-draft-detail">
          {editing ? <input className="v2-draft-title-input" aria-label="경험 제목" value={activeDraft.title || ''} onChange={(event) => update('title', event.target.value)} /> : <h3>{proposal.title || '제목 미입력'}</h3>}
          <div className="v2-draft-detail-grid">
            <div className="v2-draft-detail-main">
              <section><h4>요약</h4>{editing ? <textarea rows="3" value={activeDraft.summary || ''} onChange={(event) => update('summary', event.target.value)} /> : <p>{proposal.summary || '정리된 요약이 없습니다.'}</p>}</section>
              <section><h4>상황</h4>{editing ? <textarea rows="3" value={activeDraft.situation || ''} onChange={(event) => update('situation', event.target.value)} /> : <p>{proposal.situation || '확인된 상황이 없습니다.'}</p>}</section>
              <section><h4>행동</h4>{editing ? <textarea rows="4" value={joined(activeDraft.actions)} onChange={(event) => update('actions', lines(event.target.value))} placeholder="행동을 줄바꿈으로 구분해 주세요." /> : <DetailList items={proposal.actions} empty="확인된 행동이 없습니다." />}</section>
              <section><h4>결과</h4>{editing ? <textarea rows="3" value={joined(activeDraft.results)} onChange={(event) => update('results', lines(event.target.value))} placeholder="결과를 줄바꿈으로 구분해 주세요." /> : <DetailList items={proposal.results} empty="확인된 결과가 없습니다." />}</section>
            </div>
            <aside>
              <section><h4>나의 역할</h4>{editing ? <input value={activeDraft.role || ''} onChange={(event) => update('role', event.target.value)} /> : <p>{proposal.role || '확인된 역할이 없습니다.'}</p>}</section>
              <section><h4>역량</h4>{editing ? <textarea rows="3" value={joined(activeDraft.skills)} onChange={(event) => update('skills', lines(event.target.value))} placeholder="역량을 줄바꿈으로 구분해 주세요." /> : <div className="v2-skill-list">{proposal.skills?.length ? proposal.skills.map((skill) => <span key={skill}>{skill}</span>) : <p className="v2-draft-empty">확인된 역량이 없습니다.</p>}</div>}</section>
              <section><h4>확인된 사실</h4>{editing ? <textarea rows="4" value={joined(activeDraft.facts)} onChange={(event) => update('facts', lines(event.target.value))} placeholder="사실을 줄바꿈으로 구분해 주세요." /> : <DetailList items={proposal.facts} empty="확인된 사실이 없습니다." />}</section>
              <section className="v2-draft-evidence"><h4>원본 근거</h4><p>원본 {proposal.evidenceCount || 0}개와 연결됨</p></section>
            </aside>
          </div>
        </article>
      </div>
    </div>
    {error && <p className="v2-proposal-error" role="alert">{error}</p>}
    <footer><button type="button" className="is-danger" onClick={() => onReject(proposal)}>삭제</button>{editing ? <><button type="button" onClick={() => { setDraft(proposal); setEditing(false); setError(''); }}>취소</button><button type="button" className="is-primary" disabled={saving} onClick={save}>{saving ? '저장 중…' : '수정 저장'}</button></> : <><button type="button" onClick={beginEditing}>수정</button><button type="button" className="is-primary" onClick={() => onApprove(proposal)}>경험으로 저장</button></>}</footer>
  </section>;
}
