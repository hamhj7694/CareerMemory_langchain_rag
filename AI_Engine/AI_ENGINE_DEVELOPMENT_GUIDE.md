# Career Memory AI 엔진 개발 가이드

## 1. 문서 목적

이 문서는 Career Memory의 AI 엔진을 역할별로 분리하고 LangChain으로 조합하기 위한 개발 기준을 정의한다.

단계별 작업 상태, 프론트엔드 진입점, 스키마, 산출물과 완료 조건은
`AI_ENGINE_WORK_MAP.md`에서 관리한다.

다음 문서를 상위 요구사항으로 사용한다.

- `Data_Flow_Summary.md`
- `AI_MEMORY_CONTEXT_POLICY.md`
- `docs/DATA_SCHEMA_AUDIT_improvement.md`

AI 엔진, 백엔드 API, 프론트엔드는 이 문서에 정의된 역할 경계와 데이터 계약을 기준으로 연결한다.

---

## 2. AI 엔진의 세 가지 역할

### 2.1 대화형 챗봇

사용자와 대화하고 대화 세션의 메시지와 첨부 자료를 문맥으로 사용한다.

- 일반적인 대화와 질문에 답변한다.
- 현재 `conversation_id`의 대화와 첨부만 세션 문맥에 누적한다.
- 다른 대화 세션의 메시지 원문은 자동으로 공유하지 않는다.
- 로그인 사용자가 경험 관리에 확정 저장한 경험과 원본 근거를 세션에 관계없이 RAG로 조회할 수 있다.
- 경험 검색에는 로그인 세션에서 얻은 `user_id` 필터를 반드시 적용한다.
- 경험이나 채용공고 데이터를 직접 확정 저장하지 않는다.
- 필요한 경우 경험정리 AI 또는 채용공고 분석 AI 실행을 제안할 수 있다.

문맥 계층은 다음과 같다.

```text
단기 문맥 = 현재 conversation_id의 메시지·첨부
장기 문맥 = 현재 user_id의 확정 Experience 검색 결과
```

대화에서 발견한 경험은 사용자 승인 후 경험 관리에 저장되고 검색 인덱스가 갱신된 시점부터 장기 문맥으로 사용할 수 있다.

### 2.2 경험정리 AI

선택된 대화, 직접 입력한 텍스트, 첨부 파일에서 경험을 찾아 구조화된 초안을 생성한다.

- 한 번의 실행에서 경험을 `0..N개` 추출한다.
- 하나의 입력에서 여러 경험을 분리할 수 있다.
- 여러 입력을 하나의 경험으로 통합할 수 있다.
- 확인되지 않은 값은 추측하지 않고 빈값 또는 `missing_information`으로 반환한다.
- 결과는 확정 Experience가 아닌 사용자가 검토·수정할 수 있는 ExperienceDraft이다.

경험 초안의 계층은 다음과 같다.

```text
경험 분류
└─ 프로젝트·활동
   └─ 상세 경험
```

상세 경험은 최소한 다음 내용을 포함한다.

```text
title
summary
situation
actions[]
results[]
role
skills[]
facts[]
missing_information[]
source_ref_ids[]
field_citations{}
```

### 2.3 채용공고 분석 AI

입력된 채용공고를 요구사항 카드로 구조화하고, 확정된 경험을 RAG로 검색하여 요구사항별 관련 경험을 추천한다.

처리 단계는 다음과 같다.

```text
채용공고 원문
  ↓
요구사항 구조화
  ↓
JobRequirement[] 생성
  ↓
요구사항별 확정 Experience 검색
  ↓
관련 Evidence 재확인·재정렬
  ↓
RequirementExperienceLink[] 추천
```

요구사항은 최소한 다음 내용을 포함한다.

```text
id
title
summary
source_excerpt
source_locator
importance
keywords[]
order
confidence
```

AI 추천과 사용자의 직접 연결은 구분해서 저장한다.

```text
source: ai | user
status: suggested | selected | rejected
```

---

## 3. 전체 구성 파이프라인

```text
프론트엔드 또는 백엔드 API 요청
              ↓
           router.py
              ↓
┌──────────────────┬──────────────────────┬───────────────────────┐
│ 대화형 챗봇      │ 경험정리 AI          │ 채용공고 분석 AI      │
│ chatbot_chain    │ experience_chain     │ job_analysis_chain    │
└──────────────────┴──────────────────────┴───────────────────────┘
              ↓
프롬프트 · 검색 · 검증 · 외부 저장소 어댑터
              ↓
구조화된 응답 또는 사용자 검토용 초안
```

`AI_langchain.py`는 모델, 검색기, 검증기, 체인을 생성하여 하나의 실행 가능한 AI 애플리케이션으로 조립한다.

