// Canonical frontend mock seed shared by every experience consumer.
export const initialExperiences = [
  {
    id: 'exp-platform-conversion', domain: '직장 경험', project: '커리어 플랫폼 개선', organization: 'ABC 테크',
    title: '지원 전환율 개선', summary: '지원 단계의 이탈 데이터를 분석하고 입력 흐름을 단순화해 지원 완료율을 높였습니다.',
    period: '2024.03 – 2024.08', role: '서비스 기획', skills: ['데이터 분석', 'UX 기획', 'A/B 테스트'], evidenceCount: 3,
    status: 'confirmed', updatedAt: '2026-07-20', situation: '지원서 작성 단계에서 이탈률이 높았습니다.',
    actions: ['단계별 퍼널을 분석했습니다.', '필수 입력 항목을 재정의했습니다.', '두 가지 흐름을 A/B 테스트했습니다.'],
    results: ['지원 완료율을 18% 개선했습니다.'], facts: ['지원 완료율 18% 향상', 'A/B 테스트 2회 수행'], missing: [],
  },
  {
    id: 'exp-dashboard', domain: '직장 경험', project: '운영 대시보드 구축', organization: 'ABC 테크',
    title: '운영 지표 대시보드 기획', summary: '흩어진 운영 지표를 하나의 대시보드로 통합해 주간 보고 시간을 단축했습니다.',
    period: '2023.09 – 2024.02', role: '프로덕트 매니저', skills: ['요구사항 정의', '데이터 시각화'], evidenceCount: 2,
    status: 'needs_review', updatedAt: '2026-07-18', situation: '운영팀이 여러 문서에서 지표를 수작업 취합했습니다.',
    actions: ['사용자 인터뷰로 핵심 지표를 정의했습니다.', '개발팀과 데이터 정의서를 작성했습니다.'],
    results: ['주간 보고 준비 시간을 줄였습니다.'], facts: ['핵심 운영 지표 12개 정의'], missing: ['단축된 시간을 수치로 확인해 주세요.'],
  },
  {
    id: 'exp-launch', domain: '사이드 프로젝트', project: '커뮤니티 앱 출시', organization: '팀 모먼트',
    title: '신규 커뮤니티 MVP 출시', summary: '사용자 문제를 검증하고 핵심 기능을 좁혀 8주 안에 MVP를 출시했습니다.',
    period: '2023.01 – 2023.03', role: '팀 리드', skills: ['프로젝트 관리', '사용자 조사', '우선순위'], evidenceCount: 4,
    status: 'confirmed', updatedAt: '2026-07-12', situation: '아이디어는 있었지만 대상 사용자와 핵심 문제가 불명확했습니다.',
    actions: ['잠재 사용자 15명을 인터뷰했습니다.', '기능 우선순위를 정하고 스프린트를 운영했습니다.'],
    results: ['8주 내 MVP를 출시했습니다.'], facts: ['사용자 인터뷰 15명', '8주 내 MVP 출시'], missing: [],
  },
  {
    id: 'exp-study', domain: '교육·학습', project: '데이터 분석 과정', organization: '온라인 부트캠프',
    title: '고객 이탈 예측 프로젝트', summary: '고객 행동 데이터를 정제하고 이탈 가능성을 설명하는 분석 리포트를 만들었습니다.',
    period: '2022.09 – 2022.11', role: '분석 담당', skills: ['Python', '데이터 분석'], evidenceCount: 0,
    status: 'needs_review', updatedAt: '2026-07-08', situation: '구독 서비스의 고객 이탈 원인을 분석하는 과제였습니다.',
    actions: ['데이터를 정제하고 주요 변수를 비교했습니다.'], results: ['분석 리포트를 발표했습니다.'], facts: [], missing: ['원본 보고서를 연결해 주세요.', '모델 성능을 확인해 주세요.'],
  },
  {
    id: 'exp-mentor', domain: '대외 활동', project: '청년 진로 멘토링', organization: '커리어 브릿지',
    title: '진로 멘토링 프로그램 운영', summary: '참여자 피드백을 반영해 멘토링 운영 방식을 개선했습니다.',
    period: '2022.03 – 2022.08', role: '운영 리더', skills: ['커뮤니케이션', '운영 개선'], evidenceCount: 1,
    status: 'confirmed', updatedAt: '2026-06-29', situation: '회차별 참여율 편차가 컸습니다.', actions: ['설문을 분석하고 리마인드 방식을 변경했습니다.'],
    results: ['후반부 참여율이 안정화되었습니다.'], facts: ['총 6회 프로그램 운영'], missing: [],
  },
];

export const statusLabel = { confirmed: '확정', needs_review: '확인 필요' };
