# Career Memory AI 데이터 아키텍처

## 1. 목적과 범위

이 문서는 Career Memory가 대화·파일·채용공고 원문을 보존하고, 이를 근거·경험·
기술·정량 지표·공고 요구사항으로 구조화하는 데이터 기준을 정의한다.

현재는 SQLite, SQLAlchemy, Pydantic, Chroma를 사용한다. 단기 목표는 대규모
데이터 레이크나 그래프 DB를 도입하는 것이 아니라, 기존 구조를 다음 두 방향으로
점진적으로 공식화하는 것이다.

- 경량 도메인 온톨로지: 개념, 별칭, 관계, 판정 정책을 명시한다.
- 계층형 데이터 구조: 원본, 파생 데이터, 승인 데이터를 분리하고 lineage를 보존한다.

## 2. 변경 불가능한 핵심 원칙

1. 사용자 원문은 정규화 결과와 무관하게 보존한다.
2. AI 출력은 원본이 아니라 재생성 가능한 파생 데이터다.
3. 미등록 표현은 삭제하지 않고 `unresolved`로 보존한다.
4. 검증된 경우에만 canonical concept ID를 원문에 투영한다.
5. 모든 확정 사실은 source ID와 exact quote로 원본까지 추적할 수 있어야 한다.
6. 임베딩은 후보 검색 신호이며 명시적 기술·수치 조건의 최종 판정자가 아니다.
7. Chroma는 source of truth가 아니라 DB와 원본에서 재구축 가능한 검색 인덱스다.
8. 모든 저장·검색·삭제는 인증된 `user_id` 경계를 지킨다.
9. 스키마 변경은 additive migration을 우선한다.
10. 데이터 백필은 기본 dry-run이며 명시적인 적용 옵션이 있을 때만 저장한다.

## 3. 데이터 계층

### 3.1 Bronze — 원본

- `Conversation`, `Message`
- `LocalBlobStore`에 저장한 `Attachment` 원본과 DB 메타데이터
- 직접 입력한 경험 텍스트
- 채용공고 원문과 원본 URL
- 원본 해시, MIME type, 생성 시각

Bronze 데이터는 사용자 삭제 정책 외에는 AI 분석으로 덮어쓰지 않는다.

현재 `Attachment`는 파일 형식 검증 직후 원본을 `LocalBlobStore`에 기록하고,
사용자별 SHA-256 해시, storage key, MIME과 크기를 DB에 먼저 저장한다. 신규 원본을
DB BLOB에 중복 저장하지 않지만 기존 BLOB 레코드는 호환해서 읽는다. 텍스트 추출은
그 다음 단계에서 실행하며 실패해도 원본은 남는다. `parse_status`는
`queued -> processing -> ready/partial/failed/unsupported`로 변하고, 오류·파서
버전·품질 점수·warning·segment locator는 Silver 성격의 파생 필드로 분리한다.
같은 사용자의 같은 해시는 기존 원본을 재사용한다.

### 3.2 Silver — 근거와 정규화

- 파일 추출 텍스트와 파싱 상태
- `EvidenceDocument`, `EvidenceChunk`, `EvidenceCitation`
- `SkillMention`, `QuantifiedMetric`
- ontology concept, alias, relation
- 분석·파서·청커·스키마 버전
- `EmbeddingRecord`
- `FileProcessingJob`, `TranscriptionSegment`

Silver 데이터는 원본과 버전을 이용해 다시 만들 수 있어야 한다.

통합 파일 파서는 확장자·시그니처·Open XML/HWPX 컨테이너를 함께 검증하고,
TXT/MD·PDF·이미지·DOCX·PPTX·HWPX를 형식별로 처리하고 DOC/PPT/HWP는 설치된
격리 변환기를 통해 현대 형식으로 바꾼 뒤 같은 파서를 사용한다. PDF는 페이지별 native
text/OCR hybrid 방식이며 한 페이지 실패를 전체 문서 실패로 확대하지 않는다.
OCR 실행기는 외부 capability이므로 `GET /capabilities`의 실제 설치·언어팩 상태와
분리해 판단한다. 상세 운영 기준은 `FILE_EXTRACTION_GUIDE.md`를 따른다.

