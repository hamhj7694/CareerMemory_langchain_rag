# 추후 업데이트 로드맵

- 기준 버전: 기술·수치 무손실 정규화와 근거 검증 구조 도입 이후
- 상태: Active roadmap
- 현재 실행 우선순위: `../TODO.md`
- AI 세부 작업: `../../AI_Engine/AI_ENGINE_WORK_MAP.md`
- 데이터 설계 기준: `../AI_DATA_ARCHITECTURE.md`

이 문서는 현재 구현할 작업을 세부적으로 추적하지 않는다. 현재 작업은 TODO와 AI 작업
맵에서 관리하고, 이 문서에서는 제품과 데이터 구조가 장기적으로 발전할 방향과 다음
단계에 진입하기 위한 조건을 관리한다.

## 최우선 방향 — 온톨로지·데이터 레이크 방식의 점진적 공식화

### 목표

Career Memory를 단순한 대화형 RAG 서비스가 아니라 다음 구조를 가진 개인 커리어
지식 시스템으로 발전시킨다.

```text
사용자 원본
  -> 검증 가능한 Evidence
  -> 경력 도메인 개념과 관계
  -> 사용자 승인 커리어 지식
  -> 검색·공고 매칭·문서 생성
```

여기서 데이터 레이크 방식은 대규모 분산 플랫폼을 즉시 도입한다는 의미가 아니다.
원본·파생 데이터·승인 데이터를 계층화하고, 모든 결과의 lineage와 재생성 가능성을
보장하는 방식부터 적용한다.

### 유지할 원칙

- 원문과 규격 밖 표현은 정규화 성공 여부와 무관하게 보존한다.
- AI 분석 결과는 원본이 아니라 버전이 있는 파생 데이터로 관리한다.
- canonical concept ID는 검증된 경우에만 원문에 선택적으로 연결한다.
- 미등록 표현은 가장 가까운 기술로 추측하지 않고 `unresolved`로 유지한다.
- 임베딩은 후보 검색에 사용하고 최종 판정은 개념 관계·수치 조건·원문 근거로 수행한다.
- Chroma는 source of truth가 아니라 DB에서 재구축 가능한 검색 인덱스로 취급한다.
- 모든 단계에서 사용자별 데이터 격리와 삭제 가능성을 유지한다.

### 단계 1 — 경량 Skill Ontology

현재 코드 레지스트리의 canonical skill, alias, related relation을 DB 엔티티로 승격한다.

```text
OntologyConcept
OntologyAlias
OntologyRelation
```

초기에는 Skill만 다루고 다음 정책을 유지한다.

- canonical ID 동일 또는 `alias_of`: 필수 기술 충족
- `related_to`: 후보 검색 확장만 허용
- `broader_than`, `narrower_than`: 명시적인 정책이 있을 때만 충족
- `unresolved`: 자동 충족 금지, raw expression 보존

완료 조건:

- 기존 기술 ID와 별칭을 seed migration으로 동일하게 재현한다.
- ontology version과 관계 provenance를 기록한다.
- DB 장애나 미등록 표현 때문에 원문이 유실되지 않는다.
- 정규화 서비스와 매칭 정책이 분리된다.

### 단계 2 — Evidence와 데이터 lineage 영속화

실행 시 조립되는 source reference와 chunk를 정규 엔티티로 저장한다.

```text
EvidenceDocument
  -> EvidenceChunk
       -> EvidenceCitation
       -> EmbeddingRecord
```

완료 조건:

- Experience fact와 Job match에서 원본 메시지·파일·공고까지 추적할 수 있다.
- exact quote와 offset을 검증할 수 있다.
- content hash, parser version, chunker version을 기록한다.
- 원본 변경 시 관련 파생 데이터와 인덱스의 stale 상태를 판단할 수 있다.

### 단계 3 — Bronze/Silver/Gold 계층 운영

현재 DB 안에서 먼저 논리 계층을 적용한다.

| 계층 | 데이터 |
|---|---|
| Bronze | 메시지, 파일 바이너리, 직접 입력, 공고 원문 |
| Silver | 추출 텍스트, Evidence, concept mention, metric, embedding record |
| Gold | 사용자가 승인한 Experience, Requirement, 관계 |
| Serving | Experience/Evidence 검색 인덱스, RAG 문맥, 공고 매칭 |

완료 조건:

- 각 데이터의 source of truth와 재생성 경로가 명확하다.
- AI 재분석이 Bronze 원본을 덮어쓰지 않는다.
- Gold 승인은 사용자 동작과 백엔드 트랜잭션으로만 발생한다.
- Serving 계층을 삭제해도 DB에서 다시 만들 수 있다.

### 단계 4 — 증분 인덱싱과 재구축

저장·수정·삭제 이벤트에 따라 변경된 검색 문서만 갱신한다.

완료 조건:

- 같은 content hash는 다시 임베딩하지 않는다.
- 변경된 chunk만 갱신하고 삭제된 vector를 제거한다.
- embedding model과 검색 문서 구성이 바뀌면 새 index version을 사용한다.
- 사용자별 또는 전체 인덱스 재구축 명령을 제공한다.

