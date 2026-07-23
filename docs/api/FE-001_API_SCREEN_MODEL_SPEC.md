# FE-001 API·화면 모델 명세

- 상태: 프론트엔드 기준안, AI 엔진 담당자 확인 필요
- 기준: `PRD.md` V1, `FE-000_USER_FLOW_SPEC.md`
- 범위: 프론트엔드 DTO, 화면 모델, Mock/HTTP adapter 경계
- 제외: FastAPI·LLM·RAG·DB 구현

## 1. 계약 원칙

1. JSON 키는 `snake_case`, 프론트엔드 화면 모델은 `camelCase`를 사용한다.
2. 모든 ID는 opaque string이다. 접두사나 숫자 변환에 의존하지 않는다.
3. 시각은 timezone을 포함한 ISO 8601 문자열이다. 표시 시에만 사용자 locale로 바꾼다.
4. 응답은 성공 envelope 없이 resource를 직접 반환한다. 오류만 공통 envelope를 쓴다.
5. optional 값은 의미가 없으면 키를 생략한다. `null`은 “값이 없음을 명시”해야 할 때만 쓴다. 배열은 항상 배열이며 없으면 `[]`이다.
6. AI 제안은 저장된 사실이 아니다. 구조화 응답의 `draft_id`와 `raw_id`를 commit할 때 사용자가 수정한 전체 draft를 다시 보낸다.
7. Mock과 HTTP adapter는 동일한 도메인 반환형·오류형을 보장한다. 컴포넌트는 wire DTO를 직접 읽지 않는다.
8. 현재 V1은 장시간 작업도 동기 HTTP 응답을 기본값으로 한다. 진행률을 만들지 않으며 timeout 후 같은 입력으로 재시도할 수 있다.

## 2. 공통 wire 타입

```ts
type Id = string;
type IsoDateTime = string;

type ApiError = {
  error: {
    code: string;
    message: string;
    field_errors: Array<{ field: string; code: string; message: string }>;
    request_id: string;
    retryable: boolean;
    retry_after_seconds?: number;
    details?: Record<string, unknown>;
  };
};

type PartialFailure = {
  item_id: string;
  code: string;
  message: string;
  retryable: boolean;
};
```

### HTTP와 오류 매핑

| HTTP | 대표 code | 프론트 동작 |
|---|---|---|
| 400 | `INVALID_REQUEST` | 작업 영역 오류, 입력 유지 |
| 404 | `RESOURCE_NOT_FOUND` | ID 없음 화면과 복귀 CTA |
| 409 | `DUPLICATE_REQUEST`, `VERSION_CONFLICT` | 중복 안내 또는 최신 resource 재조회 |
| 413 | `FILE_TOO_LARGE` | 파일 필드 오류 |
| 415 | `UNSUPPORTED_FILE_TYPE` | 파일 필드 오류 |
| 422 | `VALIDATION_ERROR` | `field_errors`를 필드에 연결 |
| 429 | `RATE_LIMITED` | `retry_after_seconds` 후 재시도 |
| 500 | `INTERNAL_ERROR` | 일반 오류, request ID 표시 가능 |
| 502/503 | `AI_SERVICE_UNAVAILABLE` | retryable 오류 |
| 504 | `AI_PROCESSING_TIMEOUT` | 입력 유지, 수동 재시도 |

네트워크 단절·Abort·JSON 파싱 실패는 adapter가 각각 `NETWORK_ERROR`, `REQUEST_ABORTED`, `INVALID_RESPONSE`인 동일한 `AppError`로 정규화한다. 기술 message는 사용자에게 그대로 노출하지 않는다.

## 3. 공통 도메인 타입

```ts
type ExperienceDraft = {
  title: string;
  summary: string;
  situation: string;
  actions: string[];
  results: string[];
  role: string;
  facts: string[];
  skills: string[];
  missingInformation: string[];
  sourceRefs: string[];
};

type ProjectDraft = {
  name: string;
  organization?: string;
  period?: { start?: string; end?: string };
  experiences: ExperienceDraft[];
};

type ParsedInput = {
  rawId: Id;
  draftId: Id;
  domainName: string;
  project: ProjectDraft;
  projectCandidates: Array<{
    projectId: Id;
    name: string;
    organization?: string;
    reason: string;
    confidence?: number;
  }>;
  warnings: string[];
};

type Experience = ExperienceDraft & {
  id: Id;
  domainId: Id;
  domainName: string;
  projectId: Id;
  projectName: string;
  organization?: string;
  period?: { start?: string; end?: string };
  visibility: "visible" | "hidden";
  createdAt: IsoDateTime;
  updatedAt: IsoDateTime;
  version: number;
};
```

