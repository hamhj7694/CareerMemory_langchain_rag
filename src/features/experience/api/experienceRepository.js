import { v2ChatApi } from '../../../api/v2ChatApi.js';
import { toExperience, toExperienceChanges, toExperienceCreateInput } from '../model/experienceMapper.js';

export const experienceRepository = {
  async get(id) {
    return toExperience(await v2ChatApi.getExperience(id));
  },
  async create(draft) {
    return toExperience(await v2ChatApi.createExperience(toExperienceCreateInput(draft)));
  },
  async update(experience, originalProjectId) {
    let saved = await v2ChatApi.updateExperience(experience.id, {
      base_version: experience.version,
      changes: toExperienceChanges(experience),
    });
    if (originalProjectId && experience.projectId !== originalProjectId) {
      await v2ChatApi.bulkMoveExperiences({ experience_ids: [experience.id], target_project_id: experience.projectId });
      saved = await v2ChatApi.getExperience(experience.id);
    }
    return toExperience(saved);
  },
  async structure() {
    return v2ChatApi.listStructure();
  },
};
