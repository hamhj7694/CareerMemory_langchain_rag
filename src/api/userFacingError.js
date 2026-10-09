const FORCED_CODE_MESSAGES = Object.freeze({
  NETWORK_ERROR: '서버에 연결하지 못했어요. 서버가 실행 중인지 확인한 뒤 다시 시도해 주세요.',
  AI_PROCESSING_TIMEOUT: '처리 시간이 예상보다 길어졌어요. 입력한 내용은 유지되니 잠시 후 다시 시도해 주세요.',
  REQUEST_ABORTED: '요청이 취소됐어요. 필요하면 다시 시도해 주세요.',
  AUTHENTICATION_REQUIRED: '로그인이 필요해요. 다시 로그인해 주세요.',
  FORBIDDEN: '이 작업을 수행할 권한이 없어요.',
  VERSION_CONFLICT: '다른 곳에서 내용이 변경됐어요. 최신 내용을 불러온 뒤 다시 시도해 주세요.',
  AI_QUOTA_EXCEEDED: '현재 AI 사용 한도에 도달했어요. 잠시 후 다시 시도해 주세요.',
  AI_PROVIDER_ERROR: 'AI 응답을 받아오지 못했어요. 잠시 후 다시 시도해 주세요.',
  NOT_IMPLEMENTED: '아직 사용할 수 없는 기능이에요.',
  INVALID_RESPONSE: '서버 응답을 확인하지 못했어요. 잠시 후 다시 시도해 주세요.',
});

const TECHNICAL_MESSAGE_PATTERN = new RegExp([
  'traceback', 'exception', 'stack trace', 'sqlalchemy', 'sqlite', 'mysql',
  'econn', 'enotfound', 'fetch failed', 'networkerror', 'json', 'undefined',
  'cannot read', 'errno', 'http\\s*\\d{3}', '\\/api\\/', '[a-z]:\\\\',
  'openai', 'gemini', 'provider', 'tesseract', 'ffmpeg', 'ffprobe',
  'libreoffice', 'soffice', 'sha-?256', 'worker',
].join('|'), 'i');

function rawMessage(error) {
  if (typeof error === 'string') return error.trim();
  return String(error?.message || '').trim();
}

export function toUserFacingAttachmentError(
  error,
  fallback = '파일 내용을 읽지 못했어요. 다시 시도하거나 다른 파일을 첨부해 주세요.',
) {
  const message = rawMessage(error);
  if (!message) return fallback;
  if (/tesseract|ocr/i.test(message)) {
    return '이미지의 글자를 읽지 못했어요. 더 선명한 이미지로 다시 시도하거나 PDF·텍스트 파일을 첨부해 주세요.';
  }
  if (/ffmpeg|ffprobe|stt|transcri/i.test(message)) {
    return '음성·영상 내용을 읽지 못했어요. 다른 파일로 다시 시도해 주세요.';
  }
  if (/libreoffice|soffice|\.doc\b|\.ppt\b/i.test(message)) {
    return '이 문서를 읽지 못했어요. DOCX·PPTX 또는 PDF로 변환해 다시 첨부해 주세요.';
  }
  if (/hwp/i.test(message)) {
    return '한글 문서를 읽지 못했어요. HWPX 또는 PDF로 저장해 다시 첨부해 주세요.';
  }
  if (/암호|password|encrypted/i.test(message)) {
    return '암호로 보호된 파일은 읽을 수 없어요. 암호를 해제한 뒤 다시 첨부해 주세요.';
  }
  if (/시간.*초과|timed?\s*out/i.test(message)) {
    return '파일을 읽는 데 시간이 너무 오래 걸렸어요. 용량을 줄이거나 다시 시도해 주세요.';
  }
  if (/지원하지|unsupported/i.test(message)) {
    return '지원하지 않는 파일 형식이에요. 지원되는 형식으로 변환해 다시 첨부해 주세요.';
  }
  return toUserFacingErrorMessage(error, fallback);
}

export function toUserFacingErrorMessage(
  error,
  fallback = '요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.',
) {
  const code = typeof error === 'object' ? String(error?.code || '') : '';
  if (FORCED_CODE_MESSAGES[code]) return FORCED_CODE_MESSAGES[code];

  const message = rawMessage(error);
  if (!message) {
    if (Number(error?.status) >= 500) {
      return '서버에서 문제가 발생했어요. 잠시 후 다시 시도해 주세요.';
    }
    return fallback;
  }

  if (TECHNICAL_MESSAGE_PATTERN.test(message)) return fallback;
  if (/[가-힣]/.test(message) && message.length <= 240) return message;
  return fallback;
}

export function attachmentUnavailableMessage(file) {
  const filename = file?.name ? `‘${file.name}’ 파일` : '첨부 파일';
  if (['failed', 'upload_failed'].includes(file?.processingStatus)) {
    return `${filename}을 준비하지 못했어요. ‘재시도’를 누르거나 파일을 삭제해 주세요.`;
  }
  if (file?.processingStatus === 'unsupported') {
    return `${filename}은 지원하지 않는 형식이에요. 파일을 삭제하고 다른 형식으로 첨부해 주세요.`;
  }
  return `${filename}의 내용을 확인하고 있어요. 처리가 끝난 뒤 다시 전송해 주세요.`;
}

