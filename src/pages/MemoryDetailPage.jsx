import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { experienceApi } from '../api/experienceApi.js';
import { sourceApi } from '../api/sourceApi.js';
import { v2ChatApi } from '../api/v2ChatApi.js';
import ErrorState from '../components/common/ErrorState.jsx';
import LoadingState from '../components/common/LoadingState.jsx';
import { SourceManagerModal } from '../components/memory/SourceManagerModal.jsx';
import { downloadEvidenceFile, openEvidenceFile } from '../features/evidence/model/evidenceFileAccess.js';
import { experienceRepository } from '../features/experience/api/experienceRepository.js';
import { ExperienceDetailContent } from '../features/experience/components/ExperienceDetailContent.jsx';
import { listToText, textToMarkdownLines, textToSkills } from '../features/experience/model/experienceContent.js';
import { createEmptyExperience } from '../features/experience/model/experienceMapper.js';
import { useDirtyBlocker } from '../hooks/useDirtyBlocker.js';
import '../styles/memory.css';

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
    || skillsText !== listToText(item.skills)
    || domainDirectInput
    || projectDirectInput
    || domainInput !== (item.domainName || '')
    || projectInput !== (item.projectName || '')
  )), [editing, item, form, skillsText, domainDirectInput, projectDirectInput, domainInput, projectInput]);
  useDirtyBlocker(dirty);

  const syncDraft = (experience) => {
    setItem(experience);
    setForm(experience);
    setSkillsText(listToText(experience.skills));
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

  const applyEvidenceMetadata = (experience) => {
    if (!experience) return;
    const evidencePatch = {
      version: experience.version,
      evidenceIds: experience.evidenceIds,
      sourceRefs: experience.sourceRefs,
      evidenceCount: experience.evidenceCount,
      factEvidenceStatus: experience.factEvidenceStatus,
    };
    setItem((current) => ({ ...current, ...evidencePatch }));
    setForm((current) => ({ ...current, ...evidencePatch }));
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
      applyEvidenceMetadata(updated.experiences?.find((experience) => experience.id === experienceId));
      setSourceNotice('텍스트 근거 변경사항을 저장했습니다.');
      return true;
    } catch (reason) {
      setError(reason.message);
      return false;
    } finally {
      setStatus('success');
    }
  };

  const unlinkSource = async (source) => {
    const name = source.filename || '텍스트 입력';
    if (!window.confirm(`'${name}' 근거를 현재 경험에서 연결 해제할까요?\n\n원본 파일이나 텍스트 자체는 삭제되지 않습니다. 연결만 해제됩니다.`)) return false;
    setStatus('unlinking-source');
    setError('');
    setSourceNotice('');
    try {
      const result = await sourceApi.unlink(experienceId, source.id);
      setSources({ experienceId, sources: result.sources });
      applyEvidenceMetadata(result.experience);
      const count = result.unsupportedFacts?.length || 0;
      setSourceNotice(count ? `연결은 해제되었습니다. 확인이 필요한 사실 ${count}개가 남아 있습니다.` : '현재 경험과의 연결이 해제되었습니다.');
      return true;
    } catch (reason) {
      setError(reason.message);
      return false;
    } finally {
      setStatus('success');
    }
  };

  const addTextSource = async (input) => {
    setStatus('adding-source');
    setError('');
    setSourceNotice('');
    try {
      const result = await sourceApi.addText(experienceId, input);
      setSources({ experienceId, sources: result.sources });
      applyEvidenceMetadata(result.experience);
      setSourceNotice('텍스트 근거를 현재 경험에 추가했습니다.');
      return result;
    } catch (reason) {
      setError(reason.message);
      return false;
    } finally {
      setStatus('success');
    }
  };

  const addFileSources = async (files) => {
    setStatus('adding-source');
    setError('');
    setSourceNotice('');
    try {
      const result = await sourceApi.addFiles(experienceId, files);
      setSources({ experienceId, sources: result.sources });
      applyEvidenceMetadata(result.experience);
      setSourceNotice(`${result.addedSourceIds?.length || files.length}개 파일 근거를 현재 경험에 추가했습니다.`);
      return result;
    } catch (reason) {
      setError(reason.message);
      return false;
    } finally {
      setStatus('success');
    }
  };

  const reorganizeFromSources = async () => {
    setStatus('reorganizing-source');
    setError('');
    setSourceNotice('');
    try {
      const result = await sourceApi.reorganize(experienceId);
      setSourceNotice(`'${result.experience.title}' 경험 카드로 저장했습니다.`);
      if (onSaved) await onSaved(result.experience);
      return result;
    } catch (reason) {
      setError(reason.message);
      return false;
    } finally {
      setStatus('success');
    }
  };

  const downloadSource = async (source) => {
    setError('');
    try {
      await downloadEvidenceFile(source, sourceApi.download);
    } catch (reason) {
      setError(reason.message);
    }
  };
  const openSource = async (source) => {
    setError('');
    try {
      await openEvidenceFile(source, sourceApi.download);
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
        actions: textToMarkdownLines(form.actions?.join('\n') ?? ''),
        results: textToMarkdownLines(form.results?.join('\n') ?? ''),
        facts: textToMarkdownLines(form.facts?.join('\n') ?? ''),
        skills: textToSkills(skillsText),
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

  const careerRole = item.role?.trim() || '역할 미입력';

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
          {/* 상세 제목 아래에는 경험이 속한 분류와 사용자의 실제 담당 역할을 보여 줍니다. */}
          <p>{[item.domainName, careerRole].filter(Boolean).join(' · ')}</p>
        </div>
        <div>
          {!isNew && <button className="ui-button ui-button--secondary" onClick={openSources}>원본 근거 관리</button>}
          {!editing && <button className="ui-button" onClick={() => setEditing(true)}>수정</button>}
        </div>
      </header>

      {error && <p className="inline-error" role="alert">{error}</p>}

      <ExperienceDetailContent
        editing={editing}
        item={item}
        form={form}
        onFormChange={(key, value) => setForm((current) => ({ ...current, [key]: value }))}
        skillsText={skillsText}
        onSkillsTextChange={setSkillsText}
        structure={structure}
        availableProjects={availableProjects}
        domainDirectInput={domainDirectInput}
        projectDirectInput={projectDirectInput}
        domainInput={domainInput}
        projectInput={projectInput}
        onDomainInputChange={setDomainInput}
        onProjectInputChange={setProjectInput}
        onUpdateDomain={updateDomain}
        onUpdateProject={updateProject}
        onToggleDomainInput={domainDirectInput ? useDomainSelect : enableDirectDomain}
        onToggleProjectInput={projectDirectInput ? useProjectSelect : enableDirectProject}
        isNew={isNew}
        openSources={openSources}
      />

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
        busy={['saving-source', 'unlinking-source', 'adding-source', 'reorganizing-source'].includes(status)}
        error={error}
        notice={sourceNotice}
        onClose={() => setSourceOpen(false)}
        onSave={saveSource}
        onUnlink={unlinkSource}
        onOpenFile={openSource}
        onDownload={downloadSource}
        onAddText={addTextSource}
        onAddFiles={addFileSources}
        onReorganize={reorganizeFromSources}
      />
    </article>
  );
}
