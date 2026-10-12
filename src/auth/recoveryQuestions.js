export const RECOVERY_QUESTIONS = [
  { value: 'father_name', label: '아버지 성함은?' },
  { value: 'mother_name', label: '어머니 성함은?' },
  { value: 'elementary_school', label: '졸업한 초등학교 이름은?' },
  { value: 'birthplace', label: '어릴 적 살던 고향은?' },
  { value: 'favorite_work', label: '가장 좋아하는 책·영화·작품은?' },
  { value: 'memorable_place', label: '가장 기억에 남는 장소는?' },
  { value: 'private_nickname', label: '나만 기억하는 별명은?' },
  { value: 'first_skill', label: '처음 재미있게 배운 기술이나 도구는?' },
  { value: 'childhood_dream', label: '어릴 때 꿈꾸었던 직업은?' },
  { value: 'recovery_keyword', label: 'PIN 복구를 위해 정한 나만의 단어는?' },
];

export function recoveryQuestionLabel(value) {
  return RECOVERY_QUESTIONS.find((item) => item.value === value)?.label
    || '저장된 PIN 복구 질문';
}
