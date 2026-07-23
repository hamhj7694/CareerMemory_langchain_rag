# Career Memory V2 제품 요구사항

- 상태: Draft for implementation
- 기준일: 2026-07-22
- 제품 방향: Chat-first Career Memory Workspace
- 우선순위: 이 문서는 V2 구현에서 V1 문서보다 우선한다.

## 1. 제품 정의

Career Memory V2는 사용자가 챗봇과 대화하면서 경력 자료를 쌓고, 활용하고, 검증하는 개인 커리어 작업공간이다.

사용자는 별도의 기능을 먼저 고르지 않아도 채팅 입력창에서 다음을 할 수 있다.

- 정리되지 않은 경험을 자유롭게 적기
- PDF/TXT 파일 여러 개 첨부하기
- 저장된 경험에 관해 질문하거나 조언 구하기
- 채용공고 원문을 붙여 넣고 내 경험과 비교하기
- 대화를 통해 빠진 수치, 역할, 맥락을 보완하기

LLM은 대화와 첨부 자료를 근거로 경험 후보를 구조화한다. 구조화 결과는 곧바로 확정 데이터가 되지 않으며, 사용자가 검토·수정·승인한 뒤 경험 메모리에 반영된다. 경험 관리 화면은 이렇게 쌓인 기억을 검색하고 수정·삭제하며 관계와 근거를 한눈에 확인하는 보조 작업공간이다.

## 2. 제품 원칙

1. **Chat first**: 기본 진입점과 핵심 인터페이스는 챗봇이다.
2. **한 입력창, 다양한 의도**: 경험·파일·질문·조언·공고를 같은 composer에서 다룬다.
3. **대화가 구조를 만든다**: LLM이 필요한 정보를 후속 질문하고, 대화 전체에서 초안을 갱신한다.
4. **사용자 승인 우선**: AI 제안은 승인 전까지 draft이며 경험 메모리에 자동 확정하지 않는다.
5. **근거 추적**: 저장한 사실은 대화 메시지, 텍스트 원문, 파일과 연결된다.
6. **불확실성 공개**: 추론, 확인 필요, 근거 없음 상태를 확정 사실처럼 표현하지 않는다.
7. **관리 화면은 활용을 돕는다**: 경험 관리는 챗봇을 대체하지 않고 데이터를 보고 고치는 구조화 뷰다.
8. **입력 보존**: 오류가 발생해도 메시지, 첨부, draft 편집 내용을 잃지 않는다.

## 3. 목표 사용자와 핵심 상황

### P1 취업 준비생

- 흩어진 과제·인턴·동아리 경험을 말로 풀어 정리한다.
- 공고가 요구하는 역량과 실제 근거를 비교한다.
- 어떤 경험을 더 구체화해야 하는지 조언받는다.

### P2 이직 준비자

- 과거 프로젝트 문서와 기억을 누적한다.
- 성과, 역할, 의사결정 근거를 빠르게 회상한다.
- 특정 직무·공고에 적합한 경험을 찾는다.

### P3 직무 전환자

- 기존 경험을 새로운 직무 관점에서 해석하되 과장하지 않는다.
- 전이 가능한 역량과 부족한 근거를 구분한다.

## 4. 사용자 가치와 성공 기준

### 핵심 가치

- 사용자는 어디에 입력해야 할지 고민하지 않고 대화를 시작할 수 있다.
- 대화 결과가 재사용 가능한 경험 데이터로 축적된다.
- AI 답변과 공고 비교 결과에서 근거 경험으로 이동할 수 있다.
- 경험 전체를 관리 화면에서 빠르게 확인하고 직접 통제할 수 있다.

### V2 제품 지표 후보

- 첫 세션에서 첫 메시지 전송 완료율
- 구조화 draft 생성 후 승인 완료율
- 승인된 경험 중 원본 근거 연결 비율
- 경험 질문 답변에서 근거 열람 비율
- 공고 분석 후 관련 경험 열람·보완 비율
- draft 이탈 및 분석 실패 후 복구율

