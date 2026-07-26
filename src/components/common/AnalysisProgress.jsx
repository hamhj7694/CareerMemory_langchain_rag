import { useEffect, useMemo, useState } from 'react';
import { getEstimatedProgress } from './analysisProgressModel.js';
import './analysis-progress.css';

const DEFAULT_STAGES = [
  '입력 내용을 확인하고 있어요',
  'AI가 핵심 내용을 분석하고 있어요',
  '분석 결과를 정리하고 있어요',
];

const FILE_STAGES = [
  '첨부 파일을 확인하고 있어요',
  '이미지·PDF에서 내용을 읽고 있어요',
  'AI가 핵심 내용을 분석하고 있어요',
  '분석 결과를 정리하고 있어요',
];

export function AnalysisProgress({
  active,
  hasFiles = false,
  kind = 'experience',
  phase = 'analysis',
}) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const stages = useMemo(() => {
    if (phase === 'file') return ['파일을 확인하고 있어요', '파일에서 글자를 읽고 있어요', '입력란에 내용을 옮기고 있어요'];
    return hasFiles ? FILE_STAGES : DEFAULT_STAGES;
  }, [hasFiles, phase]);

  useEffect(() => {
    if (!active) return undefined;
    const startedAt = Date.now();
    // 이전 요청의 경과 시간이 잠깐 보이지 않도록 다음 이벤트 루프에서 초기화한다.
    const resetTimer = window.setTimeout(() => setElapsedSeconds(0), 0);
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 500);
    return () => {
      window.clearTimeout(resetTimer);
      window.clearInterval(timer);
    };
  }, [active]);

  if (!active) return null;

  const progress = getEstimatedProgress(elapsedSeconds);
  const stageIndex = Math.min(
    stages.length - 1,
    elapsedSeconds < 3 ? 0 : elapsedSeconds < 10 ? 1 : elapsedSeconds < 25 ? 2 : stages.length - 1,
  );
  const slowMessage = elapsedSeconds >= 30
    ? `${hasFiles || phase === 'file' ? '파일 내용이 많아 ' : ''}분석에 시간이 조금 더 걸리고 있어요. 요청은 정상적으로 진행 중입니다.`
    : null;
  const title = kind === 'job' ? '채용공고를 분석하고 있어요' : '경험을 정리하고 있어요';

  return (
    <section className="analysis-progress" role="status" aria-live="polite" aria-label={title}>
      <div className="analysis-progress__heading">
        <span className="analysis-progress__spinner" aria-hidden="true" />
        <div>
          <strong>{title}</strong>
          <p>{stages[stageIndex]}</p>
        </div>
        <time>{elapsedSeconds}초</time>
      </div>
      <div
        className="analysis-progress__track"
        role="progressbar"
        aria-label={stages[stageIndex]}
        aria-valuemin="0"
        aria-valuemax="100"
        aria-valuenow={Math.round(progress)}
      >
        <span style={{ width: `${progress}%` }} />
      </div>
      <ol className="analysis-progress__steps">
        {stages.map((stage, index) => (
          <li key={stage} className={index < stageIndex ? 'is-done' : index === stageIndex ? 'is-active' : ''}>
            <span aria-hidden="true">{index < stageIndex ? '✓' : index + 1}</span>
            {stage}
          </li>
        ))}
      </ol>
      {slowMessage && <p className="analysis-progress__slow">{slowMessage}</p>}
    </section>
  );
}
