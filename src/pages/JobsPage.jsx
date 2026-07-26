import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { jobApi } from '../api/index.js';
import { ErrorState } from '../components/common/index.js';
import { AnalysisProgress } from '../components/common/AnalysisProgress.jsx';
import './jobs.css';

export function JobsPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ companyName: '', roleName: '', postingTitle: '', sourceUrl: '', postingContent: '' });
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const [history, setHistory] = useState([]);
  const [historyQuery, setHistoryQuery] = useState('');
  const [postingFiles, setPostingFiles] = useState([]);
  const [extractingFiles, setExtractingFiles] = useState(false);
  const [fileInputKey, setFileInputKey] = useState(0);

  // 분석 기록은 브라우저가 아니라 현재 로그인한 사용자의 DB에서 불러온다.
  useEffect(() => {
    jobApi.list()
      .then((result) => setHistory(result.items || []))
      .catch((reason) => setError(reason.message || '분석 기록을 불러오지 못했습니다.'));
  }, []);

  const update = (event) => setForm((value) => ({ ...value, [event.target.name]: event.target.value }));
  const selectPostingFiles = (event) => {
    const files = [...event.target.files];
    if (files.length > 5) {
      setError('채용공고 파일은 최대 5개까지 선택할 수 있습니다.');
      event.target.value = '';
      return;
    }
    if (files.some((file) => file.size > 10 * 1024 * 1024)) {
      setError('파일 크기는 각각 10MB 이하여야 합니다.');
      event.target.value = '';
      return;
    }
    if (files.reduce((total, file) => total + file.size, 0) > 14 * 1024 * 1024) {
      setError('선택한 파일의 전체 크기는 14MB 이하여야 합니다.');
      event.target.value = '';
      return;
    }
    setPostingFiles(files);
    setError('');
  };
  const extractPostingFiles = async () => {
    if (!postingFiles.length) return;
    setExtractingFiles(true);
    setError('');
    try {
      const result = await jobApi.extractFiles(postingFiles);
      setForm((current) => ({
        ...current,
        postingContent: [current.postingContent.trim(), result.text?.trim()]
          .filter(Boolean)
          .join('\n\n'),
      }));
      setPostingFiles([]);
      setFileInputKey((current) => current + 1);
    } catch (reason) {
      setError(reason.message || '채용공고 파일을 읽지 못했습니다.');
    } finally {
      setExtractingFiles(false);
    }
  };
  const submit = async (event) => {
    event.preventDefault();
    if (!form.postingContent.trim()) { setError('채용공고 원문을 입력해 주세요.'); return; }
    if (form.sourceUrl.trim() && !/^https?:\/\/\S+$/i.test(form.sourceUrl.trim())) { setError('공고 링크는 http:// 또는 https://로 시작하는 주소를 입력해 주세요.'); return; }
    setPending(true); setError('');
    try {
      const job = await jobApi.analyze({
        companyName: form.companyName.trim() || undefined,
        roleName: form.roleName.trim() || undefined,
        postingTitle: form.postingTitle.trim() || undefined,
        sourceUrl: form.sourceUrl.trim() || undefined,
        postingContent: form.postingContent.trim(),
        coverLetterQuestions: [],
      });
      setHistory((current) => [job, ...current.filter((item) => item.jobId !== job.jobId)]);
      navigate(`/jobs/${job.jobId}`, { state: { job } });
    } catch (reason) { setError(reason.message || '공고를 분석하지 못했습니다.'); }
    finally { setPending(false); }
  };
  const normalizedHistoryQuery = historyQuery.trim().toLowerCase();
  const filteredHistory = history.filter((job) => `${job.companyName} ${job.roleName} ${job.postingTitle || ''} ${job.sourceUrl || ''} ${job.postingContent} ${(job.requirements || []).map((item) => item.text).join(' ')}`.toLowerCase().includes(normalizedHistoryQuery));
  const removeHistory = async (event, job) => {
    event.stopPropagation();
    if (!window.confirm(`‘${job.companyName || '회사 미입력'} · ${job.roleName || '직무 미입력'}’ 분석 기록을 삭제할까요?`)) return;
    try {
      await jobApi.remove(job.jobId);
      setHistory((current) => current.filter((item) => item.jobId !== job.jobId));
    } catch (reason) {
      setError(reason.message || '분석 기록을 삭제하지 못했습니다.');
    }
  };

  return <section className="feature-page jobs-entry">
    <header className="feature-heading"><div><span className="eyebrow">JOB SUPPORT</span><h1>채용공고 분석</h1><p>공고의 요구사항을 나누고 저장된 경험과 근거를 연결합니다.</p></div></header>
    <form className="surface job-form" onSubmit={submit} noValidate>
      <div className="form-grid two-columns">
        <label className="is-wide"><span>공고 제목 <small>선택</small></span><input name="postingTitle" value={form.postingTitle} onChange={update} placeholder="예: 2026년 서비스 기획자 경력 채용" /></label>
        <label><span>회사명 <small>선택</small></span><input name="companyName" value={form.companyName} onChange={update} placeholder="예: 넥스트랩" /></label>
        <label><span>직무명 <small>선택</small></span><input name="roleName" value={form.roleName} onChange={update} placeholder="예: 서비스 기획자" /></label>
        <label className="is-wide job-form__posting"><span>채용공고 원문 <b aria-hidden="true">*</b></span><textarea name="postingContent" value={form.postingContent} onChange={update} rows="12" placeholder="주요 업무, 자격 요건, 우대 사항을 포함한 공고 원문을 붙여 넣으세요." aria-invalid={Boolean(error)} required /></label>
        <div className="is-wide job-file-input">
          <div className="job-file-input__heading">
            <span>공고 파일 또는 화면 캡처 <small>선택</small></span>
            <small>PDF·TXT·PNG·JPG·WEBP / 최대 5개 / 파일당 10MB·전체 14MB</small>
          </div>
          <label className="job-file-input__picker">
            <input
              type="file"
              key={fileInputKey}
              accept=".pdf,.txt,.png,.jpg,.jpeg,.webp,application/pdf,text/plain,image/png,image/jpeg,image/webp"
              multiple
              onChange={selectPostingFiles}
            />
            <span>파일 선택</span>
            <em>{postingFiles.length ? `${postingFiles.length}개 선택됨` : '선택된 파일 없음'}</em>
          </label>
          {postingFiles.length > 0 && <div className="job-file-input__selected">
            <ul>{postingFiles.map((file) => <li key={`${file.name}-${file.size}`}><span>{file.name}</span><small>{(file.size / 1024 / 1024).toFixed(1)}MB</small></li>)}</ul>
            <div>
              <button type="button" className="ui-button ui-button--secondary" onClick={() => { setPostingFiles([]); setFileInputKey((current) => current + 1); }} disabled={extractingFiles}>선택 취소</button>
              <button type="button" className="ui-button" onClick={extractPostingFiles} disabled={extractingFiles}>{extractingFiles ? '파일 읽는 중…' : '파일에서 공고 읽기'}</button>
            </div>
          </div>}
          <p>이미지나 PDF의 글자를 읽은 뒤 위 원문 칸에 넣어 드립니다. 내용을 확인하고 수정한 다음 분석해 주세요.</p>
        </div>
        <label className="is-wide job-form__link"><span>공고 링크 <small>선택</small></span><input type="url" name="sourceUrl" value={form.sourceUrl} onChange={update} placeholder="https://example.com/jobs/123" /></label>
      </div>
      {error && <div className="inline-error" role="alert">{error}</div>}
      <AnalysisProgress
        active={pending || extractingFiles}
        hasFiles={postingFiles.length > 0}
        kind="job"
        phase={extractingFiles ? 'file' : 'analysis'}
      />
      <div className="form-actions"><p>분석 중에도 입력 내용은 유지됩니다.</p><button className="ui-button" disabled={pending || extractingFiles}>{pending ? '요구사항 분석 중…' : '공고 분석하기'}</button></div>
    </form>
    <section className="job-history" aria-labelledby="job-history-title">
      <div className="job-history__heading"><div><span className="eyebrow">ANALYSIS HISTORY</span><h2 id="job-history-title">기존 분석 공고</h2><p>이전에 분석한 공고와 요구사항을 다시 확인할 수 있습니다.</p></div><strong>{history.length}건</strong></div>
      {history.length > 0 && <label className="job-history__search"><span className="sr-only">기존 분석 공고 검색</span><input value={historyQuery} onChange={(event) => setHistoryQuery(event.target.value)} placeholder="공고 제목, 회사명, 직무명, 요구사항 검색" /></label>}
      {filteredHistory.length > 0 ? <div className="job-history__list">{filteredHistory.map((job) => <article key={job.jobId} className="surface job-history-card"><button className="job-history-card__main" onClick={() => navigate(`/jobs/${job.jobId}`, { state: { job } })}><span className="job-history-card__meta"><strong>{job.companyName || '회사 미입력'} · {job.roleName || '직무 미입력'}</strong><time dateTime={job.analyzedAt}>{new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium' }).format(new Date(job.analyzedAt))}</time></span><p>{job.requirements?.length ? `${job.requirements[0].text} 등 총 ${job.requirements.length}건` : '분석된 요구사항 없음 · 총 0건'}</p><span className="job-history-card__summary">상세 분석 보기 →</span></button><button className="job-history-card__delete" onClick={(event) => removeHistory(event, job)} aria-label={`${job.companyName || '회사 미입력'} ${job.roleName || '직무 미입력'} 분석 기록 삭제`}>삭제</button></article>)}</div> : <div className="surface job-history__empty"><h3>{history.length ? '검색 결과가 없습니다.' : '아직 분석한 공고가 없습니다.'}</h3><p>{history.length ? '다른 공고 제목이나 회사명, 직무명으로 검색해 보세요.' : '위에서 첫 채용공고를 분석하면 이곳에 자동으로 저장됩니다.'}</p>{history.length > 0 && <button onClick={() => setHistoryQuery('')}>검색어 지우기</button>}</div>}
    </section>
    {error && error.includes('연결') && <ErrorState title="API 연결을 확인해 주세요" description={error} onRetry={() => setError('')} />}
  </section>;
}
