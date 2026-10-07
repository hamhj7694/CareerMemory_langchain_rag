function fileItems(dataTransfer) {
  const items = Array.from(dataTransfer?.items || []);
  const fromItems = items
    .filter((item) => item.kind === 'file')
    .map((item) => item.getAsFile?.())
    .filter(Boolean);
  return fromItems.length ? fromItems : Array.from(dataTransfer?.files || []);
}

function clipboardName(file, now = new Date()) {
  if (file.name && !/^image\.(png|jpe?g|webp)$/i.test(file.name)) return file.name;
  const stamp = now.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
  const extension = file.type === 'image/jpeg' ? 'jpg' : file.type?.split('/')[1] || 'png';
  return `clipboard-${stamp}.${extension}`;
}

function renameClipboardFile(file, now) {
  const name = clipboardName(file, now);
  if (name === file.name || typeof File === 'undefined') return file;
  return new File([file], name, {
    type: file.type,
    lastModified: file.lastModified || Date.now(),
  });
}

export function filesFromPaste(clipboardData, now = new Date()) {
  return fileItems(clipboardData).map((file) => renameClipboardFile(file, now));
}

export function filesFromDrop(dataTransfer) {
  return fileItems(dataTransfer);
}

export function hasFilePayload(dataTransfer) {
  return Array.from(dataTransfer?.types || []).includes('Files')
    || Array.from(dataTransfer?.items || []).some((item) => item.kind === 'file');
}

export { clipboardName };
