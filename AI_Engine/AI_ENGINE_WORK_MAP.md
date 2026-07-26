# Career Memory AI 엔진 작업 매핑

## 1. 문서 목적

이 문서는 Career Memory의 AI 엔진 개발 순서와 각 작업의 입력·출력·스키마·프론트엔드 연결 지점·완료 조건을 한곳에서 추적한다.

- AI 역할과 설계 원칙: `AI_ENGINE_DEVELOPMENT_GUIDE.md`
- 서비스 전체 AI 흐름: `../Data_Flow_Summary.md`
- 데이터 구조 개선 기준: `../docs/DATA_SCHEMA_AUDIT_improvement.md`
- 프론트엔드 작업 매핑: `../docs/WORK_AGENT_MATRIX.md`
- 프론트엔드 작업 분해: `../docs/WORK_BREAKDOWN.md`
- AI ↔ 프론트엔드 변환 계약: `AI_FRONTEND_CONTRACT_MAPPING.md`
- AI 기억·세션 공유 정책: `../AI_MEMORY_CONTEXT_POLICY.md`

상태 표시는 `[ ]` todo, `[~]` in progress, `[!]` blocked, `[?]` review, `[x]` done을 사용한다.

---

## 2. 전체 실행 구조

```text
React 프론트엔드
  ↓ HTTP/SSE
백엔드 API
  ↓ 검증된 Pydantic 요청
AI_langchain.py
  ├─ 명시적 요청 → 해당 체인 직접 실행
  └─ 자동 모드 → router.py → 실행 체인 선택
       ├─ 대화형 챗봇
       ├─ 경험정리 AI
       └─ 채용공고 분석 AI
            ↓
프롬프트 · LLM · 검색기 · 검증기 · 저장소 Adapter
            ↓
검증된 구조화 응답
```

핵심 원칙:

1. 세 AI의 책임과 체인은 분리한다.
2. `[경험 정리]`, `[공고 분석]`, 전용 버튼은 라우터 판정 없이 목적 체인을 직접 실행한다.
3. `[자동]` 모드에서만 `router.py`가 의도를 판정한다.
4. AI는 확정 경험을 직접 저장하지 않고 `ExperienceDraft[]`를 반환한다.
5. 사용자 승인 후 백엔드 트랜잭션이 경험·근거 연결을 확정 저장한다.
6. 프론트엔드는 Python AI 엔진을 직접 호출하지 않고 API 계약을 사용한다.
7. 대화 원문은 현재 세션에서만 사용하고, 사용자 승인 후 저장된 경험만 계정의 모든 세션에서 RAG로 공유한다.
8. 경험 RAG의 모든 저장·검색에는 로그인 세션에서 얻은 `user_id` 필터를 강제한다.

---

## 3. 역할별 AI 작업

| ID | 상태 | AI 역할 | 주요 입력 | 주요 출력 | 구현 위치 | 완료 조건 |
|---|---|---|---|---|---|---|
| AI-110 | `[~]` | 대화형 챗봇 | 현재 세션 문맥, 새 메시지, 첨부 ID, 현재 사용자의 저장 경험·근거 검색 결과 | 답변, 인용, 후속 행동, 스트리밍 이벤트 | `chatbot_ai.py` | 세션 간 대화 원문을 섞지 않고 사용자별 저장 경험 RAG·첨부 본문·인용 연결 |
| AI-120 | `[~]` | 경험정리 AI | 대화 범위 또는 직접 입력 텍스트·파일 | `ExperienceDraft[]` 0..N개, 원본 근거, 누락 정보 | `experience_ai.py` | strict 함수 호출과 공통 스키마 변환 완료. 대화·파일 본문 수집 파이프라인 연결 대기 |
| AI-130 | `[~]` | 공고 요구사항 구조화 | 공고 원문·첨부 파일 | `JobRequirement[]` | `job_analysis_ai.py` | strict 함수 호출과 원문 인용 위치 검증 완료. 실제 첨부 본문 수집 연결 대기 |
| AI-140 | `[~]` | 요구사항별 경험 추천 | 요구사항, 확정 Experience 검색 문서 | `RequirementExperienceLink[]` | `job_analysis_ai.py` | retriever 주입·후보 제한·추천 근거 검증 완료. 실제 Chroma 인덱스 연결 대기 |

