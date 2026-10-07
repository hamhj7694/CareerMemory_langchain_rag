# Career Memory AI 엔진 개발 가이드

## 1. 문서 책임

이 문서는 Career Memory AI 엔진의 역할 경계, 근거 사용, 정규화, RAG, 저장 원칙을
정의한다. 데이터 테이블과 lineage는 `../docs/AI_DATA_ARCHITECTURE.md`, 작업 상태는
`AI_ENGINE_WORK_MAP.md`, API·화면 변환은 `AI_FRONTEND_CONTRACT_MAPPING.md`에서 관리한다.

상위 기준:

- `../PRD.md`
- `../Data_Flow_Summary.md`
- `../AI_MEMORY_CONTEXT_POLICY.md`
- `../docs/AI_DATA_ARCHITECTURE.md`
- `../docs/v2/V2_API_CONTRACT.md`

## 2. AI 엔진의 역할

### 2.1 대화형 챗봇

- 현재 대화의 메시지와 첨부를 단기 문맥으로 사용한다.
- 로그인 사용자의 확정 경험과 근거만 계정 공통 RAG로 검색한다.
- 다른 대화의 원문과 미확정 Proposal을 자동으로 공유하지 않는다.
- 경험이나 공고 데이터를 직접 확정 저장하지 않는다.
- 답변에서 사용한 근거와 경험 ID를 반환할 수 있어야 한다.

### 2.2 경험정리 AI

- 대화 범위, 직접 입력, 파일에서 경험 `0..N개`를 구조화한다.
- 하나의 입력을 여러 경험으로 나누거나 여러 입력을 하나의 경험으로 합칠 수 있다.
- 확인할 수 없는 값은 생성하지 않고 `missing_information`에 남긴다.
- 결과는 사용자가 수정·승인할 `ExperienceDraft`다.

```text
경험 분류
└─ 프로젝트·활동
   └─ 상세 경험
      ├─ 상황·행동·결과·역할
      ├─ raw skills와 normalized skill mentions
      ├─ facts와 quantified metrics
      └─ source refs와 field citations
```

### 2.3 채용공고 분석 AI

- 공고 원문을 `JobRequirement[]`로 구조화한다.
- 요구사항의 exact source excerpt와 위치를 검증한다.
- 확정 Experience를 RAG로 검색해 후보를 만든다.
- canonical concept, 정량 조건, 원본 근거를 다시 확인해 최종 연결한다.
- AI 추천과 사용자의 직접 연결을 구분한다.

## 3. 실행 구조

```text
React
  -> FastAPI와 인증된 user_id
  -> AI_langchain.py
       ├─ chatbot_ai.py
       ├─ experience_ai.py
       └─ job_analysis_ai.py
  -> Pydantic 검증
  -> Proposal 또는 저장 가능한 분석 결과
```

자동 대화 분석은 LangGraph workflow를 사용한다.

```text
콘텐츠 라우팅
  -> 공고 중복 제거
  -> 경험·공고 원문 분리
  -> 공고 분석
  -> 경험 분석
  -> 부분 실패를 포함한 결과 반환
```

LangGraph는 실행 순서를 관리하는 workflow graph다. 저장된 개념과 관계를 표현하는
knowledge graph와는 구분한다.

## 4. 요청 라우팅

지원 요청 유형:

```text
auto | chat | experience_extraction | job_analysis
```

규칙:

1. 명시적으로 선택한 모드는 해당 AI를 바로 실행한다.
2. `[자동]`에서만 의도 분류기를 사용한다.
3. 일반 질문은 불필요한 분류 모델 호출 없이 chat으로 단축할 수 있다.
4. 낮은 확신도와 분류 실패는 chat으로 안전하게 fallback한다.
5. 단어 하나의 포함 여부만으로 경험 정리나 공고 분석을 실행하지 않는다.
6. 완전한 채용공고가 아닌 단일 자격요건 문장은 공고로 저장하지 않는다.

## 5. 원본과 AI 문맥

- 사용자 메시지, 직접 입력, 첨부파일, 공고 원문만 사실의 원본이 될 수 있다.
- AI 답변은 짧은 사용자 응답의 질문 문맥을 복원하는 데 제한적으로 사용할 수 있다.
- AI 답변에만 존재하는 주장은 fact, metric, skill evidence로 저장하지 않는다.
- 무관 대화와 공고 원문은 경험 근거에서 분리한다.
- 분류되지 않은 사용자 원문은 삭제하지 않고 `uncertain`으로 보존한다.

## 6. 초안과 확정 데이터

```text
AI output
  -> versioned Pydantic schema
  -> ExperienceDraft / Job analysis proposal
  -> 사용자 검토·수정
  -> 백엔드 검증과 트랜잭션
  -> confirmed data
```

- AI는 확정 Experience를 직접 저장하지 않는다.
- 안정적인 `draft_id`와 `client_request_id`로 중복 승인을 방지한다.
- 성공하지 않은 증분 분석은 대화 체크포인트를 이동하지 않는다.
- 확정 사실은 원본 인용이 있어야 한다.
- raw `skills`, `facts`, `keywords`, source text는 정규화 성공 여부와 무관하게 보존한다.

## 7. 경량 온톨로지와 기술 정규화

현재 기술 정규화는 다음 값을 보존한다.

```text
raw_name
normalized_name?
canonical_skill_id?
match_type: exact | alias | related | unresolved
normalization_status
source_ref_id?
quote
```

정책:

