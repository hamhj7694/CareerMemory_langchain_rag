import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { experienceApi } from '../api/experienceApi.js';
import { sourceApi } from '../api/sourceApi.js';
import ErrorState from '../components/common/ErrorState.jsx';
import LoadingState from '../components/common/LoadingState.jsx';
import { SourceManagerModal } from '../components/memory/SourceManagerModal.jsx';
import '../styles/memory.css';
import { useDirtyBlocker } from '../hooks/useDirtyBlocker.js';

const join = (items) => (items ?? []).join('\n');
const split = (text) => text.split('\n').map((x) => x.trim()).filter(Boolean);
export function MemoryDetailPage() {
  const { experienceId } = useParams(); const [item, setItem] = useState(null); const [form, setForm] = useState(null); const [status, setStatus] = useState('loading'); const [editing, setEditing] = useState(false); const [sources, setSources] = useState(null); const [sourceOpen, setSourceOpen] = useState(false); const [error, setError] = useState('');
  useDirtyBlocker(editing);
  const load = async () => { setStatus('loading'); try { const data = await experienceApi.get(experienceId); setItem(data); setForm(data); setStatus('success'); } catch { setStatus('error'); } };
  useEffect(() => {
    let active = true;
    experienceApi.get(experienceId).then((data) => { if (active) { setItem(data); setForm(data); setStatus('success'); } }, () => { if (active) setStatus('error'); });
    return () => { active = false; };
  }, [experienceId]);
  useEffect(() => { const protect = (e) => { if (editing) { e.preventDefault(); e.returnValue = ''; } }; window.addEventListener('beforeunload', protect); return () => window.removeEventListener('beforeunload', protect); }, [editing]);
  const openSources = async () => { setSourceOpen(true); if (!sources) { try { setSources(await experienceApi.getSources(experienceId)); } catch (e) { setError(e.message); } } };
  const saveSource = async (source, text) => { setStatus('saving-source'); setError(''); try { const updated = await sourceApi.update(source.id, { text }); setSources((current) => ({ ...current, sources: current.sources.map((item) => item.id === source.id ? { ...item, ...updated, text } : item) })); } catch (e) { setError(e.message); } finally { setStatus('success'); } };
  const deleteSource = async (source) => { if (!window.confirm(`'${source.filename || '텍스트 입력'}' 원본을 삭제할까요? 확정된 경험은 유지되지만 근거 연결은 제거됩니다.`)) return; setStatus('deleting-source'); setError(''); try { await sourceApi.remove(source.id); setSources((current) => ({ ...current, sources: current.sources.filter((item) => item.id !== source.id) })); } catch (e) { setError(e.message); } finally { setStatus('success'); } };
  const downloadSource = async (source) => { setError(''); try { const blob = await sourceApi.download(source); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = source.filename || `source-${source.id}.txt`; anchor.click(); URL.revokeObjectURL(url); } catch (e) { setError(e.message); } };
  const save = async () => {
    const editable = ['title', 'summary', 'situation', 'actions', 'results', 'role', 'facts', 'skills', 'missingInformation'];
    const changes = Object.fromEntries(editable.filter((key) => JSON.stringify(form[key]) !== JSON.stringify(item[key])).map((key) => [key, form[key]]));
    if (!Object.keys(changes).length) { setEditing(false); return; }
    setStatus('saving'); setError('');
    try { const saved = await experienceApi.update(experienceId, { version: item.version, changes }); setItem(saved); setForm(saved); setEditing(false); setStatus('success'); }
    catch (e) { setError(e.message); setStatus('success'); }
  };
  if (status === 'loading') return <div className="memory-detail"><LoadingState label="경험 상세를 불러오는 중입니다." /></div>;
  if (status === 'error') return <div className="memory-detail"><ErrorState title="경험을 찾을 수 없습니다" description="삭제되었거나 잘못된 주소일 수 있습니다." onRetry={load} /><Link className="ui-button ui-button--secondary" to="/memory">경험 목록으로</Link></div>;
  const period = [item.period?.start, item.period?.end].filter(Boolean).join(' – ');
  const field = (key, label, multiline = false, array = false) => <label>{label}{multiline ? <textarea rows="4" value={array ? join(form[key]) : (form[key] ?? '')} onChange={(e) => setForm({ ...form, [key]: array ? split(e.target.value) : e.target.value })} /> : <input value={form[key] ?? ''} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />}</label>;
  return <article className="memory-detail"><div className="detail-breadcrumb"><Link to="/memory">경험 메모리</Link><span>/</span><span>{item.projectName}</span></div><header className="detail-header"><div><span className="eyebrow">사용자 확정 경험</span><h2>{item.title}</h2><p>{[item.domainName, item.projectName, item.organization, period].filter(Boolean).join(' · ')}</p></div><div><button className="ui-button ui-button--secondary" onClick={openSources}>원본 근거 관리</button><button className="ui-button" onClick={() => setEditing(true)}>수정</button></div></header>
    {error && <p className="inline-error" role="alert">{error}</p>}
    {item.missingInformation?.length > 0 && !editing && <section className="detail-missing" role="status"><strong>추가로 확인하면 좋은 정보</strong><ul>{item.missingInformation.map((text) => <li key={text}>{text}</li>)}</ul></section>}
    {editing ? <section className="detail-editor">{field('title', '제목')}{field('summary', '요약', true)}{field('situation', '상황', true)}{field('actions', '행동 (한 줄에 하나)', true, true)}{field('results', '결과 (한 줄에 하나)', true, true)}{field('role', '역할')}{field('facts', '확인된 사실 (한 줄에 하나)', true, true)}{field('skills', '역량 (한 줄에 하나)', true, true)}<div className="sticky-actions"><button className="ui-button ui-button--secondary" onClick={() => { setForm(item); setEditing(false); }}>취소</button><button className="ui-button" onClick={save} disabled={status === 'saving'}>{status === 'saving' ? '저장 중…' : '변경 저장'}</button></div></section> : <div className="detail-grid"><main><section className="detail-card lead"><h3>요약</h3><p>{item.summary}</p></section><section className="detail-card"><h3>상황</h3><p>{item.situation || '등록된 내용이 없습니다.'}</p></section><section className="detail-card"><h3>행동</h3><ul>{item.actions?.map((x) => <li key={x}>{x}</li>)}</ul></section><section className="detail-card"><h3>결과</h3><ul>{item.results?.map((x) => <li key={x}>{x}</li>)}</ul></section></main><aside><section className="detail-card"><h3>나의 역할</h3><p>{item.role || '등록된 내용이 없습니다.'}</p></section><section className="detail-card"><h3>역량</h3><div className="skill-list">{item.skills?.map((x) => <span key={x}>{x}</span>)}</div></section><section className="detail-card facts"><h3>확인된 사실</h3>{item.facts?.length ? <ul>{item.facts.map((fact) => <li key={fact}>{fact}</li>)}</ul> : <p>등록된 사실이 없습니다.</p>}</section><section className="detail-card evidence"><h3>원본 근거</h3><p>원본 {item.sourceRefs?.length ?? 0}개와 연결됨</p><button onClick={openSources}>원본 관리 →</button></section></aside></div>}
    <SourceManagerModal open={sourceOpen} sources={sources?.sources || []} busy={status === 'saving-source' || status === 'deleting-source'} error={error} onClose={() => setSourceOpen(false)} onSave={saveSource} onDelete={deleteSource} onDownload={downloadSource} />
  </article>;
}
