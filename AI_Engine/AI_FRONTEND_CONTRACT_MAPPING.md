# AI 엔진 ↔ 프론트엔드 계약 매핑

## 1. 문서 목적

이 문서는 AI 엔진의 Pydantic 입출력을 백엔드 API가 프론트엔드 공개 계약으로 변환하는 규칙을 정의한다.

기준 문서는 다음과 같다.

- 사용자 흐름: `../Data_Flow_Summary.md`
- AI 역할과 파이프라인: `AI_ENGINE_DEVELOPMENT_GUIDE.md`
- AI 작업 상태: `AI_ENGINE_WORK_MAP.md`
- 프론트 V2 계약: `../docs/v2/V2_API_CONTRACT.md`
- 프론트 V1 화면 모델: `../docs/api/FE-001_API_SCREEN_MODEL_SPEC.md`

AI 엔진은 프론트 화면 모델을 직접 만들지 않는다. 백엔드 API Adapter가 AI 내부 DTO를 공개 API DTO로 변환하고, 프론트 API Adapter가 공개 DTO를 화면 모델로 변환한다.

```text
AI Pydantic DTO (snake_case)
  ↓ Backend AI/API Adapter
공개 API wire DTO (snake_case)
  ↓ Frontend HTTP Adapter / mapper
화면 모델 (camelCase)
```

---

## 2. 공통 경계 규칙

1. AI와 공개 API의 JSON 키는 `snake_case`를 사용한다.
2. 프론트 화면 모델의 `camelCase` 변환은 프론트 API Adapter에서 한 번만 수행한다.
3. ID는 의미를 해석하지 않는 opaque string이다.
4. 날짜는 timezone이 포함된 ISO 8601 문자열이다.
5. 배열은 결과가 없어도 `[]`를 반환한다.
6. AI가 생성한 경험과 공고 결과는 사용자가 승인하기 전까지 Proposal이다.
7. AI는 Experience를 직접 확정 저장하지 않는다.
8. `client_request_id`는 API가 받고 AI 실행과 저장 작업 전체에 전달한다.
9. 같은 사용자 동작의 재시도는 같은 `client_request_id`를 사용한다.
10. AI 내부 모델·프롬프트·스키마·인덱스 버전은 저장 및 관측용으로 보존한다.
11. 현재 대화의 메시지는 해당 `conversation_id`에서만 문맥으로 사용한다.
12. 경험 관리에 확정 저장된 경험만 현재 사용자의 모든 대화에서 RAG 검색할 수 있다.
13. 다른 대화 세션의 메시지 원문과 미확정 Proposal은 자동으로 전달하지 않는다.
14. 경험 검색의 사용자 ID는 요청 본문이 아니라 인증된 서버 세션에서 가져온다.

확정 경험 검색 인덱스의 현재 기본값은 다음과 같다.

```text
embedding_model: text-embedding-3-small
index_version: experience-index-v2
```

임베딩 모델이나 검색 문서 구성이 바뀌면 `index_version`을 올리고 기존 문서를 새 인덱스로 전체 재임베딩한다. 서로 다른 임베딩 모델로 생성한 벡터를 같은 컬렉션에 혼합하지 않는다.

---

## 3. 경험정리 결과 → Proposal

### 3.1 입력 변환

#### 대화내용으로 경험 정리

API가 마지막 성공 분석 이후의 범위를 계산하고 AI 요청을 만든다.

| API/저장 값 | AI `ExperienceExtractionRequest` |
|---|---|
| 요청 UUID | `client_request_id` |
| 고정값 | `input_type = "conversation"` |
| 경로의 대화 ID | `conversation_id` |
| 마지막 성공 체크포인트 다음 번호 | `from_sequence` |
| 이번 분석의 마지막 메시지 번호 | `to_sequence` |
| 분석 대상 메시지 | `message_ids[]` |
| 메시지에 연결된 첨부 | `attachment_ids[]` |

#### 경험 관리의 직접 입력

| API/저장 값 | AI `ExperienceExtractionRequest` |
|---|---|
| 요청 UUID | `client_request_id` |
| 고정값 | `input_type = "direct_input"` |
| 사용자가 입력한 원문 | `text` |
| 직접 입력 원본 ID | `manual_input_id` |
| 업로드된 첨부 | `attachment_ids[]` |

API Adapter는 저장소에서 대화 본문과 파싱된 첨부 본문을 조회하여 `ExperienceAI.organize()`의 원본 입력으로 주입한다.

현재 구현 상태:

- `GET /api/v2/conversations/{conversation_id}/experience-extraction-status`가 마지막 성공 범위 이후의 미분석 사용자 메시지 수를 반환한다.
- `POST /api/v2/conversations/{conversation_id}/experience-extractions`가 미분석 사용자 메시지를 실제 경험정리 AI로 전달한다.
- 대화내용 분석에서는 AI 답변과 `job` 모드로 입력한 채용공고를 경험 근거에서 제외한다.
- 생성한 Proposal은 assistant 메시지 action에 저장되어 새로고침과 대화 재진입 후에도 복원된다.
- Proposal을 거절하면 해당 분석 범위를 다시 경험 정리 대상으로 사용할 수 있다.
- `POST /api/v2/experience-extractions/direct-input`에서 텍스트 직접 입력을 실제 경험정리 AI로 실행한다.
- 반환된 `ExperienceExtractionResult`는 프론트 Adapter가 기존 경험 구조화 제안 화면 모델로 변환한다.
- AI 결과에 없는 가짜 추가 초안은 생성하지 않는다.
- 경험정리 직접 입력의 PDF·TXT·PNG·JPG·WEBP는 `/api/v2/experience-extractions/direct-input-files`에서 본문을 추출한다.
- 직접 작성한 텍스트와 파일 근거는 동일한 분석 범위로 묶어 한 번에 경험 초안을 생성한다.
- TXT와 텍스트 PDF는 서버에서 직접 추출하고, 이미지와 스캔 PDF는 로컬 Tesseract OCR(`kor+eng`)로 읽는다.
- 파일 판독에는 Gemini를 사용하지 않으며, 추출된 텍스트를 경험 초안으로 구조화할 때만 활성 AI Provider를 호출한다.
- 승인된 초안은 로그인 사용자 ID와 연결된 실제 Experience DB에 저장한다.

### 3.2 출력 변환

| AI `ExperienceExtractionResult` | 공개 API `Proposal` |
|---|---|
| `run.id` | `extraction_run_id` |
| `run.from_sequence`, `run.to_sequence` | `analysis_scope` |
| `experience_drafts[]` | `payload.experiences[]` |
| 첫 초안의 `domain` | `payload.domain` 호환 projection |
| 첫 초안의 `project` | `payload.project` 호환 projection |
| `sources[]` | `source_refs[]` |
| `warnings[]` | `warnings[]` |

Proposal의 고정값은 다음과 같다.

```json
{
  "type": "create_experiences",
  "status": "pending",
  "version": 1
}
```

`payload.domain`과 `payload.project`는 V1 호환 projection이다. 진짜 원본은 각 `payload.experiences[]`의 `domain`, `project`이며 프론트는 모든 경험을 개별 처리해야 한다.

`ExperienceDraft`의 다음 필드는 손실 없이 보존한다.

```text
draft_id
domain
project
title
summary
situation
actions[]
results[]
role
skills[]
skill_groups[]
facts[]
missing_information[]
source_ref_ids[]
field_citations{}
confidence
status
```

`source_refs`는 Proposal 최상위에서 원본 상세를 한 번 제공하고, 각 초안은 `source_ref_ids`로 참조한다. 같은 원본 객체를 초안마다 중복 복사하지 않는다.

---

## 4. 챗봇 요청과 SSE 변환

### 4.1 프론트 메시지 요청 → AI `ChatRequest`

API는 사용자 메시지를 먼저 저장한 뒤 AI를 호출한다.

API가 AI 요청을 조립할 때 다음 두 문맥을 구분한다.

```text
conversation_context: URL의 conversation_id에 속한 메시지·첨부
experience_context: 로그인 user_id로 필터한 관련 확정 경험·근거
```

`conversation_context`에는 다른 대화 세션의 메시지를 포함하지 않는다. `experience_context`는 질문과 관련된 상위 검색 결과만 포함하며, 전체 경험 목록을 그대로 전달하지 않는다.

| 프론트/API 값 | AI `ChatRequest` |
|---|---|
| `client_request_id` | `client_request_id` |
| URL의 conversation ID | `conversation_id` |
| 저장된 사용자 메시지 ID | `message_id` |
| 저장된 메시지 순번 | `sequence` |
| `intent` | `mode` |
| `content` | `content` |
| `attachment_ids[]` | `attachment_ids[]` |

`intent` 매핑:

| 공개 API `intent` | AI 실행 |
|---|---|
| `auto` | Router가 의도 판정 |
| `experience` | 경험정리 파이프라인 직접 실행 |
| `job` | 공고 분석 파이프라인 직접 실행 |
| `question`, `advice` | 대화형 챗봇 직접 실행 |

API Adapter는 `question`, `advice`를 AI의 명시적 `chat` 모드로 변환한다. 명시적 intent는 Router의 LLM 판정을 거치지 않는다. `auto`에서만 의도를 판정하며 확신도가 낮으면 챗봇으로 fallback한다.

### 4.2 AI 스트림 → 공개 SSE

AI의 스트림은 내부 실행 이벤트다. 공개 SSE는 메시지 저장, 첨부 처리, Proposal 생성까지 포함하므로 API가 다음과 같이 변환·보강한다.

| AI `ChatStreamEvent` | 공개 V2 SSE |
|---|---|
| 실행 전 API가 생성 | `message.accepted` |
| Router 결과 | `intent.resolved` |
| 첨부 처리 Adapter | `attachment.processing` |
| `started` | 별도 공개 이벤트 없음 |
| `token.text_delta` | `assistant.delta.delta` |
| `citation.citation` | `citation.added.citation` |
| `action.action` | 완료 Message의 `actions[]` |
| 경험/공고 결과 저장 | `proposal.created` |
| `completed.response` | `message.completed.message` |
| `error.error` | `message.failed.error` |
| API heartbeat timer | `stream.heartbeat` |

공개 SSE 규칙:

1. `message.accepted`가 첫 의미 이벤트다.
2. `assistant.delta.delta`는 누적 본문이 아니라 추가 문자열이다.
3. Proposal은 `message.completed` 전에 생성한다.
4. 정상 종료와 실패 종료 이벤트는 하나만 전송한다.
5. SSE `id`에는 증가하는 `sequence`를 사용한다.
6. 재연결을 위해 API 계층이 `Last-Event-ID`를 처리한다.

---

## 5. 채용공고 분석 결과 → Job/Match

AI 내부의 `JobAnalysisAI`는 다음 파이프라인을 공유한다.

```text
공고 요구사항 추출
  ↓
확정 경험 RAG 검색
  ↓
요구사항별 경험 추천
```

프론트 공개 API는 기존 화면 계약을 유지하기 위해 두 단계로 제공한다.

### 5.1 `POST /api/jobs/analyze`

이 API는 `JobAnalysisResult` 중 공고와 요구사항을 저장하고 반환한다.

| AI `JobAnalysisResult` | 공개 Job |
|---|---|
| `job_posting.posting_id` | `job_id` |
| `job_posting.company_name` | `company_name` |
| `job_posting.role_name` | `role_name` |
| `job_posting.posting_title` | `posting_title` |
| `job_posting.source_url` | `source_url` |
| `job_posting.posting_content` | `posting_content` |
| `requirements[]` | `requirements[]` |
| `warnings[]` | `warnings[]` |
| `analyzed_at` | `analyzed_at` |

요구사항의 `title`, `summary`, `source_excerpt`, `source_locator`, `confidence`는 V1 화면이 당장 표시하지 않더라도 버리지 않고 V2 저장 데이터에 보존한다.

#### 요구사항 enum 변환

AI 스키마는 의미를 과도하게 세분화하지 않고, 공개 V1 API는 기존 화면 필터와 표시를 위해 세부 유형을 사용한다.

| AI `type` | AI `importance` | 공개 V1 `type` |
|---|---|---|
| `responsibility` | 모든 값 | `responsibility` |
| `qualification` | `required` | `required_qualification` |
| `qualification` | `preferred` | `preferred_qualification` |
| `qualification` | `unknown` | `required_qualification`이 아닌 일반 `qualification`으로 V2에 보존하고 V1에서는 `skill`로 임의 변환하지 않음 |
| `collaboration` | 모든 값 | `collaboration` |
| `other` | 모든 값 | `other`로 V2에 보존하고 V1 화면에서는 `unknown` 표시 |

중요도 변환:

| AI `importance` | 공개 V1 `importance` |
|---|---|
| `required` | `required` |
| `preferred` | `preferred` |
| `unknown` | `unspecified` |

V1의 `skill`, `domain_experience`는 공고 원문에 해당 의미가 명확할 때 API Adapter가 `keywords`, `title`, `summary`를 근거로 별도 projection할 수 있다. 문자열 포함 여부만으로 분류하지 않으며, 근거가 부족하면 AI의 원래 `type`을 V2에 보존하고 V1에는 `unknown`을 전달한다.

