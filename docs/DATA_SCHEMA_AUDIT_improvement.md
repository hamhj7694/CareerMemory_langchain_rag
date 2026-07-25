# AI 데이터 구조 개선 점검

> 기준 문서: `Data_Flow_Summary.md`
>
> 이 문서는 AI 엔진·백엔드 API·프론트엔드가 함께 지켜야 할 핵심 구현 기준을 간단히 정리한다.

## 1. 이해한 서비스 구조

AI는 세 가지 역할을 담당한다.

1. **대화형 챗봇**: 대화와 첨부 파일을 누적하고 질문에 답한다.
2. **경험정리 AI**: 선택된 대화·입력 텍스트·파일에서 0개 이상의 경험을 찾아 `경험 분류 → 프로젝트·활동 → 상세 경험` 구조의 초안을 만든다.
3. **채용공고 분석 AI**: 공고를 요구사항 카드로 구조화하고, 확정된 경험을 RAG로 검색하여 요구사항별 관련 경험을 추천한다.

핵심 원칙은 다음과 같다.

- 한 메시지 또는 한 파일이 반드시 하나의 경험이 되는 것은 아니다.
- 여러 메시지·파일이 하나의 경험이 될 수 있고, 한 입력이 여러 경험으로 나뉠 수도 있다.
- AI 결과는 바로 확정 데이터가 아니라 **사용자가 검토·수정·부분 저장할 수 있는 초안**이다.
- AI가 알 수 없는 값은 추측하지 않고 빈값과 `missing_information`으로 남긴다.
- 모든 확정 사실은 원본 대화·입력 텍스트·파일까지 추적할 수 있어야 한다.

## 2. 권장 전체 흐름

```text
원본 저장
Conversation → Message → Attachment/ManualInput
        ↓
ExtractionRun 실행
        ↓
0..N ExperienceDraft 생성
        ↓
사용자 검토·수정·분리·병합·부분 승인
        ↓
승인 트랜잭션
Domain → Project → Experience
                  ├─ Fact ↔ Evidence
                  └─ ExperienceSkill ↔ Skill → SkillGroup

JobPosting → JobRequirement
                  ↓ RAG
RequirementExperienceLink → Experience
```

AI는 DB에 Experience를 직접 저장하지 않는다. AI는 JSON Schema에 맞는 초안을 반환하고, 백엔드가 검증한 뒤 사용자 승인 시에만 확정 데이터를 저장한다.

## 3. 반드시 분리할 데이터

| 구분 | 데이터 | 기준 |
|---|---|---|
| 원본 | `Conversation`, `Message`, `Attachment`, `ManualInput` | AI 가공 전 데이터. 삭제 정책 외에는 원문을 보존 |
| 분석 실행 | `ExtractionRun` | 어떤 범위와 파일을 어떤 모델·스키마로 분석했는지 기록 |
| AI 초안 | `Proposal`, `ExperienceDraft`, `JobRequirementDraft` | 수정·삭제·부분 승인 가능 |
| 확정 데이터 | `Domain`, `Project`, `Experience`, `Fact`, `Skill` | 모든 페이지가 동일 ID로 조회 |
| 근거 관계 | `Evidence`, `ExperienceEvidenceLink`, `FactEvidenceLink` | 원본 삭제와 경험에서 연결 해제를 분리 |
| 공고 매칭 | `JobPosting`, `JobRequirement`, `RequirementExperienceLink` | 요구사항별 추천·선택·제외 상태 보존 |

## 4. 구현 전에 제대로 설계해야 할 부분

### P0. AI 연결 전에 필수

1. **증분 대화 분석 기준**
   - 단순한 “마지막 버튼 클릭 시각” 대신 `last_successful_message_sequence`를 저장한다.
   - `ExtractionRun`에 `from_sequence`, `to_sequence`, `message_ids`, `attachment_ids`를 기록한다.
   - 실패한 실행은 체크포인트를 이동하지 않고, 재시도해도 중복 경험이 생기지 않도록 `client_request_id`를 사용한다.
   - 이전 대화는 문맥으로 참고할 수 있지만, 새 경험의 근거 범위와는 구분한다.