지표 수집 구현과 개인정보 정책은 별도 승인 전까지 범위에 포함하지 않는다.

## 5. 정보 구조와 라우트

### 전역 내비게이션

1. `챗봇` — 메인
2. `경험 관리` — 구조화 데이터 조회·편집
3. `채용공고` — 저장된 분석 목록과 상세
4. `설정` — V2 후속 범위

### 라우트

| Route | 목적 |
|---|---|
| `/` | `/chat`으로 이동 |
| `/chat` | 새 대화 또는 최근 대화의 chat-first workspace |
| `/chat/:conversationId` | 특정 대화 복원·계속하기 |
| `/memory` | 경험 전체 목록·검색·필터·시각적 구조 확인 |
| `/memory/:experienceId` | 경험 상세·수정·삭제·근거 관리 |
| `/jobs` | 분석한 채용공고 목록과 새 분석 진입 |
| `/jobs/:jobId` | 공고 요구사항과 경험 비교 결과 |

자기소개서 작성은 V2 핵심 흐름에서 제외한다. 향후 공고 상세 또는 채팅의 후속 액션으로 별도 모듈화할 수 있다.

## 6. 핵심 화면

### 6.1 Chat Workspace

필수 영역:

- 대화 목록/새 대화
- 메시지 타임라인
- 답변의 인라인 근거 및 관련 경험 카드
- 구조화 draft side panel 또는 drawer
- 다중 파일 첨부가 가능한 composer
- 빠른 시작 예시: 경험 정리, 내 경험 질문, 조언, 공고 분석

Composer는 텍스트와 파일을 동시에 보낼 수 있어야 한다. 사용자가 의도를 명시하지 않아도 엔진의 분류 결과를 UI가 표시하고, 애매하면 챗봇이 확인 질문을 한다.

### 6.2 Experience Library

- 전체 경험 검색
- 영역, 프로젝트, 역량, 근거 상태, 보완 필요 여부 필터
- 카드/목록 보기
- 카드에 제목, 프로젝트, 요약, 역량, 근거 수, 최종 수정일, 보완 상태 표시
- 경험 수정·삭제·복수 선택
- 프로젝트/영역 단위 그룹 보기
- 선택한 경험의 관계를 도형화한 구조 뷰

“도형화”의 V2 정의는 자유 배치 그래프가 아니라, 사용자가 이해하고 수정하기 쉬운 `영역 → 프로젝트 → 경험 → 사실/근거` 관계 뷰다. 화면 크기에 따라 tree, grouped cards, detail panel로 표현하며 임의의 canvas 편집은 제외한다.

### 6.3 Experience Detail

- 요약, 상황, 행동, 결과, 역할, 사실, 역량
- 확인 필요·부족한 정보
- 연결 프로젝트와 영역
- 원본 근거 목록
- 편집, 저장, 삭제
- “챗봇에서 이 경험 열기”

### 6.4 Job Analysis

- 채팅에 붙여 넣은 공고를 감지하고 분석 제안
- 회사/직무/원문 확인
- 요구사항별 관련 경험과 직접·부분·간접·근거 없음 상태
- 근거 문장과 원본 연결
- 부족한 경험 정보와 보완 질문
- 챗봇에서 후속 조언 받기

## 7. 기능 범위

### Must — V2 Frontend

- V2 내비게이션과 `/chat` 기본 진입
- 대화 생성·목록·복원 UI
- 사용자/assistant/system 상태 메시지
- 텍스트 및 다중 PDF/TXT 첨부 composer
- 첨부 목록, 개별/전체 제거, 업로드/처리 상태
- 답변 스트리밍 또는 단계별 processing 표시를 수용하는 UI
- 답변의 관련 경험·근거·공고 카드
- 구조화 draft 생성·실시간 갱신·검토·수정·승인·폐기 UI
- 승인 전후 상태 구분
- 경험 library 검색·필터·정렬·카드/목록
- 경험 상세 CRUD와 원본 근거 관리
- 공고 목록·상세·경험 비교
- empty/loading/processing/partial/error/offline/dirty/conflict 상태
- Mock/real API adapter 경계
- 반응형 및 키보드 접근성

