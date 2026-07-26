import { fingerprintFile } from '../../../utils/fileFingerprint.js';

export const EVIDENCE_FILE_LIMITS = {
  acceptedTypes: ['application/pdf', 'text/plain', 'image/png', 'image/jpeg', 'image/webp'],
  maxCount: 5,
  maxFileBytes: 10 * 1024 * 1024,
  maxTotalBytes: 14 * 1024 * 1024,
};

export const evidenceFileKey = (item) => item.selectionId || item.contentHash || `${item.name}-${item.size}-${item.lastModified || 0}`;
export const evidenceFileStatusLabel = (item) => item.duplicateStatus === 'reused'
  ? '기존 근거 재사용'
  : item.duplicateStatus === 'new-version'
    ? '동일 이름 · 새 버전'
    : '새 파일';

const isAccepted = (file) => EVIDENCE_FILE_LIMITS.acceptedTypes.includes(file.type) || /\.(pdf|txt|png|jpe?g|webp)$/i.test(file.name || '');
const clientId = (file, contentHash) => `${contentHash}:${file.name}:${file.size}`;

export async function mergeEvidenceFileSelections(currentFiles, incomingFiles, preflight) {
  const current = Array.from(currentFiles || []);
  const incoming = Array.from(incomingFiles || []);
  const unsupported = incoming.filter((file) => !isAccepted(file));
  const oversized = incoming.filter((file) => (file.size || 0) > EVIDENCE_FILE_LIMITS.maxFileBytes);
  const candidates = incoming.filter((file) => isAccepted(file) && (file.size || 0) <= EVIDENCE_FILE_LIMITS.maxFileBytes);
  const errors = [];
  const notices = [];

  if (unsupported.length) errors.push(`PDF/TXT/이미지가 아닌 파일 ${unsupported.length}개`);
  if (oversized.length) errors.push(`10MiB를 넘는 파일 ${oversized.length}개`);

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
  const result = descriptors.length ? await preflight(descriptors.map((descriptor) => ({
    client_id: descriptor.client_id,
    filename: descriptor.filename,
    content_hash: descriptor.content_hash,
    size_bytes: descriptor.size_bytes,
    mime_type: descriptor.mime_type,
    last_modified: descriptor.last_modified,
  }))) : { items: [] };
  const matches = new Map((result.items || []).map((item) => [item.client_id, item]));
  const next = [...current];
  const selectedHashes = new Set(current.map((item) => item.contentHash).filter(Boolean));
  let totalBytes = current.reduce((sum, item) => sum + (item.size || 0), 0);

  for (const descriptor of descriptors) {
    if (selectedHashes.has(descriptor.content_hash)) {
      notices.push(`${descriptor.filename}: 이미 선택한 동일 파일이라 추가하지 않았습니다.`);
      continue;
    }
    if (next.length >= EVIDENCE_FILE_LIMITS.maxCount) {
      errors.push(`최대 개수 ${EVIDENCE_FILE_LIMITS.maxCount}개 초과`);
      break;
    }
    if (totalBytes + descriptor.size_bytes > EVIDENCE_FILE_LIMITS.maxTotalBytes) {
      errors.push('전체 용량 14MiB 초과');
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
