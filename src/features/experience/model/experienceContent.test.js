import { describe, expect, it } from 'vitest';
import { listToText, textToMarkdownLines, textToSkills, toExperienceContent } from './experienceContent.js';

describe('experience content contract', () => {
  it('keeps mixed Markdown list lines and indentation', () => {
    const source = '1. 첫 단계\n  - 하위 내용\n- 별도 행동';
    const lines = textToMarkdownLines(source);

    expect(lines).toEqual(['1. 첫 단계', '  - 하위 내용', '- 별도 행동']);
    expect(listToText(lines)).toBe(source);
  });

  it('normalizes skills from commas and new lines', () => {
    expect(textToSkills('데이터 분석, UX 기획\nA/B 테스트')).toEqual(['데이터 분석', 'UX 기획', 'A/B 테스트']);
  });

  it('creates the same core shape for drafts and confirmed experiences', () => {
    expect(toExperienceContent({ title: '경험', actions: ['- 행동'] })).toEqual({
      title: '경험',
      summary: '',
      situation: '',
      actions: ['- 행동'],
      results: [],
      role: '',
      skills: [],
      facts: [],
    });
  });
});