음성·영상은 FFmpeg로 단일 channel 16kHz audio로 정규화한 뒤 STT한다. 전사
결과는 본문뿐 아니라 provider, model, 시작·종료 ms를 `TranscriptionSegment`로
저장해 해당 원본 구간까지 역추적할 수 있게 한다.

### 3.3 Gold — 사용자 승인 지식

- 확정된 `Experience`
- 승인된 사실과 원본 인용
- `JobRequirement`
- `RequirementExperienceLink`
- 사용자가 직접 선택하거나 거절한 관계

AI 초안은 Gold가 아니다. 사용자 승인과 백엔드 트랜잭션이 완료되어야 Gold가 된다.

### 3.4 Serving — 검색과 화면 제공

- 확정 경험 검색 문서
- Evidence chunk 검색 인덱스
- 사용자별 Chroma collection
- 공고–경험 매칭 결과
- 챗봇 RAG 문맥

Serving 데이터는 Bronze, Silver, Gold에서 다시 생성할 수 있어야 한다.

## 4. 현재 데이터 흐름

```text
Message / Attachment / Job posting
              │
              ▼
 LocalBlobStore 원문 보존 + DB 작업 생성
              │
              ▼
   lease 기반 파싱·변환·STT 작업
              │
              ▼
 Evidence source · exact citation
              │
              ▼
 ExperienceDraft / JobRequirement
              │
        사용자 검토·승인
              ▼
       Confirmed Experience
              │
      검색 문서와 벡터 인덱스
              ▼
   Chat RAG / Job–Experience match
```

## 5. 경량 도메인 온톨로지

### 5.1 현재 구현

`ontology_concepts`, `ontology_aliases`, `ontology_relations` 테이블과
`OntologyRepository`가 다음 기능을 제공한다.

- canonical skill ID
- canonical name
- curated alias
- related skill relation
- ontology version과 관계별 `matching_policy`
- unknown expression preservation
- exact, alias, related, unresolved 구분

기존 코드 레지스트리는 `career-ontology-v1` seed로 이동했다. 서버 시작 시 stable ID로
멱등 입력하며 DB를 우선 조회한다. DB 장애나 마이그레이션 전 환경에서는 curated seed만
fallback으로 사용하고, 미등록 표현을 유사 개념으로 임의 추정하지 않는다. 관리 UI와
사용자 승인 기반 개념 승격은 아직 범위 밖이다.

### 5.2 구현 엔티티

```text
OntologyConcept
- id
- concept_type
- canonical_name
- description
- status
- ontology_version
- created_at
- updated_at

OntologyAlias
- id
- concept_id
- alias
- locale
- normalization_key
- created_at

OntologyRelation
- id
- source_concept_id
- relation_type
- target_concept_id
- matching_policy
- provenance
- ontology_version
- created_at
```

초기 `concept_type`은 `skill`만 사용한다. 실제 요구가 생기면 `role`,
`organization`, `industry`, `certificate`, `task`로 확장한다.

### 5.3 관계와 판정 정책

| 관계 | 의미 | 필수 기술 충족 |
|---|---|---|
| canonical ID 동일 | 같은 표준 개념 | 예 |
| `alias_of` | 같은 개념의 다른 표기 | 예 |
| `related_to` | 관련됐지만 다른 개념 | 아니요 |
| `broader_than` | 상위 개념 | 명시적 정책이 있을 때만 |
| `narrower_than` | 하위 개념 | 명시적 정책이 있을 때만 |
| `unresolved` | 아직 연결되지 않은 원문 | 아니요 |

예시:

```text
페스트API --alias_of--> FastAPI
FastAPI --related_to--> REST API
JavaScript --related_to--> TypeScript
FastAPI --narrower_than--> Python Web Framework
```

별칭은 동일 개념이므로 충족으로 인정한다. `related_to`는 검색 후보 확장에만 사용한다.

## 6. Evidence와 lineage

### 6.1 구현 엔티티