---

## 4. 공통 계약과 기반 작업

| ID | 상태 | 작업 | 관련 파일 | 산출물·완료 조건 |
|---|---|---|---|---|
| AI-001 | `[x]` | AI 역할·파이프라인 개발 기준 수립 | `AI_ENGINE_DEVELOPMENT_GUIDE.md` | 세 AI 책임, 라우팅, RAG, 저장 경계 정의 |
| AI-002 | `[x]` | 경험·근거·공고 스키마 작성 및 역할별 분리 | `schemas/common.py`, `evidence.py`, `experience.py`, `job.py` | 경험 초안, 근거, 공고 요구사항, 추천 연결을 각 소유 모듈에서 검증 |
| AI-003 | `[x]` | 스키마 패키지와 공개 import 경계 구성 | `schemas/__init__.py`, `schemas/experience_job.py` | 공개 import와 이전 통합 import 경로 모두 호환 |
| AI-004 | `[x]` | 챗봇·라우팅 스키마 작성 | `schemas/chat.py`, `schemas/routing.py` | 요청·응답·인용·SSE 이벤트·라우팅 판정 계약 |
| AI-005 | `[~]` | 오류 코드·API 응답 envelope 확정 | `schemas/common.py`, `AI_FRONTEND_CONTRACT_MAPPING.md`, 백엔드 API 계약 | 변환 규칙 문서화 완료. API Adapter 구현과 계약 테스트 대기 |
| AI-006 | `[~]` | 스키마 버전과 예제 fixture 고정 | `schemas/`, `AI_FRONTEND_CONTRACT_MAPPING.md`, `tests/fixtures/` | 버전 필드와 fixture 요구사항 문서화 완료. 실제 JSON fixture 작성 대기 |

현재 검증: 스키마 단위 테스트 18개, Python 컴파일, 공개/영역별 import, JSON Schema 생성 통과.

---

## 5. 원본 처리·RAG·외부 연동 작업

| ID | 상태 | 작업 | 입력 → 출력 | 구현 위치 | 완료 조건 |
|---|---|---|---|---|---|
| AI-210 | `[ ]` | 첨부 파일 파싱 | PDF/TXT → 페이지·문단·offset가 있는 원문 | `experience_ai.py`, `job_analysis_ai.py` | 파일 원문과 인용 위치를 재현 가능 |
| AI-211 | `[ ]` | 중복 파일 판정 | filename, size, SHA-256 → duplicate 상태 | `experience_ai.py`, 백엔드 저장 API | 동일 해시는 재사용하고 수정본은 별도 버전 처리 |
| AI-220 | `[ ]` | EvidenceChunk 생성·임베딩 | 원본 대화·텍스트·파일 → 검색 chunk | `experience_ai.py` | 원본 ID·page·offset가 보존되고 중복 임베딩 방지 |
| AI-230 | `[~]` | Experience Search Document 생성·임베딩 | 사용자별 확정 Experience → 검색용 문서 | `schemas/retrieval.py`, `job_analysis_ai.py` | `user_id` 메타데이터와 필터를 강제하고 확정·근거 보유 경험만 문서화. 생성·수정·삭제 저장소 이벤트 연결 대기 |
| AI-240 | `[?]` | LLM 모델 생성 | `load_dotenv → ChatOpenAI` | 역할별 AI 파일 | 역할별 모델 생성 방식 구현, 실제 API 호출 확인 대기 |
| AI-250 | `[ ]` | Vector Store 연결 | 임베딩 문서 ↔ 검색 결과 | `job_analysis_ai.py` | 인덱스 버전과 필터 조건을 응답에 기록 |
| AI-260 | `[ ]` | 저장 데이터 연결 | 대화·근거·경험·공고 조회/저장 | `AI_langchain.py`, 백엔드 저장 API | AI 실행과 실제 저장 경계를 구분 |

원본 근거와 파생 문서는 분리한다.

