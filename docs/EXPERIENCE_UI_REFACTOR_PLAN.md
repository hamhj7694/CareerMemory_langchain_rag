# 경험 상세·미리보기·카드 단방향 리팩터링 설계

작성일: 2026-07-24  
대상: 프론트엔드 목데이터 환경

## 1. 목표

경험 상세 데이터를 유일한 원본으로 사용하고, 미리보기와 경험 관리 카드는 같은 `Experience`에서 필요한 필드만 선택해 표시한다.

```text
Experience 원본
├─ ExperiencePreviewModel  → 미리보기
└─ ExperienceCardModel     → 경험 관리 카드
```

미리보기와 카드는 데이터를 별도로 저장하지 않는다. 경험 상세가 수정되면 두 화면도 즉시 같은 내용으로 갱신되어야 한다.

## 2. 현재 문제

### 2.1 편집 경로가 분리되어 있음

- 분류·프로젝트 이동/삭제는 `pendingOps`에 쌓인 뒤 일괄 저장된다.
- `ExperienceForm`에서 경험을 수정하면 API에 즉시 저장된다.
- 경험 상세 페이지는 `unifiedMockApi`를 통해 별도로 저장한다.
- 분류·프로젝트 이름 변경은 `window.prompt`를 사용한다.
- 신규 분류·프로젝트는 인라인 임시 상태를 사용한다.

이 때문에 구조 편집을 취소해도 이미 저장된 경험 내용은 되돌아가지 않을 수 있다.

### 2.2 같은 경험을 서로 다른 모양으로 변환함

- 경험 관리: `normalizeExperience()`
- 경험 상세: `unifiedMockApi.toExperience()`
- 채팅 제안: proposal payload를 직접 사용
- 채용공고 매칭: 다시 `toExperience()`로 변환

변환 함수마다 필드 기본값과 이름이 달라질 수 있다.

### 2.3 간이 입력 폼과 상세 스키마가 다름

현재 경험 관리의 `ExperienceForm`은 다음 일부 필드만 다룬다.

- 제목
- 요약
- 역할
- 역량
- 경험 분류
- 프로젝트·활동

하지만 상세 경험에는 상황, 행동, 결과, 확인된 사실, 원본 근거 등도 존재한다. 따라서 간이 폼에서 만든 경험은 처음부터 불완전한 상세 데이터가 된다.

## 3. 기준 데이터 모델

프론트엔드에서 사용할 정규형은 하나로 통일한다.

```ts
type Experience = {
  id: string;
  version: number;
  status: 'draft' | 'confirmed';

  domainId: string;
  projectId: string;
  domainName: string;
  projectName: string;
  organization: string;

  title: string;
  summary: string;
  role: string;
  situation: string;
  actions: string[];
  results: string[];
  skills: string[];
  facts: string[];
  missingInformation: string[];

  evidenceIds: string[];
  createdAt: string;
  updatedAt: string;
};
```

API의 snake_case 응답은 데이터 접근 계층에서 한 번만 위 구조로 변환한다.

## 4. 화면별 책임

### 4.1 경험 상세

유일한 경험 내용 편집 화면이다.

- 모든 상세 필드 조회
- 경험 내용 수정
- 경험 분류와 프로젝트·활동 지정
- 원본 근거 연결 관리
- 변경 저장 및 취소

신규 경험도 빈 상세 편집 화면에서 시작한다.

권장 경로:

- 신규: `/memory/new?domainId=...&projectId=...`
- 기존: `/memory/:experienceId`

### 4.2 미리보기

읽기 전용 파생 UI다.

표시 필드:

- `title`
- `projectName`
- `summary`
- `skills`

가능한 행동:

- 닫기
- 상세 보기

미리보기 내부에는 수정·저장 로직을 두지 않는다.

### 4.3 경험 관리 카드

읽기 전용 파생 UI다.

표시 필드:

- `title`
- `skills` 중 앞의 1~2개

카드 클릭 시 같은 `Experience.id`로 미리보기를 연다.

### 4.4 경험 관리의 편집 모드

콘텐츠가 아니라 구조만 편집한다.