```text
EvidenceDocument
- id
- user_id
- source_type
- source_record_id
- original_text 또는 storage_key
- content_hash
- parser_version
- parse_status
- created_at
- updated_at

EvidenceChunk
- id
- document_id
- chunk_index
- text
- start_offset
- end_offset
- content_hash
- chunker_version
- created_at

EvidenceExperienceLink
- user_id
- experience_id
- document_id

EmbeddingRecord
- id
- target_type
- target_id
- provider
- model
- dimensions
- content_hash
- index_version
- indexed_at
```

경험 생성·수정·원본 연결·연결 해제 경로는 `source_refs`를 위 구조로 동기화한다.
문서와 청크 ID는 source와 content hash로 결정되므로 같은 입력을 반복해도 중복되지
않는다. 원본이 바뀌면 이전 문서·청크·EmbeddingRecord를 stale로 표시한다.

### 6.2 추적 경로

```text
Experience fact
  -> EvidenceCitation
  -> EvidenceChunk
  -> EvidenceDocument
  -> Message / Attachment / Job posting
```

`source_ref_id`는 마이그레이션 기간에도 유지한다. 신규 Evidence ID를 도입할 때는
기존 ID를 갑자기 바꾸지 않고 호환 projection 또는 매핑을 제공한다.

### 6.3 검증 규칙

- citation의 quote는 원문에 실제로 존재해야 한다.
- 가능하면 quote와 함께 start/end offset을 기록한다.
- structured skill과 metric의 source ID는 소유한 Evidence와 일치해야 한다.
- 같은 내용은 `content_hash`로 중복 처리를 방지한다.
- 원본이 변경되면 파생 Evidence와 임베딩을 stale로 표시한다.

## 7. 임베딩과 인덱스

두 인덱스를 분리한다.

1. Experience search index
   - 확정 경험의 의미 검색과 공고 후보 검색
2. Evidence chunk index
   - 원문 확인, 인용 검색, 후보 경험의 근거 재검증

증분 갱신 흐름:

```text
원본 또는 확정 경험 저장
  -> Evidence 문서·청크와 경험 link 동기화
  -> content_hash 비교
  -> 다음 검색 또는 관리 명령에서 신규·변경 대상만 임베딩
  -> stale vector 삭제
  -> EmbeddingRecord 갱신
```

검색 요청 전 동기화는 DB의 현재 Evidence projection과 Chroma를 비교하므로 서버가
중단되거나 벡터 저장소가 삭제돼도 자동 복구할 수 있다. 즉시 재구축이 필요하면
`python -m AI_Engine.rebuild_evidence_index --apply`를 사용한다. 기본 실행은
dry-run이며 vector를 변경하지 않는다.

다음 중 하나가 바뀌면 새 인덱스 버전을 사용한다.

- embedding provider 또는 model
- 검색 문서 구성
- chunk 크기나 overlap
- 정규화 projection 구성

같은 컬렉션에 서로 다른 임베딩 모델의 벡터를 섞지 않는다.

## 8. 저장과 삭제 정책

- LocalBlobStore가 첨부 원본의 source of truth이고 DB는 해시·경로·처리 상태를 가진다.
- `file_processing_jobs`는 서버 재시작에도 남으며 만료 lease만 제한 횟수 안에서 복구한다.
- 기존 DB BLOB은 dry-run과 해시 검증을 거친 `--apply`에서만 로컬 저장소로 옮긴다.
- 원본 삭제, 경험 연결 해제, 경험 삭제, 초안 삭제는 서로 다른 동작이다.
- 대화 삭제가 이미 승인된 경험을 자동 삭제해서는 안 된다.
- 계정 삭제는 원본, 파생 데이터, ontology mention, 벡터를 사용자 범위에서 제거한다.
- 전역 ontology concept은 사용자 소유 데이터와 분리한다.
- 사용자별 unresolved 표현을 전역 개념으로 자동 승격하지 않는다.

## 9. 마이그레이션·rollback

적용 순서:

1. `create_all`로 신규 온톨로지·Evidence 테이블만 추가한다.
2. stable ID의 curated registry를 멱등 seed한다.
3. `python -m AI_Engine.knowledge_layer_backfill`로 예상 건수와 충돌을 확인한다.
4. 검토 후에만 `--apply`로 ontology와 기존 `source_refs` projection을 저장한다.
5. `python -m AI_Engine.rebuild_evidence_index`로 사용자별 예상 청크를 확인한다.
6. 검토 후에만 `--apply`로 Chroma를 전체 재구축한다.
7. API·lineage·사용자 격리·검색 회귀 테스트를 실행한다.

