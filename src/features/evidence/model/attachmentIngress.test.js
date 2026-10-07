import { describe, expect, it } from 'vitest';
import { clipboardName, filesFromDrop, filesFromPaste, hasFilePayload } from './attachmentIngress.js';

const fakeFile = (name = 'image.png', type = 'image/png') => ({ name, type, size: 10 });
const item = (file) => ({ kind: 'file', getAsFile: () => file });

describe('attachment ingress', () => {
  it('reads file items from paste without treating ordinary text as a file', () => {
    const image = fakeFile();
    const files = filesFromPaste({
      items: [item(image), { kind: 'string' }],
      files: [],
    }, new Date('2026-10-07T10:20:30Z'));

    expect(files).toHaveLength(1);
    expect(files[0].name).toBe('clipboard-20261007T102030Z.png');
    expect(files[0].type).toBe('image/png');
    expect(clipboardName(image, new Date('2026-10-07T10:20:30Z'))).toBe('clipboard-20261007T102030Z.png');
  });

  it('reads desktop files from a drop payload', () => {
    const document = fakeFile('resume.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document');
    const transfer = { items: [item(document)], files: [document], types: ['Files'] };

    expect(hasFilePayload(transfer)).toBe(true);
    expect(filesFromDrop(transfer)).toEqual([document]);
  });
});