2. **다중 경험 초안**
   - 한 번의 실행 결과는 `experience_drafts[]` 0..N개다.
   - 각 초안은 `domain`, `project`, `title`, `summary`, `situation`, `actions[]`, `results[]`, `role`, `skills[]`, `facts[]`, `missing_information[]`, `source_ref_ids[]`를 가진다.
   - 초안마다 안정적인 `draft_id`가 필요하며 배열 인덱스만 식별자로 사용하지 않는다.
   - 같은 경험 분류·프로젝트명은 정규화된 ID 기준으로 병합하고, 이름만 같다고 자동 병합하지 않는다.

3. **근거와 출처 추적**
   - 대화 요약문은 원본 대화를 대체하지 않는 파생 Evidence다.
   - 파일은 `Attachment → 파싱 결과 → Evidence`로 승격하고 원본 파일, 해시, 업로드 날짜, 페이지 위치를 보존한다.
   - 최소한 Fact별로 `source_id`, `quote`, `page/start_offset/end_offset`, `confidence`를 연결한다.
   - “연결 해제”, “원본 삭제”, “초안 삭제”는 서로 다른 동작이어야 한다.

4. **승인 트랜잭션**
   - 사용자 승인 시 Domain/Project 조회·생성부터 Experience, Fact, Evidence Link, Skill Link까지 한 트랜잭션으로 저장한다.
   - 일부 초안만 저장할 수 있어야 하며, 이미 저장된 초안을 다시 승인해도 중복 생성되지 않아야 한다.
   - 새로고침·직접 URL 접근 후에도 같은 확정 데이터가 보여야 한다.

### P1. 결과 품질과 화면 연동

5. **Skill과 SkillGroup**
   - AI는 원문에서 역량 후보와 신뢰도를 제안한다.
   - 백엔드는 별칭을 정규 `Skill`로 통합하고, 버전이 있는 분류 체계로 `SkillGroup`에 연결한다.
   - `데이터·분석`, `기획·제품` 같은 그룹은 프론트 하드코딩이 아니라 이 분류 결과에서 조회한다.
   - 사용자 수정값, AI 제안값, 근거 ID를 함께 보존한다.

6. **채용공고 분석**
   - 요구사항은 최소 `title`, `summary`, `sourceExcerpt`, `importance`, `keywords`, `order`를 가진다.
   - `sourceExcerpt`는 공고의 실제 원문이어야 하며 가능하면 위치 정보도 기록한다.
   - RAG 결과는 요구사항별 `experience_id`, `similarity_score`, `reason`, `source`, `status`, `model/index_version`으로 저장한다.
   - AI 추천과 사용자 직접 연결을 구분하고, 사용자 선택·제외 상태를 재분석 후에도 보존한다.

7. **단일 화면 모델**
   - 경험 관리, 경험 상세, 내 역량, 채팅 초안, 공고 매칭은 동일한 Experience ID와 공통 mapper를 사용한다.
   - 프론트는 키워드 규칙으로 역량 그룹이나 경험을 임의 생성하지 않는다.
   - 초안 컴포넌트는 채팅과 경험 관리에서 같은 데이터 계약을 사용한다.

### P2. 운영 정책

8. 원본 대화·파일·AI 출력의 보존 기간과 soft delete/복원 정책
9. 모델명, 프롬프트 버전, JSON Schema 버전, RAG 인덱스 버전의 감사 로그
10. 개인정보 마스킹, 파일 악성코드 검사, 사용자별 저장 용량 제한
11. PDF OCR 지원 범위와 파싱 실패·부분 성공 표시 방식

## 5. 권장 핵심 스키마 보완

```text
ExtractionRun
- id, conversation_id
- from_sequence, to_sequence
- message_ids[], attachment_ids[]
- status: queued | running | succeeded | failed
- model_version, prompt_version, schema_version
- client_request_id, started_at, completed_at

ExperienceDraft
- draft_id
- domain{id?, name}, project{id?, name}
- title, summary, situation, actions[], results[], role
- skills[], facts[], missing_information[]
- source_ref_ids[], field_citations{}
- confidence, status

JobRequirement
- id, job_posting_id, title, summary, source_excerpt
- source_locator?, importance, keywords[], order, confidence

RequirementExperienceLink
- requirement_id, experience_id
- source: ai | user
- status: suggested | selected | rejected
- similarity_score?, reason?, evidence_ids[]
- model_version?, index_version?
```