```text
원본 대화·텍스트·파일
  └─ Evidence / EvidenceChunk 임베딩

사용자 확정 경험
  └─ Experience Search Document 임베딩
```

AI 요약은 원본 근거를 대체하지 않으며, 모든 사실과 추천은 원본 ID 또는 확정 경험 ID로 추적할 수 있어야 한다.

---

## 6. LangChain 파이프라인 작업

| ID | 상태 | 파이프라인 | 실행 흐름 | 주요 계약 |
|---|---|---|---|---|
| AI-310 | `[~]` | 커리어 챗 | 현재 세션 문맥 수집 → 사용자별 확정 경험 RAG → 챗봇 → 스트리밍 응답 | 세션 원문 격리, 계정 공통 경험 검색, 참고 경험 표시와 API 연결 대기 |
| AI-320 | `[ ]` | 대화내용으로 경험 정리 | 마지막 성공 범위 계산 → 대화·첨부 수집 → 경험정리 AI | `ExperienceExtractionRequest`, `ExtractionRun`, `ExperienceExtractionResult` |
| AI-330 | `[~]` | 경험 관리의 `+ 경험 추가` | 직접 텍스트·첨부 수집 → 공통 경험정리 AI | 텍스트 직접 입력은 실제 Gemini/FastAPI와 경험 제안 화면 연결 완료. 파일 파싱과 확정 저장 API 연결 대기 |
| AI-340 | `[ ]` | 채용공고 분석 | 공고 파싱 → 요구사항 구조화 → 경험 RAG → 요구사항별 추천 | `JobAnalysisRequest`, `JobAnalysisResult` |
| AI-350 | `[ ]` | 자동 모드 라우팅 | 요청 문맥 분석 → 체인 판정 → 낮은 확신은 chat fallback | `AIRouteRequest`, `AIRouteDecision` |
| AI-360 | `[ ]` | AI 조립 진입점 | Adapter·Retriever·Validator·Chain 생성과 의존성 주입 | `AI_langchain.py` |

`AI-320`과 `AI-330`은 입력 수집 Adapter만 다르고 동일한 경험정리 체인을 재사용한다.

---

## 7. 프론트엔드 진입점 ↔ AI 파이프라인 매핑

| 프론트엔드 사용자 행동 | 요청 유형 | AI 파이프라인 | AI 응답 | 프론트엔드 반영 |
|---|---|---|---|---|
| 커리어 챗에서 메시지 전송 `[자동]` | `auto` | `router → chatbot/experience/job` | 채팅 응답 또는 제안 | 채팅 메시지·제안 컴포넌트 |
| 커리어 챗에서 메시지 전송 `[경험 정리]` | `experience_extraction` | 경험정리 직접 실행 | `ExperienceDraft[]` | 공통 경험 구조화 제안 컴포넌트 |
| 커리어 챗에서 메시지 전송 `[공고 분석]` | `job_analysis` | 공고 분석 직접 실행 | 공고 초안 또는 분석 결과 | 공고 제안·분석 결과 화면 |
| `[대화내용으로 경험 정리하기]` | `experience_extraction` | AI-320 | 최신 미분석 범위의 초안 0..N개 | 채팅 안 공통 경험 초안 |
| 경험 관리의 `[+ 경험 추가]` | `experience_extraction` | AI-330 | 직접 입력 기반 초안 0..N개 | 경험 구조화 제안 페이지 |
| 채용공고 분석의 `[공고 분석하기]` | `job_analysis` | AI-340 | 요구사항과 추천 연결 | 공고 요구사항·매칭 경험 화면 |

권장 API 경계:

| API | 요청 스키마 | 응답 스키마 | 전송 |
|---|---|---|---|
| `POST /ai/chat` | `ChatRequest` | `ChatStreamEvent` / `ChatResponse` | SSE |
| `POST /ai/experience-extractions/conversation` | `ExperienceExtractionRequest` | `ExperienceExtractionResult` | JSON 또는 작업 상태 |
| `POST /api/v2/experience-extractions/direct-input` | `ExperienceExtractionRequest` | `ExperienceExtractionResult` | JSON. 텍스트 직접 입력 연결 완료 |
| `POST /ai/job-analyses` | `JobAnalysisRequest` | `JobAnalysisResult` | JSON 또는 작업 상태 |

