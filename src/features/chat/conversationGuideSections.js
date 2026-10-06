const MAX_GUIDE_MARKERS = 12;

function sectionImportance(section, sections) {
  const previous = sections[section.index - 1];
  const next = sections[section.index + 1];
  let score = 0;

  if (section.hasProposal) score += 120;
  if (section.hasAttachment) score += 100;
  if (section.category !== 'general') score += 50;
  if (previous && previous.category !== section.category) score += 35;
  if (next && next.category !== section.category) score += 15;

  return score;
}

export function selectGuideSections(sections, maxMarkers = MAX_GUIDE_MARKERS) {
  if (sections.length <= maxMarkers) {
    return sections.map((section) => ({
      ...section,
      rangeStart: section.index,
      rangeEnd: section.index,
      representedCount: 1,
    }));
  }

  const interiorSlotCount = Math.max(1, maxMarkers - 2);
  const interiorCount = sections.length - 2;
  const selected = [{
    ...sections[0],
    rangeStart: 0,
    rangeEnd: 0,
    representedCount: 1,
  }];

  for (let slot = 0; slot < interiorSlotCount; slot += 1) {
    const rangeStart = 1 + Math.floor((slot * interiorCount) / interiorSlotCount);
    const rangeEndExclusive = 1 + Math.floor(((slot + 1) * interiorCount) / interiorSlotCount);
    const candidates = sections.slice(rangeStart, rangeEndExclusive);
    const representative = candidates.reduce((best, candidate) => (
      sectionImportance(candidate, sections) > sectionImportance(best, sections)
        ? candidate
        : best
    ));

    selected.push({
      ...representative,
      rangeStart,
      rangeEnd: rangeEndExclusive - 1,
      representedCount: rangeEndExclusive - rangeStart,
    });
  }

  const lastIndex = sections.length - 1;
  selected.push({
    ...sections[lastIndex],
    rangeStart: lastIndex,
    rangeEnd: lastIndex,
    representedCount: 1,
  });

  return selected;
}