- 경험 분류 추가·이름 변경·삭제·순서 변경
- 프로젝트·활동 추가·이름 변경·삭제·순서 변경
- 경험 카드의 프로젝트 이동·순서 변경

다음 기능은 경험 관리 편집 모드에서 제거한다.

- 경험 상세 내용 수정 폼
- 제목·요약·역할·역량 직접 수정
- 경험 API 즉시 저장

`+ 경험 추가`는 상세 신규 작성 화면으로 이동시키는 탐색 동작으로 변경한다.

## 5. 파생 모델

파생 모델은 저장하지 않고 selector 함수로 생성한다.

```js
export function selectExperiencePreview(experience) {
  return {
    id: experience.id,
    title: experience.title,
    projectName: experience.projectName,
    summary: experience.summary,
    skills: experience.skills,
  };
}

export function selectExperienceCard(experience) {
  return {
    id: experience.id,
    title: experience.title,
    skills: experience.skills.slice(0, 2),
  };
}
```

금지 사항:

- 카드용 제목 복사본 저장
- 미리보기용 요약 복사본 저장
- 화면 컴포넌트에서 snake_case 직접 처리
- 근거 수를 별도 상태로 중복 저장

## 6. 상태와 저장 구조

### 6.1 조회 상태

경험 목록과 선택된 경험은 같은 저장소의 객체를 참조한다.

```text
experienceById
experienceIds
selectedExperienceId
```

`selectedExperience` 객체를 별도로 복사해 보관하지 않고 `selectedExperienceId`로 조회한다. 그래야 상세 저장 후 미리보기가 오래된 객체를 표시하지 않는다.

### 6.2 구조 편집 상태

```ts
type StructureEditSession = {
  original: ExperienceStructure;
  draft: ExperienceStructure;
  operations: StructureOperation[];
  dirty: boolean;
};
```

구조 편집 중에는 `draft`만 변경한다.

- 저장: operations 일괄 반영 후 목록 재조회
- 취소: draft 폐기
- 페이지 이탈: 저장되지 않은 변경 확인

### 6.3 상세 편집 상태

상세 페이지 안에서만 별도 form draft를 사용한다.

- 저장 전에는 원본 `Experience`를 변경하지 않는다.
- 저장 성공 후 캐시의 해당 `Experience.id`를 교체한다.
- 미리보기와 카드가 자동 갱신된다.

## 7. 컴포넌트 재구성

권장 구조:

```text
src/features/experience/
├─ model/
│  ├─ experienceSchema.js
│  ├─ experienceMapper.js
│  └─ experienceSelectors.js
├─ api/
│  └─ experienceRepository.js
├─ detail/
│  ├─ ExperienceDetailPage.jsx
│  └─ ExperienceDetailForm.jsx
├─ preview/
│  └─ ExperiencePreview.jsx
└─ manager/
   ├─ ExperienceManagerPage.jsx
   ├─ ExperienceStructureEditor.jsx
   ├─ DomainSection.jsx
   ├─ ProjectRow.jsx
   └─ ExperienceCard.jsx
```

현재 `ExperienceManagerV3.jsx`가 담당하는 폼, 구조 편집, 미리보기, 자산 모달을 단계적으로 분리한다.

## 8. API 및 목데이터 개선

`v2ChatApi`를 화면에서 직접 호출하지 않고 repository를 통과시킨다.

```js
experienceRepository.list()
experienceRepository.get(id)
experienceRepository.create(draft)
experienceRepository.update(id, version, changes)
experienceRepository.move(id, projectId)
```

repository가 담당할 내용:

- snake_case ↔ camelCase 변환
- 누락 배열 기본값 보정
- domain/project 참조 정규화
- 저장 후 캐시 갱신
- 목 API와 향후 실제 API의 차이 격리

목데이터의 `Experience`도 상세 필드를 항상 포함해야 한다. 빈 값이어도 필드를 생략하지 않는다.

## 9. 신규 경험 흐름

```text
경험 관리에서 + 경험 추가
→ 빈 상세 편집 페이지
→ 분류 및 프로젝트 선택
→ 상세 내용 작성
→ 저장 확인
→ Experience 생성
→ 경험 관리로 복귀
→ 신규 카드 표시
→ 카드 클릭 시 미리보기 표시
```

