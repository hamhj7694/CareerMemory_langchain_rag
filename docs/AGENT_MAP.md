# 에이전트 매핑

| 에이전트 | 소유 영역 | 주요 입력 | 주요 산출물 | 하지 않는 일 |
|---|---|---|---|---|
| Supervisor | 독립 감독·최종 검토 | PRD, 산출물, 검증 증거 | 승인·반려, 사용자 요약 | 직접 구현·작업 배정 |
| AgentRouter | 요청 분류·오케스트레이션 | PRD, TODO, 사용자 요청 | 작업 배정, 인수인계 | 직접 기능 소유 |
| Planner | 제품·UX 기획 | PRD 기능 ID | 흐름, 상태, 완료 조건 | AI 로직 설계 |
| Designer | 레퍼런스·UI·스타일 설계 | 기획 흐름, 데이터 상태, 최신 사례 | 리서치, 레이어 배치, 톤앤매너, 토큰 | 제품 범위·AI 로직 결정 |
| Frontend | React 프론트엔드 | 기획, API 계약 | 화면, 컴포넌트, 테스트 | AI 엔진 구현 |
| API Integration | FE/AI 경계 | PRD 7장, 서버 응답 | DTO, Mock, 어댑터, 계약 이슈 | 서버 내부 구현 |
| QA | 품질 게이트 | 완료 조건, 빌드 | 테스트 결과, 결함 | 범위 임의 변경 |
| Schedule Manager | 순서·진척·블로커 | WBS, TODO | Phase 상태, 다음 작업 | 구현 품질 승인 |

## 협업 흐름

`사용자 → Supervisor → Router → Planner/Designer → Frontend/API Integration → QA → Supervisor 승인`

Schedule Manager는 전 과정의 상태와 블로커를 갱신한다. 교차 결정이 필요하면 관련 에이전트만 회의한다.

AI 엔진 관련 결정은 `API Integration → 사용자`로 전달하고 확정 내용을 다시 Frontend와 QA에 배포한다.

## 파일 위치

- 라우터: `agents/AgentRouter.md`
- 전문 에이전트: `agents/*_agent.md`
- 작업 기준: `docs/WORK_BREAKDOWN.md`
- 실행 목록: `docs/TODO.md`
- 책임 매핑: `docs/WORK_AGENT_MATRIX.md`
- API 협업: `docs/API_CONTRACT_WORKSPACE.md`
- 회의 규칙: `docs/MEETING_PROTOCOL.md`
- 사용자 보고: `docs/reports/`
- 디자인 산출물: `docs/design/`