기간의 부분 날짜는 `YYYY` 또는 `YYYY-MM` 문자열을 허용한다. `confidence`는 0~1이며 UI에 확정성으로 표현하지 않는다.

## 4. 12개 endpoint 계약

### API-01 `POST /api/inputs/text`

Request:

```json
{ "content": "경험 원문", "client_request_id": "uuid" }
```

제약: trim 후 1자 이상. 권장 상한 50,000자(서버 확정 필요). `client_request_id`는 재시도 중 동일하게 유지한다.

Response `200 ParsedInputWire`:

```json
{
  "raw_id": "RAW-001", "draft_id": "DRF-001", "domain_name": "직장 경험",
  "project": {
    "name": "SNS 운영", "organization": "SBI저축은행",
    "period": { "start": "2023-01", "end": "2023-12" },
    "experiences": [{
      "title": "KPI 개선", "summary": "저장·공유 KPI 제안", "situation": "기존 지표 한계",
      "actions": ["대안 지표 분석"], "results": [], "role": "기획",
      "facts": ["저장·공유 중심 KPI 제안"], "skills": ["데이터 분석"],
      "missing_information": ["정량 성과"], "source_refs": ["SRC-001"]
    }]
  },
  "project_candidates": [], "warnings": []
}
```

빈 구조화 결과는 200과 빈 `experiences`로 반환하며 UI가 보완 안내를 표시한다.

### API-02 `POST /api/inputs/file`

`multipart/form-data`: 단일 입력은 `file`, 다중 입력은 반복 `files`, 그리고 `client_request_id`가 필수다. PDF/TXT 최대 5개, 파일당 25MiB, 요청 전체 100MiB를 프론트 기본값으로 사용한다. 서버는 여러 원본을 하나의 구조화 초안으로 통합하되 각 사실의 source 연결을 유지한다.

Response `200`: API-01 필드에 아래를 추가한다.

```json
{
  "file": { "file_id": "FILE-001", "filename": "portfolio.pdf", "mime_type": "application/pdf", "size_bytes": 12345, "page_count": 15 }
}
```

TXT의 `page_count`는 생략한다. 동일 파일 판정 방식은 서버 미확정이며 프론트는 같은 선택 이벤트를 허용한다.

### API-03 `POST /api/experiences/commit`

Request:

```json
{
  "raw_id": "RAW-001", "draft_id": "DRF-001", "client_request_id": "uuid",
  "save_mode": "existing_project", "target_project_id": "PROJ-001",
  "domain_name": "직장 경험",
  "project": { "name": "SNS 운영", "organization": "SBI저축은행", "period": {}, "experiences": [] }
}
```

`save_mode`: `existing_project | new_project`. `existing_project`이면 `target_project_id` 필수, `new_project`이면 금지한다. `defer`는 영속 계약이 없어 V1 commit 값에서 제외한다. 경험 1개 이상 필수다.

Response `201`:

```json
{
  "project_id": "PROJ-001", "experience_ids": ["EXP-001"],
  "experiences": [], "committed_at": "2026-07-22T12:00:00+09:00"
}
```

`experiences`에는 생성된 Experience 전체를 반환해 별도 상세 호출 없이 cache를 갱신한다.

### API-04 `GET /api/experiences/tree`

Response `200`:

```json
{
  "domains": [{
    "id": "DOM-001", "name": "직장 경험", "experience_count": 1,
    "projects": [{
      "id": "PROJ-001", "name": "SNS 운영", "organization": "SBI저축은행",
      "period": {}, "experience_count": 1,
      "experiences": [{ "id": "EXP-001", "title": "KPI 개선", "summary": "...", "skills": ["분석"], "updated_at": "2026-07-22T12:00:00+09:00" }]
    }]
  }],
  "total_experience_count": 1
}
```

빈 상태는 200과 `domains: []`이다. V1은 pagination을 사용하지 않는다. 기본적으로 hidden 경험은 제외한다.

### API-05 `GET /api/experiences/{experienceId}`

Response `200`: 공통 `Experience`의 snake_case wire 표현 전체. 경로 ID는 URL encoding한다. 없는 ID는 404다.

### API-06 `PATCH /api/experiences/{experienceId}`

Request:

```json
{
  "version": 3,
  "changes": { "title": "수정 제목", "actions": ["수정 행동"], "skills": ["분석"] }
}
```

