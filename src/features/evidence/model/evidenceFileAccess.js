const localPayload = (source) => source.rawBytes || source.raw_bytes || source.raw?.rawBytes || source.raw?.raw_bytes;

export async function evidenceBlob(source, loadBlob) {
  const payload = localPayload(source);
  if (payload) return new Blob([payload], { type: source.mimeType || source.mime_type || 'application/octet-stream' });
  if (source.text && String(source.mimeType || source.mime_type).startsWith('text/')) return new Blob([source.text], { type: source.mimeType || source.mime_type || 'text/plain' });
  if (loadBlob) return loadBlob(source);
  throw new Error('저장된 원본 파일 데이터가 없습니다.');
}

export async function openEvidenceFile(source, loadBlob) {
  const popup = window.open('', '_blank');
  try {
    const blob = await evidenceBlob(source, loadBlob);
    const url = URL.createObjectURL(blob);
    if (popup) popup.location.href = url;
    else window.open(url, '_blank', 'noopener,noreferrer');
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (error) {
    popup?.close();
    throw error;
  }
}

export async function downloadEvidenceFile(source, loadBlob) {
  const blob = await evidenceBlob(source, loadBlob);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = source.filename || source.title || `source-${source.id}`;
  anchor.click();
  URL.revokeObjectURL(url);
}
