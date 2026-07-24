const GROUP_RULES = [
  ['data-analysis', '\uB370\uC774\uD130\u00B7\uBD84\uC11D', /\uB370\uC774\uD130|\uBD84\uC11D|python|\uC2DC\uAC01\uD654|a\/b|\uC9C0\uD45C/i],
  ['planning-product', '\uAE30\uD68D\u00B7\uC81C\uD488', /\uAE30\uD68D|\uC694\uAD6C\uC0AC\uD56D|\uC6B0\uC120\uC21C\uC704|\uD504\uB85C\uC81D\uD2B8|\uC81C\uD488|ux/i],
  ['user-research', '\uC0AC\uC6A9\uC790\u00B7\uB9AC\uC11C\uCE58', /\uC0AC\uC6A9\uC790|\uC870\uC0AC|\uC778\uD130\uBDF0|\uB9AC\uC11C\uCE58/i],
  ['operations-collaboration', '\uC6B4\uC601\u00B7\uD611\uC5C5', /\uC6B4\uC601|\uD611\uC5C5|\uCEE4\uBBA4\uB2C8\uCF00\uC774\uC158|\uB9AC\uB4DC|\uAD00\uB9AC/i],
];

const clean = (value) => String(value || '').trim();
const slug = (value) => {
  const text = clean(value).toLowerCase();
  const ascii = text.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '');
  if (ascii) return ascii;
  const hash = [...text].reduce((total, character) => ((total * 31) + character.codePointAt(0)) >>> 0, 0);
  return `value-${hash.toString(36)}`;
};

export function getSkillGroup(skill, explicitGroup) {
  if (explicitGroup?.id && explicitGroup?.name) return { id: explicitGroup.id, name: explicitGroup.name, source: 'ai' };
  const match = GROUP_RULES.find(([, , rule]) => rule.test(skill));
  return match ? { id: match[0], name: match[1], source: 'fallback' } : { id: 'other', name: '\uAE30\uD0C0 \uC804\uBB38 \uC5ED\uB7C9', source: 'fallback' };
}

function experienceSkillLinks(experience) {
  const explicitLinks = experience.skillLinks || experience.skill_links || [];
  if (explicitLinks.length) return explicitLinks.map((link) => {
    const skill = link.skill || {};
    const name = clean(link.name || link.skill_name || skill.name);
    const group = link.group || skill.group;
    const normalizedGroup = getSkillGroup(name, group);
    return { skillId: link.skill_id || skill.id || `SKILL-${slug(name)}`, name, group: normalizedGroup, confidence: link.confidence ?? skill.confidence ?? null, evidenceIds: link.evidence_ids || link.evidenceIds || [] };
  }).filter((link) => link.name);
  return (experience.skills || []).map((name) => ({
    skillId: `SKILL-${slug(name)}`,
    name: clean(name),
    group: getSkillGroup(name),
    confidence: null,
    evidenceIds: experience.evidenceIds || experience.source_ids || [],
  })).filter((link) => link.name);
}

export function buildSkillProfile(experiences = []) {
  const skillMap = new Map();
  const linkMap = [];
  experiences.forEach((experience) => experienceSkillLinks(experience).forEach((link) => {
    const skill = skillMap.get(link.skillId) || { id: link.skillId, name: link.name, group: link.group, experienceIds: [], evidenceIds: [], confidences: [] };
    if (!skill.experienceIds.includes(experience.id)) skill.experienceIds.push(experience.id);
    skill.evidenceIds = [...new Set([...skill.evidenceIds, ...link.evidenceIds])];
    if (link.confidence != null) skill.confidences.push(link.confidence);
    skillMap.set(link.skillId, skill);
    linkMap.push({ experienceId: experience.id, skillId: link.skillId, evidenceIds: link.evidenceIds, confidence: link.confidence, group: link.group });
  }));
  const skills = [...skillMap.values()];
  const groups = new Map();
  linkMap.forEach((link) => {
    const group = groups.get(link.group.id) || { id: link.group.id, name: link.group.name, source: link.group.source, count: 0, skills: new Set(), experienceIds: new Set(), evidenceIds: new Set() };
    const skill = skillMap.get(link.skillId);
    group.count += 1;
    group.skills.add(skill.name);
    group.experienceIds.add(link.experienceId);
    link.evidenceIds.forEach((id) => group.evidenceIds.add(id));
    groups.set(link.group.id, group);
  });
  const totalLinks = linkMap.length;
  return {
    skills,
    links: linkMap,
    totalLinks,
    groups: [...groups.values()].map((group) => ({ ...group, skills: [...group.skills], experienceIds: [...group.experienceIds], evidenceIds: [...group.evidenceIds], percent: totalLinks ? Math.round((group.count / totalLinks) * 100) : 0 })).sort((a, b) => b.count - a.count),
  };
}

export function listExperienceRoles(experiences = []) {
  return [...new Set(experiences.flatMap((experience) => [experience.role, ...(experience.roles || experience.roleTags || [])]).map(clean).filter(Boolean))];
}
