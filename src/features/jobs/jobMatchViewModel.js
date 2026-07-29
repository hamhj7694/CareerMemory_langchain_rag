const linkSource = (experience) => (
  experience?.linkSource
  || experience?.link_source
  || experience?.source
  || 'ai'
);

export function aiRecommendedExperienceIds(match) {
  return new Set(
    (match?.experiences || [])
      .filter((experience) => linkSource(experience) === 'ai')
      .map((experience) => experience.experienceId || experience.id)
      .filter(Boolean),
  );
}
