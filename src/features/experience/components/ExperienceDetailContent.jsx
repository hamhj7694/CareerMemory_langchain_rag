import { listToText, textToMarkdownLines } from '../model/experienceContent.js';
import {
  editableCustomBlocks,
  metricsToText,
  periodToText,
  textToMetrics,
  textToPeriod,
} from '../model/experienceDetailModel.js';
import { ExperienceRichList, ExperienceRichText } from './ExperienceRichText.jsx';
import { ContentDocumentRenderer } from './ContentBlockRenderer.jsx';

const emptyText = '저장된 내용이 없습니다.';
const editableBlockTypes = new Set(['paragraph', 'list', 'callout']);

const newEditableBlock = () => ({
  id: `custom-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`}`,
  type: 'paragraph',
  data: { title: '추가 정보', text: '' },
  origin: 'user',
  review_status: 'confirmed',
  visibility: 'visible',
  schema_version: 1,
});

function DetailCard({ title, children, tone, className = '' }) {
  return (
    <section className={`detail-card${tone ? ` ${tone}` : ''} ${className}`.trim()}>
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function DirectInputToggle({ active, label, onClick }) {
  const actionLabel = active ? `${label} 목록에서 선택` : `${label} 직접 입력`;
  return (
    <button type="button" className="detail-editor__direct-button" aria-label={actionLabel} aria-pressed={active} title={actionLabel} onClick={onClick}>
      {active ? (
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m15.5 15.5 4 4" /></svg>
      ) : (
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 20 4.2-1 10.6-10.6a2.1 2.1 0 0 0-3-3L5.2 16Z" /><path d="m14.8 6.4 2.8 2.8M4 20l1.2-4" /></svg>
      )}
    </button>
  );
}

function EvidenceCard({ count, isNew, openSources, manage }) {
  return (
    <DetailCard title="원본 근거" tone={manage ? 'evidence' : undefined}>
      <p>원본 {count}개와 연결됨</p>
      {!isNew && (manage
        ? <button onClick={openSources}>원본 관리 →</button>
        : <button className="ui-button ui-button--secondary" onClick={openSources}>원본 관리</button>)}
    </DetailCard>
  );
}

export function ExperienceDetailContent({
  editing,
  item,
  form,
  onFormChange,
  skillsText,
  onSkillsTextChange,
  structure,
  availableProjects,
  domainDirectInput,
  projectDirectInput,
  domainInput,
  projectInput,
  onDomainInputChange,
  onProjectInputChange,
  onUpdateDomain,
  onUpdateProject,
  onToggleDomainInput,
  onToggleProjectInput,
  isNew,
  openSources,
}) {
  if (!editing) {
    const customBlocks = editableCustomBlocks(item.contentBlocks);
    const periodText = periodToText(item.period);
    const metricsText = metricsToText(item.metrics);
    const hasMainContent = Boolean(
      item.summary?.trim()
      || item.situation?.trim()
      || item.actions?.some(Boolean)
      || item.results?.some(Boolean)
      || item.missingInformation?.some(Boolean)
      || customBlocks.length,
    );
    return (
      <div className="detail-grid detail-grid--compact">
        <main>
          {item.summary?.trim() && <DetailCard title="요약" tone="lead"><ExperienceRichText text={item.summary} /></DetailCard>}
          {item.situation?.trim() && <DetailCard title="상황"><ExperienceRichText text={item.situation} /></DetailCard>}
          {item.actions?.some(Boolean) && <DetailCard title="행동"><ExperienceRichList items={item.actions} /></DetailCard>}
          {item.results?.some(Boolean) && <DetailCard title="결과"><ExperienceRichList items={item.results} /></DetailCard>}
          {item.missingInformation?.some(Boolean) && <DetailCard title="확인이 필요한 정보" tone="attention"><ExperienceRichList items={item.missingInformation} /></DetailCard>}
          {customBlocks.length > 0 && <ContentDocumentRenderer blocks={customBlocks} />}
          {!hasMainContent && <DetailCard title="경험 내용"><p>{emptyText}</p></DetailCard>}
        </main>
        <aside>
          {item.role?.trim() && <DetailCard title="내 직군·직업 및 역할"><p style={{ whiteSpace: 'pre-wrap' }}>{item.role}</p></DetailCard>}
          {item.skills?.length > 0 && <DetailCard title="역량"><div className="skill-list">{item.skills.map((value) => <span key={value}>{value}</span>)}</div></DetailCard>}
          {item.facts?.some(Boolean) && <DetailCard title="근거에서 확인된 내용"><ExperienceRichList items={item.facts} /></DetailCard>}
          {periodText && <DetailCard title="기간"><ExperienceRichText text={periodText} /></DetailCard>}
          {metricsText && <DetailCard title="수치 성과"><ExperienceRichText text={metricsText} /></DetailCard>}
          <EvidenceCard count={item.evidenceIds.length} isNew={isNew} openSources={openSources} manage />
        </aside>
      </div>
    );
  }

  const systemBlocks = (form.contentBlocks || []).filter((block) => block.origin === 'system_projection');
  const editableBlocks = editableCustomBlocks(form.contentBlocks);
  const setEditableBlocks = (blocks) => onFormChange('contentBlocks', [...systemBlocks, ...blocks]);
  const updateEditableBlock = (index, updater) => setEditableBlocks(editableBlocks.map((block, blockIndex) => blockIndex === index ? updater(block) : block));
  const moveEditableBlock = (index, offset) => {
    const target = index + offset;
    if (target < 0 || target >= editableBlocks.length) return;
    const next = [...editableBlocks];
    [next[index], next[target]] = [next[target], next[index]];
    setEditableBlocks(next);
  };

  return (
    <div className="detail-grid detail-grid--edit">
      <main>
        <DetailCard title="요약" tone="lead">
          <textarea rows="4" value={form.summary ?? ''} placeholder="이 경험을 정리해 주세요. 일반 문장이나 마크업(예: **핵심 결과**, 줄바꿈)을 사용할 수 있습니다." onChange={(event) => onFormChange('summary', event.target.value)} />
        </DetailCard>
        <DetailCard title="상황">
          <textarea rows="4" value={form.situation ?? ''} placeholder="경험이 발생한 배경과 맥락을 적어 주세요. 목록(예: - 배경)이나 강조 마크업을 사용할 수 있습니다." onChange={(event) => onFormChange('situation', event.target.value)} />
        </DetailCard>
        <DetailCard title="행동">
          <textarea rows="6" value={listToText(form.actions)} placeholder="마크업 문법으로 입력할 수 있습니다. 예: 1. 내용 / - 내용" onChange={(event) => onFormChange('actions', textToMarkdownLines(event.target.value))} />
        </DetailCard>
        <DetailCard title="결과">
          <textarea rows="6" value={listToText(form.results)} placeholder="마크업 문법으로 입력할 수 있습니다. 예: 1. 내용 / - 내용" onChange={(event) => onFormChange('results', textToMarkdownLines(event.target.value))} />
        </DetailCard>
        <DetailCard title="확인이 필요한 정보">
          <textarea rows="4" value={listToText(form.missingInformation)} placeholder="추가 확인이 필요한 내용을 한 줄에 하나씩 입력해 주세요." onChange={(event) => onFormChange('missingInformation', textToMarkdownLines(event.target.value))} />
        </DetailCard>
        <DetailCard title="추가 정보 블록" className="detail-block-editor">
          <p className="detail-block-editor__guide">정해진 항목에 들어가지 않는 맥락도 블록으로 추가해 그대로 보존할 수 있습니다.</p>
          {editableBlocks.map((block, index) => {
            const type = block.type || block.block_type || 'custom';
            const supported = editableBlockTypes.has(type);
            const data = block.data || {};
            return <article className="detail-block-editor__item" key={block.id || `custom-block-${index}`}>
              <header><strong>블록 {index + 1}</strong><span><button type="button" disabled={index === 0} onClick={() => moveEditableBlock(index, -1)} aria-label={`블록 ${index + 1} 위로 이동`}>↑</button><button type="button" disabled={index === editableBlocks.length - 1} onClick={() => moveEditableBlock(index, 1)} aria-label={`블록 ${index + 1} 아래로 이동`}>↓</button><button type="button" className="is-danger" onClick={() => setEditableBlocks(editableBlocks.filter((_, blockIndex) => blockIndex !== index))}>삭제</button></span></header>
              <label>형식<select value={supported ? type : 'custom'} onChange={(event) => updateEditableBlock(index, (current) => ({ ...current, type: event.target.value, data: { title: current.data?.title || '추가 정보', ...(event.target.value === 'paragraph' ? { text: current.data?.text || '' } : { items: current.data?.items || [] }) } }))}><option value="paragraph">문단</option><option value="list">목록</option><option value="callout">강조 메모</option>{!supported && <option value="custom">사용자 정의(읽기 전용)</option>}</select></label>
              <label>제목<input value={data.title || ''} onChange={(event) => updateEditableBlock(index, (current) => ({ ...current, data: { ...(current.data || {}), title: event.target.value } }))} /></label>
              {supported && type === 'paragraph' && <label>내용<textarea rows="4" value={data.text || ''} onChange={(event) => updateEditableBlock(index, (current) => ({ ...current, data: { ...(current.data || {}), text: event.target.value } }))} /></label>}
              {supported && ['list', 'callout'].includes(type) && <label>내용<textarea rows="4" value={listToText(data.items || [])} placeholder="한 줄에 하나씩 입력해 주세요." onChange={(event) => updateEditableBlock(index, (current) => ({ ...current, data: { ...(current.data || {}), items: textToMarkdownLines(event.target.value) } }))} /></label>}
              {!supported && <pre>{JSON.stringify(data, null, 2)}</pre>}
            </article>;
          })}
          <button type="button" className="ui-button ui-button--secondary" onClick={() => setEditableBlocks([...editableBlocks, newEditableBlock()])}>+ 정보 블록 추가</button>
        </DetailCard>
      </main>
      <aside>
        <DetailCard title="분류">
          <div className="detail-editor__classification">
            <label>
              <span className="detail-editor__field-heading">경험 분류 <DirectInputToggle active={domainDirectInput} label="경험 분류" onClick={onToggleDomainInput} /></span>
              {domainDirectInput
                ? <input value={domainInput} placeholder="예: 사이드 프로젝트" onChange={(event) => onDomainInputChange(event.target.value)} />
                : <select value={form.domainId} onChange={(event) => onUpdateDomain(event.target.value)}><option value="">선택</option>{structure.map((domain) => <option value={domain.id} key={domain.id}>{domain.name}</option>)}</select>}
            </label>
            <label>
              <span className="detail-editor__field-heading">프로젝트·활동 <DirectInputToggle active={projectDirectInput} label="프로젝트·활동" onClick={onToggleProjectInput} /></span>
              {projectDirectInput
                ? <input value={projectInput} placeholder="예: 신규 서비스 출시" onChange={(event) => onProjectInputChange(event.target.value)} />
                : <select value={form.projectId} onChange={(event) => onUpdateProject(event.target.value)} disabled={!form.domainId}><option value="">선택</option>{availableProjects.map((project) => <option value={project.id} key={project.id}>{project.name}</option>)}</select>}
            </label>
          </div>
          <label>제목<input value={form.title ?? ''} placeholder="경험 제목을 입력해 주세요." onChange={(event) => onFormChange('title', event.target.value)} /></label>
        </DetailCard>
        <DetailCard title="내 직군·직업 및 역할">
          <label>역할<input value={form.role ?? ''} placeholder="예: 서비스 기획" onChange={(event) => onFormChange('role', event.target.value)} /></label>
        </DetailCard>
        <DetailCard title="역량">
          <textarea rows="4" value={skillsText} placeholder="줄바꿈이나 쉼표로 여러 역량을 입력할 수 있습니다." onChange={(event) => onSkillsTextChange(event.target.value)} />
        </DetailCard>
        <DetailCard title="근거에서 확인된 내용">
          <textarea rows="4" value={listToText(form.facts)} placeholder="원본 근거에서 확인된 수치, 기간, 횟수와 성과를 입력해 주세요." onChange={(event) => onFormChange('facts', textToMarkdownLines(event.target.value))} />
        </DetailCard>
        <DetailCard title="기간">
          <textarea rows="2" value={periodToText(form.period)} placeholder="예: 2026-01 ~ 2026-06" onChange={(event) => onFormChange('period', textToPeriod(event.target.value))} />
        </DetailCard>
        <DetailCard title="수치 성과">
          <textarea rows="4" value={metricsToText(form.metrics)} placeholder="한 줄에 하나씩 입력해 주세요." onChange={(event) => onFormChange('metrics', textToMetrics(event.target.value))} />
        </DetailCard>
        <EvidenceCard count={item.evidenceIds.length} isNew={isNew} openSources={openSources} />
      </aside>
    </div>
  );
}
