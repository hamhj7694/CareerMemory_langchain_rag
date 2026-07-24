import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { experienceApi } from '../api/experienceApi.js';
import { sourceApi } from '../api/sourceApi.js';
import { v2ChatApi } from '../api/v2ChatApi.js';
import ErrorState from '../components/common/ErrorState.jsx';
import LoadingState from '../components/common/LoadingState.jsx';
import { SourceManagerModal } from '../components/memory/SourceManagerModal.jsx';
import { experienceRepository } from '../features/experience/api/experienceRepository.js';
import { createEmptyExperience } from '../features/experience/model/experienceMapper.js';
import { useDirtyBlocker } from '../hooks/useDirtyBlocker.js';
import '../styles/memory.css';

const join = (items) => (items ?? []).join('\n');
const splitLines = (text) => String(text ?? '').split('\n');
const splitSkills = (text) => String(text ?? '').split(/[\n,]/).map((value) => value.trim()).filter(Boolean);
const emptyText = '저장된 내용이 없습니다.';

function DetailCard({ title, children, tone, className = '' }) {
  return (
    <section className={`detail-card${tone ? ` ${tone}` : ''} ${className}`.trim()}>
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function DetailText({ value }) {
  return <p style={{ whiteSpace: 'pre-wrap' }}>{value || emptyText}</p>;
}

function renderInline(text) {
  const nodes = [];
  const source = String(text ?? '');
  const pattern = /(\*\*.+?\*\*|\*.+?\*|`.+?`)/g;
  let lastIndex = 0;
  let match;
  while ((match = pattern.exec(source)) !== null) {
    const index = match.index;
    if (index > lastIndex) nodes.push(source.slice(lastIndex, index));
    const token = match[0];
    if (token.startsWith('**')) nodes.push(<strong key={`${index}-strong`}>{token.slice(2, -2)}</strong>);
    else if (token.startsWith('*')) nodes.push(<em key={`${index}-em`}>{token.slice(1, -1)}</em>);
    else nodes.push(<code key={`${index}-code`}>{token.slice(1, -1)}</code>);
    lastIndex = index + token.length;
  }
  if (lastIndex < source.length) nodes.push(source.slice(lastIndex));
  return nodes;
}

function MarkdownBlocks({ text, empty = emptyText }) {
  const lines = String(text ?? '').split('\n');
  const blocks = [];
  let paragraph = [];
  let listItems = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(<p key={`p-${blocks.length}`}>{paragraph.map((line, index) => <span key={`${line}-${index}`}>{index > 0 && <br />}{renderInline(line)}</span>)}</p>);
    paragraph = [];
  };

  const buildList = (items) => {
    const roots = [];
    const stack = [];
    const indentSize = 2;
    items.forEach((item, index) => {
      const level = Math.max(0, Math.floor(item.indent / indentSize));
      const node = { ...item, children: [] };
      while (stack.length > level) stack.pop();
      if (stack.length === 0) roots.push(node);
      else stack[stack.length - 1].children.push(node);
      stack[level] = node;
      stack.length = level + 1;
      node.key = `${item.text}-${index}`;
    });

    const renderNodes = (nodes) => {
      if (!nodes.length) return null;
      const groups = [];
      nodes.forEach((node) => {
        const current = groups[groups.length - 1];
        if (!current || current.ordered !== node.ordered) groups.push({ ordered: node.ordered, nodes: [node] });
        else current.nodes.push(node);
      });

      return groups.map((group, groupIndex) => {
        const List = group.ordered ? 'ol' : 'ul';
        return (
          <List key={`${group.ordered ? 'ol' : 'ul'}-${groupIndex}`}>
            {group.nodes.map((node) => (
              <li key={node.key}>
                {renderInline(node.text)}
                {node.children.length ? renderNodes(node.children) : null}
              </li>
            ))}
          </List>
        );
      });
    };

    return renderNodes(roots);
  };

  for (const rawLine of lines) {
    const line = rawLine ?? '';
    if (!line.trim()) {
      flushParagraph();
      if (listItems.length) {
        blocks.push(<div key={`ul-${blocks.length}`}>{buildList(listItems)}</div>);
        listItems = [];
      }
      continue;
    }

    const bulletMatch = line.match(/^(\s*)([-*+])\s+(.*)$/);
    const orderedMatch = line.match(/^(\s*)(\d+)[.)]\s+(.*)$/);
    if (bulletMatch || orderedMatch) {
      flushParagraph();
      const indent = bulletMatch ? bulletMatch[1].length : orderedMatch[1].length;
      const textValue = bulletMatch ? bulletMatch[3] : orderedMatch[3];
      listItems.push({ indent, text: textValue, ordered: Boolean(orderedMatch) });
    } else {
      if (listItems.length) {
        blocks.push(<div key={`ul-${blocks.length}`}>{buildList(listItems)}</div>);
        listItems = [];
      }
      paragraph.push(line);
    }
  }
  flushParagraph();
  if (listItems.length) blocks.push(<div key={`ul-${blocks.length}`}>{buildList(listItems)}</div>);
  return blocks.length ? blocks : <p>{empty}</p>;
}

