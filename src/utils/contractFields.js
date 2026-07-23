export const projectCandidateId = (candidate) => candidate.projectId || candidate.id;
export const failureRequirementIds = (failures) => failures.map((item) => item.itemId || item.requirementId || item.id).filter(Boolean);
