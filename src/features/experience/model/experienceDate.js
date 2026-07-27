const savedDateFormatter = new Intl.DateTimeFormat('ko-KR', {
  year: 'numeric',
  month: 'numeric',
  day: 'numeric',
});

const savedDateTimeFormatter = new Intl.DateTimeFormat('ko-KR', {
  year: 'numeric',
  month: 'numeric',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
});

export function formatExperienceSavedDateTime(value) {
  if (!value) return '';

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';

  // 날짜만 저장된 과거 데이터에는 존재하지 않는 자정 시간을 표시하지 않는다.
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value.trim())) {
    return savedDateFormatter.format(date);
  }

  return savedDateTimeFormatter.format(date);
}

export function formatExperienceSavedDate(value) {
  return formatExperienceSavedDateTime(value);
}