`router.py`는 들어온 요청의 명시적 모드 또는 판정된 의도에 따라 실행할 체인을 선택한다.

---

## 4. 권장 디렉터리 구조

```text
AI_Engine/
├─ chatbot_ai.py
├─ experience_ai.py
├─ job_analysis_ai.py
├─ AI_langchain.py
├─ router.py
└─ schemas/
│  ├─ __init__.py
│  ├─ common.py
│  ├─ evidence.py
│  ├─ experience.py
│  ├─ job.py
│  ├─ chat.py
│  ├─ routing.py
│  └─ experience_job.py  # 이전 import 경로 호환 전용
```

### 파일별 책임

| 위치 | 책임 |
|---|---|
| `chatbot_ai.py` | `ChatOpenAI`, `create_agent`, 대화 메모리와 스트리밍을 포함한 대화형 챗봇 |
| `experience_ai.py` | 입력 텍스트·대화·파일에서 경험 0..N개를 구조화하는 경험정리 AI |
| `job_analysis_ai.py` | 공고 요구사항 구조화와 확정 경험 RAG 추천 |
| `AI_langchain.py` | 세 AI를 프론트엔드 실행 흐름에 맞게 연결하는 진입점 |
| `router.py` | 요청 유형에 따른 체인 선택 및 실행 위임 |
| `schemas/__init__.py` | 외부에서 사용할 스키마의 안정적인 공개 import 경계 |
| `schemas/common.py` | 공통 기본 타입과 구조화 오류 계약 |
| `schemas/evidence.py` | 대화·직접 입력·파일 원본 근거 계약 |
| `schemas/experience.py` | 경험 초안·증분 분석 요청·결과 계약 |
| `schemas/job.py` | 공고·요구사항·경험 추천 연결 계약 |
| `schemas/chat.py` | 챗봇 메시지·응답·인용·스트리밍 이벤트 계약 |
| `schemas/routing.py` | 자동 모드 의도 판정과 체인 선택 계약 |
| `schemas/experience_job.py` | 이전 통합 import 경로를 유지하는 호환 계층. 신규 구현은 이 파일에 추가하지 않음 |

`chatbot_ai.py`의 `InMemorySaver`는 단일 프로세스 개발·단위 테스트용 기본값이다. 운영 환경에서는 API가 저장한 대화 Repository에서 문맥을 수집하거나 영속 Checkpointer를 주입해야 한다. 서버 재시작과 멀티 워커에서 상태가 유지되지 않는 `InMemorySaver`만으로는 커리어 챗 완료 조건을 충족하지 않는다.

---

## 5. 요청 라우팅 기준

요청 유형은 다음 값 중 하나를 사용한다.

```python
request_type = (
    "auto"
    | "chat"
    | "experience_extraction"
    | "job_analysis"
)
```

라우팅 규칙은 다음과 같다.

1. 사용자가 `[경험 정리]` 모드를 선택한 경우 `experience_extraction`을 직접 실행한다.
2. 사용자가 `[공고 분석]` 모드를 선택한 경우 `job_analysis`를 직접 실행한다.
3. `[대화내용으로 경험 정리하기]` 버튼은 라우터의 의도 판정 없이 `experience_extraction`을 직접 실행한다.
4. `[자동]` 모드에서만 라우터가 요청 의도를 판정한다.
5. 특정 단어 포함 여부만으로 라우팅하지 않는다.
6. 분류 확신도가 낮으면 기본적으로 `chat`을 사용하고 사용자에게 실행 가능한 작업을 제안한다.

---

## 6. 커리어 챗에서 경험정리 AI를 실행하는 흐름

```text
사용자가 대화와 파일을 입력
  ↓
Conversation · Message · Attachment 저장
  ↓
[대화내용으로 경험 정리하기] 실행
  ↓
마지막 성공 분석 이후의 메시지 범위 결정
  ↓
ExtractionRun 생성
  ↓
대화 텍스트와 첨부 파일의 추출 텍스트 수집
  ↓
경험정리 AI 실행
  ↓
ExperienceDraft[] 0..N개 반환
  ↓
프론트엔드에서 미리보기·수정·삭제
  ↓
사용자가 개별 저장 또는 전체 저장
  ↓
백엔드 검증 및 트랜잭션
  ↓
Domain · Project · Experience · Evidence Link 확정 저장
```

증분 분석을 위해 `ExtractionRun`은 최소한 다음 값을 관리한다.

```text
from_sequence
to_sequence
message_ids[]
attachment_ids[]
client_request_id
status
model_version
prompt_version
schema_version
```