- 같은 canonical concept 또는 검증된 alias만 동일 기술로 본다.
- `related`는 검색 후보를 확장하지만 필수 조건을 충족하지 않는다.
- unknown skill은 가장 가까운 기술로 추측하지 않고 unresolved로 유지한다.
- 온톨로지 DB 도입 후에도 raw 표현은 삭제하지 않는다.
- concept과 relation 변경은 `ontology_version`으로 추적한다.

구체적인 테이블과 마이그레이션은 `../docs/AI_DATA_ARCHITECTURE.md`를 따른다.

## 8. 수치 정규화

- LLM이 제안한 숫자를 그대로 신뢰하지 않는다.
- exact source quote에서 값, 단위, 방향, 범위, 전후 값, 근사 연산자를 다시 파싱한다.
- 49%와 50%, 증가와 감소, 최소와 최대를 구분한다.
- `절반`, `오십 퍼센트`, `약 2배` 같은 표현은 raw expression과 함께 저장한다.
- 달력 연도는 성과 지표로 오인하지 않는다.
- 파싱할 수 없는 표현은 unresolved로 보존한다.
- 수치 조건의 최종 충족 여부는 결정론적으로 비교한다.

## 9. Evidence와 인용

- 모든 fact citation은 알려진 source ID를 참조해야 한다.
- quote는 해당 source 원문에 실제로 존재해야 한다.
- structured skill과 metric도 가능하면 source ID와 exact quote를 가진다.
- 파일은 바이너리, 추출 텍스트, 해시, 파서 버전을 분리한다.
- 목표 구조에서는 EvidenceDocument, EvidenceChunk, EmbeddingRecord를 영속화한다.
- 원본이 수정되면 관련 파생 데이터와 인덱스를 stale로 판단할 수 있어야 한다.

## 10. RAG와 검색 판정

두 검색 대상을 분리한다.

1. Experience search document: 공고와 관련 있는 확정 경험 후보 검색
2. Evidence chunk: 원본 인용과 후보 경험 근거 재확인

```text
질문 또는 JobRequirement
  -> embedding/lexical candidate retrieval
  -> user_id와 confirmed 상태 필터
  -> canonical concept와 수치 조건 검증
  -> Evidence 재확인
  -> 답변 또는 RequirementExperienceLink
```

임베딩 점수만으로 필수 기술이나 수치 조건을 충족했다고 판정하지 않는다. 인덱스는
content hash와 index version으로 갱신하고 DB에서 전체 재구축할 수 있어야 한다.

## 11. 데이터·API 경계

- AI 내부 및 공개 API JSON은 `snake_case`를 사용한다.
- 프론트 화면의 `camelCase` 변환은 프론트 Adapter에서 한 번만 한다.
- 프론트는 LLM 자유 형식 텍스트를 직접 파싱하지 않는다.
- AI 출력은 strict function calling과 Pydantic schema로 검증한다.
- API 요청의 사용자 ID를 신뢰하지 않고 인증 세션에서 얻는다.
- 빈 결과는 오류가 아니라 빈 배열일 수 있다.
- 모델·prompt·schema·ontology·index version을 관측 가능하게 보존한다.

## 12. 코드 책임

| 위치 | 책임 |
|---|---|
| `chatbot_ai.py` | 대화 답변, 문맥, 스트리밍 |
| `intent_classifier.py` | 자동 모드 의도 분류 |
| `conversation_content_router.py` | 사용자 원문 유형 분류와 공고 탐지 |
| `conversation_analysis_workflow.py` | 통합 LangGraph 실행 순서 |
| `experience_ai.py` | 경험 초안 구조화와 근거 검증 |
| `experience_file_text.py` | 파일 텍스트·OCR 추출 |
| `job_analysis_ai.py` | 공고 요구사항과 경험 매칭 |
| `skill_normalization.py` | 기술 개념 정규화와 관계 판정 |
| `metric_normalization.py` | 수치 추출과 결정론적 비교 |
| `chat_retrieval.py` | 경험·Evidence RAG |
| `schemas/` | 버전 가능한 입력·출력 계약 |
| `database/` | 영속 모델과 additive migration |
| `api/` | 인증, 저장, 공개 DTO 변환 |

## 13. 구현과 검증 순서

1. 상위 제품·데이터·API 문서를 확인한다.
2. raw source와 derived projection의 경계를 정의한다.
3. Pydantic schema와 DB migration을 additive하게 설계한다.
4. 결정론적 검증기를 먼저 구현한다.
5. LLM 출력과 검증기를 연결한다.
6. API Adapter와 프론트 계약을 갱신한다.
7. 단위 테스트와 통합 테스트를 실행한다.
8. 실제 모델 benchmark는 별도 고정 fixture로 실행한다.
9. 비용·시간·토큰·품질 결과를 기록한다.
10. 작업 상태와 문서를 현재 코드에 맞게 갱신한다.

## 14. 공통 완료 기준

- 경험 0개·1개·여러 개를 정상 처리한다.
- 원본과 규격 밖 표현이 손실되지 않는다.
- 정확하지 않은 인용과 알려지지 않은 source ID가 거부된다.
- AI 답변 오염과 무관 대화 누출을 방지한다.
- 반복 요청이 중복 저장과 불필요한 재임베딩을 만들지 않는다.
- 다른 사용자의 데이터와 벡터가 검색되지 않는다.
- 모델 장애 시 원본 데이터가 손상되지 않는다.
- 관련 테스트, 계약 검증, 빌드가 통과한다.
- 남은 범위와 평가 세트의 한계를 결과 문서에 명시한다.
