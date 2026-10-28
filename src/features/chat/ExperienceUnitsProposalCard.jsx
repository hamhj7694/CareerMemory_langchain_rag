import { useEffect, useState } from 'react';
import { chatExperienceApi } from '../../api/chatExperienceApi.js';
import { experienceExtractionApi } from '../../api/experienceExtractionApi.js';

const lines = (value) => Array.isArray(value) ? value.join('\n') : '';
const splitLines = (value) => value.split('\n').map((item) => item.trim()).filter(Boolean);

export function ExperienceUnitsProposalCard({
  proposal,
  onApprove,
  onReject,
  onChange,
  onRemoveExperience,
}) {
  const [editingId, setEditingId] = useState(null);
  const [draftUnits, setDraftUnits] = useState(proposal.units || []);
  const [unresolvedSpans, setUnresolvedSpans] = useState([]);
  const [spanError, setSpanError] = useState('');
  const [approvingAll, setApprovingAll] = useState(false);
  useEffect(() => {
    const unresolvedIds = new Set(proposal.coverage?.unresolved_span_ids || []);
    if (!unresolvedIds.size) {
      return undefined;
    }
    let active = true;
    const loader = proposal.conversationId && proposal.chatMessageId
      ? () => chatExperienceApi.getUnitsProposalSpans(proposal.conversationId, proposal.chatMessageId)
      : (proposal.analysisRunId
          ? () => experienceExtractionApi.getUnitsProposalSpans(proposal.analysisRunId)
          : null);
    if (!loader) return undefined;
    loader()
      .then((result) => {
        if (active) setUnresolvedSpans((result.items || []).filter((item) => unresolvedIds.has(item.id)));
      })
      .catch(() => {
        if (active) setSpanError('검토 필요 원문을 불러오지 못했습니다.');
      });
    return () => { active = false; };
  }, [proposal.analysisRunId, proposal.chatMessageId, proposal.conversationId, proposal.coverage?.unresolved_span_ids]);

  const update = (unitId, field, value) => setDraftUnits((current) => current.map((unit) => (
    unit.unitId === unitId ? { ...unit, [field]: value } : unit
  )));
  const save = async () => {
    await onChange({ ...proposal, units: draftUnits });
    setEditingId(null);
  };
  const approveAll = async () => {
    setApprovingAll(true);
    try {
      let current = proposal;
      for (const unit of current.units.filter((item) => !item.approved)) {
        current = await onApprove({ ...current, selection: { unit_id: unit.unitId } }) || current;
      }
    } finally {
      setApprovingAll(false);
    }
  };
  const coverage = proposal.coverage || {};
  const pending = draftUnits.filter((unit) => !unit.approved);

  return <section className="v2-experience-units" data-contract="experience-units-v2">
    <header className="v2-experience-units__header">
      <div>
        <strong>경험 단위 · {draftUnits.length}개</strong>
        <small>관련된 행동과 결과만 한 묶음으로 분리했습니다.</small>
      </div>
      <span>{coverage.processing_status === 'complete' ? '전체 구간 처리' : `확인 필요 ${coverage.unresolved_span_ids?.length || 0}`}</span>
    </header>
    <div className="v2-experience-units__coverage" aria-label="원문 처리 현황">
      <span>경험 {coverage.experience_span_count || 0}</span>
      <span>공고 {coverage.job_span_count || 0}</span>
      <span>공통 맥락 {coverage.context_span_count || 0}</span>
      <span>기타 {coverage.other_span_count || 0}</span>
      <span className={coverage.unresolved_span_ids?.length ? 'has-warning' : ''}>검토 필요 {coverage.unresolved_span_ids?.length || 0}</span>
    </div>

    <div className="v2-experience-units__list">
      {draftUnits.map((unit, index) => {
        const editing = editingId === unit.unitId;
        const updatesExisting = unit.saveStrategy?.operation === 'update';
        return <article className={`v2-experience-unit${unit.approved ? ' is-approved' : ''}`} key={unit.unitId}>
          <div className="v2-experience-unit__path">
            <span>{unit.domain || '미분류'}</span><span>›</span><span>{unit.project || '프로젝트 미지정'}</span>
            <span className={`v2-experience-unit__save-mode ${updatesExisting ? 'is-update' : 'is-create'}`}>
              {updatesExisting ? '기존 경험 업데이트' : '새 경험 생성'}
            </span>
          </div>
          {editing ? <div className="v2-experience-unit__editor">
            <label>경험 제목<input value={unit.title || ''} onChange={(event) => update(unit.unitId, 'title', event.target.value)} /></label>
            <label>핵심 요약<textarea value={unit.summary || ''} onChange={(event) => update(unit.unitId, 'summary', event.target.value)} /></label>
            <label>행동<textarea value={lines(unit.actions)} onChange={(event) => update(unit.unitId, 'actions', splitLines(event.target.value))} /></label>
            <label>결과<textarea value={lines(unit.results)} onChange={(event) => update(unit.unitId, 'results', splitLines(event.target.value))} /></label>
          </div> : <>
            <h3>{unit.title || '제목 없는 경험'}</h3>
            {unit.summary && <p>{unit.summary}</p>}
            {unit.actions?.length > 0 && <section><h4>행동</h4><ul>{unit.actions.map((item) => <li key={item}>{item}</li>)}</ul></section>}
            {unit.results?.length > 0 && <section><h4>결과</h4><ul>{unit.results.map((item) => <li key={item}>{item}</li>)}</ul></section>}
            {unit.skills?.length > 0 && <div className="v2-experience-unit__tags">{unit.skills.map((item) => <span key={item}>{item}</span>)}</div>}
            {updatesExisting && <p className="v2-experience-unit__merge-notice">
              <strong>{unit.saveStrategy.experience_title || '기존 경험'}</strong>에 새로운 행동·성과·근거를 중복 없이 추가합니다.
            </p>}
            {!updatesExisting && unit.reusedSkills?.length > 0 && <p className="v2-experience-unit__merge-notice">
              기존 기술 표기 재사용: {unit.reusedSkills.join(' · ')}
            </p>}
            {unit.evidencePreview && <details><summary>연결된 원문 구간 {unit.primarySpanIds?.length || 0}개</summary><pre>{unit.evidencePreview}</pre></details>}
          </>}
          <footer>
            {!unit.approved && <button type="button" className="is-danger" onClick={() => onRemoveExperience(proposal, index)}>삭제</button>}
            {!unit.approved && (editing
              ? <><button type="button" onClick={() => { setDraftUnits(proposal.units || []); setEditingId(null); }}>취소</button><button type="button" onClick={save}>수정 저장</button></>
              : <button type="button" onClick={() => setEditingId(unit.unitId)}>수정</button>)}
            <button type="button" className="is-primary" disabled={unit.approved || editing} onClick={() => onApprove({ ...proposal, selection: { unit_id: unit.unitId } })}>
              {unit.approved
                ? (unit.saveOperation === 'updated' ? '업데이트됨' : '저장됨')
                : (updatesExisting ? '기존 경험에 추가' : '경험으로 저장')}
            </button>
          </footer>
        </article>;
      })}
      {(unresolvedSpans.length > 0 || spanError) && <details className="v2-experience-units__unresolved">
        <summary>검토 필요 원문 {unresolvedSpans.length || coverage.unresolved_span_ids?.length || 0}개</summary>
        {spanError && <p>{spanError}</p>}
        {unresolvedSpans.map((span) => <blockquote key={span.id}><small>{span.source_title}</small>{span.text}</blockquote>)}
      </details>}
    </div>
    <footer className="v2-experience-units__footer">
      <span>저장하지 않은 단위 {pending.length}개</span>
      {pending.length > 0 && <div>
        <button type="button" className="is-danger" disabled={approvingAll} onClick={() => onReject(proposal)}>나머지 삭제</button>
        <button type="button" className="is-primary" disabled={approvingAll || Boolean(editingId)} onClick={approveAll}>
          {approvingAll ? '저장 중…' : '전체 저장'}
        </button>
      </div>}
    </footer>
  </section>;
}
