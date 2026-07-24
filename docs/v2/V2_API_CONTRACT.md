# Career Memory V2 API 계약

## 경험 구조 관리 (Mock)

경험 분류와 프로젝트·활동은 경험 유무와 관계없이 독립적으로 유지된다. 모든 변경 API는 `version`/`base_version` 낙관적 잠금을 지원한다.

- `listStructure()` / `listDomains()` / `listProjects({ domain_id })`
- `createDomain({ name })`, `updateDomain(id, { base_version, name })`
- `createProject({ domain_id, name, organization })`, `updateProject(id, { base_version, ...changes })`
- `getStructureDeletionImpact(type, id)`
- `deleteDomain` / `deleteProject`: `confirm: true`와 내용이 있을 경우 `strategy: "cascade"` 또는 이동 대상 ID가 필요하다.
- `bulkMoveExperiences({ experience_ids, target_domain_id?, target_project_id })`
- `bulkDeleteExperiences({ experience_ids, confirm: true })`
- 삭제는 soft delete이며 `restoreDeleted("domain" | "project" | "experience", id)`로 복원할 수 있다.

- 상태: 프론트엔드 기준안
- 목적: 챗봇을 단일 진입점으로 삼아 대화·텍스트·파일·공고를 이해하고, 검토 가능한 경험 자산으로 전환한다.
- 범위: 프론트엔드 계약, Mock 이벤트, V1 호환 전략
- 제외: LLM 프롬프트, RAG 검색·임베딩·DB·파일 파싱의 내부 구현

## 1. 핵심 원칙

1. **대화와 확정 데이터는 분리한다.** LLM 결과는 `proposal`이며 사용자가 승인하기 전에는 경험 원본을 변경하지 않는다.
2. **근거를 잃지 않는다.** 구조화된 모든 사실은 메시지·텍스트 범위·첨부 파일 페이지 등 하나 이상의 `source_ref`를 가질 수 있다.
3. **한 메시지에 여러 의도가 가능하다.** 프론트는 힌트를 줄 수 있지만 최종 분류는 AI 엔진이 수행한다.
4. **스트리밍은 표시 방식이고 저장 의미가 아니다.** `done` 이벤트를 받아도 proposal 승인 전에는 경험에 반영되지 않는다.
5. JSON은 `snake_case`, ID는 opaque string, 시간은 timezone 포함 ISO 8601을 사용한다.
6. mutation에는 `client_request_id`, 갱신에는 `version` 또는 `base_version`을 사용한다.

## 2. 책임 경계

| 프론트엔드/Codex | 사용자 담당 AI 엔진 |
|---|---|
| 세션·메시지 UI, 첨부 업로드 상태, 스트림 렌더링 | 메시지 의도 분류, LLM 응답 생성, RAG 검색 |
| proposal diff·편집·승인/거절 UI | 경험/사실/프로젝트 구조화 제안 생성 |
| 경험 목록·검색·CRUD 화면 | 원본 파싱, chunk/page 좌표, 근거 연결·보존 |
| 낙관적 UI, 재시도, 오류 복구 | 트랜잭션, 멱등성, 버전 충돌, 권한·보안 |
| Mock adapter와 HTTP adapter | 실제 DB·스토리지·SSE 연결 및 정책 집행 |
| 다운로드 동작과 사용자 확인 | 악성 파일 검사, MIME 검증, signed download 또는 stream |

AI 엔진은 대화만 저장하고 임의로 경험을 확정해서는 안 된다. 다만 사용자가 명시적으로 “바로 저장”을 요청해도 V2 기본 정책은 proposal 생성 후 승인이다.

## 3. 공통 타입과 오류

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