공개 계약은 알 수 없는 enum을 버리지 않는다. 프론트 Adapter는 이를 `unknown`으로 보존하고 화면은 “확인 필요”로 표시한다.

### 5.2 `POST /api/jobs/{job_id}/match`

이 API는 저장된 분석 결과의 `experience_links[]`를 요구사항별로 그룹화하고, 연결된 Experience 상세와 Evidence를 조회하여 화면용 결과를 만든다.

| AI `RequirementExperienceLink` | 공개 Match 항목 |
|---|---|
| `requirement_id` | `requirement_id` |
| `experience_id` | `experiences[].experience_id` |
| `similarity_score` | `experiences[].score` |
| `reason` | Match의 `reason` 또는 경험별 추천 사유 |
| `evidence_ids[]` | `experiences[].evidence[]` 조회 키 |
| `source` | AI 추천/사용자 연결 provenance |
| `status` | 선택·거절 상태 |

API Adapter가 추가로 조회·계산하는 필드:

```text
requirement_text
experiences[].title
experiences[].project_name
experiences[].evidence[].quote
missing_information[]
failures[]
```

`status` 화면 projection:

| 조건 | 공개 status |
|---|---|
| 직접 수행을 확인할 근거가 충분함 | `direct` |
| 일부만 근거로 확인됨 | `partial` |
| 전이 가능한 간접 경험 | `indirect` |
| 추천할 근거가 없음 | `no_evidence` |
| 사용자 확인이 필요함 | `needs_confirmation` |

AI 모델의 `RequirementExperienceLink.status`와 화면의 관련성 `status`는 의미가 다르므로 같은 enum으로 취급하지 않는다.

선택된 `requirement_ids[]`만 재매칭할 수 있으며, 항목별 실패는 HTTP 200의 `failures[]`에 기록한다. 요청 전체가 실행되지 못한 경우에만 4xx/5xx를 사용한다.

---

### 5.3 현재 실제 연결 상태

- `GET /api/jobs`: 로그인 사용자의 분석 기록 목록을 최신순으로 조회한다.
- `POST /api/jobs/analyze`: 요구사항 추출과 사용자별 확정 경험 RAG를 실행한 뒤 DB에 저장한다.
- `POST /api/jobs/extract-text`: TXT는 서버에서 읽고 PDF·PNG·JPG·WEBP는 Gemini 시각 인식으로 원문을 추출한다.
- `GET /api/jobs/{job_id}`: 새로고침 뒤에도 저장된 분석 결과를 복원한다.
- `POST /api/jobs/{job_id}/match`: 저장된 요구사항별 추천 경험과 근거를 화면 모델로 반환한다.
- 요구사항–경험 `PUT/DELETE`: 사용자가 직접 변경한 연결을 DB에 반영한다.
- `DELETE /api/jobs/{job_id}`: 현재 사용자 소유의 분석 기록만 삭제한다.
- 채용공고 레코드와 Chroma 컬렉션은 모두 사용자별로 분리한다.
- 파일 원문은 먼저 화면의 공고 원문 칸에 표시하여 사용자가 확인·수정한 뒤 분석한다.
- 파일은 최대 5개, 파일당 25MiB·요청 전체 100MiB로 제한하며 현재 허용 형식은 PDF·TXT·PNG·JPG·WEBP이다.
- 경험 근거 PDF는 기본 최대 100페이지까지 읽으며 `AI_MAX_PDF_PAGES`로 조절한다.

## 6. AI 오류 → 공개 API 오류

