import { toExperience } from './experienceMapper.js';

export function selectExperiencePreview(value) {
  const experience = toExperience(value);
  return {
    id: experience.id,
    title: experience.title,
    projectName: experience.projectName,
    summary: experience.summary,
    skills: experience.skills,
  };
}

export function selectExperienceCard(value) {
  const experience = toExperience(value);
  return {
    id: experience.id,
    title: experience.title,
    skills: experience.skills.slice(0, 2),
  };
}