function MarkdownList({ items }) {
  const text = join(items);
  return <MarkdownBlocks text={text} />;
}

export function MemoryDetailPage({ experienceId: experienceIdProp, initialDraft = null, initialDomainId = '', initialProjectId = '', onClose, onSaved } = {}) {
  const { experienceId: routeExperienceId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const experienceId = experienceIdProp || routeExperienceId;
  const isNew = experienceId === 'new';

  const [item, setItem] = useState(null);
  const [form, setForm] = useState(null);
  const [structure, setStructure] = useState([]);
  const [status, setStatus] = useState('loading');
  const [editing, setEditing] = useState(isNew);
  const [sources, setSources] = useState(null);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [sourceNotice, setSourceNotice] = useState('');
  const [error, setError] = useState('');
  const [skillsText, setSkillsText] = useState('');
  const [domainDirectInput, setDomainDirectInput] = useState(false);
  const [projectDirectInput, setProjectDirectInput] = useState(false);
  const [domainInput, setDomainInput] = useState('');
  const [projectInput, setProjectInput] = useState('');

  const dirty = useMemo(() => Boolean(editing && item && form && (
    JSON.stringify(item) !== JSON.stringify(form)
    || skillsText !== join(item.skills)
    || domainDirectInput
    || projectDirectInput
    || domainInput !== (item.domainName || '')
    || projectInput !== (item.projectName || '')
  )), [editing, item, form, skillsText, domainDirectInput, projectDirectInput, domainInput, projectInput]);
  useDirtyBlocker(dirty);

  const syncDraft = (experience) => {
    setItem(experience);
    setForm(experience);
    setSkillsText(join(experience.skills));
    setDomainDirectInput(false);
    setProjectDirectInput(false);
    setDomainInput(experience.domainName || '');
    setProjectInput(experience.projectName || '');
  };

  const load = async () => {
    setStatus('loading');
    try {
      const tree = await experienceRepository.structure();
      const domains = tree.domains || [];
      setStructure(domains);

      if (isNew) {
        if (initialDraft) {
          syncDraft(initialDraft);
          setEditing(true);
          setStatus('success');
          return;
        }
        const projectId = initialProjectId || searchParams.get('projectId') || '';
        const project = domains.flatMap((domain) => domain.projects.map((entry) => ({ ...entry, domain }))).find((entry) => entry.id === projectId);
        const empty = createEmptyExperience({
          domainId: project?.domain.id || initialDomainId || searchParams.get('domainId') || '',
          domainName: project?.domain.name || '',
          projectId: project?.id || '',
          projectName: project?.name || '',
          organization: project?.organization || '',
        });
        syncDraft(empty);
        setEditing(true);
      } else {
        const data = await experienceRepository.get(experienceId);
        syncDraft(data);
      }

      setStatus('success');
    } catch {
      setStatus('error');
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => load(), 0);
    return () => window.clearTimeout(timer);
    // experienceId가 바뀔 때 새 상세 원본을 다시 조회한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [experienceId, initialDraft, initialDomainId, initialProjectId]);

  useEffect(() => {
    const protect = (event) => {
      if (dirty) {
        event.preventDefault();
        event.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', protect);
    return () => window.removeEventListener('beforeunload', protect);
  }, [dirty]);

  const selectedDomain = structure.find((domain) => domain.id === form?.domainId);
  const availableProjects = selectedDomain?.projects || [];

  const updateProject = (projectId) => {
    const project = availableProjects.find((entry) => entry.id === projectId);
    setForm((current) => ({
      ...current,
      projectId,
      projectName: project?.name || '',
      organization: project?.organization || '',
    }));
  };

  const enableDirectDomain = () => {
    setDomainInput(form?.domainName || '');
    setProjectInput('');
    setDomainDirectInput(true);
    setProjectDirectInput(false);
    setForm((current) => ({ ...current, domainId: '', domainName: '', projectId: '', projectName: '' }));
  };

  const enableDirectProject = () => {
    setProjectInput(form?.projectName || '');
    setProjectDirectInput(true);
    setForm((current) => ({ ...current, projectId: '', projectName: '' }));
  };

  const useDomainSelect = () => {
    setDomainDirectInput(false);
    setDomainInput('');
    setForm((current) => ({ ...current, domainId: '', domainName: '', projectId: '', projectName: '' }));
  };

  const useProjectSelect = () => {
    setProjectDirectInput(false);
    setProjectInput('');
    setForm((current) => ({ ...current, projectId: '', projectName: '' }));
  };

  const resolveStructure = async (draft) => {
    let domainId = draft.domainId;
    let domainName = draft.domainName;
    let projectId = draft.projectId;
    let projectName = draft.projectName;

    if (domainDirectInput) {
      domainName = domainInput.trim();
      if (!domainName) throw new Error('경험 분류 이름을 입력해 주세요.');
      const existingDomain = structure.find((domain) => domain.name.trim().toLowerCase() === domainName.toLowerCase());
      const domain = existingDomain || await v2ChatApi.createDomain({ name: domainName });
      domainId = domain.id;
      domainName = domain.name;
    }

    if (projectDirectInput) {
      projectName = projectInput.trim();
      if (!projectName) throw new Error('프로젝트·활동 이름을 입력해 주세요.');
      if (!domainId) throw new Error('프로젝트·활동을 만들 경험 분류를 먼저 선택하거나 입력해 주세요.');
      const domainProjects = structure.find((domain) => domain.id === domainId)?.projects || [];
      const existingProject = domainProjects.find((project) => project.name.trim().toLowerCase() === projectName.toLowerCase());
      const project = existingProject || await v2ChatApi.createProject({ domain_id: domainId, name: projectName, organization: draft.organization });
      projectId = project.id;
      projectName = project.name;
    }

    if (!domainId || !projectId) throw new Error('경험 분류와 프로젝트·활동을 선택하거나 직접 입력해 주세요.');
    return { ...draft, domainId, domainName, projectId, projectName };
  };

  const updateDomain = (domainId) => {
    const domain = structure.find((entry) => entry.id === domainId);
    const project = domain?.projects?.[0];
    setForm((current) => ({
      ...current,
      domainId,
      domainName: domain?.name || '',
      projectId: project?.id || '',
      projectName: project?.name || '',
      organization: project?.organization || '',
    }));
  };

  const openSources = async () => {
    if (isNew) return;
    setSourceOpen(true);
    setSourceNotice('');
    if (!sources) {
      try {
        setSources(await experienceApi.getSources(experienceId));
      } catch (reason) {
        setError(reason.message);
      }
    }
  };

  const saveSource = async (source, text) => {
    setStatus('saving-source');
    setError('');
    setSourceNotice('');
    try {
      const updated = await sourceApi.update(source.id, { text });
      setSources((current) => ({
        ...current,
        sources: current.sources.map((entry) => (entry.id === source.id ? { ...entry, ...updated, text } : entry)),
      }));
    } catch (reason) {
      setError(reason.message);
    } finally {
      setStatus('success');
    }
  };

  const unlinkSource = async (source) => {
    const name = source.filename || '텍스트 입력';
    if (!window.confirm(`'${name}' 근거를 현재 경험에서 연결 해제할까요?\n\n원본 파일이나 텍스트 자체는 삭제되지 않습니다. 연결만 해제됩니다.`)) return;
    setStatus('unlinking-source');
    setError('');
    setSourceNotice('');
    try {
      const result = await sourceApi.unlink(experienceId, source.id);
      setSources({ experienceId, sources: result.sources });
      syncDraft(result.experience);
      const count = result.unsupportedFacts?.length || 0;
      setSourceNotice(count ? `연결은 해제되었습니다. 확인이 필요한 사실 ${count}개가 남아 있습니다.` : '현재 경험과의 연결이 해제되었습니다.');
    } catch (reason) {
      setError(reason.message);
    } finally {
      setStatus('success');
    }
  };

  const downloadSource = async (source) => {
    setError('');
    try {
      const blob = await sourceApi.download(source);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = source.filename || `source-${source.id}.txt`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(reason.message);
    }
  };

  const save = async () => {
    if (!form.title.trim()) {
      setError('경험 제목을 입력해 주세요.');
      return;
    }
    if (!window.confirm(isNew ? '이 경험을 저장할까요?' : '변경한 경험 내용을 저장할까요?')) return;
    setStatus('saving');
    setError('');
    try {
      const resolvedForm = await resolveStructure(form);
      const payload = {
        ...resolvedForm,
        actions: splitLines(form.actions?.join('\n') ?? ''),
        results: splitLines(form.results?.join('\n') ?? ''),
        facts: splitLines(form.facts?.join('\n') ?? ''),
        skills: splitSkills(skillsText),
        status: 'confirmed',
      };
      const saved = isNew ? await experienceRepository.create(payload) : await experienceRepository.update(payload, item.projectId);
      syncDraft(saved);
      setEditing(false);
      setStatus('success');
      if (onSaved) await onSaved(saved);
      if (isNew) {
        if (onClose) onClose();
        else navigate(`/memory/${saved.id}`, { replace: true });
      }
    } catch (reason) {
      setError(reason.message);
      setStatus('success');
    }
  };

  const cancel = () => {
    if (dirty && !window.confirm('수정 중인 변경사항을 취소할까요?')) return;
    if (isNew && onClose) onClose();
    else if (isNew) navigate('/memory');
    else {
      syncDraft(item);
      setEditing(false);
      setError('');
    }
  };

  if (status === 'loading') return <div className="memory-detail"><LoadingState label="경험 상세를 불러오는 중입니다." /></div>;
  if (status === 'error') return <div className="memory-detail"><ErrorState title="경험을 찾을 수 없습니다" description="대상이 없거나 잘못된 주소일 수 있습니다." onRetry={load} /><Link className="ui-button ui-button--secondary" to="/memory">경험 목록으로</Link></div>;

  const period = [item.period?.start, item.period?.end].filter(Boolean).join(' · ');

  return (
    <article className="memory-detail">
      <div className="detail-breadcrumb">
        <Link to="/memory">경험 메모리</Link>
        <span>/</span>
        <span>{isNew ? '새 경험' : item.projectName}</span>
      </div>

      <header className="detail-header">
        <div>
          <span className="eyebrow">{isNew ? '새 경험 작성' : '사용자 확정 경험'}</span>
          <h2>{isNew ? '새 경험' : item.title}</h2>
          <p>{[item.domainName, item.projectName, item.organization, period].filter(Boolean).join(' · ')}</p>
        </div>
        <div>
          {!isNew && <button className="ui-button ui-button--secondary" onClick={openSources}>원본 근거 관리</button>}
          {!editing && <button className="ui-button" onClick={() => setEditing(true)}>수정</button>}
        </div>
      </header>

      {error && <p className="inline-error" role="alert">{error}</p>}

      {editing ? (
        <div className="detail-grid detail-grid--edit">
          <main>
            <DetailCard title="요약" tone="lead">
              <textarea
                rows="4"
                value={form.summary ?? ''}
                placeholder="이 경험을 정리해 주세요. 일반 문장이나 마크업(예: **핵심 결과**, 줄바꿈)을 사용할 수 있습니다."
                onChange={(event) => setForm({ ...form, summary: event.target.value })}
              />
            </DetailCard>
            <DetailCard title="상황">
              <textarea
                rows="4"
                value={form.situation ?? ''}
                placeholder="경험이 발생한 배경과 맥락을 적어 주세요. 목록(예: - 배경)이나 강조 마크업을 사용할 수 있습니다."
                onChange={(event) => setForm({ ...form, situation: event.target.value })}
              />
            </DetailCard>
            <DetailCard title="행동">
              <textarea rows="6" value={join(form.actions)} placeholder="마크업 문법으로 입력할 수 있습니다. 예: 1. 내용 / - 내용" onChange={(event) => setForm({ ...form, actions: splitLines(event.target.value) })} />
            </DetailCard>
            <DetailCard title="결과">
              <textarea rows="6" value={join(form.results)} placeholder="마크업 문법으로 입력할 수 있습니다. 예: 1. 내용 / - 내용" onChange={(event) => setForm({ ...form, results: splitLines(event.target.value) })} />
            </DetailCard>
          </main>

          <aside>
            <DetailCard title="분류">
              <div className="detail-editor__classification">
                <label>
                  <span className="detail-editor__field-heading">경험 분류 <button type="button" className="detail-editor__direct-button" onClick={domainDirectInput ? useDomainSelect : enableDirectDomain}>{domainDirectInput ? '목록에서 선택' : '직접 입력'}</button></span>
                  {domainDirectInput ? <input value={domainInput} placeholder="예: 사이드 프로젝트" onChange={(event) => setDomainInput(event.target.value)} /> : <select value={form.domainId} onChange={(event) => updateDomain(event.target.value)}>
                    <option value="">선택</option>
                    {structure.map((domain) => <option value={domain.id} key={domain.id}>{domain.name}</option>)}
                  </select>}
                </label>
                <label>
                  <span className="detail-editor__field-heading">프로젝트·활동 <button type="button" className="detail-editor__direct-button" onClick={projectDirectInput ? useProjectSelect : enableDirectProject}>{projectDirectInput ? '목록에서 선택' : '직접 입력'}</button></span>
                  {projectDirectInput ? <input value={projectInput} placeholder="예: 신규 서비스 출시" onChange={(event) => setProjectInput(event.target.value)} /> : <select value={form.projectId} onChange={(event) => updateProject(event.target.value)} disabled={!form.domainId}>
                    <option value="">선택</option>
                    {availableProjects.map((project) => <option value={project.id} key={project.id}>{project.name}</option>)}
                  </select>}
                </label>
              </div>
              <label>
                제목
                <input value={form.title ?? ''} placeholder="경험 제목을 입력해 주세요." onChange={(event) => setForm({ ...form, title: event.target.value })} />
              </label>
            </DetailCard>

            <DetailCard title="나의 역할">
              <label>
                역할
                <input value={form.role ?? ''} placeholder="예: 서비스 기획" onChange={(event) => setForm({ ...form, role: event.target.value })} />
              </label>
            </DetailCard>

            <DetailCard title="역량">
              <textarea
                rows="4"
                value={skillsText}
                placeholder="줄바꿈이나 쉼표로 여러 역량을 입력할 수 있습니다."
                onChange={(event) => setSkillsText(event.target.value)}
              />
            </DetailCard>

            <DetailCard title="확인된 사실">
              <textarea rows="4" value={join(form.facts)} placeholder="마크업 문법으로 입력할 수 있습니다. 예: - 사실 / 1. 사실" onChange={(event) => setForm({ ...form, facts: splitLines(event.target.value) })} />
            </DetailCard>

            <DetailCard title="원본 근거">
              <p>원본 {item.evidenceIds.length}개와 연결됨</p>
              {!isNew && <button className="ui-button ui-button--secondary" onClick={openSources}>원본 관리</button>}
            </DetailCard>
          </aside>
        </div>
      ) : (
        <div className="detail-grid">
          <main>
            <DetailCard title="요약" tone="lead">
              <MarkdownBlocks text={item.summary} />
            </DetailCard>
            <DetailCard title="상황">
              <MarkdownBlocks text={item.situation} />
            </DetailCard>
            <DetailCard title="행동">
              <MarkdownList items={item.actions} />
            </DetailCard>
            <DetailCard title="결과">
              <MarkdownList items={item.results} />
            </DetailCard>
          </main>

          <aside>
            <DetailCard title="나의 역할">
              <DetailText value={item.role} />
            </DetailCard>
            <DetailCard title="역량">
              <div className="skill-list">
                {item.skills?.length ? item.skills.map((value) => <span key={value}>{value}</span>) : <p>{emptyText}</p>}
              </div>
            </DetailCard>
            <DetailCard title="확인된 사실">
              <MarkdownList items={item.facts} />
            </DetailCard>
            <DetailCard title="원본 근거" tone="evidence">
              <p>원본 {item.evidenceIds.length}개와 연결됨</p>
              <button onClick={openSources}>원본 관리 →</button>
            </DetailCard>
          </aside>
        </div>
      )}

      <div className="sticky-actions">
        {editing ? (
          <>
            <button className="ui-button ui-button--secondary" onClick={cancel}>취소</button>
            <button className="ui-button" onClick={save} disabled={status === 'saving'}>{status === 'saving' ? '저장 중…' : isNew ? '경험 저장' : '변경 저장'}</button>
          </>
        ) : null}
      </div>

      <SourceManagerModal
        open={sourceOpen}
        sources={sources?.sources || []}
        busy={status === 'saving-source' || status === 'unlinking-source'}
        error={error}
        notice={sourceNotice}
        onClose={() => setSourceOpen(false)}
        onSave={saveSource}
        onUnlink={unlinkSource}
        onDownload={downloadSource}
      />
    </article>
  );
}
