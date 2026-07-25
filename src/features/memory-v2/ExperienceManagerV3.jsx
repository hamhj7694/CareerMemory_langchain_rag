import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { v2ChatApi } from '../../api/v2ChatApi.js';
import { createEmptyExperience, toExperience } from '../experience/model/experienceMapper.js';
import { selectExperienceCard, selectExperiencePreview } from '../experience/model/experienceSelectors.js';
import { buildSkillProfile, listExperienceRoles } from '../experience/model/skillModel.js';
import { ExperienceIntakeModal } from '../experience/components/ExperienceIntakeModal.jsx';
import { InlineProposalCard } from '../chat/InlineProposalCard.jsx';
import { MemoryDetailPage } from '../../pages/MemoryDetailPage.jsx';
import './memory-manager.css';

const toView = (item) => toExperience(item);

const createdTimeValue = (item) => new Date(item.created_at || item.createdAt || 0).getTime() || 0;
const structureNameKey = (value) => String(value || '')
  .normalize('NFKC')
  .replace(/[\u200B-\u200D\uFEFF]/g, '')
  .trim()
  .replace(/\s+/g, ' ')
  .toLocaleLowerCase('ko-KR');
const ORDER_STORAGE_KEY = 'career-memory.experience-structure-order.v1';
const FAILED_EXPERIENCE_DRAFTS_KEY = 'career-memory.failed-experience-drafts.v1';
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
  const mappedExperiences = experiences.items.map(toView);
  return { experiences: mappedExperiences, domains: mergeExperienceStructure(structure.domains, mappedExperiences) };
}

// Keep experiences visible even when an older/mock record has a missing or stale
// domain/project reference. The record remains unchanged; only the view structure
// receives a deterministic fallback node.
function mergeExperienceStructure(domains, experiences) {
  const next = [];
  const domainById = new Map();
  const domainByName = new Map();
  const projectById = new Map();

  // Older mock data can contain different IDs for visually identical names.
  // Normalize and merge those nodes before experiences are assigned.
  structuredClone(domains || []).forEach((sourceDomain) => {
    const domainName = sourceDomain.name?.trim() || '미분류 경험';
    const domainKey = structureNameKey(domainName) || `id:${sourceDomain.id}`;
    let domain = domainByName.get(domainKey);
    if (!domain) {
      domain = { ...sourceDomain, name: domainName, projects: [] };
      next.push(domain);
      domainByName.set(domainKey, domain);
    }
    domainById.set(sourceDomain.id, domain);

    const projectByName = new Map(domain.projects.map((project) => [structureNameKey(project.name), project]));
    (sourceDomain.projects || []).forEach((sourceProject) => {
      const projectName = sourceProject.name?.trim() || '프로젝트·활동 미분류';
      const projectKey = structureNameKey(projectName) || `id:${sourceProject.id}`;
      let project = projectByName.get(projectKey);
      if (!project) {
        project = { ...sourceProject, domain_id: domain.id, name: projectName };
        domain.projects.push(project);
        projectByName.set(projectKey, project);
      }
      projectById.set(sourceProject.id, project);
    });
  });

  experiences.forEach((experience) => {
    const domainKey = structureNameKey(experience.domainName);
    let domain = (experience.domainId && domainById.get(experience.domainId)) || domainByName.get(domainKey);
    if (!domain) {
      const key = experience.domainId || experience.domainName || '미분류 경험';
      domain = { id: `ORPHAN-DOM-${encodeURIComponent(key)}`, name: experience.domainName || '미분류 경험', projects: [], created_at: experience.createdAt || '', updated_at: experience.updatedAt || '', version: 1 };
      next.push(domain);
      domainById.set(domain.id, domain);
      domainByName.set(structureNameKey(domain.name), domain);
    }
    experience.domainId = domain.id;
    experience.domainName = domain.name;
    const projectByName = new Map((domain.projects || []).map((project) => [structureNameKey(project.name), project]));
    let project = (experience.projectId && projectById.get(experience.projectId)) || projectByName.get(structureNameKey(experience.projectName));
    if (!project) {
      const key = experience.projectId || experience.projectName || '프로젝트·활동 미분류';
      project = { id: `ORPHAN-PROJ-${encodeURIComponent(domain.id)}-${encodeURIComponent(key)}`, domain_id: domain.id, name: experience.projectName || '프로젝트·활동 미분류', organization: experience.organization || '', experiences: [], created_at: experience.createdAt || '', updated_at: experience.updatedAt || '', version: 1 };
      domain.projects = [...(domain.projects || []), project];
      projectById.set(project.id, project);
    }
    experience.projectId = project.id;
    experience.projectName = project.name;
  });
  return next;
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
  const profile = buildSkillProfile(experiences);
  const roles = listExperienceRoles(experiences);
  const groups = profile.groups;
  const totalOccurrences = profile.totalLinks;
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
    {evidenceMode ? <div className="mv2-evidence-library mv2-source-library">{experiences.filter((item) => item.evidenceCount > 0).map((item) => <article key={item.id} className="mv2-source-group"><div className="mv2-source-group__summary"><div><strong>{item.title}</strong><span>{item.domainName} · {item.projectName}</span></div><span className="mv2-evidence-count">원본 {item.evidenceCount}개</span><button onClick={() => setExpanded(expanded === item.id ? null : item.id)} aria-expanded={expanded === item.id}>{expanded === item.id ? '접기' : '원본 보기'}</button></div>{expanded === item.id && <div className="mv2-source-items">{sourceEntries(item).map((source) => <section key={source.id}><div><span className={`mv2-source-kind is-${source.type}`}>{source.type === 'text' ? '텍스트' : '파일'}</span><strong>{source.name}</strong></div>{source.type === 'text' ? <p>{source.content}</p> : <button onClick={() => downloadSource(source)}>다운로드</button>}</section>)}</div>}</article>)}</div> : <div className="mv2-profile-groups"><section><h3>내 직군·직업 및 역할</h3><div className="mv2-profile-tags">{roles.map((role) => <span key={role}>{role}</span>)}</div></section><section><h3>유사 역량 그룹</h3><div className="mv2-skill-distribution" aria-label="전체 역량 그룹 구성비">{groups.map((group) => <button type="button" key={group.name} style={{ width: `${group.percent}%` }} title={`${group.name} · 전체의 ${group.percent}% (${group.count}회)`} aria-label={`${group.name}, 전체의 ${group.percent}%, ${group.count}회. 클릭하여 역량 그룹 보기`} aria-pressed={selectedSkillGroup === group.name} onMouseEnter={() => setHoveredSkillGroup(group.name)} onMouseLeave={() => setHoveredSkillGroup(null)} onFocus={() => setHoveredSkillGroup(group.name)} onBlur={() => setHoveredSkillGroup(null)} onClick={() => toggleSkillGroup(group.name, true)} />)}</div><div className="mv2-skill-groups">{groups.map((group, index) => <article id={`skill-group-${encodeURIComponent(group.name)}`} role="button" tabIndex="0" className={activeSkillGroup === group.name ? 'is-focused' : ''} key={group.name} onClick={() => onSearch({ type: 'group', value: group.name })} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSearch({ type: 'group', value: group.name }); } }}><div className="mv2-skill-group__heading"><strong><i className={`mv2-skill-dot is-${index + 1}`} />{group.name}</strong><span>전체의 {group.percent}% · {group.count}회</span></div><div className="mv2-profile-tags is-skills">{group.skills.map((skill) => <button type="button" key={skill} onClick={(event) => { event.stopPropagation(); onSearch({ type: 'skill', value: skill }); }}>{skill}</button>)}</div></article>)}</div><p className="mv2-percent-note">모든 그룹의 비율을 합하면 약 100%입니다. 반올림으로 1% 정도 차이가 날 수 있으며, 숙련도나 달성률을 의미하지 않습니다.</p></section></div>}
  </section></div>;
}

