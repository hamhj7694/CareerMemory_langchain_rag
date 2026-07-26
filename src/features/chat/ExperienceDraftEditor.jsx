import { useState } from 'react';
import { ExperienceRichList, ExperienceRichText } from '../experience/components/ExperienceRichText.jsx';
import { listToText, textToMarkdownLines, textToSkills } from '../experience/model/experienceContent.js';
import { ProposalEvidenceDialog } from './ProposalEvidenceDialog.jsx';
import { splitProposalSources } from './proposalMapper.js';

const collapsedDrafts = new Map();
const collapsedProjects = new Map();

export function ExperienceDraftEditor({ item, index, collapseKey, grouped = false, editing, approved, saving, onUpdate, onEdit, onSave, onCancel, onDelete, onApprove }) {
  const [collapsed, setCollapsed] = useState(() => collapsedDrafts.get(collapseKey) ?? false);
  const projectCollapseKey = `${collapseKey}:project`;
  const [projectCollapsed, setProjectCollapsed] = useState(() => collapsedProjects.get(projectCollapseKey) ?? false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const toggleCollapsed = () => setCollapsed((value) => {
    const next = !value;
    collapsedDrafts.set(collapseKey, next);
    return next;
  });
  const toggleProjectCollapsed = () => setProjectCollapsed((value) => {
    const next = !value;
    collapsedProjects.set(projectCollapseKey, next);
    return next;
  });
  const update = (key, value) => onUpdate(index, key, value);
  const sourceRefs = item.source_refs || [];
  const sourceGroups = splitProposalSources(sourceRefs);
  const actionButtons = approved
    ? <strong className="v2-draft-structure__saved">저장되었습니다</strong>
    : <>{editing
      ? <><button type="button" onClick={onCancel}>취소</button><button type="button" disabled={saving} onClick={onSave}>{saving ? '저장 중…' : '수정 저장'}</button></>
      : <button type="button" onClick={onEdit}>수정</button>}
      <button type="button" className="is-danger" disabled={saving} onClick={onDelete}>삭제</button>
      <button type="button" className="is-primary" disabled={saving} onClick={onApprove}>경험으로 저장</button></>;

  return <div className={`v2-draft-structure v2-draft-structure--detail ${editing ? 'is-editing' : ''}`}>
    {!grouped && <header className={`v2-draft-structure__domain-bar ${collapsed ? 'is-collapsed' : ''}`} onClick={toggleCollapsed}>
      <span>경험 분류</span>
      {editing ? <input aria-label={`경험 분류 ${index + 1}`} value={item.domain || ''} onClick={(event) => event.stopPropagation()} onChange={(event) => update('domain', event.target.value)} /> : <strong>{item.domain || '미분류 경험'}</strong>}
      <div className="v2-draft-structure__actions" onClick={(event) => event.stopPropagation()}>
        {actionButtons}
      </div>
      <button type="button" className="v2-draft-structure__collapse" aria-label={`${item.domain || '경험 분류'} ${collapsed ? '펼치기' : '접기'}`} aria-expanded={!collapsed} onClick={(event) => { event.stopPropagation(); toggleCollapsed(); }}>{collapsed ? '⌄' : '⌃'}</button>
    </header>}
    {(grouped || !collapsed) && <div className={`v2-draft-project ${grouped ? 'is-grouped' : ''} ${projectCollapsed ? 'is-collapsed' : ''}`}>
      <div className="v2-draft-project__bar" onClick={toggleProjectCollapsed}>
        <span>프로젝트·활동</span>
        {editing ? <input aria-label={`프로젝트·활동 ${index + 1}`} value={item.project || ''} onClick={(event) => event.stopPropagation()} onChange={(event) => update('project', event.target.value)} /> : <strong>{item.project || '새 프로젝트'}</strong>}
        {grouped && <div className="v2-draft-structure__actions" onClick={(event) => event.stopPropagation()}>{actionButtons}</div>}
        <button type="button" className="v2-draft-project__collapse" aria-label={`${item.project || '프로젝트·활동'} ${projectCollapsed ? '펼치기' : '접기'}`} aria-expanded={!projectCollapsed} onClick={(event) => { event.stopPropagation(); toggleProjectCollapsed(); }}>{projectCollapsed ? '⌄' : '⌃'}</button>
      </div>
      {!projectCollapsed && <article className="v2-draft-detail">
        {grouped && editing && <label className="v2-grouped-domain-edit">경험 분류<input aria-label={`경험 분류 ${index + 1}`} value={item.domain || ''} onChange={(event) => update('domain', event.target.value)} /></label>}
        {editing ? <input className="v2-draft-title-input" aria-label={`경험 제목 ${index + 1}`} value={item.title || ''} onChange={(event) => update('title', event.target.value)} /> : <h3>{item.title || '제목 미입력'}</h3>}
        <div className="v2-draft-detail-grid">
          <div className="v2-draft-detail-main">
            <section><h4><span>1.</span> 핵심 요약</h4>{editing ? <textarea rows="3" value={item.summary || ''} onChange={(event) => update('summary', event.target.value)} /> : <ExperienceRichText text={item.summary} empty="정리된 요약이 없습니다." />}</section>
            <section><h4><span>2.</span> 상황</h4>{editing ? <textarea rows="3" value={item.situation || ''} onChange={(event) => update('situation', event.target.value)} /> : <ExperienceRichText text={item.situation} empty="확인된 상황이 없습니다." />}</section>
            <section><h4><span>3.</span> 주요 행동</h4>{editing ? <textarea rows="4" value={listToText(item.actions)} onChange={(event) => update('actions', textToMarkdownLines(event.target.value))} placeholder="Markdown 목록과 줄바꿈을 사용할 수 있습니다." /> : <ExperienceRichList items={item.actions} empty="확인된 행동이 없습니다." />}</section>
            <section><h4><span>4.</span> 주요 성과</h4>{editing ? <textarea rows="3" value={listToText(item.results)} onChange={(event) => update('results', textToMarkdownLines(event.target.value))} placeholder="Markdown 목록과 줄바꿈을 사용할 수 있습니다." /> : <ExperienceRichList items={item.results} empty="확인된 결과가 없습니다." />}</section>
          </div>
          <aside>
            <section><h4>역할</h4>{editing ? <input value={item.role || ''} onChange={(event) => update('role', event.target.value)} /> : <p>{item.role || '확인된 역할이 없습니다.'}</p>}</section>
            <section><h4>핵심 역량</h4>{editing ? <textarea rows="3" value={listToText(item.skills)} onChange={(event) => update('skills', textToSkills(event.target.value))} placeholder="역량을 줄바꿈이나 쉼표로 구분해 주세요." /> : <div className="v2-skill-list">{item.skills?.length ? item.skills.map((skill) => <span key={skill}>{skill}</span>) : <p className="v2-draft-empty">확인된 역량이 없습니다.</p>}</div>}</section>
            {editing
              ? <section><h4>근거에서 확인된 내용</h4><textarea rows="4" value={listToText(item.facts)} onChange={(event) => update('facts', textToMarkdownLines(event.target.value))} placeholder="원본 근거에서 확인된 수치, 기간, 횟수와 성과를 입력해 주세요." /></section>
              : <details className="v2-draft-facts"><summary>근거에서 확인된 내용</summary><ExperienceRichList items={item.facts} empty="근거에서 확인된 내용이 없습니다." /></details>}
            <section className="v2-draft-evidence">
              <div className="v2-draft-evidence__heading"><h4>관련 근거</h4><strong>총 {sourceGroups.totalCount}개</strong></div>
              <p className="v2-draft-evidence__counts">대화·텍스트 {sourceGroups.conversationCount}개 · 파일 {sourceGroups.fileCount}개</p>
              <button type="button" className="v2-draft-evidence__open" disabled={!sourceGroups.totalCount} onClick={() => setEvidenceOpen(true)}>관련 근거 보기</button>
            </section>
          </aside>
        </div>
      </article>}
    </div>}
    {evidenceOpen && <ProposalEvidenceDialog sources={sourceRefs} onClose={() => setEvidenceOpen(false)} />}
  </div>;
}
