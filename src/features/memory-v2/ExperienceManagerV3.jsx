import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { v2ChatApi } from '../../api/v2ChatApi.js';
import './memory-manager.css';

const toView = (item) => ({
  ...item,
  domainName: item.domain?.name || '미분류',
  projectName: item.project?.name || '프로젝트·활동 미분류',
  organization: item.project?.organization || '',
  evidenceCount: item.evidence_count ?? item.source_ids?.length ?? 0,
});

const createdTimeValue = (item) => new Date(item.created_at || item.createdAt || 0).getTime() || 0;
const ORDER_STORAGE_KEY = 'career-memory.experience-structure-order.v1';
const readStructureOrder = () => {
  try { return { domains: [], projects: {}, experiences: {}, ...JSON.parse(window.localStorage.getItem(ORDER_STORAGE_KEY) || '{}') }; }
  catch { return { domains: [], projects: {}, experiences: {} }; }
};
const sortBySavedOrder = (items, ids = []) => {
  const rank = new Map(ids.map((id, index) => [id, index]));
  return [...items].sort((a, b) => {
    const aRank = rank.get(a.id); const bRank = rank.get(b.id);
    if (aRank == null && bRank == null) return createdTimeValue(b) - createdTimeValue(a);
    if (aRank == null) return -1;
    if (bRank == null) return 1;
    return aRank - bRank;
  });
};
const readDragPayload = (event) => {
  try { return JSON.parse(event.dataTransfer.getData('application/json')); }
  catch { return null; }
};

async function loadLibrary() {
  const [experiences, structure] = await Promise.all([v2ChatApi.listExperiences(), v2ChatApi.listStructure()]);
  return { experiences: experiences.items.map(toView), domains: structure.domains };
}

function MoreMenu({ label, children }) {
  return <details className="mv2-action-menu" onClick={(event) => event.stopPropagation()}><summary aria-label={label}>···</summary><div>{children}</div></details>;
}

function HighlightText({ text, query }) {
  const term = query.trim();
  if (!term) return text;
  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const parts = String(text).split(new RegExp(`(${escaped})`, 'ig'));
  return parts.map((part, index) => part.toLowerCase() === term.toLowerCase() ? <mark key={`${part}-${index}`}>{part}</mark> : part);
}

function ExperienceForm({ item, domains, onClose, onSave }) {
  const firstDomain = item?.domainName || domains[0]?.name || '';
  const initialDomain = domains.find((domain) => domain.name === firstDomain);
  const projects = initialDomain?.projects || [];
  const [form, setForm] = useState({
    id: item?.id, version: item?.version, title: item?.title || '', summary: item?.summary || '',
    role: item?.role || '', skills: item?.skills || [], domainId: initialDomain?.id || '', domainName: firstDomain,
    projectId: item?.project?.id || projects[0]?.id || '',
    newDomainName: '', newProjectName: '',
  });
  const activeDomain = domains.find((domain) => domain.id === form.domainId);
  const activeProjects = activeDomain?.projects || [];
  const changeDomain = (id) => {
    if (id === '__new__') setForm((value) => ({ ...value, domainId: '__new__', domainName: '', projectId: '__new__', newProjectName: '' }));
    else { const domain = domains.find((candidate) => candidate.id === id); setForm((value) => ({ ...value, domainId: id, domainName: domain?.name || '', newDomainName: '', projectId: domain?.projects[0]?.id || '', newProjectName: '' })); }
  };
  const changeProject = (id) => setForm((value) => ({ ...value, projectId: id, newProjectName: id === '__new__' ? value.newProjectName : '' }));
  return <div className="mv2-modal-backdrop"><form className="mv2-modal" onSubmit={(event) => { event.preventDefault(); onSave(form); }}>
    <header><div><span className="mv2-kicker">{item?.id ? '경험 수정' : '직접 추가'}</span><h2>{item?.id ? item.title : '새 경험 추가'}</h2></div><button type="button" className="mv2-icon-button" onClick={onClose} aria-label="닫기">×</button></header>
    <div className="mv2-form-grid">
      <label>경험 분류<select value={form.domainId} onChange={(event) => changeDomain(event.target.value)}><option value="">선택</option>{domains.map((domain) => <option key={domain.id} value={domain.id}>{domain.name}</option>)}<option value="__new__">+ 새 분류 직접 입력</option></select></label>
      <label>프로젝트·활동<select required value={form.projectId} onChange={(event) => changeProject(event.target.value)} disabled={!form.domainId}><option value="">선택</option>{activeProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}<option value="__new__">+ 새 프로젝트·활동 직접 입력</option></select></label>
      {form.domainId === '__new__' && <label className="is-wide mv2-direct-field">새 경험 분류 이름<input autoFocus required placeholder="예: 자격증·수상" value={form.newDomainName} onChange={(event) => setForm({ ...form, newDomainName: event.target.value })} /><small>새 분류 아래에 프로젝트·활동도 함께 만들어집니다.</small></label>}
      {form.projectId === '__new__' && <label className="is-wide mv2-direct-field">새 프로젝트·활동 이름<input required placeholder="예: 데이터 분석 자격증 준비" value={form.newProjectName} onChange={(event) => setForm({ ...form, newProjectName: event.target.value })} /></label>}
      <label className="is-wide">경험 제목<input required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
      <label className="is-wide">요약<textarea rows="4" value={form.summary} onChange={(event) => setForm({ ...form, summary: event.target.value })} /></label>
      <label>역할<input value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })} /></label>
      <label>역량 (쉼표 구분)<input value={form.skills.join(', ')} onChange={(event) => setForm({ ...form, skills: event.target.value.split(',').map((value) => value.trim()).filter(Boolean) })} /></label>
    </div>
    <footer><button type="button" className="mv2-button mv2-button--secondary" onClick={onClose}>취소</button><button className="mv2-button">저장</button></footer>
  </form></div>;
}

