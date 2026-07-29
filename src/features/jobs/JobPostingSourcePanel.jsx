export function JobPostingSourcePanel({ job, expanded, onToggle }) {
  const sourceFields = [
    { label: '공고 제목', value: job?.postingTitle },
    { label: '회사명', value: job?.companyName },
    { label: '직무명', value: job?.roleName },
  ];
  const hasSource = sourceFields.some((field) => field.value?.trim())
    || job?.sourceUrl?.trim()
    || job?.postingContent?.trim();

  return (
    <section className={`surface job-posting-source ${expanded ? 'is-expanded' : ''}`}>
      <button
        type="button"
        className="job-posting-source__toggle"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls="job-posting-source-content"
      >
        <span className="job-posting-source__heading">
          <span className="eyebrow">ORIGINAL POSTING</span>
          <strong>입력한 공고 원본</strong>
          <small>
            {hasSource
              ? '분석할 때 입력한 공고 정보와 원문을 확인할 수 있습니다.'
              : '이 분석 기록에는 저장된 공고 원본이 없습니다.'}
          </small>
        </span>
        <span className="job-posting-source__action">
          {expanded ? '원본 접기' : '원본 보기'}
          <span aria-hidden="true">⌄</span>
        </span>
      </button>

      {expanded && (
        <div id="job-posting-source-content" className="job-posting-source__content">
          {hasSource ? (
            <>
              <dl className="job-posting-source__meta">
                {sourceFields.map((field) => (
                  <div key={field.label}>
                    <dt>{field.label}</dt>
                    <dd>{field.value?.trim() || '입력하지 않음'}</dd>
                  </div>
                ))}
                <div className="is-wide">
                  <dt>공고 링크</dt>
                  <dd>
                    {job.sourceUrl?.trim() ? (
                      <a href={job.sourceUrl} target="_blank" rel="noreferrer">
                        {job.sourceUrl}
                      </a>
                    ) : '입력하지 않음'}
                  </dd>
                </div>
              </dl>
              <div className="job-posting-source__body">
                <h3>채용공고 원문</h3>
                <pre>{job.postingContent?.trim() || '저장된 공고 원문이 없습니다.'}</pre>
              </div>
            </>
          ) : (
            <p className="job-posting-source__empty">
              이전 분석 기록에 원본이 저장되지 않았습니다. 새 공고를 분석하면 입력한 원본도 함께 저장됩니다.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
