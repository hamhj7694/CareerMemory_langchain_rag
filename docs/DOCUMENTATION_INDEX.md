# Career Memory 문서 체계

이 문서는 현재 개발에 사용하는 기준 문서와 각 문서의 책임을 정의한다.
같은 내용을 여러 문서에서 중복 관리하지 않는다.

## 1. 문서 우선순위

서로 다른 문서의 내용이 충돌하면 다음 순서를 따른다.

1. `PRD.md` — 제품 범위와 사용자 요구사항
2. `docs/v2/V2_API_CONTRACT.md` — 공개 API 계약
3. `AI_MEMORY_CONTEXT_POLICY.md` — 기억 범위와 데이터 공유 정책
4. `docs/AI_DATA_ARCHITECTURE.md` — 데이터 계층, 온톨로지, Evidence, 인덱스 원칙
5. `AI_Engine/AI_ENGINE_DEVELOPMENT_GUIDE.md` — AI 엔진 구현 원칙
6. `AI_Engine/AI_FRONTEND_CONTRACT_MAPPING.md` — AI DTO와 화면 계약의 변환 규칙
7. `AI_Engine/AI_ENGINE_WORK_MAP.md` — AI 작업 상태와 완료 조건
8. `docs/TODO.md` — 저장소 전체의 현재 작업과 장기 백로그

코드와 문서가 다르면 코드를 임의로 문서에 맞추지 않는다. 먼저 차이를 기록하고,
현재 제품 계약에 맞는 쪽을 확인한 다음 코드 또는 문서를 함께 수정한다.

## 2. 현재 사용하는 기준 문서

| 문서 | 단일 책임 | 갱신 시점 |
|---|---|---|
| `README.md` | 실행 방법과 저장소 입구 | 실행법·주요 기술 변경 |
| `PRD.md` | 제품 목표와 사용자 기능 | 제품 범위 변경 |
| `Data_Flow_Summary.md` | 사용자 입력부터 저장·검색까지의 전체 흐름 | 주요 데이터 흐름 변경 |
| `AI_MEMORY_CONTEXT_POLICY.md` | 세션 기억·장기 기억·사용자 격리 | 기억 범위 변경 |
| `docs/AI_DATA_ARCHITECTURE.md` | Bronze/Silver/Gold, 온톨로지, Evidence, 인덱스 | DB·데이터 구조 변경 |
| `docs/FILE_EXTRACTION_GUIDE.md` | 첨부 형식, OCR 실행 환경, 파서·처리 상태 | 파일 지원·OCR 정책 변경 |
| `AI_Engine/AI_ENGINE_DEVELOPMENT_GUIDE.md` | AI 역할, 검증, RAG, 구현 규칙 | AI 동작 원칙 변경 |
| `AI_Engine/AI_FRONTEND_CONTRACT_MAPPING.md` | AI 내부 DTO와 API·화면 DTO 매핑 | 필드·enum·오류 계약 변경 |
| `AI_Engine/AI_ENGINE_WORK_MAP.md` | AI 작업 ID, 상태, 완료 조건 | AI 작업 시작·완료 |
| `docs/TODO.md` | 현재 우선순위와 장기 백로그 | 작업 우선순위 변경 |
| `AI_ENGINE_CODING_COLLABORATION_GUIDE.md` | 구현·검증·인수인계 방식 | 협업 규칙 변경 |

## 3. 세부 계약과 결과 문서

- `docs/API_CONTRACT_WORKSPACE.md`: API 협의 중인 결정과 열린 질문
- `docs/v2/V2_API_CONTRACT.md`: V2 공개 API 계약
- `docs/api/`: 화면별 API 모델 상세
- `docs/FILE_EXTRACTION_GUIDE.md`: 파일 형식·OCR·파서 지원 및 운영 절차
- `docs/design/`: 디자인 기준과 레퍼런스
- `AI_Engine/benchmarks/RESULTS.md`: AI 품질·비용·시간 측정 결과
- `docs/reports/`: 완료된 작업의 보고와 회의 기록
- `docs/roadmap/FUTURE_UPDATES.md`: 장기 제품 기능과 온톨로지·데이터 인프라 발전 방향

`docs/reports/`와 포트폴리오 원본 자료는 현재 설계의 기준 문서가 아니라 기록물이다.

## 4. 문서 통합 결과

다음 문서는 중복과 노후화 때문에 더 이상 사용하지 않는다.

| 이전 문서 | 현재 위치 |
|---|---|
| `AI_Engine/작업 가이드.md` | `AI_ENGINE_DEVELOPMENT_GUIDE.md`, `AI_ENGINE_WORK_MAP.md` |
| `docs/DATA_SCHEMA_AUDIT.md` | `docs/AI_DATA_ARCHITECTURE.md` |
| `docs/DATA_SCHEMA_AUDIT_improvement.md` | `docs/AI_DATA_ARCHITECTURE.md` |
| `docs/WORK_BREAKDOWN.md` | `docs/TODO.md` |
| `docs/WORK_AGENT_MATRIX.md` | `docs/AGENT_MAP.md` |
| 임시 온톨로지·데이터 레이크 계획 TXT | `docs/AI_DATA_ARCHITECTURE.md`, `AI_ENGINE_WORK_MAP.md` |

## 5. 갱신 규칙

- 설계 원칙은 개발 가이드나 데이터 아키텍처 문서 한 곳에만 작성한다.
- 작업 상태는 `AI_ENGINE_WORK_MAP.md` 또는 `TODO.md`에서만 관리한다.
- 완료된 작업의 긴 설명은 `docs/reports/` 또는 벤치마크 결과로 옮긴다.
- 문서를 삭제하거나 이름을 바꾸면 저장소 전체에서 참조를 검색해 함께 수정한다.
- 테스트 개수 같은 시점 정보는 고정 규칙 문서보다 결과 문서에 기록한다.
- 구현 완료 표시는 관련 테스트와 계약 검증이 통과한 뒤에만 `[x]`로 변경한다.