type Page<T> = {
  items: T[];
  next_cursor?: string;
  total_count?: number;
};
```

주요 오류 코드는 `VALIDATION_ERROR`, `NOT_FOUND`, `VERSION_CONFLICT`, `DUPLICATE_REQUEST`, `FILE_TOO_LARGE`, `UNSUPPORTED_FILE_TYPE`, `UPLOAD_FAILED`, `STREAM_INTERRUPTED`, `AI_SERVICE_UNAVAILABLE`, `RATE_LIMITED`, `INVALID_RESPONSE`다.

## 4. 대화 도메인

### 4.1 세션

```ts
type Conversation = {
  id: Id;
  title: string;
  status: "active" | "archived";
  last_message_preview?: string;
  message_count: number;
  pending_proposal_count: number;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
  version: number;
};
```

| Method | Endpoint | 의미 |
|---|---|---|
| POST | `/api/v2/conversations` | 새 대화 생성 |
| GET | `/api/v2/conversations?cursor=&limit=20&status=active` | 대화 목록 |
| GET | `/api/v2/conversations/{id}` | 세션 복구 |
| PATCH | `/api/v2/conversations/{id}` | 제목 변경·보관/복원 |
| DELETE | `/api/v2/conversations/{id}` | 대화 삭제; 확정 경험은 유지 |

생성 요청:

```json
{ "title": "선택 입력", "client_request_id": "uuid" }
```

### 4.2 메시지와 의도

```ts
type InputIntent = "auto" | "experience" | "file" | "job" | "question" | "advice";

type Message = {
  id: Id;
  conversation_id: Id;
  role: "user" | "assistant" | "system";
  status: "queued" | "processing" | "streaming" | "completed" | "failed" | "cancelled";
  content: string;
  requested_intent: InputIntent;
  resolved_intents: Exclude<InputIntent, "auto">[];
  attachment_ids: Id[];
  citations: Citation[];
  proposal_ids: Id[];
  actions: MessageAction[];
  error?: ApiError["error"];
  created_at: IsoDateTime;
  completed_at?: IsoDateTime;
};

type MessageAction = {
  type: "open_experience" | "review_proposal" | "analyze_job" | "write_cover_letter" | "add_information";
  label: string;
  target_id?: Id;
};
```

의도 의미:

- `experience`: 사용자의 경험 서술을 구조화한다.
- `file`: 첨부를 읽어 경험·사실 후보를 찾는다.
- `job`: 공고 요구사항을 분석하고 저장 경험과 비교한다.
- `question`: 확정된 경험과 근거에서 답한다.
- `advice`: 커리어 조언을 제공하며 사실과 추론을 구분한다.
- `auto`: 복합 입력을 서버가 하나 이상으로 분류한다.

| Method | Endpoint | 의미 |
|---|---|---|
| GET | `/api/v2/conversations/{id}/messages?cursor=&limit=50` | 메시지 이력 |
| POST | `/api/v2/conversations/{id}/messages` | 비스트리밍 메시지 전송 |
| POST | `/api/v2/conversations/{id}/messages/stream` | SSE 스트리밍 전송 |
| POST | `/api/v2/conversations/{id}/messages/{message_id}/cancel` | 처리 취소 요청 |
| POST | `/api/v2/conversations/{id}/messages/{message_id}/retry` | 동일 입력 재시도 |

메시지 요청:

```json
{
  "content": "이 공고에 내 경험이 얼마나 맞는지 봐줘",
  "intent": "auto",
  "attachment_ids": ["ATT-001"],
  "context": {
    "experience_ids": [],
    "job_id": null,
    "selected_proposal_id": null
  },
  "response_mode": "stream",
  "client_request_id": "uuid"
}
```

비스트리밍 응답은 완성된 `Message`를 반환한다. 스트리밍 endpoint는 `202`가 아니라 `200 text/event-stream`으로 연결되며, 최초 `message.accepted` 이벤트에서 사용자/assistant message ID를 제공한다.

## 5. 첨부 파일

업로드는 메시지 전송과 분리하여 재시도·진행률·복수 파일을 지원한다.

| Method | Endpoint | 의미 |
|---|---|---|
| POST | `/api/v2/attachments` | `multipart/form-data`, `files` 반복 |
| GET | `/api/v2/attachments/{id}` | 처리 상태·메타데이터 |
| GET | `/api/v2/attachments/{id}/download` | 원본 다운로드 |
| DELETE | `/api/v2/attachments/{id}` | 미확정 첨부 삭제; 연결 시 영향 결과 반환 |

```ts
type Attachment = {
  id: Id;
  filename: string;
  mime_type: string;
  size_bytes: number;
  kind: "pdf" | "text";
  status: "uploaded" | "scanning" | "parsing" | "ready" | "failed";
  page_count?: number;
  error?: ApiError["error"];
  created_at: IsoDateTime;
};
```

기본 한도는 PDF/TXT 최대 5개, 파일당 25MiB, 요청 합계 100MiB다. 서버가 반환한 `limits`가 있으면 프론트는 이를 우선한다. 메시지는 `ready` 첨부만 참조하는 것을 기본으로 하며, 처리 중이면 `409 ATTACHMENT_NOT_READY`를 반환한다.

## 6. 근거와 인용

```ts
type Citation = {
  id: Id;
  source_id: Id;
  experience_id?: Id;
  attachment_id?: Id;
  message_id?: Id;
  quote: string;
  locator?: { page?: number; start_offset?: number; end_offset?: number };
  label: string;
};