### 단계 5 — 온톨로지 범위 확장

Skill ontology가 안정화되고 실제 기능에서 필요성이 확인된 개념만 순차적으로 추가한다.

권장 순서:

```text
Skill
  -> Role / Task
  -> Organization / Industry
  -> Certificate
  -> Achievement / Metric semantics
```

새 개념을 추가할 때는 실제 사용자 질의나 공고 매칭에서 필요한 관계와 평가 사례를 먼저
정의한다. 범용 개념 그래프를 먼저 만들지 않는다.

### 단계 6 — 운영 규모에 따른 물리 인프라 전환

다음 조건이 실제로 발생할 때만 대규모 인프라를 검토한다.

| 후보 | 진입 조건 |
|---|---|
| S3·MinIO | DB BLOB 백업·용량·배포 문제가 실제 운영 제약이 됨 |
| PostgreSQL | SQLite 동시성·운영 migration이 제약이 됨 |
| 작업 queue | 분석 시간이 요청 timeout과 재시도 정책을 넘음 |
| Neo4j | 다단계 관계 탐색이 핵심 사용자 기능이 되고 SQL 유지가 어려움 |
| RDF·OWL | 외부 지식 체계와의 상호운용 또는 형식 추론이 필요함 |
| Kafka·분산 처리 | 단일 프로세스 이벤트 처리로 감당하기 어려운 규모가 확인됨 |

기술 자체를 포트폴리오에 추가하기 위해 도입하지 않는다. 현재 문제와 측정된 병목이
진입 조건을 만족할 때만 채택한다.

### 품질 측정 방향

기존 사실·인용·수치 평가에 다음 지표를 추가한다.

- concept resolution precision/recall
- alias resolution accuracy
- relation classification accuracy
- unresolved preservation rate
- Evidence lineage completeness
- stale embedding rate
- ontology migration success rate
- index rebuild consistency
- Retrieval Recall@K, Precision@K, MRR

소규모 합성 정답 세트는 회귀 방지에 사용하고, 일반화 성능을 주장하려면 실제와 유사한
익명화 사례를 별도 데이터셋으로 확대한다.

### 단기 범위에서 제외

- Neo4j 또는 범용 graph database 즉시 도입
- RDF, OWL, SPARQL 구현
- Spark, Kafka 기반 분산 파이프라인
- S3, MinIO 즉시 전환
- generic triple store
- 미등록 개념의 자동 전역 ontology 승격

구체적인 현재 작업 순서는 `../../AI_Engine/AI_ENGINE_WORK_MAP.md`의
`ARCH`, `ONT`, `EVD`, `IDX`, `MIG`, `QA` 작업을 따른다.

## 우선 후보 — 채용공고 비교

### 목적

사용자가 관심 공고 여러 개를 한 화면에서 비교하고, 자신의 경험이 어느 공고에 더 직접적인 근거를 가지는지 판단하도록 돕는다. 합격 가능성을 계산하거나 특정 공고를 자동 선택하지 않고, 요구사항과 근거를 투명하게 비교한다.

### 사용자 흐름

1. 분석이 완료된 공고 목록에서 2~4개를 선택한다.
2. `[선택 공고 비교]`를 실행한다.
3. 회사·직무·주요 업무·필수/우대 조건·기술·역량을 열 단위로 비교한다.
4. 공통 요구사항과 공고별 고유 요구사항을 확인한다.
5. 각 공고에 대한 경험 근거 수준과 부족 정보를 비교한다.
6. 한 공고를 선택해 기존 경험 대조·자기소개서 흐름으로 이동한다.

### 권장 라우트

```text
/jobs
  └─ 저장·분석된 공고 목록과 비교 선택

/jobs/compare?ids=JOB-001,JOB-002
  └─ 공고 비교 화면
```

공유 가능한 비교 상태는 query에 공고 ID만 저장한다. 비교 결과 자체는 서버 데이터에서 다시 구성한다.

### 비교 항목

| 구분 | 비교 내용 |
|---|---|
| 기본 정보 | 회사명, 직무명, 공고 분석일 |
| 주요 업무 | 요구사항별 원문과 중요도 |
| 필수 조건 | 공통 조건과 공고별 차이 |
| 우대 조건 | 공고별 추가 기대사항 |
| 기술·역량 | 키워드와 의미상 유사 항목 |
| 경험 적합 근거 | direct, partial, indirect, no_evidence, needs_confirmation |
| 부족 정보 | 경험에 추가 확인이 필요한 항목 |
| 자기소개서 | 문항 수와 선택 문항 |

### UX 원칙

- 총점이나 합격 확률을 기본 제공하지 않는다.
- 공고별 요구사항 수가 달라도 같은 요구사항인 것처럼 억지로 정렬하지 않는다.
- 유사 요구사항은 `AI 제안 그룹`으로 표시하고 사용자가 펼쳐 원문을 확인할 수 있게 한다.
- 판정 상태는 색상, 아이콘, 텍스트를 함께 사용한다.
- 비교 열이 많아지지 않도록 V1 확장판은 최대 4개로 제한한다.
- 좁은 화면에서는 전체 표를 축소하지 않고 공고 2개씩 전환한다.

