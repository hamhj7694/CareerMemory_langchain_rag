# FE-003 레이어 및 레이아웃 명세

## 1. 공통 셸

### 데스크톱: 1280px 이상

- `AppSidebar`: 240px 고정, 접힘 시 72px. 전체 화면 높이, 자체 스크롤.
- `Header`: 콘텐츠 상단 64px sticky, 현재 페이지/처리 상태/주요 행동 배치.
- `Main`: 남은 폭, `max-width: 1600px`, 중앙 정렬, 24px padding.
- 패널 사이 gutter 16px, 카드 내부 padding 20px.
- 페이지 전체 이중 스크롤을 피한다. Header 아래의 패널만 `height: calc(100dvh - 64px)`로 독립 스크롤한다.

### 태블릿: 768–1279px

- Sidebar는 72px 아이콘 레일. 1024px 미만에서는 overlay drawer.
- 3패널은 2패널로 축소: 목록 32%, 작업 영역 68%; 근거는 우측 360px drawer.
- Header는 64px, 보조 액션은 overflow 메뉴로 이동.

### 소형 화면: 360–767px

- 상단 56px Header + 하단 64px 주요 내비게이션(`경험`, `공고`).
- 한 번에 한 레이어만 표시한다. 목록→상세→근거는 push navigation 또는 full-screen sheet.
- 고정 하단 액션 바는 safe-area 포함 72px. 입력 중 키보드와 겹치지 않게 `dvh` 사용.
- V1은 모바일 완전 최적화를 약속하지 않는다. 360px 규칙은 핵심 정보 손실·불필요한 가로 스크롤·작업 차단을 피하기 위한 접근성 baseline이며, 모바일 전용 기능·제스처·고도화는 범위 밖이다.

## 2. 공통 정보 레이어

1. **탐색 레이어**: 사이드바, 경험 트리, 요구사항 목록.
2. **작업 레이어**: 입력·구조화 편집·공고 매칭·문서 작성.
3. **검증 레이어**: 원문, 인용, 부족한 정보, AI 상태.
4. **행동 레이어**: 저장·분석·생성 등 다음 단계. 데스크톱에서는 Header/패널 하단 sticky, 모바일에서는 하단 고정.

## 3. `/memory` — 경험 탐색·입력·검토·질문

### browse

- 비율: 경험 트리 `320px` / 상세 또는 시작 안내 `minmax(0, 1fr)`.
- 트리 상단: 검색, 새 경험 CTA. 영역/프로젝트 그룹 헤더 sticky.
- 상세 우선순위: 제목·기간·상태 → 요약 → 상황/행동/결과/역할 → 역량 → 근거.
- 트리와 미리보기는 각각 독립 스크롤한다. 키보드 focus·일시 미리보기는 로컬 상태로 유지하고, 경험을 활성화하면 정식 상세 라우트 `/memory/:experienceId`로 이동한다. `/memory` query에 선택 ID를 중복 저장하지 않는다.

### input

- `max-width: 960px`, 중앙 단일 컬럼.
- 상단 segmented control `텍스트 | 파일`; 두 방식을 한 번에 노출하지 않는다.
- 입력 카드 최소 높이 360px. 예시·글자 수는 입력 하단, 제출 CTA는 카드 하단 sticky가 아닌 자연 흐름.
- 처리 중에는 입력을 읽기 전용으로 보존하고 같은 위치에 진행 상태를 덮지 않는다. 상단 processing banner를 사용한다.

### review

- 비율: 구조 목차 `240px` / 편집 `minmax(560px, 1fr)` / 검증 `320px`.
- 목차: 영역→프로젝트→경험, 오류 개수와 dirty 표시. 클릭 시 해당 편집 섹션으로 스크롤.
- 편집: accordion이지만 한 프로젝트 안에서는 1개 이상 열림 유지. 경험별 필드는 `요약`, `상황·행동·결과·역할`, `사실`, `역량`, `맥락` 순.
- 검증 패널: `원문 근거`, `연결 후보`, `부족한 정보` 탭. 선택 필드에 대응하는 근거가 자동 강조된다.
- 하단 sticky action bar: 왼쪽 dirty/오류 요약, 오른쪽 `취소`, `확정 저장`.

### chat

- 비율: 대화 `minmax(560px, 62%)` / 관련 경험·근거 `minmax(320px, 38%)`.
- 대화 composer는 하단 sticky. 답변의 인용 번호 클릭 시 우측 패널 해당 근거로 이동.
- 우측은 `관련 경험`과 `원문 근거` 탭. 근거가 없으면 빈 패널이 아니라 경고와 질문 보완 예시를 표시.