---

## 8. 검증·품질 작업

| ID | 상태 | 검증 | 완료 조건 |
|---|---|---|---|
| AI-QA-510 | `[~]` | 스키마 단위 테스트 | 모든 모델의 정상·경계·오류 사례 통과 |
| AI-QA-520 | `[ ]` | Prompt/구조화 출력 테스트 | JSON Schema 위반·근거 없는 사실·임의 추측 차단 |
| AI-QA-530 | `[ ]` | 경험 추출 평가 | 0개, 1개, 여러 경험, 여러 파일, 정보 부족 사례 평가 |
| AI-QA-540 | `[ ]` | RAG 검색 평가 | 요구사항별 관련 경험 recall/precision과 인용 추적성 확인 |
| AI-QA-550 | `[ ]` | 라우터 평가 | 자동 모드 혼합 의도와 낮은 확신 fallback 검증 |
| AI-QA-560 | `[ ]` | API 계약 테스트 | snake_case ↔ camelCase mapper, 오류, SSE 재연결 검증 |
| AI-QA-570 | `[ ]` | 프론트엔드 E2E | 초안 검토·개별/전체 저장·삭제·공고 매칭까지 회귀 통과 |

현재 연결 메모:

- 직접 입력 → Gemini 경험정리 → 초안 검토 → 개별/전체 저장 → 사용자별 DB 조회 경로를 연결했다.
- 경험 CRUD API와 프론트 단위 테스트까지 통과했으며, 브라우저 수동 E2E 확인 후 관련 항목을 `[x]`로 확정한다.

---

## 9. 구현 순서

```text
1. AI-005~006  오류·버전·fixture 계약 고정
2. AI-240~260  LLM·Vector Store·Repository Adapter
3. AI-210~230  파일 파싱·근거 chunk·확정 경험 인덱스
4. AI-110      대화형 챗봇
5. AI-120      경험정리 AI
6. AI-130~140  공고 요구사항 구조화·경험 추천
7. AI-310~350  프론트엔드 행동별 LangChain 파이프라인
8. AI-360      AI_langchain.py 조립
9. API 연결과 AI-QA-510~570 검증
```

독립 엔진을 먼저 검증하고, 검증된 엔진을 LangChain 파이프라인으로 조립한다. 체인부터 크게 만든 뒤 내부 역할을 나누지 않는다.

---

## 10. 작업 완료 기준

- 세 역할의 입력·출력과 실패 상태가 Pydantic/JSON Schema로 검증된다.
- 한 입력에서 경험 0..N개가 반환되고 동일 분류·프로젝트 계층으로 묶일 수 있다.
- 모르는 값은 추측하지 않고 빈값 또는 `missing_information`으로 반환된다.
- 경험 사실과 공고 요구사항은 원문 위치로 추적할 수 있다.
- 요구사항별 AI 추천과 사용자 직접 연결이 구분된다.
- 대화 경험정리의 성공 체크포인트만 다음 증분 분석 범위를 이동한다.
- 동일한 요청의 재시도가 경험·공고·근거를 중복 저장하지 않는다.
- 초안 저장 전에는 확정 Experience와 검색 인덱스가 변경되지 않는다.
- 프론트엔드 Mock/실API 전환 시 화면 컴포넌트를 수정하지 않는다.
- 단위·계약·RAG 평가·E2E 검증 결과가 보고 문서에 남는다.

---

## 11. 문서 갱신 규칙

- 작업 시작 시 상태를 `[~]`로 변경한다.
- 구현과 자동 검증이 끝나면 `[?]`로 변경한다.
- API/프론트 통합 또는 사용자 확인까지 끝난 뒤 `[x]`로 변경한다.
- 스키마나 API가 바뀌면 이 문서, `Data_Flow_Summary.md`, `DATA_SCHEMA_AUDIT_improvement.md`를 함께 확인한다.
- 실제 코드와 문서가 다르면 코드를 임의로 맞추기 전에 계약 차이를 먼저 기록한다.
