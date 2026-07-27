const fingerprintCache = new WeakMap();

export async function sha256ArrayBuffer(buffer) {
  if (!globalThis.crypto?.subtle) {
    throw new Error('이 브라우저에서는 파일 중복 확인을 지원하지 않습니다.');
  }
  const digest = await globalThis.crypto.subtle.digest('SHA-256', buffer);
  // 서버 Attachment.content_hash 계약은 알고리즘 접두어가 없는 SHA-256 64자리 hex다.
  return [...new Uint8Array(digest)]
    .map((value) => value.toString(16).padStart(2, '0'))
    .join('');
}

export async function fingerprintFile(file) {
  if (file?.contentHash) return file.contentHash;
  if (file && typeof file === 'object' && fingerprintCache.has(file)) return fingerprintCache.get(file);
  if (typeof file?.arrayBuffer !== 'function') throw new Error(`${file?.name || '선택한 파일'}의 내용을 읽을 수 없습니다.`);
  const fingerprint = sha256ArrayBuffer(await file.arrayBuffer());
  if (file && typeof file === 'object') fingerprintCache.set(file, fingerprint);
  return fingerprint;
}