type Source = {
  id: Id;
  type: "message_text" | "file" | "manual_text";
  text?: string;
  filename?: string;
  mime_type?: string;
  size_bytes?: number;
  version: number;
  linked_fact_count: number;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
};
```

| Method | Endpoint |
|---|---|
| GET | `/api/v2/sources/{id}` |
| PATCH | `/api/v2/sources/{id}` |
| DELETE | `/api/v2/sources/{id}` |
| GET | `/api/v2/sources/{id}/download` |

텍스트 원본만 수정할 수 있다. 파일 원본은 교체 대신 새 첨부로 등록한다. 삭제는 `impact` 미리보기를 지원하도록 `GET /api/v2/sources/{id}/deletion-impact`를 제공하며, DELETE 요청은 `{ version, confirm: true, client_request_id }`를 받는다. 경험 자체는 자동 삭제하지 않고 연결 사실을 `evidence_missing`으로 표시한다.

## 7. 구조화 제안(Proposal)

```ts
type Proposal = {
  id: Id;
  conversation_id: Id;
  originating_message_id: Id;
  type: "create_experiences" | "update_experience" | "link_sources" | "analyze_job";
  status: "pending" | "edited" | "approved" | "rejected" | "expired";
  title: string;
  summary: string;
  payload: ProposalPayload;
  source_refs: Citation[];
  warnings: string[];
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
  version: number;
};

