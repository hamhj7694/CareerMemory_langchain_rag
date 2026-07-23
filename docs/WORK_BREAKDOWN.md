# 프론트엔드 작업 분해 구조(WBS)

## 범위 원칙

프론트엔드와 통합 경계만 포함한다. AI-I/P/L/S/R/C/J/M/W 구현, DB, 임베딩, RAG 평가는 사용자 소유다.

## Phase 0 — 계약과 기획

| ID | 작업 | 선행 | 완료 조건 |
|---|---|---|---|
| FE-000 | V1 화면 흐름·상태 확정 | 없음 | 주요 정상/예외 흐름과 PRD ID 연결 |
| FE-001 | API DTO와 화면 모델 정의 | FE-000 | 12개 endpoint의 요청/응답/오류 가정 기록 |
| FE-002 | Mock fixture 계약 정의 | FE-001 | Mock과 실API가 같은 어댑터 경로 사용 |
| FE-003 | 레퍼런스·정보 구조·레이어·톤앤매너·와이어프레임 | FE-000 | 출처가 있는 리서치와 주요 화면의 구현 가능 디자인 명세 |

## Phase 1 — 기반 구조

| ID | 작업 | 선행 | 완료 조건 |
|---|---|---|---|
| FE-100 | Vite React 프로젝트/품질 도구 | FE-000 | dev, build, lint, test 실행 가능 |
| FE-110 | Router와 AppLayout | FE-100 | 최소 `/memory`, `/jobs`, `/jobs/:jobId` 동작 |
| FE-120 | 디자인 토큰·공통 UI | FE-003, FE-100 | Loading/Error/Empty/Modal/Tag 재사용 가능 |
| FE-130 | API client와 Mock 스위치 | FE-001, FE-100 | 환경변수로 Mock/실API 전환 |

## Phase 2 — 경험 메모리 핵심

| ID | PRD | 작업 | 선행 |
|---|---|---|---|
| FE-201 | M01~M02 | 텍스트 입력·파일 업로드 | FE-120, FE-130 |
| FE-202 | M03~M05 | 구조화 결과 계층·편집·연결 선택 | FE-201 |
| FE-203 | M06 | 경험 저장과 성공/실패 처리 | FE-202 |
| FE-204 | M07~M09 | 경험 트리·상세·원본 보기 | FE-120, FE-130 |
| FE-205 | M10~M11 | 경험 질문·근거 기반 답변 UI | FE-204 |

## Phase 3 — 공고와 자기소개서

| ID | PRD | 작업 | 선행 |
|---|---|---|---|
| FE-301 | J01~J02 | 공고 입력·요구사항 카드 | FE-120, FE-130 |
| FE-302 | J03~J04 | 경험 대조·판정·경험 선택 | FE-204, FE-301 |
| FE-303 | C01~C03 | 경험 선택·조건 입력·생성 요청 | FE-302 |
| FE-304 | C04 | 결과·근거·직접 편집·수정 요청 | FE-303 |

## Phase 4 — 통합과 출시 점검

| ID | 작업 | 선행 | 완료 조건 |
|---|---|---|---|
| INT-401 | 입력/경험 API 통합 | FE-203, 사용자 API | text/file/commit/tree/detail/source smoke 통과 |
| INT-402 | RAG/공고/자소서 API 통합 | FE-205, FE-304, 사용자 API | chat/job/match/generate/revise smoke 통과 |
| QA-410 | 전체 시연 회귀·접근성 점검 | INT-401, INT-402 | Blocker/Major 0건, PRD 5.13 통과 |

## 권장 병렬화

- Phase 1에서 `FE-110`, `FE-120`, `FE-130`은 계약만 확정되면 병렬 가능하다.
- Phase 2의 `FE-204`는 fixture가 있으면 입력/편집 흐름과 병렬 가능하다.
- Phase 3의 공고 UI와 자기소개서 화면 골격은 계약 fixture 기준으로 일부 병렬 가능하다.
- 사용자 AI 엔진은 전 Phase와 병렬 개발하며, 통합 전 계약 동결 시점만 맞춘다.
