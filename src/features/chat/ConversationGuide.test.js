import { describe, expect, it } from 'vitest';
import { selectGuideSections } from './conversationGuideSections.js';

function makeSections(count) {
  return Array.from({ length: count }, (_, index) => ({
    id: String(index),
    index,
    category: 'general',
    hasAttachment: false,
    hasProposal: false,
  }));
}

describe('selectGuideSections', () => {
  it('keeps every section when the conversation is short', () => {
    const sections = makeSections(8);

    const selected = selectGuideSections(sections);

    expect(selected.map((section) => section.id)).toEqual(sections.map((section) => section.id));
    expect(selected.every((section) => section.representedCount === 1)).toBe(true);
  });

  it('caps a long conversation while retaining its first and last sections', () => {
    const selected = selectGuideSections(makeSections(30));

    expect(selected).toHaveLength(12);
    expect(selected[0].id).toBe('0');
    expect(selected.at(-1).id).toBe('29');
    expect(selected.reduce((total, section) => total + section.representedCount, 0)).toBe(30);
  });

  it('prefers important content inside each represented range', () => {
    const sections = makeSections(30);
    sections[4] = { ...sections[4], hasAttachment: true };
    sections[12] = { ...sections[12], category: 'experience' };
    sections[21] = { ...sections[21], hasProposal: true };

    const selectedIds = selectGuideSections(sections).map((section) => section.id);

    expect(selectedIds).toContain('4');
    expect(selectedIds).toContain('12');
    expect(selectedIds).toContain('21');
  });
});