type ProposalPayload = {
  domain?: { id?: Id; name: string };
  project?: { id?: Id; name: string; organization?: string; period?: { start?: string; end?: string } };
  experiences?: ExperienceDraft[];
  target_experience_id?: Id;
  job_draft?: JobDraft;
};
```

`ExperienceDraft`는 다음 계층을 포함해야 한다.

```ts
type ExperienceDraft = {
  domain: { id?: Id; name: string };
  project: { id?: Id; name: string; organization?: string };
  title: string;
  summary: string;
  situation: string;
  actions: string[];
  results: string[];
  role: string;
  facts: string[];
  skills: string[];
  missing_information: string[];
  source_ref_ids: Id[];
  source_refs?: Source[];
};
```

AI 엔진은 하나의 메시지·파일에서 경험 후보를 0개 이상으로 분해하고, 각 후보마다 `domain → project → ExperienceDraft`를 채워야 한다. 여러 후보가 같은 원문에서 나왔으면 같은 `source_ref_id`를 공유할 수 있으며, 한 후보가 여러 파일에 근거하면 여러 ID를 가진다. 프론트는 `experiences[]`를 임의로 첫 항목으로 축약하지 않고 전체를 검토·수정·승인한다.

| Method | Endpoint | 의미 |
|---|---|---|
| GET | `/api/v2/proposals/{id}` | proposal 조회 |
| PATCH | `/api/v2/proposals/{id}` | 사용자가 draft 편집 |
| POST | `/api/v2/proposals/{id}/approve` | 원자적으로 경험/공고에 반영 |
| POST | `/api/v2/proposals/{id}/reject` | 거절; 원본 대화·첨부는 유지 |

편집 요청:

```json
{
  "base_version": 2,
  "payload": { "experiences": [] },
  "client_request_id": "uuid"
}
```

승인 요청과 응답:

```json
{
  "base_version": 3,
  "selection": { "experience_indexes": [0, 1] },
  "client_request_id": "uuid"
}
```

```json
{
  "proposal": { "id": "PRP-001", "status": "approved", "version": 4, "approved_experience_indexes": [0, 1] },
  "created": { "experience_ids": ["EXP-101", "EXP-102"], "job_id": null },
  "updated": { "experience_ids": [] },
  "approved_at": "2026-07-22T16:00:00+09:00"
}
```

경험 제안은 `selection.experience_indexes`에 지정한 초안만 부분 승인할 수 있다. 부분 승인 후 proposal은 `edited` 상태로 유지되고 `approved_experience_indexes`에 승인된 원본 인덱스를 기록한다. 모든 초안이 승인되면 `approved`로 전환된다. 이미 승인된 인덱스를 재요청해도 중복 경험을 만들지 않는다. 이미 승인된 proposal에 동일 `client_request_id`로 재요청하면 같은 결과를 반환한다.

## 8. 경험 관리 CRUD

| Method | Endpoint | 의미 |
|---|---|---|
| GET | `/api/v2/experiences?query=&domain_id=&project_id=&skill=&evidence_status=&cursor=` | 전체 목록·필터 |
| POST | `/api/v2/experiences` | 사용자가 직접 경험 생성 |
| GET | `/api/v2/experiences/{id}` | 경험 상세 |
| PATCH | `/api/v2/experiences/{id}` | 부분 수정 |
| GET | `/api/v2/experiences/{id}/sources` | 연결 근거 |
| GET | `/api/v2/experiences/{id}/deletion-impact` | 삭제 영향 확인 |
| DELETE | `/api/v2/experiences/{id}` | 확인 후 삭제 |

목록 item은 `id`, `title`, `summary`, `domain`, `project`, `skills`, `evidence_count`, `evidence_status`, `missing_information_count`, `updated_at`, `version`을 반환한다. `evidence_status`는 `verified | partial | missing`이다.

PATCH:

```json
{
  "base_version": 4,
  "changes": { "title": "수정 제목", "skills": ["데이터 분석"] },
  "client_request_id": "uuid"
}
```

DELETE:

```json
{ "version": 4, "confirm": true, "client_request_id": "uuid" }
```

삭제는 기본 hard delete가 아니라 `deleted_at`을 남기는 soft delete를 권장한다. 복원 정책을 제공한다면 `POST /api/v2/experiences/{id}/restore`를 추가한다.

## 9. 공고·자기소개서 연계

공고 원문을 채팅에 붙여 넣거나 파일로 첨부하면 `resolved_intents`에 `job`이 포함되고 `analyze_job` proposal 또는 Job 리소스가 생성된다. 기본값은 proposal이다.

| Method | Endpoint |
|---|---|
| GET | `/api/v2/jobs?cursor=` |
| POST | `/api/v2/jobs/analyze` |
| GET | `/api/v2/jobs/{id}` |
| POST | `/api/v2/jobs/{id}/match` |
| DELETE | `/api/v2/jobs/{id}` |
| POST | `/api/v2/cover-letters/generate` |
| GET | `/api/v2/cover-letters/{id}` |
| PATCH | `/api/v2/cover-letters/{id}` |
| POST | `/api/v2/cover-letters/{id}/revise` |

`jobs/analyze`는 채팅 밖 관리 화면의 직접 입력을 위한 보조 경로다. 채팅에서 생성된 Job은 `conversation_id`, `originating_message_id`, `source_ids`를 포함한다. match 결과는 요구사항별 `direct | partial | indirect | no_evidence | needs_confirmation`, 관련 `experience_ids`, citations, missing information을 반환한다.

자기소개서는 공고 분석 후 선택 기능이며 공고 입력 시 문항을 요구하지 않는다. 생성 시에만 `job_id`, `question`, `character_limit`, `experience_ids`(1~2개), `tone`을 받는다.

## 10. SSE 스트리밍 이벤트 모델

SSE 형식은 `event: <type>`, `id: <sequence>`, `data: <JSON>`이다. 연결 재개를 위해 `Last-Event-ID`를 지원하며 이벤트는 최소 10분 보존을 권장한다.

```ts
type StreamEvent =
  | { type: "message.accepted"; sequence: number; user_message: Message; assistant_message_id: Id }
  | { type: "intent.resolved"; sequence: number; intents: string[] }
  | { type: "attachment.processing"; sequence: number; attachment_id: Id; status: string; progress?: number }
  | { type: "assistant.delta"; sequence: number; message_id: Id; delta: string }
  | { type: "citation.added"; sequence: number; message_id: Id; citation: Citation }
  | { type: "proposal.created"; sequence: number; proposal: Proposal }
  | { type: "message.completed"; sequence: number; message: Message }
  | { type: "message.failed"; sequence: number; message_id: Id; error: ApiError["error"] }
  | { type: "stream.heartbeat"; sequence: number; at: IsoDateTime };