재실행 기준:

- seed, Evidence ID와 chunk ID는 결정적이므로 같은 버전의 재실행은 멱등이다.
- parser/chunker/ontology/index 버전이 바뀌면 이전 projection을 stale로 남기고 새
  버전으로 재생성한다.
- dry-run은 사용자 원문·경험·projection·vector를 쓰지 않는다. 단, 앱 초기화는
  누락된 신규 테이블을 생성할 수 있다.

rollback 기준:

- 공개 API와 기존 `skills`, `facts`, `metrics`, `source_refs` JSON은 변경하지 않았으므로
  신규 projection 읽기를 끄고 기존 경로로 즉시 되돌릴 수 있다.
- Chroma는 source of truth가 아니므로 해당 index-version collection을 폐기하고 이전
  인덱스를 사용하거나 DB에서 다시 구축한다.
- 신규 테이블은 기존 레코드를 덮어쓰지 않으므로 장애 중에는 보존한 채 읽기만 중단한다.
  자동 destructive down migration은 제공하지 않는다.

마이그레이션은 원문, `skills`, `facts`, `metrics`, `source_refs`를 덮어쓰지 않는다.

## 10. 내부 저장과 공개 API 경계

| 구분 | 내부 저장 | 공개 API |
|---|---|---|
| 원문 표현 | raw skill, source text, exact quote | 기존 필드를 그대로 반환 |
| 정규화 결과 | concept ID, match type, ontology version | 기존 `skill_mentions`·매칭 설명에 필요한 값만 반환 |
| ontology 관리 | alias normalization key, provenance, relation edge·policy | 직접 노출하지 않음 |
| Evidence | document/chunk/link ID, original text, offset, hash, stale 상태 | 기존 source ref와 검증된 citation을 유지 |
| embedding | provider/model/hash/index version/collection/vector ID | 노출하지 않음 |
| 저장 경로 | LocalBlobStore storage key | 노출하지 않고 attachment API로 접근 |

프론트가 내부 ID를 저장하거나 해석하지 않아도 기존 화면이 동작하는 것이 호환성
기준이다. 향후 원본 상세 화면이 필요할 때만 권한 검사된 Evidence locator DTO를 별도
추가하며, DB 모델을 그대로 직렬화하지 않는다.

## 11. 구현 범위와 남은 항목

구현된 범위는 다음과 같다.

1. ontology concept·alias·relation DB 모델
2. 기존 기술 레지스트리 seed와 repository
3. EvidenceDocument·EvidenceChunk·EmbeddingRecord 영속화
4. content hash 기반 증분 인덱싱
5. 온톨로지 기반 매칭 정책 분리
6. dry-run 백필
7. 정답 세트와 lineage 회귀 테스트 확장

남은 운영 항목은 실제 익명화 corpus 확대, 관리 UI, 사용자 승인 기반 unresolved 개념
승격, 운영 규모의 별도 비동기 embedding queue다.

다음은 단기 범위에서 제외한다.

- Neo4j와 별도 그래프 DB
- RDF, OWL, SPARQL
- Spark, Kafka
- S3, MinIO 전환
- 범용 추론 엔진
- generic triple store
- 미등록 표현의 자동 전역 개념 승격

## 12. 완료 기준

- 모든 원문과 규격 외 표현이 보존된다.
- 기존 별칭·수치·인용 테스트가 유지된다.
- Fact에서 실제 원본까지 추적할 수 있다.
- 동일 입력을 반복 처리해도 중복 chunk와 embedding이 생성되지 않는다.
- 관련 기술이 필수 기술 충족으로 오판되지 않는다.
- Chroma를 삭제한 뒤 DB에서 다시 구축할 수 있다.
- 사용자별 데이터와 벡터가 섞이지 않는다.
- 백필 dry-run 결과와 실제 적용 결과를 비교할 수 있다.
- API·프론트엔드 계약을 깨지 않고 additive하게 도입된다.
