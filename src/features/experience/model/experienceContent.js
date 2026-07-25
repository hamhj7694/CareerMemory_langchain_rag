const array = (value) => Array.isArray(value) ? value : [];
const text = (value) => value == null ? '' : String(value);

/**
 * AI 초안과 확정 경험이 함께 사용하는 콘텐츠 계약이다.
 * 화면 전용 상태나 승인 상태는 여기에 넣지 않는다.
 */
export function toExperienceContent(value = {}) {
  return {
    title: text(value.title),
    summary: text(value.summary),
    situation: text(value.situation),
    actions: array(value.actions).map(text),
    results: array(value.results).map(text),
    role: text(value.role),
    skills: array(value.skills).map(text).map((item) => item.trim()).filter(Boolean),
    facts: array(value.facts).map(text),
  };
}

export const listToText = (items) => array(items).map(text).join('\n');

// 빈 줄과 들여쓰기를 보존해야 혼합 Markdown 목록이 저장 후에도 동일하게 보인다.
export const textToMarkdownLines = (value) => text(value).replace(/\r\n/g, '\n').split('\n');

export const textToSkills = (value) => text(value)
  .split(/[\n,，]/)
  .map((item) => item.trim())
  .filter(Boolean);

export function toExperienceContentChanges(value = {}) {
  const content = toExperienceContent(value);
  return {
    title: content.title,
    summary: content.summary,
    situation: content.situation,
    actions: content.actions,
    results: content.results,
    role: content.role,
    skills: content.skills,
    facts: content.facts,
  };
}