## 6. 현재 구현 대비 핵심 부족 사항

- 프론트 목 Proposal과 다중 초안 UI는 일부 구현됐지만 실제 영속 DB 트랜잭션이 아니다.
- “마지막 성공 분석 이후”를 보장하는 ExtractionRun/체크포인트 모델이 없다.
- Attachment와 Evidence의 정식 승격·파싱·인용 위치 계약이 완성되지 않았다.
- SkillGroup과 직군·직업·역할 데이터가 확정 스키마보다 화면 파생값에 의존하는 부분이 있다.
- 공고 요구사항의 표시 필드는 보강됐지만 RequirementExperienceLink의 점수·이유·모델 버전 저장이 필요하다.
- 페이지별 Experience 변환 로직을 하나의 mapper/repository로 더 통합해야 한다.

## 7. 완료 판정

- 동일 입력이 0개·1개·여러 경험으로 정상 분리된다.
- 증분 분석 재시도와 중복 클릭으로 같은 Experience가 중복 저장되지 않는다.
- 모든 Fact에서 원본 대화·텍스트·파일 위치를 열 수 있다.
- 초안 일부 저장, 전체 저장, 나머지 삭제 후 새로고침해도 결과가 유지된다.
- 저장·수정·삭제한 경험이 경험 관리, 상세, 내 역량, 공고 매칭에 동일하게 반영된다.
- 공고 요구사항별 AI 추천 이유와 사용자가 직접 연결한 경험이 구분된다.

## 8. 프론트엔드 공통 경계

AI 엔진 연결 전에 다음 경계를 코드로 분리한다.

- `experienceContent`: 초안과 확정 경험이 공유하는 제목·요약·상황·행동·결과·역할·역량·사실 계약
- `proposalMapper`: AI/API Proposal을 검토 화면 모델로 변환하고 수정값을 다시 Proposal payload로 변환
- `experienceMapper`: 확정 Experience API 데이터와 화면 모델 사이의 변환
- `evidenceMapper`: 대화·직접 텍스트·파일 근거의 snake_case/camelCase를 하나의 Evidence view model로 정규화
- `EvidenceWorkspace`: 관련 근거와 원본 근거 관리가 공유하는 목록·선택·원문·연결 내용 화면. `readonly`와 `manage` 모드로 권한만 구분
- `experienceProposalService`: 현재 목 분석기를 감싸는 AI 어댑터 경계. 추후 실제 AI API로 내부 구현만 교체
- `ExperienceRichText`: 초안과 상세에서 동일한 Markdown·혼합 목록 렌더링

초안 검토와 확정 경험 관리는 같은 콘텐츠·근거 모델을 사용하지만 권한은 분리한다.

- 초안: 확인, 수정, 초안 삭제, 부분 승인
- 확정 경험: 수정 저장, 근거 추가·수정, 연결 해제, 새 정리본 생성
- 원본 대화는 읽기 전용이며 수동 텍스트 근거만 수정할 수 있다.
- 초안의 파일도 저장 전 원본 바이트로 열람·다운로드할 수 있고, 저장 후에는 Source API를 통해 같은 동작을 유지한다.

## 9. 파일 중복 관리와 임베딩 파이프라인

### 프론트엔드 계약

- 커리어 챗과 경험정리 AI는 같은 파일 선택 모듈을 사용한다.
- 파일 선택 시 브라우저에서 SHA-256 `content_hash`를 계산하고 업로드 전 중복 확인 API를 호출한다.
- 판정 상태는 `new_file`, `exact_duplicate`, `same_name_different_content`, `already_linked`로 통일한다.
- `exact_duplicate`는 원본을 다시 업로드하지 않고 기존 `attachment_id/evidence_id`를 현재 대화 또는 경험에 연결한다.
- 같은 이름이지만 해시가 다르면 새 파일로 저장하되 `original_attachment_id`로 수정본 관계를 남긴다.
- 프론트 해시는 UX 최적화용이며 보안·무결성의 최종 판정값으로 신뢰하지 않는다.