const skillGroupRules = [
  ['데이터·분석', /데이터|분석|python|시각화|a\/b|지표/i],
  ['기획·제품', /기획|요구사항|우선순위|프로젝트|제품|ux/i],
  ['사용자·리서치', /사용자|조사|인터뷰|리서치/i],
  ['운영·협업', /운영|협업|커뮤니케이션|리드|관리/i],
];

const getSkillGroupName = (skill) => skillGroupRules.find(([, rule]) => rule.test(skill))?.[0] || '기타 전문 역량';

function groupSkills(experiences) {
  const occurrences = experiences.flatMap((item) => item.skills || []);
  const groups = new Map();
  occurrences.forEach((skill) => {
    const name = getSkillGroupName(skill);
    const group = groups.get(name) || { name, count: 0, skills: new Set() };
    group.count += 1; group.skills.add(skill); groups.set(name, group);
  });
  return [...groups.values()].map((group) => ({ ...group, skills: [...group.skills], percent: occurrences.length ? Math.round((group.count / occurrences.length) * 100) : 0 })).sort((a, b) => b.count - a.count);
}

function sourceEntries(item) {
  return Array.from({ length: item.evidenceCount }, (_, index) => index === 0 ? { id: `${item.id}-text`, type: 'text', name: '텍스트 원문', content: item.summary || `${item.title}에 관한 경험 기록입니다.` } : { id: `${item.id}-file-${index}`, type: 'file', name: `${item.projectName}-근거-${index}.txt`, content: `${item.title}\n${item.summary || ''}\n${(item.results || []).join('\n')}` });
}

function downloadSource(source) {
  const url = URL.createObjectURL(new Blob([source.content], { type: 'text/plain;charset=utf-8' }));
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = source.name; anchor.click(); URL.revokeObjectURL(url);
}

function AssetModal({ type, experiences, onClose, onSearch }) {
  const [expanded, setExpanded] = useState(null);
  const [selectedSkillGroup, setSelectedSkillGroup] = useState(null);
  const [hoveredSkillGroup, setHoveredSkillGroup] = useState(null);
  if (!type) return null;
  const evidenceMode = type === 'evidence';
  const roles = [...new Set(experiences.map((item) => item.role).filter(Boolean))];
  const groups = groupSkills(experiences);
  const totalOccurrences = groups.reduce((sum, group) => sum + group.count, 0);
  const activeSkillGroup = hoveredSkillGroup || selectedSkillGroup;
  const toggleSkillGroup = (groupName, shouldScroll = false) => {
    const nextGroup = selectedSkillGroup === groupName ? null : groupName;
    setSelectedSkillGroup(nextGroup);
    if (!nextGroup || !shouldScroll) return;
    window.requestAnimationFrame(() => {
      const target = document.getElementById(`skill-group-${encodeURIComponent(groupName)}`);
      target?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      target?.focus({ preventScroll: true });
    });
  };
  return <div className="mv2-modal-backdrop"><section className="mv2-asset-dialog" role="dialog" aria-modal="true">
    <header><div><span className="mv2-kicker">{evidenceMode ? 'SOURCE LIBRARY' : 'CAREER PROFILE'}</span><h2>{evidenceMode ? '경험 근거' : '내 역량'}</h2><p>{evidenceMode ? '텍스트 원문을 읽고 파일 근거를 내려받을 수 있습니다.' : `유사 역량 그룹이 전체 역량 태그 ${totalOccurrences}회에서 차지하는 비중입니다.`}</p></div><button className="mv2-icon-button" onClick={onClose} aria-label="닫기">×</button></header>
    {evidenceMode ? <div className="mv2-evidence-library mv2-source-library">{experiences.filter((item) => item.evidenceCount > 0).map((item) => <article key={item.id} className="mv2-source-group"><div className="mv2-source-group__summary"><div><strong>{item.title}</strong><span>{item.domainName} · {item.projectName}</span></div><span className="mv2-evidence-count">원본 {item.evidenceCount}개</span><button onClick={() => setExpanded(expanded === item.id ? null : item.id)} aria-expanded={expanded === item.id}>{expanded === item.id ? '접기' : '원본 보기'}</button></div>{expanded === item.id && <div className="mv2-source-items">{sourceEntries(item).map((source) => <section key={source.id}><div><span className={`mv2-source-kind is-${source.type}`}>{source.type === 'text' ? '텍스트' : '파일'}</span><strong>{source.name}</strong></div>{source.type === 'text' ? <p>{source.content}</p> : <button onClick={() => downloadSource(source)}>다운로드</button>}</section>)}</div>}</article>)}</div> : <div className="mv2-profile-groups"><section><h3>내 직군·직업</h3><div className="mv2-profile-tags">{roles.map((role) => <span key={role}>{role}</span>)}</div></section><section><h3>유사 역량 그룹</h3><div className="mv2-skill-distribution" aria-label="전체 역량 그룹 구성비">{groups.map((group) => <button type="button" key={group.name} style={{ width: `${group.percent}%` }} title={`${group.name} · 전체의 ${group.percent}% (${group.count}회)`} aria-label={`${group.name}, 전체의 ${group.percent}%, ${group.count}회. 클릭하여 역량 그룹 보기`} aria-pressed={selectedSkillGroup === group.name} onMouseEnter={() => setHoveredSkillGroup(group.name)} onMouseLeave={() => setHoveredSkillGroup(null)} onFocus={() => setHoveredSkillGroup(group.name)} onBlur={() => setHoveredSkillGroup(null)} onClick={() => toggleSkillGroup(group.name, true)} />)}</div><div className="mv2-skill-groups">{groups.map((group, index) => <article id={`skill-group-${encodeURIComponent(group.name)}`} role="button" tabIndex="0" className={activeSkillGroup === group.name ? 'is-focused' : ''} key={group.name} onClick={() => onSearch({ type: 'group', value: group.name })} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSearch({ type: 'group', value: group.name }); } }}><div className="mv2-skill-group__heading"><strong><i className={`mv2-skill-dot is-${index + 1}`} />{group.name}</strong><span>전체의 {group.percent}% · {group.count}회</span></div><div className="mv2-profile-tags is-skills">{group.skills.map((skill) => <button type="button" key={skill} onClick={(event) => { event.stopPropagation(); onSearch({ type: 'skill', value: skill }); }}>{skill}</button>)}</div></article>)}</div><p className="mv2-percent-note">모든 그룹의 비율을 합하면 약 100%입니다. 반올림으로 1% 정도 차이가 날 수 있으며, 숙련도나 달성률을 의미하지 않습니다.</p></section></div>}
  </section></div>;
}

