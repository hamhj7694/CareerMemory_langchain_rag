import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { jobApi } from '../api/index.js';
import { v2ChatApi } from '../api/v2ChatApi.js';
import { EmptyState, ErrorState, LoadingState, Tag } from '../components/common/index.js';
import { AnalysisProgress } from '../components/common/AnalysisProgress.jsx';
import './jobs.css';
import { failureRequirementIds } from '../utils/contractFields.js';

const normalizeExperience = (item) => ({
  experienceId: item.experienceId || item.id,
  title: item.title,
  projectName: item.projectName || item.project?.name || '미분류 프로젝트·활동',
  projectId: item.projectId || item.project?.id || item.projectName || item.project?.name || 'unclassified-project',
  domainName: item.domainName || item.domain?.name || '미분류 경험',
  domainId: item.domainId || item.domain?.id || item.domainName || item.domain?.name || 'unclassified-domain',
  skills: item.skills || [],
  summary: item.summary || '',
  role: item.role || '',
  results: item.results || [],
  evidenceCount: item.evidenceCount ?? item.evidence_count ?? item.source_ids?.length ?? 0,
});

function buildStructure(experiences) {
  const domains = new Map();
  experiences.forEach((experience) => {
    if (!domains.has(experience.domainId)) domains.set(experience.domainId, { id: experience.domainId, name: experience.domainName, projects: new Map() });
    const domain = domains.get(experience.domainId);
    if (!domain.projects.has(experience.projectId)) domain.projects.set(experience.projectId, { id: experience.projectId, name: experience.projectName, experiences: [] });
    domain.projects.get(experience.projectId).experiences.push(experience);
  });
  return [...domains.values()].map((domain) => ({ ...domain, projects: [...domain.projects.values()] }));
}

const SearchIcon = () => <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6" /><path d="m16 16 4 4" /></svg>;
const TrashIcon = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5" /></svg>;
const requirementTitle = (requirement) => requirement.title || requirement.text || '요구사항 제목 없음';
const requirementSummary = (requirement) => requirement.summary
  || (requirement.keywords?.length ? `${requirement.keywords.slice(0, 3).join('·')} 관련 역량과 실무 경험을 요구합니다.` : '');
const requirementSourceExcerpt = (requirement) => requirement.sourceExcerpt
  || requirement.source_excerpt
  || (requirement.title && requirement.text !== requirement.title ? requirement.text : '');
const requirementImportance = (requirement) => {
  if (requirement.importance === 'required') return { label: '필수', tone: 'danger' };
  if (requirement.importance === 'preferred') return { label: '우대', tone: 'ai' };
  return { label: '일반', tone: 'default' };
};
const requirementNeedsReview = (requirement) => requirement.needsReview
  ?? requirement.needs_review
  ?? (Number.isFinite(requirement.confidence) ? requirement.confidence < 0.5 : requirementSourceExcerpt(requirement).trim().length < 8);

function RequirementExperienceTree({ experiences, linkedIds, recommendedIds, onToggle, onOpenDetail }) {
  const [collapsedDomains, setCollapsedDomains] = useState(() => new Set());
  const [collapsedProjects, setCollapsedProjects] = useState(() => new Set());
  const structure = buildStructure(experiences);
  if (!experiences.length) return <EmptyState title="표시할 경험이 없습니다" description="다른 보기에서 경험을 확인해 주세요." />;
  const toggleDomain = (domainId) => setCollapsedDomains((current) => {
    const next = new Set(current);
    next.has(domainId) ? next.delete(domainId) : next.add(domainId);
    return next;
  });
  const toggleProject = (projectKey) => setCollapsedProjects((current) => {
    const next = new Set(current);
    next.has(projectKey) ? next.delete(projectKey) : next.add(projectKey);
    return next;
  });
  return <div className="job-experience-structure">{structure.map((domain) => {
    const collapsed = collapsedDomains.has(domain.id);
    const count = domain.projects.reduce((sum, project) => sum + project.experiences.length, 0);
    return <section key={domain.id} className={`job-experience-domain ${collapsed ? 'is-collapsed' : ''}`}>
      <header><button type="button" className="job-experience-domain__toggle" onClick={() => toggleDomain(domain.id)} aria-expanded={!collapsed}><span>경험 분류</span><strong>{domain.name}</strong><small>{count}개 경험</small><span className="job-experience-domain__chevron" aria-hidden="true">⌃</span></button></header>
      {!collapsed && <div className="job-experience-projects">{domain.projects.map((project) => {
        const projectKey = `${domain.id}:${project.id}`;
        const projectCollapsed = collapsedProjects.has(projectKey);
        return <div className={`job-experience-project ${projectCollapsed ? 'is-collapsed' : ''}`} key={project.id}>
          <button type="button" className="job-experience-project__title" onClick={() => toggleProject(projectKey)} aria-expanded={!projectCollapsed}>
            <span>프로젝트·활동</span>
            <strong>{project.name}</strong>
            <small>{project.experiences.length}개 경험</small>
            <span className="job-experience-project__chevron" aria-hidden="true">⌃</span>
          </button>
          {!projectCollapsed && <div className="job-experience-cards">{project.experiences.map((experience) => {
            const linked = linkedIds.has(experience.experienceId);
            const recommended = recommendedIds.has(experience.experienceId);
            return <article className={`job-experience-card ${linked ? 'is-selected' : ''}`} key={experience.experienceId}><label className="job-experience-card__select"><input type="checkbox" checked={linked} onChange={() => onToggle(experience.experienceId)} /><span><strong>{experience.title}</strong><small>{experience.skills.slice(0, 2).join(' · ') || '역량 미입력'}</small></span></label><span className="job-experience-card__badges">{recommended && <em>AI 추천</em>}{linked && !recommended && <em className="is-manual">직접 연결</em>}<button type="button" onClick={() => onOpenDetail(experience)}>상세 보기</button></span></article>;
          })}</div>}
        </div>;
      })}</div>}
    </section>;
  })}</div>;
}