## 4. `/memory/:experienceId` — 경험 상세

- 데스크톱: 본문 `minmax(600px, 2fr)` / 근거 `minmax(320px, 1fr)`.
- Header: breadcrumb, 제목, `수정`, `원문 보기`, `이 경험으로 질문`.
- 편집 진입 시 필드 단위 편집으로 바뀌며 하단 sticky 저장 바 표시.
- 원문은 우측 패널 기본, 1280px 미만 drawer, 모바일 full-screen sheet.
- 존재하지 않는 ID는 빈 상세 대신 404 상태와 `/memory` 복귀 CTA.

## 5. `/jobs` — 공고 입력

- `max-width: 960px`, 단일 컬럼.
- 회사/직무는 같은 행(각 50%), 공고 원문은 최소 420px로 둔다. `/jobs`는 요구사항 분석과 경험 비교 시작에 집중하며 자기소개서 문항은 받지 않는다.
- 제출 전 필수 오류는 공고 원문 바로 아래. 분석 중 입력은 보존하며 Header에 처리 상태 표시.
- 기존 분석 중인 공고가 있다면 우측 상단에 작은 resume card를 두되 입력을 가리지 않는다.

## 6. `/jobs/:jobId` — 요구사항·경험 매칭·생성 조건

- 기본 비율: 요구사항 rail `300px` / 결과 `minmax(560px, 1fr)` / 선택 tray `320px`.
- rail: 유형 필터 + 요구사항 목록. 그룹 헤더 sticky, 각 항목에 근거 상태 badge.
- 결과: 선택 요구사항 문장 → 판정과 이유 → 관련 경험 → 근거 → 부족 정보 순.
- tray: 선택 경험 0/2, 생성 문항, 글자 수, 문체. `자기소개서 생성`은 조건 충족 시 활성화.
- `경험과 대조하기` 전에는 결과/선택 tray 대신 단계 안내를 표시.
- 1279px 이하: rail + 결과 2패널, 선택 tray는 우측 drawer. 767px 이하: 요구사항 목록→상세→선택 sheet.

## 7. `/documents/:documentId` — 자기소개서 편집

- 비율: 편집기 `minmax(640px, 68%)` / 근거 패널 `minmax(320px, 32%)`.
- 편집기 상단: 문항, 글자 수 `현재/제한`, 문체. 본문은 읽기 폭 72ch 이내.
- 선택 텍스트가 있을 때만 floating AI toolbar(`짧게`, `구체적으로`, `자연스럽게`, `다시 작성`). 전체 적용은 상단 메뉴에서 별도 선택.
- AI 수정 결과는 원문 위에 덮지 않고 inline diff 또는 preview card로 표시하며 `적용`, `취소`, `다시 생성` 제공.
- 근거 패널: 사용 경험 → 사용 근거 → 부족 정보. 본문 인용 선택 시 대응 근거 강조.
- dirty 상태에서는 이탈 확인. 저장 정책이 확정되기 전 V1은 로컬 편집 상태와 1단계 undo를 보장.

## 8. Overlay와 z-index

- base 0, sticky 10, dropdown 30, drawer backdrop 40/drawer 50, modal backdrop 60/modal 70, toast 80.
- Modal은 파괴적 확인과 미저장 이탈에만 사용. 근거·상세는 drawer/sheet.
- Drawer 폭: desktop 420px, tablet 360px, mobile 100vw.

## 9. 화면 상태 배치

- `loading`: 실제 레이아웃과 같은 skeleton; 전체 화면 spinner 금지.
- `processing`: Header 상태 pill + 작업 영역 상단 진행 banner. 예상 시간을 약속하지 않는다.
- `empty`: 해당 패널 안에서 이유 1문장 + 다음 행동 1개.
- `error-validation`: 필드 인접 + 첫 오류로 focus 이동.
- `error-retryable`: 실패한 작업 영역 안에 입력 보존 안내와 retry.
- `saving`: 저장 CTA만 disabled, 읽기·스크롤 가능.
- `dirty`: Header/하단 bar에 점+`저장되지 않음` 텍스트.

## 10. 키보드·접근성

- DOM 순서: Header → 탐색 → 작업 → 검증. skip link 제공.
- 모든 drawer/modal은 focus trap, 닫은 뒤 trigger로 focus 복귀.
- 트리는 방향키 탐색과 `aria-expanded`; accordion은 button/region 관계를 갖는다.
- 최소 터치 영역 44×44px, focus ring 2px + 2px offset.