### Should

- 대화 제목 변경·보관
- draft 변경점 비교
- 관련 경험을 답변 옆에서 빠르게 열기
- 경험 보완 질문을 채팅으로 전달
- 마지막 실패 메시지만 재시도

### Out of scope

- LLM 프롬프트·intent classifier·RAG·embedding 구현
- PDF/TXT 본문 추출과 저장
- SQLite/Chroma 처리
- 인증·다중 사용자·공유
- 음성 입력
- 외부 채용공고 자동 수집
- 자동 지원·합격 확률
- 자유 배치 그래프 편집
- 자기소개서 생성/편집 V2 재구현
- 공고 여러 개 비교(roadmap 유지)

## 8. 프론트엔드와 AI 엔진 책임 경계

### Codex/Frontend

- 화면, 라우팅, 접근성, 반응형
- 사용자 입력과 첨부 선택·클라이언트 검증
- API 호출·취소·재시도·상태 표현
- wire DTO를 화면 모델로 변환
- draft 편집·승인 요청 UI
- 근거 링크·경고·불확실성 표현
- Mock fixtures와 계약 테스트

### 사용자/AI Engine

- 대화 세션 저장 및 메시지 처리
- 의도 분류와 확인 질문 결정
- LLM 호출, tool orchestration, RAG
- 문서 추출·청킹·embedding
- 경험 draft 생성·병합·충돌 판단
- 공고 요구사항 추출·경험 매칭
- 원본/대화/경험/공고 DB 처리
- 스트리밍·작업 상태 API 제공

프론트엔드는 AI 판단을 재현하거나 임의로 사실을 생성하지 않는다.

## 9. 핵심 도메인 상태

### Conversation

`new | active | processing | failed | archived`

### Message

`draft | uploading | queued | streaming | complete | partial | failed | cancelled`

### Structured Draft

`none | extracting | needs_input | ready | user_editing | approving | approved | rejected | conflicted | failed`

### Experience

`confirmed | needs_review | hidden | deleted`

### Evidence

`available | processing | unavailable | deleted`

AI draft, 사용자가 승인한 사실, 원본 근거는 색상뿐 아니라 라벨과 문구로도 구분한다.

## 10. 데이터 및 API 요구사항(프론트엔드 관점)

V2 구현 전 AI 엔진과 다음 리소스 계약을 확정한다.

- conversations: 생성, 목록, 상세, 제목 변경, 보관
- messages: 전송, 취소, 재시도, 스트리밍/상태 조회
- attachments: 다중 업로드, 상태, 다운로드, 삭제
- drafts: 조회, 부분 수정, 승인, 폐기, version conflict
- experiences: 목록, 상세, 수정, 삭제
- sources/evidence: 조회, 텍스트 수정, 다운로드, 삭제
- jobs: 목록, 상세, 분석 및 경험 비교

필수 공통 필드:

- opaque ID
- ISO 8601 timestamp
- `client_request_id`
- resource `version`
- 공통 오류 envelope와 `retryable`
- 부분 성공 시 item별 실패 사유
- 메시지와 draft에서 `source_refs`, `experience_refs`, `job_refs`

파일 기본 클라이언트 제한은 PDF/TXT 최대 5개, 파일당 25MiB, 요청 전체 100MiB다. 서버 정책이 더 엄격하면 서버 값을 우선하고 UI에 명시한다.

## 11. 비기능 요구사항

- 데스크톱 우선이되 390px 이상에서 핵심 채팅·승인 흐름 사용 가능
- 키보드로 메시지 작성, 첨부 제거, draft 검토 가능
- focus visible, semantic label, 상태 변화 aria-live 적용
- 긴 한글 문장은 단어 중간에서 부자연스럽게 깨지지 않도록 처리
- 실패 후 입력·첨부·편집 draft 보존
- 중복 제출 방지와 취소 가능한 요청 구분
- 대화가 길어져도 composer 접근성을 유지
- 서버 원문을 신뢰해 HTML로 직접 삽입하지 않음