허용 changes: `title`, `summary`, `situation`, `actions`, `results`, `role`, `facts`, `skills`, `missing_information`. 명시한 값만 수정한다. 빈 `changes`는 422. Response `200`은 갱신된 Experience 전체다. version 불일치는 409 `VERSION_CONFLICT`다.

PRD의 숨기기는 이 endpoint에 섞지 않는다. 의미·복원 UI가 정해지기 전 별도 계약 보류다.

### API-07 `GET /api/experiences/{experienceId}/sources`

Response `200`:

```json
{
  "experience_id": "EXP-001",
  "sources": [{
    "id": "SRC-001", "raw_id": "RAW-001", "source_type": "file",
    "text": "근거 문장", "filename": "portfolio.pdf", "page": 3,
    "captured_at": "2026-07-22T12:00:00+09:00",
    "linked_facts": [{ "fact": "KPI 제안", "quote": "저장과 공유 중심 KPI를 제안" }]
  }]
}
```

`source_type`: `text | file`. 텍스트 입력은 filename/page를 생략한다. 원본이 없으면 200과 빈 배열이다.

### API-08 `POST /api/chat/experiences`

Request:

```json
{ "message": "데이터 기반 개선 경험을 찾아줘", "experience_id": "EXP-001", "conversation_id": "CONV-001", "client_request_id": "uuid" }
```

`experience_id`, `conversation_id`는 optional이다. V1 프론트는 현재 세션의 마지막 `conversation_id`만 유지한다.

Response `200`:

```json
{
  "conversation_id": "CONV-001", "message_id": "MSG-002",
  "answer": "관련 경험은 KPI 개선입니다.",
  "experiences": [{ "id": "EXP-001", "title": "KPI 개선", "project_id": "PROJ-001", "project_name": "SNS 운영", "summary": "..." }],
  "evidence": [{ "source_id": "SRC-001", "experience_id": "EXP-001", "quote": "...", "filename": "portfolio.pdf", "page": 3 }],
  "missing_information": [], "warnings": []
}
```

근거가 없으면 배열을 비우고 warnings에 근거 부족을 표시한다.

### API-09 `POST /api/jobs/analyze`

Request:

```json
{
  "company_name": "회사", "role_name": "직무", "posting_content": "공고 원문",
  "cover_letter_questions": ["지원 동기"], "client_request_id": "uuid"
}
```

공고 원문은 trim 후 필수다. Response `201`:

```json
{
  "job_id": "JOB-001", "company_name": "회사", "role_name": "직무",
  "posting_content": "공고 원문", "cover_letter_questions": ["지원 동기"],
  "requirements": [{ "id": "REQ-001", "type": "responsibility", "text": "데이터 분석", "importance": "required", "keywords": ["데이터"] }],
  "warnings": [], "analyzed_at": "2026-07-22T12:00:00+09:00"
}
```

`type`: `responsibility | required_qualification | preferred_qualification | skill | domain_experience | collaboration`. `importance`: `required | preferred | unspecified`. 요구사항이 없으면 빈 배열로 성공 처리한다.

### API-10 `POST /api/jobs/{jobId}/match`

Request:

```json
{ "requirement_ids": [], "client_request_id": "uuid" }
```

빈 `requirement_ids`는 전체 요구사항을 뜻한다. 부분 재시도 시 실패한 ID만 보낸다.

Response `200`:

```json
{
  "job_id": "JOB-001",
  "matches": [{
    "requirement_id": "REQ-001", "requirement_text": "데이터 분석",
    "status": "direct", "reason": "직접 수행 근거가 있음",
    "experiences": [{ "experience_id": "EXP-001", "title": "KPI 개선", "project_name": "SNS 운영", "evidence": [{ "source_id": "SRC-001", "quote": "..." }] }],
    "missing_information": []
  }],
  "failures": []
}
```

`status`: `direct | partial | indirect | no_evidence | needs_confirmation`. 항목별 실패는 HTTP 200과 `failures: PartialFailure[]`; 요청 전체 실패만 4xx/5xx다. 같은 ID의 재시도 결과는 기존 항목을 교체한다.

### API-11 `POST /api/cover-letters/generate`

Request:

```json
{
  "job_id": "JOB-001", "question": "문항", "character_limit": 700,
  "experience_ids": ["EXP-001"], "tone": "default", "client_request_id": "uuid"
}
```

경험은 1~2개, tone은 `default | concise | concrete`, 글자 수는 양의 정수다.

Response `201`:

```json
{
  "document_id": "DOC-001", "job_id": "JOB-001", "question": "문항",
  "content": "생성 내용", "character_limit": 700, "character_count": 650,
  "tone": "default", "experience_ids": ["EXP-001"],
  "evidence": [{ "experience_id": "EXP-001", "source_id": "SRC-001", "quote": "..." }],
  "missing_information": [], "warnings": [], "version": 1,
  "created_at": "2026-07-22T12:00:00+09:00", "updated_at": "2026-07-22T12:00:00+09:00"
}
```

`character_count`의 기준은 서버와 프론트가 동일해야 한다(공백 포함 Unicode code point 권장, 확인 필요). 초과 결과도 자동 절삭하지 않고 warning과 실제 count를 반환한다.

### API-12 `POST /api/cover-letters/revise`

Request:

```json
{
  "document_id": "DOC-001", "base_version": 1, "revision_type": "shorten",
  "content": "사용자가 편집한 현재 내용", "client_request_id": "uuid"
}
```

`revision_type`: `shorten | expand | natural | rewrite`. Response `200`은 API-11 문서 전체와 `previous_content`를 반환한다. 프론트는 결과를 즉시 덮어쓰지 않고 비교/적용 또는 1단계 undo를 제공한다. 서버의 직접 편집 저장 endpoint가 없으므로 V1 직접 편집은 로컬 dirty 상태이며 새로고침 영속성을 약속하지 않는다.

## 5. 화면 모델

### 원본 관리 확장 계약

```http
PATCH /api/sources/{sourceId}
DELETE /api/sources/{sourceId}
GET /api/sources/{sourceId}/download
```

- PATCH는 텍스트 원본만 수정하며 `{ version?, changes: { text }, client_request_id }`를 받는다.
- DELETE는 원본과 경험 사실의 연결을 제거한다. 확정 경험 자체는 자동 삭제하지 않는다.
- DOWNLOAD는 업로드된 원본 파일을 attachment로 반환한다.
- 삭제 응답에는 근거를 잃은 연결 사실 ID와 경고를 포함하는 것을 권장한다.

| 화면 | Screen model | 조합 API | 필수 상태 |
|---|---|---|---|
| `/memory` browse | `MemoryBrowseVM { tree, selectedId, expandedIds }` | API-04 | loading/empty/error/ready |
| `/memory` input | `MemoryInputVM { method, content, file, validation }` | API-01/02 | editing/processing/error |
| `/memory` review | `ExperienceReviewVM { parsed, editableProject, linkChoice, dirty }` | API-01/02→03 | clean/dirty/saving/saved |
| `/memory/:id` | `ExperienceDetailVM { experience, sourcesState, editDraft }` | API-05/06/07 | loading/not-found/ready/dirty |
| memory chat | `ExperienceChatVM { conversationId, messages, pendingQuestion }` | API-08 | idle/sending/error |
| `/jobs` | `JobInputVM { fields, validation }` | API-09 | editing/analyzing/error |
| `/jobs/:id` | `JobDetailVM { job, matchesByRequirement, failedIds, selectedExperienceIds }` | API-09 결과→10 | ready/matching/partial/selected |
| `/documents/:id` | `CoverLetterVM { document, editContent, previousContent, dirty }` | API-11/12 | ready/dirty/revising/error |

DTO에서 VM으로 바꿀 때 누락 optional 값에만 화면 기본값을 적용한다. 서버가 보낸 빈 문자열·빈 배열을 임의 데이터로 채우지 않는다. `status`, `type`, `tone` 등 알 수 없는 enum은 adapter에서 버리지 않고 `unknown`으로 보존하고 UI는 “확인 필요”로 표시한다.

## 6. Adapter와 요청 정책

- API 모듈 공개 함수는 wire가 아닌 도메인 타입을 반환한다: `parseText`, `parseFile`, `commitExperiences`, `getExperienceTree`, `getExperience`, `updateExperience`, `getExperienceSources`, `askExperiences`, `analyzeJob`, `matchJob`, `generateCoverLetter`, `reviseCoverLetter`.
- `VITE_USE_MOCK=true`는 fixture adapter, `false`는 HTTP adapter를 선택한다. 컴포넌트 분기 금지.
- JSON 요청은 `Content-Type: application/json`, 응답은 JSON을 기대한다. 파일만 multipart이며 브라우저가 boundary를 설정한다.
- AbortController를 화면 이탈/사용자 취소에 사용한다. 취소는 오류 toast를 띄우지 않는다.
- 자동 재시도는 GET의 네트워크 오류 1회만 허용한다. AI POST는 자동 재시도하지 않는다.
- 모든 mutation에 요청별 UUID `client_request_id`를 보낸다. 같은 사용자 동작의 수동 재시도는 같은 ID, 내용을 고쳐 새로 제출하면 새 ID를 쓴다. 서버의 멱등성 보장 여부는 확인 필요다.
- 기본 timeout 제안: GET 15초, 일반 PATCH/commit 30초, AI 분석·대화·매칭·생성·수정 120초, 파일 구조화 180초.
- cache key는 resource ID 기반이다. commit 후 tree invalidate, experience patch 후 detail/tree invalidate, job match는 job detail 내 merge, revise는 document 교체다.
- wire schema가 잘못되면 성공으로 간주하지 않고 `INVALID_RESPONSE`로 처리한다.