성공적으로 확정 저장된 경우에만 다음 분석 시작 지점을 갱신한다. 실패한 실행은 체크포인트를 이동시키지 않는다.

---

## 7. 초안과 확정 데이터의 경계

AI는 확정 Experience를 직접 저장하지 않는다.

```text
AI 출력
  ↓
ExperienceDraft
  ↓
사용자 검토·수정·승인
  ↓
백엔드 검증 및 트랜잭션
  ↓
Experience 확정
```

필수 원칙은 다음과 같다.

- 초안은 개별 저장, 전체 저장, 삭제가 가능해야 한다.
- 한 번 저장된 초안을 다시 승인해도 Experience가 중복 생성되지 않아야 한다.
- 배열 인덱스 대신 안정적인 `draft_id`를 사용한다.
- 동일한 경험 분류와 프로젝트·활동은 이름 문자열만으로 합치지 않고 정규화된 ID 또는 명시적인 사용자 선택을 사용한다.
- AI가 모르는 값은 생성하지 않는다.
- 확정된 사실은 항상 원본 근거로 추적할 수 있어야 한다.

---

## 8. RAG와 근거 사용 원칙

### 원본 근거

- 대화 메시지, 직접 입력 텍스트, TXT/PDF 파일은 원본 데이터로 보존한다.
- 파일은 원본 바이너리, 해시, 업로드 날짜, 파싱 결과를 분리하여 관리한다.
- 원본 근거는 `EvidenceDocument`와 `EvidenceChunk`로 변환한다.
- Fact에는 인용한 근거의 ID와 원문 위치를 연결한다.

### 임베딩 대상

다음 두 종류는 분리하여 임베딩한다.

1. `EvidenceChunk`
   - 원본 확인과 인용 검색에 사용한다.
2. `Experience Search Document`
   - 채용공고와 유사한 확정 경험을 찾는 1차 검색에 사용한다.

검색은 다음 2단계 구조를 권장한다.

```text
JobRequirement
  ↓
Experience Search Document에서 후보 경험 검색
  ↓
후보 경험의 EvidenceChunk 재검색·재정렬
  ↓
추천 이유와 인용 근거 생성
```

---

## 9. 프론트엔드와의 데이터 계약

프론트엔드는 AI 모델의 자유 형식 텍스트를 직접 해석하지 않는다.

- AI 출력은 항상 버전이 있는 JSON Schema로 검증한다.
- 백엔드는 AI 응답을 검증하고 프론트엔드 API 형식으로 변환한다.
- 챗봇 초안, 경험 구조화 제안, 경험 관리 페이지는 동일한 Experience 콘텐츠 계약과 공통 mapper를 사용한다.
- 채용공고 요구사항과 경험 연결은 `JobRequirement`와 `RequirementExperienceLink` 계약을 사용한다.
- snake_case와 camelCase 변환은 mapper 또는 API 경계에서 한 번만 수행한다.

---

## 10. 구현 순서

1. `schemas/`에 공통 입력·출력 스키마 정의
2. `AI_FRONTEND_CONTRACT_MAPPING.md`에서 AI 스키마·API wire DTO·프론트 mapper·Mock 응답·화면 소비 필드를 대조
3. `chatbot_ai.py` 구현
4. `experience_ai.py` 구현 및 다중 경험 추출 검증
5. `job_analysis_ai.py`에 RAG와 공고 분석 구현
6. `router.py`에서 명시적 모드와 자동 모드 라우팅 구현
7. `AI_langchain.py`에서 세 AI 실행 흐름 연결
8. 백엔드 API Adapter에서 AI DTO를 프론트엔드 공개 계약으로 변환
9. Mock 응답과 실제 AI 응답에 같은 프론트 mapper·계약 테스트 적용
10. 단위 테스트, 통합 테스트, 중복 실행 및 실패 복구 테스트

---

## 11. 완료 기준

- 하나의 입력에서 경험 `0개`, `1개`, `여러 개`를 정상적으로 반환한다.
- 여러 입력에서 하나의 경험을 구성할 수 있다.
- 마지막 성공 분석 이후의 대화만 증분 분석한다.
- 동일 요청을 재시도해도 경험이 중복 저장되지 않는다.
- 각 Fact와 추천 경험의 근거를 원문까지 추적할 수 있다.
- 개별 저장, 전체 저장, 나머지 삭제 결과가 새로고침 후에도 유지된다.
- 채용공고 요구사항별 AI 추천과 사용자 직접 연결을 구분한다.
- 경험 관리, 경험 상세, 내 역량, 채용공고 분석이 동일한 확정 Experience ID를 사용한다.
- 모델, 프롬프트, 스키마, 임베딩 인덱스 버전을 기록한다.