## 12. Acceptance Criteria

- AC-V2-01: `/` 진입 시 핵심 화면인 `/chat`이 열린다.
- AC-V2-02: 사용자는 한 composer에서 텍스트와 최대 5개 파일을 함께 보낼 수 있다.
- AC-V2-03: 경험 입력, 일반 질문, 조언, 공고 입력이 대화 타임라인 안에서 처리된다.
- AC-V2-04: 의도가 불명확할 때 확인 질문이 표시되고 입력 내용은 보존된다.
- AC-V2-05: 경험 구조화 결과는 `draft`로 표시되며 명시적 승인 전 library에 확정 반영되지 않는다.
- AC-V2-06: 사용자는 draft의 핵심 필드를 수정·승인·폐기할 수 있다.
- AC-V2-07: 승인된 사실에서 대화 메시지 또는 파일 근거를 열 수 있다.
- AC-V2-08: 경험 library에서 검색·필터·상세·수정·삭제가 가능하다.
- AC-V2-09: 경험 관계 뷰에서 영역→프로젝트→경험→근거 관계를 식별할 수 있다.
- AC-V2-10: 공고 원문을 대화에 넣으면 요구사항과 경험 비교 결과 및 근거가 표시된다.
- AC-V2-11: 모든 비동기 흐름에 loading/processing/success/partial/error/retry 상태가 있다.
- AC-V2-12: API 실패 후 마지막 사용자 입력과 승인 전 편집 내용이 유지된다.
- AC-V2-13: AI 제안·사용자 확정·원본 근거가 라벨로 구분된다.
- AC-V2-14: Mock 성공/빈 데이터/부분 성공/오류 시나리오에서 주요 라우트가 동작한다.
- AC-V2-15: LLM/RAG 내부 구현이 프론트엔드 코드에 포함되지 않는다.

## 13. V1 마이그레이션

### 유지·재사용

- API adapter와 AppError 패턴
- 공통 loading/error/empty/confirm 구성요소
- 파일 검증 규칙과 source manager의 개념
- 경험 상세 도메인 필드
- 공고 요구사항/경험 매칭 화면 모델
- 디자인 토큰 중 접근성 기준을 충족하는 항목

### 재설계

- 기본 라우트 `/memory` → `/chat`
- memory 내부 `경험 질문` 탭 → 독립된 핵심 Chat Workspace
- 새 경험 입력 폼 → chat composer와 draft panel
- 경험 tree 중심 화면 → 검색 가능한 Experience Library
- 채용공고 입력 폼 → chat에서도 시작 가능한 분석 흐름
- 사이드바 우선순위 → 챗봇, 경험 관리, 채용공고 순서

### 보류·제거

- 자기소개서 관련 라우트와 UI는 V2 핵심 구현에서 숨기고 코드 제거 여부는 별도 migration 단계에서 결정
- V1 URL은 가능하면 새 대응 화면으로 redirect
- V1 mock fixture는 직접 확장하지 않고 V2 fixture schema를 별도로 만든다.

### 데이터 호환

- 기존 확정 경험은 `confirmed` 상태로 library에 노출한다.
- 기존 source ID와 experience ID는 바꾸지 않는다.
- 기존 경험에 대화 출처가 없으면 `legacy_import`로 표시하고 원본 유무를 그대로 보존한다.
- migration 실패 데이터는 삭제하지 않고 `needs_review`로 격리한다.

## 14. 구현 단계 권고

1. V2 API 계약·Mock schema
2. V2 shell, routing, Chat Workspace 정적 UI
3. message/attachment/draft 상태 머신과 Mock 연결
4. Experience Library와 관계 뷰
5. Experience Detail/source 관리 재연결
6. Job Analysis의 chat 진입과 상세 연결
7. 반응형·접근성·E2E·회귀 QA
8. 실 AI API 통합

각 단계는 QA 통과 후 Supervisor 승인을 받아 완료 처리한다.