## 7. Mock fixture 요구사항

각 endpoint는 최소 `success`, `empty`(해당 시), `validation-error`, `retryable-error` fixture를 갖는다. 추가로 tree는 nested/empty, sources는 text/file/empty, chat은 evidence/no-evidence, match는 full/partial/no-evidence, cover letter는 warning/over-limit을 포함한다. fixture는 wire DTO 형태로 저장하고 HTTP adapter와 같은 mapper를 통과시킨다.

## 8. FE-000 결정 반영

| 결정 | FE-001 기준 |
|---|---|
| D-002 장시간 요청 | 동기 HTTP + processing; polling은 서버 요구 시 후속 변경 |
| D-004 대화 기록 | 현재 세션, optional conversation ID |
| D-005 글자 수 초과 | 표시·경고, 자동 절삭 금지 |
| D-006 숨기기 | 계약·복원 UX 확정 전 보류 |
| D-007 프로젝트 보류 | commit enum에서 제외, review 로컬 선택으로만 표현 |
| D-008 직접 편집 저장 | 로컬 dirty; revise 전 content 전달; 최소 1단계 undo |
| D-009 부분 성공 | job match의 item failure 구조 확정, 나머지 분석은 전체 성공/실패 |

## 9. AI 엔진 담당자 확인이 필요한 계약

| 우선순위 | ID | 질문 | 프론트 기본값 |
|---|---|---|---|
| 필수 | OQ-01 | 장시간 endpoint가 동기 방식과 제안 timeout을 지원하는가? | 동기, 120/180초 |
| 필수 | OQ-02 | mutation의 `client_request_id` 멱등성을 보장하는가? 보존 시간은? | UI 중복 방지만 보장 |
| 필수 | OQ-03 | PDF/TXT MIME, 최대 크기, 암호화 PDF 처리 정책은? | PDF/TXT, 10 MiB, 암호화 PDF 거절 |
| 필수 | OQ-04 | `character_count`는 공백·줄바꿈·Unicode를 어떻게 센는가? | 공백 포함 code point |
| 확정 | OQ-05 | 공고 상세 새로고침 복구 API를 추가할 것인가? | `GET /api/jobs/{jobId}` 추가 승인 |
| 확정 | OQ-06 | 문서 조회·직접 편집 저장 API를 추가할 것인가? | `GET/PATCH /api/documents/{documentId}` 추가 승인 |
| 중요 | OQ-07 | 숨기기/복원 기능의 서버 의미와 endpoint는? | 구현 보류 |
| 중요 | OQ-08 | `defer` project 연결을 서버가 보존할 것인가? | commit 전 로컬 상태 |
| 중요 | OQ-09 | match 부분 실패를 제안 schema로 반환 가능한가? | 전체 실패 fallback 가능 |
| 중요 | OQ-10 | 개발 CORS origin과 base URL은? | `http://localhost:5173`, `http://localhost:8000` |

사용자 승인에 따라 새로고침 복구와 직접 편집 저장을 위한 다음 API를 계약 범위에 추가한다. 상세 DTO는 FE-002 fixture 작성 시 기존 `JobAnalysis`, `CoverLetterDocument` 타입을 재사용해 고정한다.

```http
GET /api/jobs/{jobId}
GET /api/documents/{documentId}
PATCH /api/documents/{documentId}
```

## 10. 완료 기준

- 12개 endpoint의 request/response와 오류·빈·부분 성공 해석이 정의되어 있다.
- 모든 wire DTO가 화면 모델과 adapter 함수에 연결된다.
- Mock/HTTP 전환이 컴포넌트에 노출되지 않는다.
- AI 엔진 미확정 사항과 안전한 프론트 기본값이 분리되어 있다.
- AI 엔진 내부 구현을 요구하거나 포함하지 않는다.
