import { fingerprintFile } from '../../../utils/fileFingerprint.js';

export const SUPPORTED_EVIDENCE_EXTENSIONS = [
  'pdf', 'txt', 'md', 'markdown', 'png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'tif', 'tiff',
  'docx', 'pptx', 'hwpx',
  'doc', 'ppt', 'hwp',
  'wav', 'mp3', 'm4a', 'ogg', 'flac', 'mp4', 'mov', 'webm', 'mkv', 'mpeg', 'mpg',
];

export const SUPPORTED_EVIDENCE_MIME_TYPES = [
  'application/pdf', 'text/plain', 'text/markdown',
  'image/png', 'image/jpeg', 'image/webp', 'image/gif', 'image/bmp', 'image/tiff',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/vnd.hancom.hwpx',
  'application/msword', 'application/vnd.ms-powerpoint', 'application/x-hwp',
  'audio/wav', 'audio/mpeg', 'audio/mp4', 'audio/ogg', 'audio/flac',
  'video/mp4', 'video/quicktime', 'video/webm', 'video/x-matroska', 'video/mpeg',
];

export const EVIDENCE_FILE_ACCEPT = [
  ...SUPPORTED_EVIDENCE_EXTENSIONS.map((extension) => `.${extension}`),
  ...SUPPORTED_EVIDENCE_MIME_TYPES,
].join(',');

export const EVIDENCE_FILE_LIMITS = {
  acceptedTypes: SUPPORTED_EVIDENCE_MIME_TYPES,
  acceptedExtensions: SUPPORTED_EVIDENCE_EXTENSIONS,
  maxCount: 10,
  maxFileBytes: 25 * 1024 * 1024,
  maxTotalBytes: 100 * 1024 * 1024,
};

export const CHAT_ATTACHMENT_LIMITS = {
  ...EVIDENCE_FILE_LIMITS,
  maxCount: 10,
};

export const evidenceFileKey = (item) => item.selectionId || item.contentHash || `${item.name}-${item.size}-${item.lastModified || 0}`;
export const evidenceFileStatusLabel = (item) => {
  const statusLabels = {
    uploading: '업로드 중',
    queued: '처리 대기',
    processing: '내용 추출 중',
    ready: '분석 준비 완료',
    partial: '일부 추출 완료',
    failed: '처리 실패',
    unsupported: '지원 불가',
    upload_failed: '업로드 실패',
  };
  if (statusLabels[item.processingStatus]) return statusLabels[item.processingStatus];
  if (item.duplicateStatus === 'reused') return '기존 근거 재사용';
  if (item.duplicateStatus === 'new-version') return '동일 이름 · 새 버전';
  return '새 파일';
};

export const isSupportedEvidenceFile = (file, limits = EVIDENCE_FILE_LIMITS) => {
  const mimeType = (file.type || '').toLowerCase();
  const extension = (file.name || '').split('.').pop()?.toLowerCase();
  return limits.acceptedTypes.includes(mimeType) || limits.acceptedExtensions.includes(extension);
};
const clientId = (file, contentHash) => `${contentHash}:${file.name}:${file.size}`;

export async function mergeEvidenceFileSelections(currentFiles, incomingFiles, preflight, limits = EVIDENCE_FILE_LIMITS) {
  const current = Array.from(currentFiles || []);
  const incoming = Array.from(incomingFiles || []);
  const unsupported = incoming.filter((file) => !isSupportedEvidenceFile(file, limits));
  const oversized = incoming.filter((file) => (file.size || 0) > limits.maxFileBytes);
  const candidates = incoming.filter((file) => isSupportedEvidenceFile(file, limits) && (file.size || 0) <= limits.maxFileBytes);
  const errors = [];
  const notices = [];

  if (unsupported.length) errors.push(`지원하지 않는 형식의 파일 ${unsupported.length}개`);
  if (oversized.length) errors.push(`25MiB를 넘는 파일 ${oversized.length}개`);

  const descriptors = await Promise.all(candidates.map(async (file) => {
    const contentHash = await fingerprintFile(file);
    return {
      client_id: clientId(file, contentHash),
      filename: file.name,
      content_hash: contentHash,
      size_bytes: file.size || 0,
      mime_type: file.type || 'application/octet-stream',
      last_modified: file.lastModified || 0,
      file,
    };
  }));
  const preflightItems = [];
  for (let start = 0; start < descriptors.length; start += limits.maxCount) {
    const batch = descriptors.slice(start, start + limits.maxCount);
    const result = await preflight(batch.map((descriptor) => ({
      client_id: descriptor.client_id,
      filename: descriptor.filename,
      content_hash: descriptor.content_hash,
      size_bytes: descriptor.size_bytes,
      mime_type: descriptor.mime_type,
      last_modified: descriptor.last_modified,
    })));
    preflightItems.push(...(result.items || []));
  }
  const matches = new Map(preflightItems.map((item) => [item.client_id, item]));
  const next = [...current];
  const selectedHashes = new Set(current.map((item) => item.contentHash).filter(Boolean));
  let totalBytes = current.reduce((sum, item) => sum + (item.size || 0), 0);

  for (const descriptor of descriptors) {
    if (selectedHashes.has(descriptor.content_hash)) {
      notices.push(`${descriptor.filename}: 이미 선택한 동일 파일이라 추가하지 않았습니다.`);
      continue;
    }
    if (next.length >= limits.maxCount) {
      errors.push(`최대 개수 ${limits.maxCount}개 초과`);
      break;
    }
    if (totalBytes + descriptor.size_bytes > limits.maxTotalBytes) {
      errors.push(`전체 용량 ${Math.round(limits.maxTotalBytes / 1024 / 1024)}MiB 초과`);
      continue;
    }

    const match = matches.get(descriptor.client_id);
    const exact = match?.status === 'exact_duplicate' ? match.existing_attachment : null;
    const sameName = match?.status === 'same_name_different_content' ? match.existing_attachment : null;
    const selection = {
      selectionId: descriptor.client_id,
      file: descriptor.file,
      name: exact?.filename || descriptor.filename,
      requestedName: descriptor.filename,
      size: exact?.size_bytes ?? descriptor.size_bytes,
      type: exact?.mime_type || descriptor.mime_type,
      lastModified: descriptor.last_modified,
      contentHash: descriptor.content_hash,
      existingAttachmentId: exact?.id || '',
      duplicateStatus: exact ? 'reused' : sameName ? 'new-version' : 'new',
      previousAttachmentId: sameName?.id || '',
    };
    if (exact) notices.push(`${descriptor.filename}: 동일한 기존 근거를 새로 올리지 않고 재사용합니다.`);
    if (sameName) notices.push(`${descriptor.filename}: 같은 이름의 기존 파일과 내용이 달라 새 버전으로 추가합니다.`);
    next.push(selection);
    selectedHashes.add(descriptor.content_hash);
    totalBytes += selection.size;
  }

  return {
    files: next,
    error: [...new Set(errors)].length ? `${[...new Set(errors)].join(' · ')}는 추가하지 않았습니다.` : '',
    notice: notices.join(' '),
  };
}