### 백엔드 필수 작업

1. 업로드 사전 확인 API
   - 입력: `filename`, `content_hash`, `size_bytes`, `mime_type`, `last_modified`
   - 출력: 판정 상태와 재사용 가능한 기존 `attachment/evidence` 식별자
   - 중복 검색 범위는 반드시 사용자 또는 테넌트 내부로 제한한다.

2. 서버의 최종 해시 검증
   - 업로드 스트림에서 SHA-256을 다시 계산하고 프론트 전달값과 비교한다.
   - `(owner_id, content_hash)` 고유 제약과 idempotency key를 사용해 동시 업로드 중복도 방지한다.
   - 동일 해시라면 바이너리·파싱·청크·임베딩을 새로 만들지 않고 기존 리소스를 재사용한다.

3. 권장 파일 스키마

```text
Attachment
- id, owner_id, filename, mime_type, size_bytes
- content_hash, storage_key, uploaded_at
- original_attachment_id?, version
- parse_status, parse_error?

EvidenceDocument
- id, attachment_id?, manual_input_id?, message_id?
- source_type, normalized_text, language
- parser_version, created_at

EvidenceChunk
- id, evidence_document_id, chunk_index
- text, page_number?, start_offset?, end_offset?
- content_hash, chunker_version

EmbeddingRecord
- id, target_type, target_id
- embedding_model, embedding_version, dimensions
- content_hash, vector, created_at
```

4. 삭제와 연결 해제
   - 동일 파일 하나가 여러 경험과 연결될 수 있으므로 `ExperienceEvidenceLink`만 먼저 해제한다.
   - 연결이 0개가 된 원본도 즉시 hard delete하지 않고 보존·휴지통 정책에 따라 정리한다.
   - 파일 수정본은 기존 파일을 덮어쓰지 않고 별도 Attachment/EvidenceDocument 버전으로 저장한다.

### AI 엔진 임베딩 정책

- PDF/TXT 바이너리 자체를 텍스트 임베딩하지 않는다. 본문 추출 또는 OCR 후 `EvidenceChunk` 단위로 임베딩한다.
- 원본 근거 청크 임베딩은 사실 확인·인용 검색에 사용한다.
- 확정 Experience는 제목, 분류, 프로젝트·활동, 요약, 상황, 행동, 결과, 역할, 역량, 근거에서 확인된 내용을 합친 별도의 `Experience Search Document`로 임베딩한다.
- 경험 요약 임베딩과 원본 근거 임베딩은 같은 벡터 컬렉션에 무구분으로 섞지 않고 `target_type` 또는 별도 인덱스로 구분한다.
- 검색은 `Experience Search Document`로 후보 경험을 찾은 뒤 연결된 `EvidenceChunk`를 재검색·재정렬하는 2단계 구조를 사용한다.
- 캐시 키는 최소 `content_hash + parser_version + chunker_version + embedding_model/version`을 포함한다.
- 원본 텍스트 또는 파일 내용이 변하지 않았다면 추출, 청크 분할, 임베딩을 반복하지 않는다.
- 경험 요약·역량처럼 파생 데이터만 변경되면 Experience 임베딩만 갱신하고 원본 EvidenceChunk 임베딩은 재사용한다.

### 완료 판정

- 같은 파일을 채팅과 경험정리 AI에서 다시 선택해도 원본 레코드와 임베딩이 중복 생성되지 않는다.
- 같은 이름의 다른 파일은 수정본으로 구분되며 이전 원본을 덮어쓰지 않는다.
- 이름이 달라도 내용 해시가 같으면 기존 파일을 재사용한다.
- 여러 경험이 같은 Evidence를 안전하게 공유하고 한 경험의 연결 해제가 다른 경험의 근거를 삭제하지 않는다.
- RAG 답변은 Experience 후보와 실제 EvidenceChunk 인용을 함께 반환한다.
