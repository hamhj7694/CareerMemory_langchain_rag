# 작업 ↔ 에이전트 매핑

R=책임, A=최종 승인, C=협업, Q=검증, U=사용자(AI 엔진 담당)

| 작업 | Supervisor | Router | Planner | Designer | Frontend | API | QA | Schedule | 사용자 |
|---|---|---|---|---|---|---|---|---|---|
| FE-000 흐름·상태 | A | C | R | C | C | C | Q | C | C |
| FE-001 API/화면 모델 | A | C | C | - | C | R | Q | C | U |
| FE-002 Mock 계약 | A | C | C | C | C | R | Q | C | C |
| FE-003 UI 명세 | A | C | C | R | C | - | Q | C | C |
| FE-100 기반 도구 | A | C | - | - | R | C | Q | C | - |
| FE-110~120 Router/UI | A | C | C | R | R | C | Q | C | - |
| FE-130 API client | A | C | - | - | C | R | Q | C | C |
| FE-201~205 경험 UI | A | C | C | C | R | C | Q | C | C |
| FE-301~304 공고/자소서 | A | C | C | C | R | C | Q | C | C |
| INT-401~402 실API 통합 | A | C | - | - | C | R | Q | C | U |
| QA-410 전체 검증 | A | C | C | C | C | C | R | C | C |
| 우선순위·블로커 | A | C | C | C | C | C | C | R | C |

## 인수인계 최소 정보

- Planner → Designer/Frontend: 흐름, 상태, 완료 조건, PRD ID
- Designer → Frontend/QA: 와이어프레임, 토큰, 모든 UI 상태
- API → Frontend: DTO, fixture, 오류 규칙, 미확정 필드
- Frontend → QA: 변경 범위, 실행법, 테스트 데이터, 알려진 제한
- QA → Supervisor: 통과 여부, 결함, 증거, 회귀 범위
- Supervisor → Router: 승인·재검토·반려와 근거
- API → 사용자: 계약 차이, 영향, 선택이 필요한 해결안