export function JobDetailPage() {
  const { jobId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const autoMatchStarted = useRef(false);
  const [job, setJob] = useState(location.state?.job || null);
  const [matches, setMatches] = useState([]);
  const [failures, setFailures] = useState([]);
  const [allExperiences, setAllExperiences] = useState([]);
  const [activeRequirementId, setActiveRequirementId] = useState(location.state?.job?.requirements?.[0]?.id || '');
  const [requirementLinks, setRequirementLinks] = useState({});
  const [experienceView, setExperienceView] = useState('recommended');
  const [detailExperience, setDetailExperience] = useState(null);
  const [activeLinkedChip, setActiveLinkedChip] = useState('');
  const [expandedRequirementSources, setExpandedRequirementSources] = useState(() => new Set());
  const [phase, setPhase] = useState(job ? 'ready' : 'loading');
  const [error, setError] = useState('');

  const applyMatchResult = (result, requirementIds = []) => {
    const nextMatches = result.matches || [];
    setMatches((current) => requirementIds.length ? [...current.filter((item) => !requirementIds.includes(item.requirementId)), ...nextMatches] : nextMatches);
    setFailures(result.failures || []);
    setRequirementLinks((current) => {
      const next = { ...current };
      nextMatches.forEach((match) => {
        if (!(match.requirementId in next)) next[match.requirementId] = match.linkedExperienceIds || (match.experiences || []).map((item) => item.experienceId);
      });
      return next;
    });
  };

  useEffect(() => {
    if (job) return;
    jobApi.get(jobId).then((data) => {
      setJob(data);
      setActiveRequirementId(data.requirements?.[0]?.id || '');
      setPhase('ready');
    }).catch((reason) => { setError(reason.message); setPhase('error'); });
  }, [job, jobId]);

  useEffect(() => {
    v2ChatApi.listExperiences().then((result) => setAllExperiences((result.items || []).map(normalizeExperience))).catch(() => setAllExperiences([]));
  }, []);

  useEffect(() => {
    if (!job || autoMatchStarted.current) return;
    autoMatchStarted.current = true;
    setPhase('matching');
    jobApi.match(jobId, { requirementIds: [] }).then((result) => { applyMatchResult(result); setPhase('matched'); }).catch((reason) => { setError(reason.message || '내 경험과 자동으로 대조하지 못했습니다.'); setPhase('ready'); });
  }, [job, jobId]);

  const experienceCatalog = useMemo(() => {
    const items = new Map(allExperiences.map((item) => [item.experienceId, item]));
    matches.forEach((match) => match.experiences?.forEach((item) => { const normalized = normalizeExperience(item); if (!items.has(normalized.experienceId)) items.set(normalized.experienceId, normalized); }));
    return [...items.values()];
  }, [allExperiences, matches]);
  const orderedRequirements = useMemo(() => [...(job?.requirements || [])].sort((a, b) => (a.order ?? Number.MAX_SAFE_INTEGER) - (b.order ?? Number.MAX_SAFE_INTEGER)), [job]);
  const activeRequirement = orderedRequirements.find((item) => item.id === activeRequirementId) || orderedRequirements[0];
  const activeMatch = matches.find((item) => item.requirementId === activeRequirement?.id);
  const recommendedIds = useMemo(() => new Set((activeMatch?.experiences || []).map((item) => item.experienceId)), [activeMatch]);
  const linkedIds = useMemo(() => new Set(requirementLinks[activeRequirement?.id] || []), [requirementLinks, activeRequirement]);
  const visibleExperiences = experienceView === 'all' ? experienceCatalog : experienceCatalog.filter((item) => recommendedIds.has(item.experienceId));

  const retryMatch = async (requirementIds = []) => { setPhase('matching'); setError(''); try { const result = await jobApi.rematch(jobId, requirementIds); applyMatchResult(result, requirementIds); setPhase('matched'); } catch (reason) { setError(reason.message); setPhase(matches.length ? 'matched' : 'ready'); } };
  const toggleRequirementLink = async (experienceId) => {
    const requirementId = activeRequirement?.id;
    if (!requirementId) return;
    const wasLinked = (requirementLinks[requirementId] || []).includes(experienceId);
    setRequirementLinks((current) => {
      const ids = new Set(current[requirementId] || []);
      ids.has(experienceId) ? ids.delete(experienceId) : ids.add(experienceId);
      return { ...current, [requirementId]: [...ids] };
    });
    try { await jobApi.setRequirementLink(jobId, requirementId, experienceId, !wasLinked); }
    catch (reason) {
      setRequirementLinks((current) => {
        const ids = new Set(current[requirementId] || []);
        wasLinked ? ids.add(experienceId) : ids.delete(experienceId);
        return { ...current, [requirementId]: [...ids] };
      });
      setError(reason.message || '경험 연결 상태를 저장하지 못했습니다.');
    }
  };
  const unlinkRequirementExperience = async (requirementId, experienceId) => {
    setRequirementLinks((current) => ({ ...current, [requirementId]: (current[requirementId] || []).filter((id) => id !== experienceId) }));
    setActiveLinkedChip('');
    try { await jobApi.setRequirementLink(jobId, requirementId, experienceId, false); }
    catch (reason) {
      setRequirementLinks((current) => ({ ...current, [requirementId]: [...new Set([...(current[requirementId] || []), experienceId])] }));
      setError(reason.message || '경험 연결을 해제하지 못했습니다.');
    }
  };
  const toggleRequirementSource = (requirementId) => setExpandedRequirementSources((current) => {
    const next = new Set(current);
    next.has(requirementId) ? next.delete(requirementId) : next.add(requirementId);
    return next;
  });

  if (phase === 'loading') return <LoadingState title="공고를 불러오는 중" />;
  if (phase === 'error') return <ErrorState title="공고를 찾을 수 없습니다" description={error} actionLabel="공고 목록으로" onRetry={() => navigate('/jobs')} />;
  if (!job) return null;

  return <section className="feature-page job-result-page">
    <header className="feature-heading split"><div><span className="eyebrow">{job.companyName || '회사 미입력'} · {job.roleName || '직무 미입력'}</span><h1>{job.postingTitle || job.roleName || '채용공고 분석'}</h1><p>{orderedRequirements.length}개의 요구사항과 내 경험을 함께 분석합니다.</p></div><div className="header-actions">{job.sourceUrl && <a className="ui-button ui-button--secondary" href={job.sourceUrl} target="_blank" rel="noreferrer">원문 공고 열기</a>}<button className="ui-button ui-button--secondary" onClick={() => navigate('/jobs')}>다른 공고 분석</button></div></header>
    {error && <div className="inline-error" role="alert">{error}</div>}
    <div className="job-result-flow">
      <section className="surface job-step-panel requirements-panel"><div className="section-title"><div><span className="step">1</span><div><h2>공고 요구사항</h2><p>카드를 선택하면 연결된 경험을 확인할 수 있습니다.</p></div></div></div>
        {failures.length > 0 && <div className="warning-box" role="status"><strong>{failures.length}개 요구사항을 대조하지 못했습니다.</strong><button className="tool-button" onClick={() => retryMatch(failureRequirementIds(failures))}>실패 항목 다시 시도</button></div>}
        <div className="requirement-list">{orderedRequirements.map((requirement, index) => {
          const isActive = activeRequirement?.id === requirement.id;
          const connected = (requirementLinks[requirement.id] || []).map((id) => experienceCatalog.find((item) => item.experienceId === id)).filter(Boolean);
          const summary = requirementSummary(requirement);
          const sourceExcerpt = requirementSourceExcerpt(requirement);
          const sourceExpanded = expandedRequirementSources.has(requirement.id);
          const importance = requirementImportance(requirement);
          const needsReview = requirementNeedsReview(requirement);
          return <article className={`requirement-card requirement-card--selectable ${isActive ? 'is-focused' : ''}`} key={requirement.id}>
            <button type="button" className="requirement-card__main" onClick={() => { setActiveRequirementId(requirement.id); setExperienceView('recommended'); }} aria-pressed={isActive}>
              <div className="requirement-card__title-row"><span className="requirement-number">{requirement.order || index + 1}</span><h3>{requirementTitle(requirement)}</h3><span className="requirement-card__tags"><Tag tone={importance.tone}>{importance.label}</Tag>{needsReview && <Tag tone="warning">검토 필요</Tag>}</span></div>
              {summary && <p className="requirement-card__summary">{summary}</p>}
            </button>
            {sourceExcerpt && <div className={`requirement-card__source ${sourceExpanded ? 'is-expanded' : ''}`}>
              <span>공고 원문</span>
              <blockquote id={`requirement-source-${requirement.id}`}>{sourceExcerpt}</blockquote>
              {sourceExcerpt.length > 70 && <button type="button" onClick={() => toggleRequirementSource(requirement.id)} aria-expanded={sourceExpanded} aria-controls={`requirement-source-${requirement.id}`}>{sourceExpanded ? '원문 접기' : '원문 더보기'}</button>}
            </div>}
            <div className={`requirement-linked-experiences ${connected.length ? '' : 'is-empty'}`}>{connected.length ? connected.map((experience) => {
              const chipId = `${requirement.id}:${experience.experienceId}`;
              const isOpen = activeLinkedChip === chipId;
              return <span className={`requirement-linked-chip ${isOpen ? 'is-open' : ''}`} key={experience.experienceId}><button type="button" className="requirement-linked-chip__label" onClick={() => setActiveLinkedChip(isOpen ? '' : chipId)} aria-expanded={isOpen}>{experience.title}</button>{isOpen && <span className="requirement-linked-chip__actions"><button type="button" onClick={() => setDetailExperience(experience)} aria-label={`${experience.title} 상세 보기`} title="상세 보기"><SearchIcon /></button><button type="button" className="is-danger" onClick={() => unlinkRequirementExperience(requirement.id, experience.experienceId)} aria-label={`${experience.title} 연결 해제`} title="연결 해제"><TrashIcon /></button></span>}</span>;
            }) : <span className="requirement-linked-empty">연결된 경험이 없습니다.</span>}</div>
          </article>;
        })}</div>
      </section>

      <section className="surface job-step-panel match-panel"><div className="section-title"><div><span className="step">2</span><div><h2>요구사항별 매칭 경험</h2><p>{activeRequirement ? `“${requirementTitle(activeRequirement)}”에 연결된 경험입니다.` : '요구사항을 선택해 주세요.'}</p></div></div><button type="button" className="tool-button" disabled={phase === 'matching'} onClick={() => retryMatch([])}>{phase === 'matching' ? '다시 매칭 중…' : '최신 경험으로 다시 매칭'}</button></div>
        <AnalysisProgress active={phase === 'matching'} kind="job" />
        <div className="experience-view-tabs" role="tablist" aria-label="경험 보기"><button role="tab" aria-selected={experienceView === 'recommended'} onClick={() => setExperienceView('recommended')}>AI 추천 {recommendedIds.size}</button><button role="tab" aria-selected={experienceView === 'all'} onClick={() => setExperienceView('all')}>전체 경험 {experienceCatalog.length}</button></div>
        <p className="match-panel__guide">체크하면 현재 요구사항에 연결되고, 해제하면 경험 자체가 아닌 연결만 삭제됩니다.</p>
        <div className="match-panel__scroll" tabIndex="0" aria-label="요구사항별 매칭 경험 목록">
          <RequirementExperienceTree experiences={visibleExperiences} linkedIds={linkedIds} recommendedIds={recommendedIds} onToggle={toggleRequirementLink} onOpenDetail={setDetailExperience} />
        </div>
      </section>
    </div>
    {detailExperience && <div className="job-detail-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setDetailExperience(null); }}><aside className="job-experience-detail" role="dialog" aria-modal="true" aria-labelledby="job-experience-detail-title"><header><div><span className="eyebrow">EXPERIENCE DETAIL</span><h2 id="job-experience-detail-title">{detailExperience.title}</h2><p>{detailExperience.domainName} · {detailExperience.projectName}</p></div><button type="button" onClick={() => setDetailExperience(null)} aria-label="닫기">×</button></header><section><h3>경험 요약</h3><p>{detailExperience.summary || '등록된 경험 요약이 없습니다.'}</p></section>{detailExperience.role && <section><h3>담당 역할</h3><p>{detailExperience.role}</p></section>}<section><h3>역량</h3><div className="job-detail-skills">{detailExperience.skills.length ? detailExperience.skills.map((skill) => <span key={skill}>{skill}</span>) : <p>등록된 역량이 없습니다.</p>}</div></section>{detailExperience.results.length > 0 && <section><h3>성과</h3><ul>{detailExperience.results.map((result, index) => <li key={`${result}-${index}`}>{result}</li>)}</ul></section>}<footer><span>연결된 근거 {detailExperience.evidenceCount}개</span><button type="button" className="ui-button ui-button--secondary" onClick={() => navigate(`/memory/${detailExperience.experienceId}`)}>경험 상세 페이지</button></footer></aside></div>}
  </section>;
}