AI 내부 오류는 예외 또는 `AIError`로 표현하고, API가 HTTP 상태와 공개 오류 envelope를 결정한다.

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "입력값을 확인해 주세요.",
    "field_errors": [],
    "request_id": "REQ-001",
    "retryable": false,
    "details": {}
  }
}
```

API 공개 오류에는 `field_errors`와 `request_id`가 항상 존재해야 한다. AI의 `details`는 사용자에게 직접 노출하지 않고 안전한 값만 전달한다.

| 상황 | HTTP | 공개 code | retryable |
|---|---:|---|---|
| 잘못된 요청 형식 | 400 | `INVALID_REQUEST` | false |
| 존재하지 않는 리소스 | 404 | `RESOURCE_NOT_FOUND` | false |
| 준비되지 않은 첨부 | 409 | `ATTACHMENT_NOT_READY` | true |
| 중복 요청 | 409 | `DUPLICATE_REQUEST` | false |
| Proposal/리소스 버전 충돌 | 409 | `VERSION_CONFLICT` | false |
| 파일 크기 초과 | 413 | `FILE_TOO_LARGE` | false |
| 지원하지 않는 파일 | 415 | `UNSUPPORTED_FILE_TYPE` | false |
| Pydantic 입력 검증 실패 | 422 | `VALIDATION_ERROR` | false |
| 호출 한도 초과 | 429 | `RATE_LIMITED` | true |
| 예상하지 못한 서버 오류 | 500 | `INTERNAL_ERROR` | false |
| AI/Vector Store 일시 장애 | 502/503 | `AI_SERVICE_UNAVAILABLE` | true |
| AI 처리 제한시간 초과 | 504 | `AI_PROCESSING_TIMEOUT` | true |
| AI 출력 스키마 위반 | 502 | `INVALID_RESPONSE` | true |

세부 내부 오류 매핑:

| 내부 예외 | 공개 code |
|---|---|
| `ChatbotAIInputError`, `ExperienceAIInputError`, `JobAnalysisAIInputError` | `VALIDATION_ERROR` 또는 `INVALID_REQUEST` |
| `ChatbotAIOutputError`, `ExperienceAIOutputError`, `JobAnalysisAIOutputError` | `INVALID_RESPONSE` |
| `JobAnalysisAIRetrievalError` | `AI_SERVICE_UNAVAILABLE` |
| OpenAI 연결·서비스 오류 | `AI_SERVICE_UNAVAILABLE` |
| API timeout | `AI_PROCESSING_TIMEOUT` |

SSE 연결 이후 발생한 오류는 HTTP 상태를 바꿀 수 없으므로 `message.failed`로 전달한다.

---

## 7. 계약 검증 체크리스트

AI 또는 프론트 연동 코드를 변경할 때 다음 순서로 확인한다.

1. `Data_Flow_Summary.md`의 사용자 흐름과 일치하는가?
2. AI Pydantic 요청·응답이 유효한가?
3. 이 문서의 Backend AI/API Adapter 변환 규칙과 일치하는가?
4. 공개 API wire DTO가 V1/V2 계약과 일치하는가?
5. 프론트 mapper가 화면 모델로 손실 없이 변환하는가?
6. Mock과 실제 HTTP Adapter가 같은 도메인 반환형을 만드는가?
7. 정상·빈 결과·부분 성공·오류 fixture가 있는가?
8. Python 단위 테스트와 프론트 계약 테스트가 함께 통과하는가?

---

## 8. 아직 구현이 필요한 항목

- SSE heartbeat와 `Last-Event-ID` 기반 중간 스트림 재연결
- AI 오류 예외의 공개 오류 envelope 변환
- 정상·빈 결과·부분 성공·오류 JSON fixture
- AI DTO ↔ 공개 API DTO 계약 테스트
- 자기소개서 생성 AI의 실제 API·저장 연결
- 브라우저 사용자 흐름 E2E 자동화

경험정리 Proposal 저장과 채용공고 analyze/match projection은 실제 API에 연결되어 있다.
위 목록은 현재 남은 통합·품질 작업을 나타낸다.

---

## 9. 경험정리 AI 저장 연결 현황

- `POST /api/v2/experience-extractions/direct-input`이 Gemini 경험 초안을 반환한다.
- 사용자가 초안 검토 화면에서 저장하면 `POST /api/v2/experiences`가 호출된다.
- 확정된 경험, 경험 분류, 프로젝트·활동은 로그인 사용자 ID와 함께 DB에 저장된다.
- 경험 목록과 상세 화면은 `/api/v2/experiences`와 `/api/v2/experience-structure`에서 실제 DB 값을 읽는다.
- 다른 사용자의 경험은 목록·상세·수정·삭제 API에서 조회할 수 없다.
- 예시 경험 fixture는 자동 테스트에서만 사용하며 개발·배포 화면에는 노출하지 않는다.

### 경험 휴지통

- 삭제되었거나 저장에 실패한 경험 초안은 `experience_draft_trash`에 사용자별로 보관한다.
- 분석 결과가 만들어진 실패·삭제 건은 구조화 초안 전체를 저장한다.
- 분석 자체가 실패한 건은 입력 원문과 실패 이유를 저장한다.
- 휴지통에서 삭제된 경험이나 초안을 수정하고 실제 경험으로 다시 저장할 수 있다.
- 실제 경험으로 저장되면 휴지통 항목을 제거하며, 완전 삭제는 사용자 확인 후 복구 불가능하게 처리한다.