export function ExperienceManagerV3() {
  const [experiences, setExperiences] = useState([]);
  const [domains, setDomains] = useState([]);
  const [query, setQuery] = useState('');
  const [skillGroupFilter, setSkillGroupFilter] = useState('');
  const [collapsed, setCollapsed] = useState(new Set());
  const [selectedExperienceId, setSelectedExperienceId] = useState(null);
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
  const [draftProject, setDraftProject] = useState(null);
  const [nameEditor, setNameEditor] = useState(null);
  const [newExperienceOpen, setNewExperienceOpen] = useState(false);
  const [newExperienceContext, setNewExperienceContext] = useState({ domainId: '', projectId: '' });
  const [experienceIntakeOpen, setExperienceIntakeOpen] = useState(false);
  const [experienceIntakeBusy, setExperienceIntakeBusy] = useState(false);
  const [newExperienceDraft, setNewExperienceDraft] = useState(null);
  const [experienceProposal, setExperienceProposal] = useState(null);
  const [experiencePreviewOpen, setExperiencePreviewOpen] = useState(false);
  const [experiencePreviewBusy, setExperiencePreviewBusy] = useState(false);
  const [experienceProposalEditing, setExperienceProposalEditing] = useState(false);
  const [structureOrder, setStructureOrder] = useState(readStructureOrder);
  const editSnapshotRef = useRef(null);
  const selectedExperience = experiences.find((item) => item.id === selectedExperienceId) || null;
  const selected = selectedExperience ? selectExperiencePreview(selectedExperience) : null;

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
  const hasFilters = Boolean(normalizedQuery || skillGroupFilter);
  const filtered = useMemo(() => experiences.filter((item) => {
    const searchable = `${item.title} ${item.summary} ${item.role} ${item.domainName} ${item.projectName} ${(item.skills || []).join(' ')} ${(item.results || []).join(' ')} ${(item.actions || []).join(' ')}`.toLowerCase();
    const matchesText = !normalizedQuery || searchable.includes(normalizedQuery);
    const matchesSkillGroup = !skillGroupFilter || buildSkillProfile([item]).groups.some((group) => group.name === skillGroupFilter);
    return matchesText && matchesSkillGroup;
  }).sort((a, b) => createdTimeValue(b) - createdTimeValue(a)), [experiences, normalizedQuery, skillGroupFilter]);
  const displayDomains = useMemo(() => sortBySavedOrder(domains, structureOrder.domains).map((domain) => {
    const projects = sortBySavedOrder(domain.projects, structureOrder.projects[domain.id]).map((project) => {
      const visibleExperiences = sortBySavedOrder(filtered.filter((item) => item.projectId === project.id), structureOrder.experiences[project.id]);
      return { project, experiences: visibleExperiences };
    }).filter(({ experiences: visibleExperiences }) => !hasFilters || visibleExperiences.length > 0);
    return { domain, projects, experiences: projects.flatMap((project) => project.experiences) };
  }).filter(({ projects }) => !hasFilters || projects.length > 0), [domains, filtered, hasFilters, structureOrder]);
  const visibleExperienceCount = new Set(displayDomains.flatMap((domain) => domain.experiences.map((item) => item.id))).size;
  const evidenceTotal = experiences.reduce((sum, item) => sum + item.evidenceCount, 0);
  const skillTotal = new Set(experiences.flatMap((item) => item.skills || [])).size;
  const clearSearch = () => { setQuery(''); setSkillGroupFilter(''); };
  const searchBySkill = ({ type, value }) => {
    if (type === 'group') { setSkillGroupFilter(value); setQuery(''); }
    else { setSkillGroupFilter(''); setQuery(value); }
    setAssetModal(null);
    setSelectedExperienceId(null);
  };

  const togglePreview = (experience, anchor) => {
    if (selected?.id === experience.id) {
      setSelectedExperienceId(null);
      setPreviewPosition(null);
      previewAnchorRef.current = null;
      return;
    }
    previewAnchorRef.current = anchor;
    setPreviewPosition(null);
    setSelectedExperienceId(experience.id);
  };

  useEffect(() => {
    if (!selected) return undefined;
    const updatePosition = () => {
      if (window.matchMedia('(max-width: 767px)').matches) { setPreviewPosition({}); return; }
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
      setSelectedExperienceId(null);
      setPreviewPosition(null);
      previewAnchorRef.current = null;
    };
    document.addEventListener('pointerdown', closeOnOutsideClick);
    return () => document.removeEventListener('pointerdown', closeOnOutsideClick);
  }, [selected]);

  const beginEditMode = () => { editSnapshotRef.current = { domains: structuredClone(domains), experiences: structuredClone(experiences), structureOrder: structuredClone(structureOrder) }; setPendingOps([]); setEditMode(true); setSelectedExperienceId(null); };
  const cancelEditMode = () => {
    if (pendingOps.length && !window.confirm('저장하지 않은 변경을 취소하고 원래 상태로 되돌릴까요?')) return;
    if (editSnapshotRef.current) { setDomains(editSnapshotRef.current.domains); setExperiences(editSnapshotRef.current.experiences); setStructureOrder(editSnapshotRef.current.structureOrder); }
    setPendingOps([]); setEditMode(false); setDropTarget(''); setDraftDomainId(''); setDraftProject(null); setNameEditor(null); editSnapshotRef.current = null;
  };
  const addDomain = () => {
    if (draftDomainId) { setError('먼저 작성 중인 경험 분류를 추가하거나 취소해 주세요.'); return; }
    const domain = { id: `temp-domain-${crypto.randomUUID()}`, name: '', version: 1, projects: [], created_at: new Date().toISOString(), isDraft: true };
    setQuery(''); setDomains((items) => [domain, ...items]); setDraftDomainId(domain.id);
  };
  const updateDraftDomain = (id, name) => setDomains((items) => items.map((domain) => domain.id === id ? { ...domain, name } : domain));
  const cancelDraftDomain = (id) => {
    setDomains((items) => items.filter((domain) => domain.id !== id));
    setPendingOps((items) => items.filter((operation) => !(operation.type === 'create-project' && operation.domainId === id)));
    if (draftProject?.domainId === id) setDraftProject(null);
    setDraftDomainId('');
  };
  const finalizeDraftDomain = (domain) => {
    const name = domain.name.trim();
    if (!name) { setError('경험 분류 이름을 입력해 주세요.'); return null; }
    if (domains.some((item) => item.id !== domain.id && item.name.trim().toLowerCase() === name.toLowerCase())) { setError('이미 같은 이름의 경험 분류가 있습니다.'); return null; }
    const finalized = { ...domain, name, isDraft: false };
    setDomains((items) => items.map((item) => item.id === domain.id ? finalized : item));
    setPendingOps((items) => [...items, { type: 'create-domain', domain: finalized }]);
    setDraftDomainId(''); setError('');
    return finalized;
  };
  const addProject = async (domain) => {
    if (domain.isDraft) {
      const name = domain.name.trim();
      if (!name) { setError('먼저 경험 분류 이름을 입력해 주세요.'); return; }
      try {
        const created = await v2ChatApi.createDomain({ name });
        setDomains((items) => items.map((item) => item.id === domain.id ? { ...created, projects: [] } : item));
        if (editSnapshotRef.current) editSnapshotRef.current = { ...editSnapshotRef.current, domains: [...editSnapshotRef.current.domains, { ...created, projects: [] }] };
        setPendingOps((items) => items.filter((operation) => operation.domain?.id !== domain.id));
        setDraftDomainId('');
        setError('');
        openExperienceIntake({ domainId: created.id, projectId: '' });
      } catch (reason) { setError(reason.message || '경험 분류를 추가하지 못했습니다.'); }
      return;
    }
    openExperienceIntake({ domainId: domain.id, projectId: '' });
  };
  const finalizeDraftProject = (domain) => {
    const name = draftProject?.name.trim();
    if (!name) { setError('프로젝트·활동 이름을 입력해 주세요.'); return; }
    const project = { id: `temp-project-${crypto.randomUUID()}`, name, version: 1, experiences: [] };
    setDomains((items) => items.map((item) => item.id === domain.id ? { ...item, projects: [...item.projects, project] } : item));
    setPendingOps((items) => [...items, { type: 'create-project', domainId: domain.id, project }]);
    setDraftProject(null);
    setError('');
  };
  const renderDraftProject = (domain) => <div className="mv2-project-draft">
    <label><span className="mv2-node-mark">프로젝트·활동</span><input autoFocus value={draftProject?.name || ''} onChange={(event) => setDraftProject({ domainId: domain.id, name: event.target.value })} onKeyDown={(event) => { if (event.key === 'Enter') finalizeDraftProject(domain); if (event.key === 'Escape') setDraftProject(null); }} placeholder="새 프로젝트·활동 이름" aria-label="새 프로젝트·활동 이름" /></label>
    <div><button type="button" className="mv2-button mv2-button--secondary" onClick={() => setDraftProject(null)}>취소</button><button type="button" className="mv2-button" onClick={() => finalizeDraftProject(domain)}>추가</button></div>
  </div>;
  const renameDomain = (domain) => setNameEditor({ kind: 'domain', id: domain.id, version: domain.version, name: domain.name, originalName: domain.name });
  const renameProject = (project) => setNameEditor({ kind: 'project', id: project.id, version: project.version, name: project.name, originalName: project.name });
  const commitNameEditor = () => {
    const name = nameEditor?.name.trim();
    if (!name) { setError('이름을 입력해 주세요.'); return; }
    if (name === nameEditor.originalName) { setNameEditor(null); return; }
    if (nameEditor.kind === 'domain') {
      setDomains((items) => items.map((item) => item.id === nameEditor.id ? { ...item, name } : item));
      setExperiences((items) => items.map((item) => item.domainId === nameEditor.id ? { ...item, domainName: name } : item));
      setPendingOps((items) => [...items, { type: 'rename-domain', id: nameEditor.id, version: nameEditor.version, name }]);
    } else {
      setDomains((items) => items.map((domain) => ({ ...domain, projects: domain.projects.map((item) => item.id === nameEditor.id ? { ...item, name } : item) })));
      setExperiences((items) => items.map((item) => item.projectId === nameEditor.id ? { ...item, projectName: name } : item));
      setPendingOps((items) => [...items, { type: 'rename-project', id: nameEditor.id, version: nameEditor.version, name }]);
    }
    setNameEditor(null); setError('');
  };
  const renderNameEditor = () => <div className="mv2-name-editor" onClick={(event) => event.stopPropagation()}><input autoFocus value={nameEditor.name} onChange={(event) => setNameEditor({ ...nameEditor, name: event.target.value })} onKeyDown={(event) => { if (event.key === 'Enter') commitNameEditor(); if (event.key === 'Escape') setNameEditor(null); }} /><button type="button" onClick={() => setNameEditor(null)}>취소</button><button type="button" onClick={commitNameEditor}>확정</button></div>;
  const renderDraftDomain = (domain) => {
    return <><header className="mv2-structure-header mv2-domain-draft" onClick={(event) => event.stopPropagation()}><label className="mv2-draft-domain-input"><span className="mv2-node-mark">최상단 구분 · 경험 분류</span><input autoFocus value={domain.name} onChange={(event) => updateDraftDomain(domain.id, event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') finalizeDraftDomain(domain); if (event.key === 'Escape') cancelDraftDomain(domain.id); }} placeholder="새 경험 분류 이름" aria-label="새 경험 분류 이름" /></label><div><button type="button" className="mv2-button mv2-button--danger" onClick={() => cancelDraftDomain(domain.id)}>삭제</button><button type="button" className="mv2-button" onClick={() => finalizeDraftDomain(domain)}>추가</button></div></header><div className="mv2-domain-draft__empty">{domain.projects.map((project) => <div className="mv2-draft-project-row" key={project.id}><span className="mv2-node-mark">프로젝트·활동</span><strong>{project.name}</strong></div>)}{draftProject?.domainId === domain.id ? renderDraftProject(domain) : <button type="button" className="mv2-v3-add-project" onClick={() => setDraftProject({ domainId: domain.id, name: '' })}>+ 프로젝트·활동 추가</button>}</div></>;
  };

  const requestDeleteDomain = (domain) => setConfirm({ title: `‘${domain.name}’ 분류를 삭제 목록에 추가할까요?`, description: `저장할 때 프로젝트·활동 ${domain.projects.length}개와 포함된 경험이 휴지통으로 이동합니다. 저장 전에는 취소할 수 있습니다.`, action: () => { setDomains((items) => items.filter((item) => item.id !== domain.id)); setExperiences((items) => items.filter((item) => item.domainId !== domain.id)); setPendingOps((items) => [...items, { type: 'delete-domain', domain }]); setConfirm(null); } });
  const requestDeleteProject = (project) => setConfirm({ title: `‘${project.name}’을 삭제 목록에 추가할까요?`, description: '저장할 때 포함된 경험이 휴지통으로 이동합니다. 저장 전에는 취소할 수 있습니다.', action: () => { setDomains((items) => items.map((domain) => ({ ...domain, projects: domain.projects.filter((item) => item.id !== project.id) }))); setExperiences((items) => items.filter((item) => item.projectId !== project.id)); setPendingOps((items) => [...items, { type: 'delete-project', project }]); setConfirm(null); } });
  const requestDeleteExperience = (experience) => setConfirm({ title: `‘${experience.title}’ 경험을 삭제 목록에 추가할까요?`, description: '저장할 때 경험이 휴지통으로 이동합니다. 저장 전에는 취소할 수 있습니다.', action: () => { setExperiences((items) => items.filter((item) => item.id !== experience.id)); setPendingOps((items) => [...items, { type: 'delete-experience', experience }]); setConfirm(null); if (selected?.id === experience.id) setSelectedExperienceId(null); } });
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
    const projectItems = experiences.filter((item) => item.projectId === projectId);
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
    setExperiences((items) => items.map((item) => item.id === experienceId ? { ...item, domainId: targetDomain.id, domainName: targetDomain.name, projectId: targetProject.id, projectName: targetProject.name, organization: targetProject.organization || '' } : item));
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
  const saveStructure = async ({ openExperienceFor = null } = {}) => {
    if (draftDomainId) { setError('경험 분류 이름을 먼저 확정해 주세요.'); return; }
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
      if (openExperienceFor) {
        const domainId = remapId(openExperienceFor.domainId);
        const projectId = remapId(openExperienceFor.projectId);
        openExperienceIntake({ domainId, projectId });
      }
    } catch (reason) { setError(reason.message || '변경사항을 저장하지 못했습니다. 다시 시도해 주세요.'); }
    finally { setSavingStructure(false); }
  };
  const startExperience = (domain, project) => {
    if (domain.isDraft) { setError('경험 분류 이름을 먼저 확정해 주세요.'); return; }
    if (editMode && pendingOps.length) {
      saveStructure({ openExperienceFor: { domainId: domain.id, projectId: project.id } });
      return;
    }
    openExperienceIntake({ domainId: domain.id, projectId: project.id });
  };

  const openExperienceIntake = (context = {}) => {
    setNewExperienceContext(context);
    setNewExperienceDraft(null);
    setExperienceIntakeOpen(true);
  };

  const openNewExperience = () => openExperienceIntake();
  const closeExperienceIntake = () => setExperienceIntakeOpen(false);
  const closeNewExperience = () => {
    setNewExperienceOpen(false);
    setNewExperienceDraft(null);
  };
  const makeExperienceProposal = (draft, uploadedAttachments = []) => {
    const sourceRefs = [
      ...(draft.summary ? [{ id: `LOCAL-TEXT-${Date.now()}`, source_type: 'text', title: '직접 입력 원문', text: draft.summary, captured_at: new Date().toISOString(), linked_facts: [] }] : []),
      ...uploadedAttachments.map((file) => ({ id: file.id, source_type: 'file', title: file.filename, filename: file.filename, mime_type: file.mime_type, uploaded_at: file.created_at, captured_at: file.created_at, text: file.raw_text || '', linked_facts: [] })),
    ];
    const sourceIds = sourceRefs.map((source) => source.id);
    const experience = {
      draft_id: `DRAFT-${Date.now()}-1`,
      title: draft.title,
      domain: draft.domainName,
      project: draft.projectName,
      role: draft.role,
      summary: draft.summary,
      situation: draft.situation,
      actions: draft.actions || [],
      results: draft.results || [],
      facts: draft.facts || [],
      skills: draft.skills || [],
      evidenceCount: sourceIds.length,
      source_ref_ids: sourceIds,
      source_refs: sourceRefs,
      missing_information: [],
    };
    const mockExperience = {
      ...experience,
      draft_id: `DRAFT-${Date.now()}-2`,
      domain: '사이드 프로젝트',
      project: '새 프로젝트·활동 2',
      title: `${draft.title || '새 경험'} 2`,
      summary: draft.summary || '두 번째 경험 초안입니다.',
    };
    return { id: `LOCAL-PROPOSAL-${Date.now()}`, version: 1, kind: 'experience', title: '경험 구조화 제안', domain: experience.domain, project: experience.project, experiences: [experience, mockExperience], rawPayload: { experiences: [experience, mockExperience] } };
  };
  const analyzeExperience = async ({ content, files }) => {
    setExperienceIntakeBusy(true);
    try {
      const uploadedAttachments = files.length ? await v2ChatApi.uploadAttachments(files) : [];
      // The structure may have been created immediately before opening this modal.
      // Resolve the context from the latest API snapshot instead of a possibly stale
      // React state value so the first draft receives the selected domain/project.
      let contextDomains = domains;
      try { contextDomains = (await v2ChatApi.listStructure()).domains || domains; } catch { /* use the last rendered snapshot */ }
      const domain = contextDomains.find((entry) => entry.id === newExperienceContext.domainId);
      const project = domain?.projects?.find((entry) => entry.id === newExperienceContext.projectId);
      if (contextDomains !== domains) setDomains(contextDomains);
      const fileText = files.map((file) => file.name).join(', ');
      const extractedFileText = uploadedAttachments.map((file) => file.raw_text?.trim()).filter(Boolean).join('\n\n');
      content = [content, extractedFileText].filter(Boolean).join('\n\n');
      const sourceText = [content, fileText ? `첨부 파일: ${fileText}` : ''].filter(Boolean).join('\n\n');
      const firstLine = sourceText.split('\n').map((line) => line.trim()).find(Boolean) || '새 경험';
      const draft = createEmptyExperience({
        domainId: newExperienceContext.domainId || '',
        domainName: domain?.name || '',
        projectId: newExperienceContext.projectId || '',
        projectName: project?.name || '',
        organization: project?.organization || '',
        title: firstLine.replace(/^[-*#\d.)\s]+/, '').slice(0, 60) || '새 경험',
        summary: sourceText,
        situation: sourceText,
        actions: sourceText ? [sourceText] : [],
        results: [],
        facts: [],
        status: 'draft',
      });
      setNewExperienceDraft(draft);
      setExperienceProposal(makeExperienceProposal(draft, uploadedAttachments));
      setExperienceProposalEditing(false);
      setExperienceIntakeOpen(false);
      setExperiencePreviewOpen(true);
    } finally {
      setExperienceIntakeBusy(false);
    }
  };
  const closeExperiencePreview = async () => {
    if (experiencePreviewBusy) return;
    const hasUnsaved = experienceProposal?.experiences?.some((item) => !item.approved);
    if (hasUnsaved && !window.confirm('저장하지 않은 내용은 삭제됩니다. 정말 닫을까요?')) return;
    setExperiencePreviewBusy(true);
    try {
      await discardUncommittedAttachments(experienceProposal);
      setExperiencePreviewOpen(false); setExperienceProposal(null); setExperienceProposalEditing(false);
    } finally { setExperiencePreviewBusy(false); }
  };
  const updateExperiencePreview = async (panel) => { setExperienceProposal(panel); return panel; };
  // Uploaded files belong to a draft until at least one saved experience references them.
  // Remove only unreferenced pending files when a draft is discarded.
  const discardUncommittedAttachments = async (proposal) => {
    const experiences = proposal?.experiences || [];
    const retainedSourceIds = new Set(experiences.filter((item) => item.approved).flatMap((item) => item.source_ref_ids || item.source_ids || []));
    const pendingFileIds = new Set(experiences.filter((item) => !item.approved).flatMap((item) => (item.source_refs || [])
      .filter((source) => source.source_type === 'file' || source.kind === 'file')
      .map((source) => source.id)).filter(Boolean));
    await Promise.all([...pendingFileIds].filter((id) => !retainedSourceIds.has(id)).map((id) => v2ChatApi.deleteAttachment(id).catch(() => null)));
  };
  const preserveFailedExperienceDrafts = (proposal, items) => {
    if (!items.length) return;
    try {
      window.localStorage.setItem(FAILED_EXPERIENCE_DRAFTS_KEY, JSON.stringify({
        proposal_id: proposal?.id,
        saved_at: new Date().toISOString(),
        drafts: items,
      }));
    } catch { /* storage may be unavailable; the visible error still explains the failure */ }
  };
  const saveExperienceDraft = async (item) => {
    if (item.savedExperienceId) return v2ChatApi.getExperience(item.savedExperienceId);
    const domain = typeof item.domain === 'string' ? { name: item.domain } : item.domain;
    const project = typeof item.project === 'string' ? { name: item.project } : item.project;
    return v2ChatApi.createExperience({
      ...item,
      domain: domain || { name: '새 경험 분류' },
      project: project || { name: '새 프로젝트' },
      source_ids: item.source_ref_ids || item.source_ids || [],
      source_refs: item.source_refs || [],
    });
  };
  const markExperienceSaved = (proposal, index, saved) => {
    const experiences = (proposal.experiences || []).map((item, itemIndex) => itemIndex === index
      ? { ...item, approved: true, savedExperienceId: saved.id, savedAt: saved.created_at }
      : item);
    return { ...proposal, version: (proposal.version || 0) + 1, experiences, rawPayload: { ...(proposal.rawPayload || {}), experiences } };
  };
  const approveExperiencePreview = async (proposal) => {
    const requestedDraftId = proposal.selection?.draft_id;
    const draftIndex = requestedDraftId ? proposal.experiences?.findIndex((item) => item.draft_id === requestedDraftId) : -1;
    const index = draftIndex >= 0 ? draftIndex : (proposal.selection?.experience_indexes?.[0] ?? 0);
    const item = proposal.experiences?.[index] || proposal;
    if (item.approved) return proposal;
    setExperiencePreviewBusy(true); setError('');
    try {
      const saved = await saveExperienceDraft(item);
      // Use the latest proposal passed by the card; parent state can lag one render behind.
      const nextProposal = markExperienceSaved(proposal, index, saved);
      setExperienceProposal(nextProposal);
      await refresh();
      return nextProposal;
    } finally { setExperiencePreviewBusy(false); }
  };
  const removeExperiencePreview = async (proposal, sourceIndex) => {
    // The card passes its current edited snapshot, so do not replace it with stale parent state.
    const current = proposal;
    const removed = (current.experiences || [])[sourceIndex];
    // A saved draft is immutable from this preview; it must never be removed by
    // the pending-draft deletion path (and its evidence must stay retained).
    if (removed?.approved) return current;
    const experiences = (current.experiences || []).filter((item, index) => index !== sourceIndex || item.approved);
    const nextProposal = experiences.length
      ? { ...current, version: (current.version || 0) + 1, experiences, rawPayload: { ...(current.rawPayload || {}), experiences } }
      : null;
    if (removed) {
      const remainingSourceIds = new Set(experiences.flatMap((item) => item.source_ref_ids || item.source_ids || []));
      const removedFileIds = (removed.source_refs || []).filter((source) => source.source_type === 'file' || source.kind === 'file').map((source) => source.id).filter(Boolean);
      await Promise.all([...new Set(removedFileIds)].filter((id) => !remainingSourceIds.has(id)).map((id) => v2ChatApi.deleteAttachment(id).catch(() => null)));
    }
    if (!nextProposal) { setExperiencePreviewOpen(false); setExperienceProposal(null); return null; }
    setExperienceProposal(nextProposal);
    return nextProposal;
  };
  const discardRemainingExperienceDrafts = async () => {
    const hasPending = experienceProposal?.experiences?.some((item) => !item.approved);
    if (!hasPending) {
      setExperiencePreviewOpen(false); setExperienceProposal(null); setExperienceProposalEditing(false);
      return;
    }
    if (!window.confirm('저장하지 않은 경험 초안을 모두 삭제할까요? 이미 저장된 경험은 유지됩니다.')) return;
    if (experiencePreviewBusy) return;
    setExperiencePreviewBusy(true);
    try {
      await discardUncommittedAttachments(experienceProposal);
    } finally {
      setExperiencePreviewOpen(false);
      setExperienceProposal(null);
      setExperienceProposalEditing(false);
      setExperiencePreviewBusy(false);
    }
  };
  const saveAllExperienceDrafts = async () => {
    const current = experienceProposal;
    const pending = current?.experiences?.map((item, index) => ({ item, index })).filter(({ item }) => !item.approved) || [];
    if (experiencePreviewBusy) return;
    if (!pending.length) {
      setExperiencePreviewOpen(false); setExperienceProposal(null); setExperienceProposalEditing(false);
      return;
    }
    if (!window.confirm('저장하지 않은 경험을 모두 저장할까요?')) return;
    setExperiencePreviewBusy(true); setError('');
    try {
      // Keep each draft's index paired with its result. A failed request must not
      // make the remaining drafts disappear or be treated as saved.
      const results = await Promise.allSettled(pending.map(({ item }) => saveExperienceDraft(item)));
      let nextProposal = current;
       const failures = [];
      results.forEach((result, resultIndex) => {
         const { index } = pending[resultIndex];
        if (result.status === 'fulfilled') nextProposal = markExperienceSaved(nextProposal, index, result.value);
        else failures.push(result.reason?.message || `초안 ${index + 1}`);
      });
       const failedDrafts = results.flatMap((result, resultIndex) => result.status === 'rejected' ? [pending[resultIndex].item] : []);
       setExperienceProposal(nextProposal);
       await refresh().catch((reason) => setError(reason.message || '저장 후 목록을 갱신하지 못했습니다.'));
       if (failedDrafts.length) preserveFailedExperienceDrafts(current, failedDrafts);
      if (failures.length) throw new Error(`${failures.length}개 초안을 저장하지 못했습니다. 실패한 초안을 확인하고 다시 시도해 주세요.`);
      await refresh();
      setExperiencePreviewOpen(false);
      setExperienceProposal(null);
    } catch (reason) { setError(reason.message || '일부 경험을 저장하지 못했습니다.'); }
    finally {
      // 성공·부분 실패·예외 모두 동일하게 제안 창을 닫는다.
      setExperiencePreviewOpen(false);
      setExperienceProposal(null);
      setExperienceProposalEditing(false);
      setExperiencePreviewBusy(false);
    }
  };
  const handleNewExperienceSaved = async () => {
    await refresh();
  };
  const pendingExperienceCount = experienceProposal?.experiences?.filter((item) => !item.approved).length || 0;

  return <div className={`mv2-manager mv2-manager--v3 ${selected ? 'has-preview' : ''}`}>
    <main>
      <header className="mv2-page-header"><div><span className="mv2-kicker">EXPERIENCE LIBRARY</span><h1>경험 관리</h1><p>정리된 경험을 분류하고 직접 수정·관리하세요.</p></div><div className="mv2-header-actions">{editMode ? <button type="button" className="mv2-button mv2-button--primary" onClick={addDomain}>+ 경험 구조 추가하기</button> : <><button type="button" className="mv2-button mv2-button--secondary" onClick={openNewExperience}>+ 경험 추가</button><button type="button" className="mv2-button" onClick={beginEditMode}>경험 구조 편집</button></>}</div></header>
      {status === 'loading' && <p className="mv2-sync-status">경험 구조를 불러오는 중입니다…</p>}
      {error && <div className="mv2-sync-error" role="alert"><span>{error}</span><button onClick={status === 'error' ? refresh : () => setError('')}>{status === 'error' ? '다시 시도' : '닫기'}</button></div>}
      <section className="mv2-summary" aria-label="커리어 자산 요약"><button onClick={clearSearch}><strong>{experiences.length}</strong><span>전체 경험</span><small>정리된 경험 보기</small></button><button onClick={() => setAssetModal('evidence')}><strong>{evidenceTotal}</strong><span>경험 근거</span><small>원본 리스트 보기</small></button><button onClick={() => setAssetModal('skills')}><strong>{skillTotal}</strong><span>내 역량</span><small>직군 · 직업 · 역량 보기</small></button></section>
      <section className="mv2-discovery-panel" aria-label="경험 검색"><div className="mv2-toolbar"><label className="mv2-search"><span className="mv2-search__label">경험 검색</span><input value={query} onChange={(event) => { setSkillGroupFilter(''); setQuery(event.target.value); }} placeholder="경험, 프로젝트·활동, 역량 검색" /></label><strong>{visibleExperienceCount}개 경험</strong></div></section>
      <div className="mv2-structure">{displayDomains.map(({ domain, projects, experiences: domainExperiences }) => {
        const isCollapsed = !normalizedQuery && collapsed.has(domain.id);
        const toggleDomain = () => setCollapsed((value) => { const next = new Set(value); next.has(domain.id) ? next.delete(domain.id) : next.add(domain.id); return next; });
        return <section key={domain.id} className={`${isCollapsed ? 'is-collapsed' : ''} ${dropTarget === `domain:${domain.id}` ? 'is-order-target' : ''}`} onDragOver={(event) => { if (!editMode) return; event.preventDefault(); event.stopPropagation(); setDropTarget(`domain:${domain.id}`); }} onDragLeave={() => setDropTarget('')} onDrop={(event) => { if (!editMode) return; event.preventDefault(); event.stopPropagation(); const payload = readDragPayload(event); if (payload?.kind === 'domain') reorderDomain(payload.id, domain.id); setDropTarget(''); }}>
          {domain.isDraft ? renderDraftDomain(domain) : <header className="mv2-structure-header" draggable={editMode && nameEditor?.id !== domain.id} onDragStart={(event) => { event.stopPropagation(); event.dataTransfer.setData('application/json', JSON.stringify({ kind: 'domain', id: domain.id })); }} onClick={toggleDomain}>{nameEditor?.kind === 'domain' && nameEditor.id === domain.id ? renderNameEditor() : <button className="mv2-domain-toggle" aria-expanded={!isCollapsed}><h3><HighlightText text={domain.name} query={query} /></h3></button>}{editMode && nameEditor?.id !== domain.id && <MoreMenu label={`${domain.name} 관리`}><button onClick={() => addProject(domain)}>프로젝트·활동 추가</button><button onClick={() => renameDomain(domain)}>이름 변경</button><button className="is-danger" onClick={() => requestDeleteDomain(domain)}>분류 삭제</button></MoreMenu>}<span className="mv2-domain-count">{domainExperiences.length}개 경험</span><button type="button" className="mv2-domain-chevron" aria-label={`${domain.name} ${isCollapsed ? '펼치기' : '접기'}`} aria-expanded={!isCollapsed}>{isCollapsed ? '⌄' : '⌃'}</button></header>}
          {!isCollapsed && !domain.isDraft && <div className="mv2-projects">{projects.map(({ project, experiences: projectExperiences }) => {
            return <div className={`mv2-project ${dropTarget === project.id ? 'is-drop-target' : ''}`} key={project.id} onDragOver={(event) => { if (!editMode) return; event.preventDefault(); event.stopPropagation(); setDropTarget(project.id); }} onDragLeave={() => setDropTarget('')} onDrop={(event) => { if (!editMode) return; event.preventDefault(); event.stopPropagation(); const payload = readDragPayload(event); if (payload?.kind === 'project') reorderProject(domain.id, payload.id, project.id); if (payload?.kind === 'experience') moveExperience(payload.id, project.id); setDropTarget(''); }}>
              <div className="mv2-project__title" draggable={editMode && nameEditor?.id !== project.id} onDragStart={(event) => { event.stopPropagation(); event.dataTransfer.setData('application/json', JSON.stringify({ kind: 'project', id: project.id, domainId: domain.id })); }}>{nameEditor?.kind === 'project' && nameEditor.id === project.id ? renderNameEditor() : <strong><HighlightText text={project.name} query={query} /></strong>}{editMode && nameEditor?.id !== project.id && <MoreMenu label={`${project.name} 관리`}><button onClick={() => renameProject(project)}>이름 변경</button><button className="is-danger" onClick={() => requestDeleteProject(project)}>프로젝트·활동 삭제</button></MoreMenu>}</div>
              <div className={`mv2-project__experiences ${projectExperiences.length ? '' : 'is-empty'}`}>{projectExperiences.length ? projectExperiences.map((experience) => <article className={`mv2-experience-tile ${selected?.id === experience.id ? 'is-selected' : ''} ${dropTarget === `experience:${experience.id}` ? 'is-order-target' : ''}`} draggable={editMode} key={experience.id} onDragStart={(event) => { if (!editMode) return; event.stopPropagation(); event.dataTransfer.setData('application/json', JSON.stringify({ kind: 'experience', id: experience.id, projectId: project.id })); }} onDragOver={(event) => { if (!editMode) return; event.preventDefault(); event.stopPropagation(); setDropTarget(`experience:${experience.id}`); }} onDragLeave={() => setDropTarget('')} onDrop={(event) => { if (!editMode) return; event.preventDefault(); event.stopPropagation(); const payload = readDragPayload(event); if (payload?.kind === 'experience') payload.projectId === project.id ? reorderExperience(project.id, payload.id, experience.id) : moveExperience(payload.id, project.id, experience.id); setDropTarget(''); }}><button className="mv2-experience-main" aria-expanded={selected?.id === experience.id} onClick={(event) => togglePreview(experience, event.currentTarget)}><span><strong><HighlightText text={selectExperienceCard(experience).title} query={query} /></strong><small><HighlightText text={selectExperienceCard(experience).skills.join(' · ') || '역량 미입력'} query={query} /></small></span></button>{editMode && <MoreMenu label={`${experience.title} 관리`}><button className="is-danger" onClick={() => requestDeleteExperience(experience)}>경험 삭제</button></MoreMenu>}</article>) : <div className="mv2-v3-empty-project"><p>아직 경험이 없습니다.</p><button type="button" onClick={() => startExperience(domain, project)}>+ 이곳에 경험 추가</button></div>}</div>
            </div>;
          })}{editMode && !normalizedQuery && draftProject?.domainId === domain.id && renderDraftProject(domain)}{editMode && !normalizedQuery && domain.projects.length === 0 && draftProject?.domainId !== domain.id && <button className="mv2-v3-add-project" onClick={() => setDraftProject({ domainId: domain.id, name: '' })}>+ 첫 프로젝트·활동 추가</button>}</div>}
        </section>;
      })}</div>
      {status === 'ready' && hasFilters && displayDomains.length === 0 && <section className="mv2-search-empty" role="status"><h2>조건에 맞는 경험이 없습니다.</h2><p>검색어나 필터 조건을 변경해 보세요.</p><button onClick={clearSearch}>검색·필터 초기화</button></section>}
      {status === 'ready' && domains.length === 0 && <section className="mv2-empty"><h2>첫 경험 분류를 만들어 보세요</h2><p>직장 경험, 교육·학습, 대외 활동처럼 경험을 나눌 기준을 추가할 수 있습니다.</p>{editMode ? <button className="mv2-button" onClick={addDomain}>+ 경험 분류 만들기</button> : <button className="mv2-button" onClick={beginEditMode}>편집 시작</button>}</section>}
      {editMode && <div className="mv2-edit-bar" role="status"><span>{draftDomainId ? '새 경험 분류 이름을 입력해 주세요.' : pendingOps.length ? `저장하지 않은 변경 ${pendingOps.length}건` : '편집 모드 · 아직 변경사항이 없습니다.'}</span><button className="mv2-button mv2-button--secondary" onClick={cancelEditMode} disabled={savingStructure}>취소</button><button className="mv2-button" onClick={() => saveStructure()} disabled={!pendingOps.length || Boolean(draftDomainId) || savingStructure}>{savingStructure ? '저장 중…' : '변경사항 저장'}</button></div>}
    </main>
    {selected && <aside ref={previewRef} style={previewPosition || undefined} className={`mv2-preview ${previewPosition ? '' : 'is-positioning'}`} role="dialog" aria-label={`${selected.title} 간단 상세`}><header><div><span className="mv2-kicker">경험</span><h2>{selected.title}</h2><p>{selected.projectName}</p></div><button className="mv2-icon-button" onClick={() => { setSelectedExperienceId(null); setPreviewPosition(null); previewAnchorRef.current = null; }} aria-label="닫기">×</button></header><section><h3>요약</h3><p>{selected.summary || '입력된 요약이 없습니다.'}</p></section><section><h3>역량</h3><div className="mv2-skills">{selected.skills.map((skill) => <span key={skill}>{skill}</span>)}</div></section><footer><Link className="mv2-button mv2-button--secondary" to={`/memory/${selected.id}`}>상세 보기</Link></footer></aside>}
    <ExperienceIntakeModal open={experienceIntakeOpen} onClose={closeExperienceIntake} onAnalyze={analyzeExperience} busy={experienceIntakeBusy} />
    {experiencePreviewOpen && experienceProposal && <div className="mv2-modal-backdrop mv2-experience-preview-backdrop"><section className="mv2-experience-preview-modal" role="dialog" aria-modal="true" aria-label="경험 구조화 제안"><header><div><span className="mv2-kicker">EXPERIENCE AI</span><h2>경험 구조화 제안</h2><p>경험 분류와 프로젝트·활동을 확인한 뒤 상세 작성으로 넘어가세요.</p></div><button type="button" className="mv2-icon-button" onClick={closeExperiencePreview} aria-label="닫기">×</button></header><InlineProposalCard key={`${experienceProposal.id}-${experienceProposal.version || 0}`} proposal={experienceProposal} onApprove={approveExperiencePreview} onReject={closeExperiencePreview} onChange={updateExperiencePreview} onRemoveExperience={removeExperiencePreview} onEditingChange={setExperienceProposalEditing} /><footer className="mv2-experience-preview-footer"><span>{pendingExperienceCount ? `저장하지 않은 초안 ${pendingExperienceCount}개` : '모든 초안이 저장되었습니다.'}</span><div><button type="button" className="mv2-button mv2-button--danger" disabled={!pendingExperienceCount || experiencePreviewBusy || experienceProposalEditing} onClick={discardRemainingExperienceDrafts}>나머지 삭제</button><button type="button" className="mv2-button mv2-button--primary" disabled={!pendingExperienceCount || experiencePreviewBusy || experienceProposalEditing} onClick={saveAllExperienceDrafts}>{experiencePreviewBusy ? '전체 저장 중…' : '전체 저장'}</button></div></footer></section></div>}
    {newExperienceOpen && <div className="mv2-modal-backdrop mv2-experience-editor-backdrop"><section className="mv2-experience-editor-modal" role="dialog" aria-modal="true" aria-label="새 경험 작성"><MemoryDetailPage experienceId="new" initialDraft={newExperienceDraft} initialDomainId={newExperienceContext.domainId} initialProjectId={newExperienceContext.projectId} onClose={closeNewExperience} onSaved={handleNewExperienceSaved} /></section></div>}
    <AssetModal type={assetModal} experiences={experiences} onClose={() => setAssetModal(null)} onSearch={searchBySkill} />
    {confirm && <div className="mv2-modal-backdrop"><section className="mv2-confirm" role="alertdialog" aria-modal="true"><span className="mv2-kicker is-danger">삭제 확인</span><h2>{confirm.title}</h2><p>{confirm.description}</p><footer><button className="mv2-button mv2-button--secondary" onClick={() => setConfirm(null)}>취소</button><button className="mv2-button mv2-button--danger" onClick={confirm.action}>삭제</button></footer></section></div>}
  </div>;
}

export default ExperienceManagerV3;
