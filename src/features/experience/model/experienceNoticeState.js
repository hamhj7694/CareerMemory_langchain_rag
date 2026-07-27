const uniqueIds = (values = []) => [...new Set(values.filter(Boolean))];

export const createExperienceNoticeState = () => ({
  initialized: false,
  knownIds: [],
  unreadIds: [],
});

export function normalizeExperienceNoticeState(value = {}) {
  return {
    initialized: value.initialized === true,
    knownIds: uniqueIds(Array.isArray(value.knownIds) ? value.knownIds : []),
    unreadIds: uniqueIds(Array.isArray(value.unreadIds) ? value.unreadIds : []),
  };
}

export function reconcileExperienceNoticeState(value, currentIds = []) {
  const state = normalizeExperienceNoticeState(value);
  const ids = uniqueIds(currentIds);
  const current = new Set(ids);

  // 기능을 처음 사용하는 시점의 기존 경험은 기준선으로 등록한다.
  // 이후 목록에 처음 등장한 ID만 사용자가 확인해야 할 새 경험이다.
  const newlyAdded = state.initialized
    ? ids.filter((id) => !state.knownIds.includes(id))
    : [];
  const unreadIds = uniqueIds([...state.unreadIds, ...newlyAdded])
    .filter((id) => current.has(id));

  return {
    initialized: true,
    knownIds: ids,
    unreadIds,
  };
}

export function markExperienceNoticeRead(value, experienceId) {
  const state = normalizeExperienceNoticeState(value);
  return {
    ...state,
    unreadIds: state.unreadIds.filter((id) => id !== experienceId),
  };
}
