const FAILURE_HINTS = {
  provider_auth: 'AI 서비스 인증 설정을 확인해 주세요.',
  provider_limit: 'AI 서비스의 사용량 한도를 확인해 주세요.',
  provider_unavailable: 'AI 서비스 연결을 확인한 뒤 다시 시도해 주세요.',
  invalid_output: 'AI가 반환한 초안을 검증하지 못했어요. 프로젝트별로 나눠 다시 시도해 주세요.',
  invalid_input: '분석할 원문을 확인해 주세요.',
};

export function conversationAnalysisNotice(run = {}) {
  const parts = [];
  if (run.experience_count) parts.push(`경험 초안 ${run.experience_count}개`);
  if (run.job_count) parts.push(`채용공고 ${run.job_count}개`);

  const failures = Array.isArray(run.failures) ? run.failures : [];
  if (!failures.length) {
    return parts.length
      ? `${parts.join('와 ')}를 분석했어요. 결과를 확인해 주세요.`
      : '새로 정리할 경험이나 채용공고를 찾지 못했어요.';
  }

  const stages = [...new Set(failures.map((failure) => failure.label).filter(Boolean))];
  const failedStage = stages.length ? `${stages.join(', ')} 단계에서 오류가 발생했어요.` : '일부 분석을 완료하지 못했어요.';
  const hint = failures.map((failure) => FAILURE_HINTS[failure.code]).find(Boolean)
    || '잠시 후 다시 시도해 주세요.';
  const prefix = parts.length ? `${parts.join('와 ')}를 분석했어요. ` : '';
  return `${prefix}${failedStage} ${hint}`;
}