AI가 생성한 경험도 동일하다.

```text
채팅/파일/AI 제안
→ ExperienceDraft 생성
→ 상세 편집 화면에서 사용자 검토
→ confirmed 저장
→ 카드와 미리보기 자동 생성
```

AI 응답 자체가 카드 데이터를 직접 만들면 안 된다.

## 10. 구현 단계

### 단계 1 — 정규 모델과 mapper

- `Experience` 정규형 확정
- API 변환 함수를 한 곳으로 통합
- 기존 목데이터 누락 필드 보정
- selector 단위 테스트 작성

완료 기준: 모든 페이지가 같은 ID의 경험에 대해 동일한 제목·요약·역량을 반환한다.

### 단계 2 — 상세 화면을 원본 편집기로 확정

- 신규/수정 모드 통합
- 분류·프로젝트 선택 포함
- 전체 상세 필드 저장
- 저장·취소·이탈 확인

완료 기준: 경험 생성과 내용 수정은 상세 화면에서만 가능하다.

### 단계 3 — 미리보기 파생 UI 전환

- `selected` 객체 대신 `selectedExperienceId` 사용
- selector로 표시 데이터 생성
- 수정 버튼과 내부 저장 로직 제거

완료 기준: 상세 저장 직후 다시 목록을 열지 않아도 미리보기가 갱신된다.

### 단계 4 — 카드 파생 UI 전환

- 카드 selector 적용
- 카드의 콘텐츠 수정 기능 제거
- 클릭은 미리보기 열기만 수행

완료 기준: 카드와 미리보기에 중복 저장 필드가 없다.

### 단계 5 — 구조 편집 세션 정리

- `ExperienceForm` 제거
- 분류·프로젝트 입력 방식을 모두 인라인으로 통일
- 구조 변경은 draft에만 반영
- 저장·취소를 단일 하단 바에서 수행
- 카드 이동과 순서 변경만 허용

완료 기준: 구조 편집 취소 시 화면과 목데이터가 모두 원래 상태다.

### 단계 6 — 다른 페이지 연결 점검

- 채팅 제안 → ExperienceDraft
- 경험 근거 → evidenceIds
- 내 역량 → Experience.skills 집계
- 채용공고 분석 → Experience.id 참조

완료 기준: 어느 페이지에서 경험을 열어도 동일한 상세 데이터를 조회한다.

## 11. 테스트 시나리오

1. 상세에서 제목을 수정하면 미리보기와 카드가 모두 변경된다.
2. 상세에서 역량을 수정하면 카드, 미리보기, 내 역량 집계가 모두 변경된다.
3. 구조 편집에서 카드를 이동한 뒤 취소하면 원래 프로젝트로 돌아간다.
4. 구조 편집에서 카드를 이동한 뒤 저장하면 상세의 `projectId/projectName`도 변경된다.
5. 신규 경험을 상세에서 저장하기 전에는 목록에 카드가 생기지 않는다.
6. AI 초안을 취소하면 확정 경험 목록에 추가되지 않는다.
7. 근거 연결을 해제하면 상세와 근거 관리 화면이 같은 결과를 표시한다.
8. 삭제된 분류·프로젝트에 경험 참조가 남지 않는다.

## 12. 우선 제거할 현재 코드

리팩터링 과정에서 다음을 제거하거나 대체한다.

- `ExperienceManagerV3.jsx` 내부 `ExperienceForm`
- `saveExperience()`의 즉시 API 저장
- `selected`에 경험 객체 복사 보관
- 분류·프로젝트 이름 변경용 `window.prompt`
- 화면별 `normalizeExperience()` 중복 구현
- 화면에서 직접 만드는 카드·미리보기용 기본 데이터

## 13. 권장 작업 순서

구조 편집 코드를 먼저 고치면 다시 상세 데이터와 충돌할 가능성이 크다. 따라서 다음 순서를 지킨다.

1. Experience 정규 모델
2. 상세 생성·수정 화면
3. 미리보기 selector
4. 카드 selector
5. 구조 편집 세션
6. 채팅·근거·역량·공고 분석 연결

이 순서라면 상세 원본이 먼저 안정되고 나머지 화면을 안전하게 파생시킬 수 있다.