export function ExperienceManagerV3() {
  const [experiences, setExperiences] = useState([]);
  const [domains, setDomains] = useState([]);
  const [query, setQuery] = useState('');
  const [collapsed, setCollapsed] = useState(new Set());
  const [selected, setSelected] = useState(null);
  const [editing, setEditing] = useState(null);
  const [assetModal, setAssetModal] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [dropTarget, setDropTarget] = useState('');
  const [previewPosition, setPreviewPosition] = useState(null);
  const previewRef = useRef(null);
  const previewAnchorRef = useRef(null);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState('');
  const [editMode, setEditMode] = useState(false);
  const [pendingOps, setPendingOps] = useState([]);
  const [savingStructure, setSavingStructure] = useState(false);
  const [draftDomainId, setDraftDomainId] = useState('');
  const [structureOrder, setStructureOrder] = useState(readStructureOrder);
  const editSnapshotRef = useRef(null);

  const refresh = async () => {
    setStatus('loading'); setError('');
    try { const data = await loadLibrary(); setExperiences(data.experiences); setDomains(data.domains); setStatus('ready'); }
    catch (reason) { setError(reason.message || '경험을 불러오지 못했습니다.'); setStatus('error'); }
  };
  useEffect(() => { let active = true; loadLibrary().then((data) => { if (active) { setExperiences(data.experiences); setDomains(data.domains); setStatus('ready'); } }, (reason) => { if (active) { setError(reason.message || '경험을 불러오지 못했습니다.'); setStatus('error'); } }); return () => { active = false; }; }, []);
  useEffect(() => {
    const protect = (event) => { if (pendingOps.length || draftDomainId) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', protect);
    return () => window.removeEventListener('beforeunload', protect);
  }, [pendingOps.length, draftDomainId]);

  const normalizedQuery = query.trim().toLowerCase();
  const hasFilters = Boolean(normalizedQuery);
  const filtered = useMemo(() => experiences.filter((item) => {
    const searchable = `${item.title} ${item.summary} ${item.role} ${item.domainName} ${item.projectName} ${(item.skills || []).join(' ')} ${(item.results || []).join(' ')} ${(item.actions || []).join(' ')}`.toLowerCase();
    return !normalizedQuery || searchable.includes(normalizedQuery);
  }).sort((a, b) => createdTimeValue(b) - createdTimeValue(a)), [experiences, normalizedQuery]);
  const displayDomains = useMemo(() => sortBySavedOrder(domains, structureOrder.domains).map((domain) => {
    const projects = sortBySavedOrder(domain.projects, structureOrder.projects[domain.id]).map((project) => {
      const visibleExperiences = sortBySavedOrder(filtered.filter((item) => item.project?.id === project.id), structureOrder.experiences[project.id]);
      return { project, experiences: visibleExperiences };
    }).filter(({ experiences: visibleExperiences }) => !hasFilters || visibleExperiences.length > 0);
    return { domain, projects, experiences: projects.flatMap((project) => project.experiences) };
  }).filter(({ projects }) => !hasFilters || projects.length > 0), [domains, filtered, hasFilters, structureOrder]);
  const visibleExperienceCount = new Set(displayDomains.flatMap((domain) => domain.experiences.map((item) => item.id))).size;
  const evidenceTotal = experiences.reduce((sum, item) => sum + item.evidenceCount, 0);
  const skillTotal = new Set(experiences.flatMap((item) => item.skills || [])).size;
  const clearSearch = () => setQuery('');
  const searchBySkill = ({ value }) => {
    setQuery(value);
    setAssetModal(null);
    setSelected(null);
  };

  const togglePreview = (experience, anchor) => {
    if (selected?.id === experience.id) {
      setSelected(null);
      setPreviewPosition(null);
      previewAnchorRef.current = null;
      return;
    }
    previewAnchorRef.current = anchor;
    setPreviewPosition(null);
    setSelected(experience);
  };

  useEffect(() => {
    if (!selected) return undefined;
    const updatePosition = () => {
      if (window.matchMedia('(max-width: 767px)').matches) { setPreviewPosition(null); return; }
      const anchor = previewAnchorRef.current;
      const preview = previewRef.current;
      if (!anchor?.isConnected || !preview) return;
      const anchorRect = anchor.getBoundingClientRect();
      const previewRect = preview.getBoundingClientRect();
      const gap = 12;
      const edge = 16;
      const fitsRight = anchorRect.right + gap + previewRect.width <= window.innerWidth - edge;
      const preferredLeft = fitsRight ? anchorRect.right + gap : anchorRect.left - previewRect.width - gap;
      const left = Math.max(edge, Math.min(preferredLeft, window.innerWidth - previewRect.width - edge));
      const top = Math.max(edge, Math.min(anchorRect.top, window.innerHeight - previewRect.height - edge));
      setPreviewPosition({ left, top, right: 'auto', bottom: 'auto' });
    };
    const frame = window.requestAnimationFrame(updatePosition);
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [selected]);

  useEffect(() => {
    if (!selected) return undefined;
    const closeOnOutsideClick = (event) => {
      if (previewRef.current?.contains(event.target) || previewAnchorRef.current?.contains(event.target)) return;
      setSelected(null);
      setPreviewPosition(null);
      previewAnchorRef.current = null;
    };
    document.addEventListener('pointerdown', closeOnOutsideClick);
    return () => document.removeEventListener('pointerdown', closeOnOutsideClick);
  }, [selected]);

  const beginEditMode = () => { editSnapshotRef.current = { domains: structuredClone(domains), experiences: structuredClone(experiences), structureOrder: structuredClone(structureOrder) }; setPendingOps([]); setEditMode(true); setSelected(null); };
  const cancelEditMode = () => {
    if (pendingOps.length && !window.confirm('저장하지 않은 변경을 취소하고 원래 상태로 되돌릴까요?')) return;
    if (editSnapshotRef.current) { setDomains(editSnapshotRef.current.domains); setExperiences(editSnapshotRef.current.experiences); setStructureOrder(editSnapshotRef.current.structureOrder); }
    setPendingOps([]); setEditMode(false); setDropTarget(''); setDraftDomainId(''); editSnapshotRef.current = null;
  };
  const addDomain = () => {
    if (draftDomainId) { setError('먼저 작성 중인 경험 분류를 추가하거나 취소해 주세요.'); return; }
    const domain = { id: `temp-domain-${crypto.randomUUID()}`, name: '', version: 1, projects: [], created_at: new Date().toISOString(), isDraft: true };
    setQuery(''); setDomains((items) => [domain, ...items]); setDraftDomainId(domain.id);
  };
  const updateDraftDomain = (id, name) => setDomains((items) => items.map((domain) => domain.id === id ? { ...domain, name } : domain));
  const cancelDraftDomain = (id) => { setDomains((items) => items.filter((domain) => domain.id !== id)); setDraftDomainId(''); };
  const finalizeDraftDomain = (domain) => {
    const name = domain.name.trim();
    if (!name) { setError('경험 분류 이름을 입력해 주세요.'); return; }
    if (domains.some((item) => item.id !== domain.id && item.name.trim().toLowerCase() === name.toLowerCase())) { setError('이미 같은 이름의 경험 분류가 있습니다.'); return; }
    const finalized = { ...domain, name, isDraft: false };
    setDomains((items) => items.map((item) => item.id === domain.id ? finalized : item));
    setPendingOps((items) => [...items, { type: 'create-domain', domain: finalized }]);
    setDraftDomainId(''); setError('');
  };
  const addProject = (domain) => { const name = window.prompt('새 프로젝트·활동 이름'); if (!name?.trim()) return; const project = { id: `temp-project-${crypto.randomUUID()}`, name: name.trim(), version: 1, experiences: [] }; setDomains((items) => items.map((item) => item.id === domain.id ? { ...item, projects: [...item.projects, project] } : item)); setPendingOps((items) => [...items, { type: 'create-project', domainId: domain.id, project }]); };
  const renameDomain = (domain) => { const name = window.prompt('경험 분류 이름 변경', domain.name); if (!name?.trim() || name.trim() === domain.name) return; setDomains((items) => items.map((item) => item.id === domain.id ? { ...item, name: name.trim() } : item)); setExperiences((items) => items.map((item) => item.domain?.id === domain.id ? { ...item, domain: { ...item.domain, name: name.trim() }, domainName: name.trim() } : item)); setPendingOps((items) => [...items, { type: 'rename-domain', id: domain.id, version: domain.version, name: name.trim() }]); };
  const renameProject = (project) => { const name = window.prompt('프로젝트·활동 이름 변경', project.name); if (!name?.trim() || name.trim() === project.name) return; setDomains((items) => items.map((domain) => ({ ...domain, projects: domain.projects.map((item) => item.id === project.id ? { ...item, name: name.trim() } : item) }))); setExperiences((items) => items.map((item) => item.project?.id === project.id ? { ...item, project: { ...item.project, name: name.trim() }, projectName: name.trim() } : item)); setPendingOps((items) => [...items, { type: 'rename-project', id: project.id, version: project.version, name: name.trim() }]); };

  const requestDeleteDomain = (domain) => setConfirm({ title: `‘${domain.name}’ 분류를 삭제 목록에 추가할까요?`, description: `저장할 때 프로젝트·활동 ${domain.projects.length}개와 포함된 경험이 휴지통으로 이동합니다. 저장 전에는 취소할 수 있습니다.`, action: () => { setDomains((items) => items.filter((item) => item.id !== domain.id)); setExperiences((items) => items.filter((item) => item.domain?.id !== domain.id)); setPendingOps((items) => [...items, { type: 'delete-domain', domain }]); setConfirm(null); } });
  const requestDeleteProject = (project) => setConfirm({ title: `‘${project.name}’을 삭제 목록에 추가할까요?`, description: '저장할 때 포함된 경험이 휴지통으로 이동합니다. 저장 전에는 취소할 수 있습니다.', action: () => { setDomains((items) => items.map((domain) => ({ ...domain, projects: domain.projects.filter((item) => item.id !== project.id) }))); setExperiences((items) => items.filter((item) => item.project?.id !== project.id)); setPendingOps((items) => [...items, { type: 'delete-project', project }]); setConfirm(null); } });
  const requestDeleteExperience = (experience) => setConfirm({ title: `‘${experience.title}’ 경험을 삭제 목록에 추가할까요?`, description: '저장할 때 경험이 휴지통으로 이동합니다. 저장 전에는 취소할 수 있습니다.', action: () => { setExperiences((items) => items.filter((item) => item.id !== experience.id)); setPendingOps((items) => [...items, { type: 'delete-experience', experience }]); setConfirm(null); if (selected?.id === experience.id) setSelected(null); } });

  const saveExperience = async (form) => { try {
    let domainId = form.domainId;
    if (domainId === '__new__') domainId = (await v2ChatApi.createDomain({ name: form.newDomainName.trim() })).id;
    let projectId = form.projectId;
    if (projectId === '__new__') projectId = (await v2ChatApi.createProject({ domain_id: domainId, name: form.newProjectName.trim() })).id;
    if (!projectId) throw new Error('프로젝트·활동을 선택하거나 직접 입력해 주세요.');
    if (form.id) {
      const original = experiences.find((item) => item.id === form.id);
      await v2ChatApi.updateExperience(form.id, { base_version: form.version, changes: { title: form.title, summary: form.summary, role: form.role, skills: form.skills } });
      if (original?.project?.id !== projectId) await v2ChatApi.bulkMoveExperiences({ experience_ids: [form.id], target_project_id: projectId });
    } else await v2ChatApi.createExperience({ project_id: projectId, title: form.title, summary: form.summary, role: form.role, skills: form.skills, results: [], source_ids: [] });
    setEditing(null); await refresh();
  } catch (reason) { setError(reason.message || '경험을 저장하지 못했습니다.'); } };
  const addReorderOperation = (type) => setPendingOps((items) => [...items.filter((item) => item.type !== type), { type }]);
  const moveIdBefore = (ids, sourceId, targetId) => {
    const next = ids.filter((id) => id !== sourceId);
    const targetIndex = next.indexOf(targetId);
    next.splice(targetIndex < 0 ? next.length : targetIndex, 0, sourceId);
    return next;
  };
  const reorderDomain = (sourceId, targetId) => {
    if (!editMode || sourceId === targetId) return;
    const ids = sortBySavedOrder(domains, structureOrder.domains).map((domain) => domain.id);
    setStructureOrder((value) => ({ ...value, domains: moveIdBefore(ids, sourceId, targetId) }));
    addReorderOperation('reorder-domains');
  };
  const reorderProject = (domainId, sourceId, targetId) => {
    if (!editMode || sourceId === targetId) return;
    const domain = domains.find((item) => item.id === domainId);
    if (!domain?.projects.some((project) => project.id === sourceId)) return;
    const ids = sortBySavedOrder(domain.projects, structureOrder.projects[domainId]).map((project) => project.id);
    setStructureOrder((value) => ({ ...value, projects: { ...value.projects, [domainId]: moveIdBefore(ids, sourceId, targetId) } }));
    addReorderOperation(`reorder-projects:${domainId}`);
  };
  const reorderExperience = (projectId, sourceId, targetId) => {
    if (!editMode || sourceId === targetId) return;
    const projectItems = experiences.filter((item) => item.project?.id === projectId);
    if (!projectItems.some((item) => item.id === sourceId)) return;
    const ids = sortBySavedOrder(projectItems, structureOrder.experiences[projectId]).map((item) => item.id);
    setStructureOrder((value) => ({ ...value, experiences: { ...value.experiences, [projectId]: moveIdBefore(ids, sourceId, targetId) } }));
    addReorderOperation(`reorder-experiences:${projectId}`);
  };
  const moveExperience = (experienceId, projectId, beforeExperienceId = '') => {
    if (!editMode || !experienceId || !projectId) return;
    const targetDomain = domains.find((domain) => domain.projects.some((project) => project.id === projectId));
    const targetProject = targetDomain?.projects.find((project) => project.id === projectId);
    if (!targetDomain || !targetProject) return;
    setExperiences((items) => items.map((item) => item.id === experienceId ? { ...item, domain: { ...item.domain, id: targetDomain.id, name: targetDomain.name }, domainName: targetDomain.name, project: { ...item.project, id: targetProject.id, name: targetProject.name }, projectName: targetProject.name } : item));
    setStructureOrder((value) => {
      const nextExperiences = Object.fromEntries(Object.entries(value.experiences).map(([id, ids]) => [id, ids.filter((itemId) => itemId !== experienceId)]));
      const targetIds = [...(nextExperiences[projectId] || [])];
      const targetIndex = beforeExperienceId ? targetIds.indexOf(beforeExperienceId) : -1;
      targetIds.splice(targetIndex < 0 ? targetIds.length : targetIndex, 0, experienceId);
      nextExperiences[projectId] = targetIds;
      return { ...value, experiences: nextExperiences };
    });
    setPendingOps((items) => [...items, { type: 'move-experience', experienceId, projectId }]);
    setDropTarget('');
  };
  const saveStructure = async () => {
    const deleteCount = pendingOps.filter((operation) => operation.type.startsWith('delete-')).length;
    const confirmationMessage = deleteCount
      ? `변경사항 ${pendingOps.length}건을 저장할까요?\n삭제 ${deleteCount}건은 저장 후 휴지통으로 이동합니다.`
      : `변경사항 ${pendingOps.length}건을 저장할까요?`;
    if (!window.confirm(confirmationMessage)) return;
    setSavingStructure(true); setError('');
    const idMap = new Map();
    try {
      for (const operation of pendingOps.filter((item) => item.type === 'create-domain')) {
        const currentDomain = domains.find((domain) => domain.id === operation.domain.id);
        if (!currentDomain) continue;
        const created = await v2ChatApi.createDomain({ name: currentDomain.name });
        idMap.set(operation.domain.id, created.id);
      }
      for (const operation of pendingOps.filter((item) => item.type === 'create-project')) {
        const currentProject = domains.flatMap((domain) => domain.projects).find((project) => project.id === operation.project.id);
        if (!currentProject) continue;
        const created = await v2ChatApi.createProject({ domain_id: idMap.get(operation.domainId) || operation.domainId, name: currentProject.name });
        idMap.set(operation.project.id, created.id);
      }
      for (const operation of pendingOps) {
        if (operation.type === 'rename-domain' && !operation.id.startsWith('temp-')) await v2ChatApi.updateDomain(operation.id, { base_version: operation.version, name: operation.name });
        if (operation.type === 'rename-project' && !operation.id.startsWith('temp-')) await v2ChatApi.updateProject(operation.id, { base_version: operation.version, name: operation.name });
        if (operation.type === 'move-experience') await v2ChatApi.bulkMoveExperiences({ experience_ids: [operation.experienceId], target_project_id: idMap.get(operation.projectId) || operation.projectId });
        if (operation.type === 'delete-experience' && !operation.experience.id.startsWith('temp-')) await v2ChatApi.deleteExperience(operation.experience.id, { version: operation.experience.version, confirm: true });
        if (operation.type === 'delete-project' && !operation.project.id.startsWith('temp-')) await v2ChatApi.deleteProject(operation.project.id, { version: operation.project.version, confirm: true, cascade: true });
        if (operation.type === 'delete-domain' && !operation.domain.id.startsWith('temp-')) await v2ChatApi.deleteDomain(operation.domain.id, { version: operation.domain.version, confirm: true, cascade: true });
      }
      const remapId = (id) => idMap.get(id) || id;
      const savedOrder = {
        domains: structureOrder.domains.map(remapId),
        projects: Object.fromEntries(Object.entries(structureOrder.projects).map(([domainId, ids]) => [remapId(domainId), ids.map(remapId)])),
        experiences: Object.fromEntries(Object.entries(structureOrder.experiences).map(([projectId, ids]) => [remapId(projectId), ids])),
      };
      setStructureOrder(savedOrder);
      window.localStorage.setItem(ORDER_STORAGE_KEY, JSON.stringify(savedOrder));
      setPendingOps([]); setEditMode(false); setDraftDomainId(''); editSnapshotRef.current = null; await refresh();
    } catch (reason) { setError(reason.message || '변경사항을 저장하지 못했습니다. 다시 시도해 주세요.'); }
    finally { setSavingStructure(false); }
  };

  return <div className={`mv2-manager mv2-manager--v3 ${selected ? 'has-preview' : ''}`}>
    <main>
      <header className="mv2-page-header"><div><span className="mv2-kicker">EXPERIENCE LIBRARY</span><h1>경험 관리</h1><p>정리된 경험을 분류하고 직접 수정·관리하세요.</p></div><div className="mv2-header-actions">{editMode ? <><button className="mv2-button mv2-button--secondary" onClick={addDomain}>+ 경험 분류</button><button className="mv2-button mv2-button--secondary" onClick={() => setEditing({})} disabled={!domains.some((domain) => domain.projects.length)}>+ 경험 추가</button></> : <button className="mv2-button" onClick={beginEditMode}>경험 편집하기</button>}</div></header>
      {status === 'loading' && <p className="mv2-sync-status">경험 구조를 불러오는 중입니다…</p>}
      {error && <div className="mv2-sync-error" role="alert"><span>{error}</span><button onClick={status === 'error' ? refresh : () => setError('')}>{status === 'error' ? '다시 시도' : '닫기'}</button></div>}
      <section className="mv2-summary" aria-label="커리어 자산 요약"><button onClick={clearSearch}><strong>{experiences.length}</strong><span>전체 경험</span><small>정리된 경험 보기</small></button><button onClick={() => setAssetModal('evidence')}><strong>{evidenceTotal}</strong><span>경험 근거</span><small>원본 리스트 보기</small></button><button onClick={() => setAssetModal('skills')}><strong>{skillTotal}</strong><span>내 역량</span><small>직군 · 직업 · 역량 보기</small></button></section>
      <section className="mv2-discovery-panel" aria-label="경험 검색"><div className="mv2-toolbar"><label className="mv2-search"><span className="sr-only">경험 검색</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="경험, 프로젝트·활동, 역량 검색" /></label><strong>{visibleExperienceCount}개 경험</strong></div></section>
      <div className="mv2-structure">{displayDomains.map(({ domain, projects, experiences: domainExperiences }) => {
        const isCollapsed = !normalizedQuery && collapsed.has(domain.id);
        const toggleDomain = () => setCollapsed((value) => { const next = new Set(value); next.has(domain.id) ? next.delete(domain.id) : next.add(domain.id); return next; });
        return <section key={domain.id} className={`${isCollapsed ? 'is-collapsed' : ''} ${dropTarget === `domain:${domain.id}` ? 'is-order-target' : ''}`} onDragOver={(event) => { if (!editMode) return; event.preventDefault(); event.stopPropagation(); setDropTarget(`domain:${domain.id}`); }} onDragLeave={() => setDropTarget('')} onDrop={(event) => { if (!editMode) return; event.preventDefault(); event.stopPropagation(); const payload = readDragPayload(event); if (payload?.kind === 'domain') reorderDomain(payload.id, domain.id); setDropTarget(''); }}>
          {domain.isDraft ? <header className="mv2-structure-header mv2-domain-draft" onClick={(event) => event.stopPropagation()}><input autoFocus value={domain.name} onChange={(event) => updateDraftDomain(domain.id, event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') finalizeDraftDomain(domain); if (event.key === 'Escape') cancelDraftDomain(domain.id); }} placeholder="새 경험 분류 이름" aria-label="새 경험 분류 이름" /><div><button type="button" className="mv2-button mv2-button--secondary" onClick={() => cancelDraftDomain(domain.id)}>취소</button><button type="button" className="mv2-button" onClick={() => finalizeDraftDomain(domain)}>추가</button></div></header> : <header className="mv2-structure-header" draggable={editMode} onDragStart={(event) => { event.stopPropagation(); event.dataTransfer.setData('application/json', JSON.stringify({ kind: 'domain', id: domain.id })); }} onClick={toggleDomain}><button className="mv2-domain-toggle" aria-expanded={!isCollapsed}><h3><HighlightText text={domain.name} query={query} /></h3></button>{editMode && <MoreMenu label={`${domain.name} 관리`}><button onClick={() => addProject(domain)}>프로젝트·활동 추가</button><button onClick={() => renameDomain(domain)}>이름 변경</button><button className="is-danger" onClick={() => requestDeleteDomain(domain)}>분류 삭제</button></MoreMenu>}<span className="mv2-domain-count">{domainExperiences.length}개 경험</span><button type="button" className="mv2-domain-chevron" aria-label={`${domain.name} ${isCollapsed ? '펼치기' : '접기'}`} aria-expanded={!isCollapsed}>{isCollapsed ? '⌄' : '⌃'}</button></header>}
          {!isCollapsed && !domain.isDraft && <div className="mv2-projects">{projects.map(({ project, experiences: projectExperiences }) => {
            return <div className={`mv2-project ${dropTarget === project.id ? 'is-drop-target' : ''}`} key={project.id} onDragOver={(event) => { if (!editMode) return; event.preventDefault(); event.stopPropagation(); setDropTarget(project.id); }} onDragLeave={() => setDropTarget('')} onDrop={(event) => { if (!editMode) return; event.preventDefault(); event.stopPropagation(); const payload = readDragPayload(event); if (payload?.kind === 'project') reorderProject(domain.id, payload.id, project.id); if (payload?.kind === 'experience') moveExperience(payload.id, project.id); setDropTarget(''); }}>
              <div className="mv2-project__title" draggable={editMode} onDragStart={(event) => { event.stopPropagation(); event.dataTransfer.setData('application/json', JSON.stringify({ kind: 'project', id: project.id, domainId: domain.id })); }}><strong><HighlightText text={project.name} query={query} /></strong>{editMode && <MoreMenu label={`${project.name} 관리`}><button onClick={() => setEditing({ domain, project })}>경험 추가</button><button onClick={() => renameProject(project)}>이름 변경</button><button className="is-danger" onClick={() => requestDeleteProject(project)}>프로젝트·활동 삭제</button></MoreMenu>}</div>
              <div className={`mv2-project__experiences ${projectExperiences.length ? '' : 'is-empty'}`}>{projectExperiences.length ? projectExperiences.map((experience) => <article className={`mv2-experience-tile ${selected?.id === experience.id ? 'is-selected' : ''} ${dropTarget === `experience:${experience.id}` ? 'is-order-target' : ''}`} draggable={editMode} key={experience.id} onDragStart={(event) => { if (!editMode) return; event.stopPropagation(); event.dataTransfer.setData('application/json', JSON.stringify({ kind: 'experience', id: experience.id, projectId: project.id })); }} onDragOver={(event) => { if (!editMode) return; event.preventDefault(); event.stopPropagation(); setDropTarget(`experience:${experience.id}`); }} onDragLeave={() => setDropTarget('')} onDrop={(event) => { if (!editMode) return; event.preventDefault(); event.stopPropagation(); const payload = readDragPayload(event); if (payload?.kind === 'experience') payload.projectId === project.id ? reorderExperience(project.id, payload.id, experience.id) : moveExperience(payload.id, project.id, experience.id); setDropTarget(''); }}><button className="mv2-experience-main" aria-expanded={selected?.id === experience.id} onClick={(event) => togglePreview(experience, event.currentTarget)}><span><strong><HighlightText text={experience.title} query={query} /></strong><small><HighlightText text={(experience.skills || []).slice(0, 2).join(' · ') || '역량 미입력'} query={query} /> · 근거 {experience.evidenceCount}</small></span></button>{editMode && <MoreMenu label={`${experience.title} 관리`}><button onClick={() => setEditing(experience)}>수정</button><button className="is-danger" onClick={() => requestDeleteExperience(experience)}>경험 삭제</button></MoreMenu>}</article>) : <div className="mv2-v3-empty-project"><p>아직 경험이 없습니다.</p>{editMode && <button onClick={() => setEditing({ domain, project })}>+ 이곳에 경험 추가</button>}</div>}</div>
            </div>;
          })}{editMode && !normalizedQuery && domain.projects.length === 0 && <button className="mv2-v3-add-project" onClick={() => addProject(domain)}>+ 첫 프로젝트·활동 추가</button>}</div>}
        </section>;
      })}</div>
      {status === 'ready' && hasFilters && displayDomains.length === 0 && <section className="mv2-search-empty" role="status"><h2>조건에 맞는 경험이 없습니다.</h2><p>검색어나 필터 조건을 변경해 보세요.</p><button onClick={clearSearch}>검색·필터 초기화</button></section>}
      {status === 'ready' && domains.length === 0 && <section className="mv2-empty"><h2>첫 경험 분류를 만들어 보세요</h2><p>직장 경험, 교육·학습, 대외 활동처럼 경험을 나눌 기준을 추가할 수 있습니다.</p>{editMode ? <button className="mv2-button" onClick={addDomain}>+ 경험 분류 만들기</button> : <button className="mv2-button" onClick={beginEditMode}>편집 시작</button>}</section>}
      {editMode && <div className="mv2-edit-bar" role="status"><span>{draftDomainId ? '새 경험 분류 이름을 입력해 주세요.' : pendingOps.length ? `저장하지 않은 변경 ${pendingOps.length}건` : '편집 모드 · 아직 변경사항이 없습니다.'}</span><button className="mv2-button mv2-button--secondary" onClick={cancelEditMode} disabled={savingStructure}>취소</button><button className="mv2-button" onClick={saveStructure} disabled={!pendingOps.length || Boolean(draftDomainId) || savingStructure}>{savingStructure ? '저장 중…' : '변경사항 저장'}</button></div>}
    </main>
    {selected && <aside ref={previewRef} style={previewPosition || undefined} className="mv2-preview" role="dialog" aria-label={`${selected.title} 간단 상세`}><header><div><span className="mv2-kicker">경험</span><h2>{selected.title}</h2><p>{selected.projectName}</p></div><button className="mv2-icon-button" onClick={() => { setSelected(null); setPreviewPosition(null); previewAnchorRef.current = null; }} aria-label="닫기">×</button></header><section><h3>요약</h3><p>{selected.summary || '입력된 요약이 없습니다.'}</p></section><section><h3>역량</h3><div className="mv2-skills">{(selected.skills || []).map((skill) => <span key={skill}>{skill}</span>)}</div></section><footer><Link className="mv2-button mv2-button--secondary" to={`/memory/${selected.id}`}>상세 보기</Link><button className="mv2-button" onClick={() => setEditing(selected)}>수정</button></footer></aside>}
    {editing && <ExperienceForm item={editing.id ? editing : editing.project ? { domainName: editing.domain.name, project: editing.project } : null} domains={domains} onClose={() => setEditing(null)} onSave={saveExperience} />}
    <AssetModal type={assetModal} experiences={experiences} onClose={() => setAssetModal(null)} onSearch={searchBySkill} />
    {confirm && <div className="mv2-modal-backdrop"><section className="mv2-confirm" role="alertdialog" aria-modal="true"><span className="mv2-kicker is-danger">삭제 확인</span><h2>{confirm.title}</h2><p>{confirm.description}</p><footer><button className="mv2-button mv2-button--secondary" onClick={() => setConfirm(null)}>취소</button><button className="mv2-button mv2-button--danger" onClick={confirm.action}>삭제</button></footer></section></div>}
  </div>;
}

export default ExperienceManagerV3;