### 필요한 프론트엔드 구성

- `JobList`
- `JobCompareSelector`
- `JobComparisonTable`
- `SharedRequirementGroup`
- `JobEvidenceSummary`
- `ComparisonFilter`
- 비교 선택 sticky bar
- 비교용 loading, empty, partial-success, error 상태

### 필요한 API 제안

```http
GET /api/jobs
POST /api/jobs/compare
```

`GET /api/jobs`는 분석된 공고 목록을 반환한다.

`POST /api/jobs/compare` 요청 예시:

```json
{
  "job_ids": ["JOB-001", "JOB-002"],
  "include_matches": true,
  "client_request_id": "uuid"
}
```

응답에는 공고별 원본 요구사항, 유사 요구사항 그룹, 경험 판정 요약, 부족 정보를 포함한다. 유사 그룹은 AI 제안이며 공고 원문 요구사항을 대체하지 않는다.

### 데이터 구조 추가 후보

- `job_postings.status`, `updated_at`
- 공고 보관·숨김 여부
- 비교 세션을 저장할 경우 `job_comparisons`
- 요구사항 간 유사 관계를 저장할 경우 `job_requirement_relations`

초기에는 비교 결과를 영속 저장하지 않고 요청 시 계산하는 방식을 우선 검토한다.

### 작업 단위

| ID | 작업 | 담당 |
|---|---|---|
| FUT-JC01 | 비교 사용자 흐름·완료 조건 | Planner |
| FUT-JC02 | 비교 레퍼런스·테이블/모바일 레이아웃 | Designer |
| FUT-JC03 | 공고 목록·비교 API 계약 | API Integration + 사용자 |
| FUT-JC04 | 비교 Mock fixture | API Integration |
| FUT-JC05 | 공고 선택·비교 UI | Frontend |
| FUT-JC06 | 근거 수준·부족 정보 비교 UI | Frontend |
| FUT-JC07 | 접근성·부분 성공·회귀 QA | QA |
| FUT-JC08 | PRD·범위 최종 감사 | Supervisor |

### 선행 조건

- 실API에서 공고 분석 결과의 저장·재조회가 안정화되어야 한다.
- `GET /api/jobs/{jobId}` 계약과 요구사항 ID가 안정적이어야 한다.
- 경험 매칭 판정 enum과 부분 성공 규칙이 실제 엔진에서 검증되어야 한다.
- 비교 결과를 생성하는 주체가 서버인지 프론트인지 결정해야 한다. 의미 기반 요구사항 그룹은 AI 엔진 담당을 권장한다.

### 완료 기준

- 사용자가 분석된 공고 2~4개를 선택할 수 있다.
- 공고 원문 요구사항과 AI 유사 그룹을 구분해 볼 수 있다.
- 공고별 경험 근거와 부족 정보를 비교할 수 있다.
- 근거 없는 공고를 유리하게 과장하지 않는다.
- 비교 화면에서 선택 공고의 상세·자기소개서로 이동할 수 있다.
- loading, empty, error, partial-success가 모두 검증된다.

## 추가 장기 후보

| 기능 | 설명 | 현재 우선순위 |
|---|---|---|
| 커리어 지식 탐색 | 경험·기술·성과·공고 관계를 근거와 함께 탐색 | 온톨로지 2단계 이후 |
| 미등록 개념 검토 | unresolved 표현을 사용자가 표준 개념에 연결 | Skill ontology 안정화 이후 |
| 데이터 lineage 화면 | AI 결과에서 원본 문장·파일 위치까지 탐색 | Evidence 영속화 이후 |
| 공고 보관함 | 분석한 공고 목록, 즐겨찾기, 마감·숨김 관리 | 공고 비교 선행 |
| 공고 변화 추적 | 같은 공고의 수정 전후 요구사항 차이 | 낮음 |
| 경험 갭 보완 | 부족 정보에서 경험 수정 화면으로 연결 | 중간 |
| 자소서 버전 비교 | AI 수정 전후와 사용자 편집본 비교 | 중간 |
| 공고별 자소서 묶음 | 한 공고의 여러 문항과 문서 관리 | 중간 |
| 면접 질문 준비 | 선택 경험과 공고 요구사항 기반 질문 생성 | 후속 버전 |
| 지원 결과 분석 | 지원 결과와 사용 경험·문서의 관계 분석 | 데이터 축적 후 |

## 로드맵 변경 규칙

후속 제품 기능을 시작할 때는 기존 PRD를 직접 확장하지 않고 별도 버전 PRD를 만든다.
Planner가 범위를 정의하고, API·디자인 명세와 Mock을 먼저 확정한 뒤 구현한다.

데이터 아키텍처 작업은 `AI_DATA_ARCHITECTURE.md`에서 불변 원칙과 목표 구조를 먼저
갱신하고, `AI_ENGINE_WORK_MAP.md`에 실행 작업과 완료 조건을 추가한 뒤 `TODO.md`의
현재 우선순위에 올린다. 완료 후에는 실제 코드와 benchmark 결과를 기준으로 상태를
갱신한다.

