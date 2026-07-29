import { createClientRequestId } from '../../api/requestId.js';

function analysisFingerprint(input) {
  return JSON.stringify({
    companyName: input.companyName || '',
    roleName: input.roleName || '',
    postingTitle: input.postingTitle || '',
    sourceUrl: input.sourceUrl || '',
    postingContent: input.postingContent || '',
  });
}

export function resolveJobAnalysisAttempt(
  previousAttempt,
  input,
  idFactory = createClientRequestId,
) {
  const fingerprint = analysisFingerprint(input);
  if (previousAttempt?.fingerprint === fingerprint) {
    return previousAttempt;
  }
  return {
    fingerprint,
    clientRequestId: idFactory(),
  };
}