```

이벤트 순서 보장:

1. `message.accepted`가 항상 첫 의미 이벤트다.
2. `assistant.delta`는 누적 문자열이 아니라 추가분이다.
3. proposal은 delta 도중 또는 이후 도착할 수 있으나 `message.completed` 전에 생성된다.
4. 정상 종료는 `message.completed`, 실패 종료는 `message.failed` 중 하나뿐이다.
5. 연결이 끊겼지만 서버 처리가 계속되면 GET 메시지 조회로 최종 상태를 복구한다.

비스트리밍 Mock도 동일한 내부 이벤트 배열을 순서대로 소비한 뒤 최종 Message를 반환하도록 만들어 두 adapter의 UI 차이를 최소화한다.

### Mock 시나리오

| 시나리오 | 필수 이벤트/결과 |
|---|---|
| `chat-answer` | accepted → intent(question) → delta×N → citation → completed |
| `experience-proposal` | accepted → intent(experience) → delta → proposal.created → completed |
| `multi-file` | 첨부별 processing → intent(file, experience) → proposal → completed |
| `job-match` | intent(job) → delta → citations → proposal 또는 job action → completed |
| `advice-no-evidence` | intent(advice) → delta → warnings 포함 completed |
| `partial-evidence` | 답변·일부 citation·missing information |
| `stream-interrupted` | delta 후 연결 종료; GET 복구 성공/실패 분기 |
| `proposal-conflict` | PATCH/approve 409 + 최신 proposal |
| `upload-failure` | 특정 첨부만 failed, 나머지 유지 |
| `empty-memory` | 근거 없는 답변과 경험 입력 CTA |

Mock은 고정 ID/시간을 사용하고, 사용자 mutation이 이어지는 세션 내에서는 in-memory state를 갱신한다.

## 11. 상태·재시도·보안 기준

- GET은 네트워크 오류에 한해 1회 자동 재시도한다. 메시지·승인·삭제는 자동 재시도하지 않는다.
- 동일 사용자 동작의 수동 재시도에는 같은 `client_request_id`를 사용한다.
- timeout 권장값: GET 15초, CRUD 30초, 업로드 180초. SSE는 고정 timeout 대신 20초 heartbeat 누락 3회 시 재연결한다.
- HTML/스크립트는 plain text로 표시하고 Markdown 렌더링은 sanitization한다.
- 파일명은 표시용일 뿐 저장 경로로 신뢰하지 않는다.
- 다운로드 URL은 단기 signed URL 또는 인증된 stream이어야 한다.
- citation quote는 서버 원본의 locator와 일치해야 하며 LLM이 임의 생성한 인용을 저장하면 안 된다.
- 대화 삭제와 확정 경험 삭제의 영향은 분리한다.

## 12. V1 마이그레이션·호환 전략

V2는 `/api/v2` namespace로 추가하고 V1 `/api`를 즉시 제거하지 않는다.

| V1 | V2 대응 | 전략 |
|---|---|---|
| `POST /api/inputs/text` | conversation message + proposal | V1 adapter가 임시 대화 생성→메시지→proposal 결과를 `ParsedInput`으로 변환 |
| `POST /api/inputs/file` | attachments + message | 업로드 후 자동 메시지 생성; V1 단일 응답으로 대기 가능 |
| `POST /api/experiences/commit` | proposal approve | `draft_id`↔`proposal_id` 매핑 |
| tree/detail/PATCH | V2 experiences list/detail/PATCH | 필드 mapper 유지, V2를 source of truth로 전환 |
| `POST /api/chat/experiences` | conversation messages | V1은 1개 기본 세션으로 감싼다 |
| job analyze/match | V2 jobs | 필드 호환, provenance 필드만 추가 |
| cover-letter API | V2 cover-letters | V1 response projection 제공 |
| source API | V2 sources | deletion-impact와 version만 V2에 추가 |

단계:

1. **병행:** 백엔드가 V2를 구현하고 기존 화면은 V1 adapter를 사용한다.
2. **Chat 전환:** `/chat`만 V2 conversation/SSE를 사용하고 경험 관리는 V1/V2 mapper로 운영한다.
3. **관리 전환:** 경험·source·job·문서를 V2 CRUD로 교체한다.
4. **관측:** V1 호출량과 계약 오류를 기록하고 최소 1개 릴리스 동안 호환한다.
5. **폐기:** 응답에 `Deprecation`/`Sunset` 헤더와 문서를 제공한 뒤 V1을 제거한다.

프론트에서는 `chatApi`, `experienceApi`, `jobApi`, `documentApi` interface를 유지하고 mock/v1/v2 adapter를 교체한다. 컴포넌트가 endpoint나 wire DTO를 직접 참조하지 않게 한다.

## 13. AI 엔진 구현 전 확정할 항목

1. SSE 재개 보존 시간과 reverse proxy buffering 설정
2. 대화·원본·삭제 데이터의 보존/복원 기간
3. PDF/TXT 외 파일 유형과 OCR 지원 여부
4. 한 메시지에서 복수 proposal을 만드는 기준
5. proposal 만료 시점과 기반 경험이 바뀐 경우 재검증 정책
6. source 삭제 후 파생 경험의 `evidence_status` 재계산 방식
7. 사용자 인증 방식과 사용자별 스토리지 quota
8. LLM 답변·근거·제안의 감사 로그 보존 범위

프론트 개발 기본값은 SSE 지원, proposal 복수 허용, 승인 전 영구 데이터 변경 금지, 경험/원본 soft delete다.

## 14. 프론트 완료 기준

- 새 대화 생성부터 새로고침 후 복구까지 동작한다.
- 텍스트와 복수 첨부를 한 메시지에서 전송할 수 있다.
- 질문·조언·경험·공고 및 복합 의도를 동일 composer로 처리한다.
- 스트림 중단 시 입력과 이미 받은 응답을 보존하고 복구/재시도할 수 있다.
- proposal의 원본 근거, diff, 수정, 승인, 거절이 명시적으로 구분된다.
- 승인된 경험이 경험 관리 목록에 반영되고 CRUD·삭제 영향 확인이 가능하다.
- 공고 분석에서 경험 비교 및 자기소개서 생성으로 연결된다.
- Mock/실API 전환 시 화면 컴포넌트 변경이 없다.
