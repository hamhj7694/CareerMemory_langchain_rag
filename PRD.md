# 개인 커리어 메모리 RAG

## 초기 1버전 제품 요구사항 정의서(PRD)

---

# 0. 문서 정보

| 항목        | 내용                                       |
| --------- | ---------------------------------------- |
| 제품명       | 개인 커리어 메모리 RAG                           |
| 버전        | Initial V1                               |
| 프로젝트 목적   | LangChain·LLM·RAG 기반 과제 및 포트폴리오 제작       |
| 핵심 사용자    | 취업 준비생, 이직 준비자, 직무 전환자                   |
| 프론트엔드 담당  | Codex                                    |
| AI 엔진 담당  | 함형준                                      |
| 프론트엔드 기술  | React + Vite + JavaScript + React Router |
| AI 엔진 기술  | Python + LangChain + OpenAI API          |
| API 서버    | FastAPI 권장                               |
| 관계형 DB    | SQLite                                   |
| 벡터 DB     | Chroma                                   |
| AI 테스트 UI | Gradio 선택 사용                             |
| 최종 사용자 UI | React 웹 애플리케이션                           |

---

# 1. 제품 개요

## 1.1 한 줄 정의

> 사용자가 자신의 경험을 기억나는 대로 입력하거나 기존 문서를 업로드하면 LLM이 이를 체계적인 커리어 데이터로 정리하고, RAG가 채용공고 요구사항과 관련된 경험을 찾아 자기소개서 소재와 초안을 제공하는 서비스.

## 1.2 핵심 문제

사용자는 자신의 경험을 가지고 있지만, 경험이 다음과 같이 흩어져 있다.

* 기억 속 경험
* 과거 이력서
* 자기소개서
* 경력기술서
* 포트폴리오
* 프로젝트 문서
* 개인 메모
* 면접 답변 기록

채용공고를 확인할 때마다 사용자는 과거 자료를 다시 찾고, 공고와 연결할 경험을 직접 판단해야 한다.

이 과정에서 다음 문제가 발생한다.

* 중요한 경험을 기억하지 못한다.
* 같은 경험을 여러 번 다시 정리한다.
* 공고에 적합한 경험을 놓친다.
* 팀 성과와 개인 역할을 혼동한다.
* 정량적 근거와 원본 출처를 찾기 어렵다.
* 일반 AI가 실제로 하지 않은 경험을 생성할 수 있다.

## 1.3 해결 방법

사용자는 경험을 미리 정리하지 않는다.

```text
자유 텍스트 입력 또는 파일 업로드
→ 원본 데이터 저장
→ LLM이 경험 구조화
→ 사용자가 정리 결과 확인 및 수정
→ 구조화된 경험 저장 및 임베딩
→ 경험 RAG 질의
→ 채용공고 요구사항별 경험 검색
→ 경험 선택
→ 근거 기반 자기소개서 생성
```

---

# 2. 초기 1버전 목표

## 2.1 제품 목표

초기 버전은 다음 사용자 흐름을 완성한다.

```text
① 사용자가 경험 텍스트를 입력하거나 파일을 업로드한다.

② AI 엔진이 입력 내용을 분석한다.

③ LLM이 내용을 다음 구조로 정리한다.
   큰 영역
   → 프로젝트·활동
   → 세부 경험
   → 상황·행동·결과·역할·세부 사실
   → 관련 역량

④ 사용자가 웹에서 정리 결과를 확인하고 수정한다.

⑤ 수정된 경험을 저장한다.

⑥ 새로운 경험이 입력되면 기존 경험과의 관계 및 저장 위치를 제안한다.

⑦ 사용자가 저장된 경험에 대해 AI와 대화한다.

⑧ 사용자가 채용공고를 입력한다.

⑨ RAG가 공고 요구사항별 관련 경험과 근거를 검색한다.

⑩ 사용자가 자기소개서에 사용할 경험을 선택한다.

⑪ LLM이 선택한 경험과 근거만 이용해 자기소개서 한 문항을 작성한다.
```

## 2.2 기술 목표

이번 버전에서 검증할 핵심 기술은 다음과 같다.

* 자유 입력 및 파일 내용의 LLM 구조화
* Structured Output
* 계층형 경험 데이터 저장
* 경험 단위 청킹
* 경험 데이터 임베딩
* Chroma 기반 검색
* 벡터 검색 및 Retriever
* 공고 요구사항 단위 검색
* 근거 기반 RAG 답변
* 프롬프트 엔지니어링
* 자기소개서 환각 방지
* 청킹 및 검색 전략 비교

## 2.3 초기 버전에서 제외하는 기능

* 외부 채용공고 API
* 사용자 경험 기반 자동 공고 추천
* 여러 공고 동시 비교
* 회원가입과 다중 사용자
* 면접 시뮬레이션
* 지원 결과 분석
* 모바일 완전 최적화
* 음성 입력
* 노션·구글 드라이브 연동
* 자유로운 그래프 편집
* 고급 Canvas 문서 편집기
* 자동 합격 가능성 계산

---

# 3. 전체 시스템 구조

```text
[React 웹 프론트엔드]
- 텍스트 입력
- 파일 선택·업로드
- AI 결과 표시
- 경험 구조 수정
- 경험 트리
- 공고 입력
- 대조 결과
- 자기소개서 편집

          ↓ HTTP API

[Python FastAPI 서버]
- 파일 수신
- 파일 내용 추출
- 원본 저장
- LangChain 체인 실행
- LLM 호출
- RAG 검색
- 구조화 DB 저장
- Chroma 저장
- 공고 분석
- 자기소개서 생성

          ↓

[데이터 계층]
- SQLite: 원본·구조화 데이터
- Chroma: 임베딩 검색 데이터
- 파일 저장 폴더: 업로드 원본
```

---

# 4. 작업 책임 구분

## 4.1 인터페이스 및 프론트엔드

Codex가 담당한다.

프론트엔드는 다음까지만 담당한다.

* 사용자의 텍스트 입력
* 사용자의 파일 선택
* 파일 업로드 요청
* API 요청
* API 응답 표시
* 구조화 결과 편집
* 저장 요청
* 경험 트리 표시
* 공고 입력
* 관련 경험 선택
* 자기소개서 표시 및 직접 수정
* 로딩·오류·빈 상태 표시

프론트엔드는 다음을 담당하지 않는다.

* PDF 본문 추출
* LLM 호출
* 프롬프트 작성
* 경험 구조화
* 임베딩 생성
* Chroma 접근
* RAG 검색
* 공고 요구사항 추출
* 자기소개서 AI 생성
* 원본 및 경험 DB 처리

## 4.2 AI LLM 및 RAG 엔진

사용자가 직접 담당한다.

AI 엔진은 다음을 담당한다.

* 업로드 파일 수신 및 저장
* PDF·TXT 내용 추출
* 원본 데이터 저장
* 경험 구조화 LLM
* 사용자 대화 LLM
* 경험 연결 후보 검색
* 구조화 경험 DB 저장
* 검색용 문서 생성
* 임베딩
* Chroma 저장 및 검색
* 공고 요구사항 분석
* 요구사항별 경험 검색
* 경험 근거 판정
* 자기소개서 생성 및 수정
* RAG 품질 평가

---

# 5. 인터페이스 및 프론트엔드 PRD

# 5.1 프론트엔드 기술 요구사항

* React
* Vite
* JavaScript
* React Router
* CSS 또는 CSS Modules
* fetch 또는 Axios
* React Hooks
* React Icons 선택 사용

초기 버전에서는 Redux 같은 별도 상태관리 도구는 필수가 아니다.

---

# 5.2 React Router 구조

```text
/
├─ /memory
│  ├─ 경험 메모리 메인
│  ├─ 경험 입력
│  └─ 저장된 경험 트리
│
├─ /memory/:experienceId
│  └─ 세부 경험 상세
│
├─ /jobs
│  ├─ 채용공고 입력
│  └─ 공고 분석
│
├─ /jobs/:jobId
│  ├─ 공고 요구사항
│  ├─ 경험 대조
│  └─ 자기소개서 생성
│
└─ /documents/:documentId
   └─ 생성 자기소개서 확인·수정
```

최소 구현 라우트:

```text
/memory
/jobs
/jobs/:jobId
```

---

# 5.3 공통 레이아웃

## 사이드바

메뉴:

* 경험 메모리
* 공고 지원

선택 표시:

* 저장 경험 개수
* 현재 분석 중인 공고
* API 연결 상태

## 헤더

표시 항목:

* 현재 페이지 제목
* 처리 상태
* 필요 시 이전 화면 버튼

## 공통 상태 UI

반드시 지원:

* 초기 상태
* 로딩 상태
* 성공 상태
* 오류 상태
* 데이터 없음
* 저장 중
* 분석 중

---

# 5.4 경험 메모리 화면

## 화면 목적

사용자가 경험 텍스트나 파일을 입력하고, AI가 정리한 결과를 확인·수정하며 저장된 경험을 관리한다.

## 권장 레이아웃

```text
┌──────────────────────┬────────────────────────────────────┐
│ 저장된 경험 구조     │ 경험 입력 및 AI 작업 영역         │
│                      │                                    │
│ 직장 경험            │ 텍스트 입력                       │
│ └ SBI SNS 운영       │ 파일 업로드                       │
│   ├ KPI 개선         │ AI 구조화 결과                    │
│   └ 월간 리포트      │ 사용자 확인 질문                  │
│                      │ 경험 관련 대화                    │
└──────────────────────┴────────────────────────────────────┘
```

---

# 5.5 경험 입력 UI

## FE-M01. 텍스트 입력

구성:

* 멀티라인 텍스트 입력창
* 입력 예시
* 글자 수
* `[경험 정리하기]` 버튼

예시 안내:

> 경험을 정리하지 않고 기억나는 대로 입력하세요.

유효성:

* 공백만 있는 입력 차단
* 중복 제출 방지
* 분석 중 버튼 비활성화

요청 API:

```http
POST /api/inputs/text
```

---

## FE-M02. 파일 업로드

지원 형식:

* PDF
* TXT

프론트엔드 역할:

* 파일 선택
* 파일명 표시
* 파일 크기 표시
* 확장자 검증
* 업로드 취소
* FormData 생성
* API 전송

프론트엔드에서 파일 내용을 직접 읽거나 분석하지 않는다.

요청 API:

```http
POST /api/inputs/file
Content-Type: multipart/form-data
```

파일 검증:

* 허용 확장자
* 최대 파일 크기
* 파일 미선택
* 동일 파일 재선택 처리

---

# 5.6 AI 구조화 결과 확인 UI

## FE-M03. 계층 구조 표시

AI 응답을 다음 구조로 표시한다.

```text
큰 영역
→ 프로젝트·활동
→ 세부 경험
→ 상황
→ 행동
→ 결과
→ 역할
→ 관련 역량
→ 누락 정보
```

예시:

```text
직장 경험
└─ SBI저축은행 SNS 운영
   ├─ SNS KPI 개선 제안
   │  ├─ 상황: 좋아요·댓글 중심 지표의 한계 인식
   │  ├─ 행동: 저장·공유 중심 KPI 제안
   │  └─ 결과: 등록된 결과 없음
   └─ AI 습핫 콘셉트 기획
```

표시 방식:

* 카드
* 아코디언
* 접기·펼치기
* 역량 태그
* 누락 정보 경고 박스

---

## FE-M04. 구조화 결과 수정

사용자가 수정할 수 있는 항목:

* 큰 영역명
* 프로젝트명
* 조직명
* 기간
* 세부 경험 제목
* 요약
* 상황
* 행동
* 결과
* 역할
* 세부 사실
* 역량
* 누락 정보

지원 기능:

* 텍스트 수정
* 배열 항목 추가
* 배열 항목 삭제
* 역량 태그 추가
* 역량 태그 삭제
* 세부 경험 추가
* 세부 경험 삭제

초기 버전 제외:

* 드래그 앤 드롭
* 경험 병합
* 경험 분할 자동화
* 복잡한 관계 그래프

---

## FE-M05. 기존 프로젝트 연결 선택

AI 엔진이 기존 프로젝트 후보를 반환하면 선택지를 표시한다.

예시:

```text
저장 위치를 선택하세요.

○ 기존 ‘SBI저축은행 SNS 운영’ 프로젝트에 추가
○ 새로운 프로젝트로 저장
○ 보류
```

사용자는 AI 추천을 그대로 따르지 않아도 된다.

---

## FE-M06. 구조화 경험 저장

사용자가 수정한 최종 데이터를 전송한다.

```http
POST /api/experiences/commit
```

성공 시:

* 성공 메시지
* 경험 트리 갱신
* 신규 경험 강조
* 입력 영역 초기화

실패 시:

* 오류 내용
* 다시 시도
* 입력값 유지

---

# 5.7 경험 트리 UI

## FE-M07. 저장된 경험 조회

구조:

```text
큰 영역
└─ 프로젝트
   └─ 세부 경험
```

필수 기능:

* 접기·펼치기
* 프로젝트 클릭
* 경험 클릭
* 선택 경험 강조
* 데이터가 없을 때 안내

요청:

```http
GET /api/experiences/tree
```

---

## FE-M08. 경험 상세

표시 항목:

* 큰 영역
* 프로젝트
* 경험 제목
* 요약
* 상황
* 행동
* 결과
* 역할
* 역량
* 원본 근거

기능:

* 수정
* 숨기기
* 원본 보기
* 이 경험으로 질문하기

---

## FE-M09. 원본 보기

사용자가 `[원본 보기]`를 누르면 모달 또는 패널로 표시한다.

표시:

* 원본 텍스트
* 파일명
* 페이지
* 입력 시각
* 연결된 세부 사실

요청:

```http
GET /api/experiences/{experienceId}/sources
```

---

# 5.8 경험 대화 UI

## FE-M10. 경험 질문

사용자는 저장된 경험에 대해 자연어로 질문한다.

예시:

* 데이터 기반으로 개선한 경험을 찾아줘.
* 리더십 경험이 있었어?
* AI 관련 프로젝트만 보여줘.
* 정량 성과가 부족한 경험을 알려줘.

요청:

```http
POST /api/chat/experiences
```

## FE-M11. RAG 답변 표시

응답 표시:

* AI 답변
* 관련 경험 카드
* 관련 프로젝트
* 근거 문장
* 부족한 정보
* 원본 보기
* 자기소개서에 사용

채팅 답변 안에서 관련 경험 카드를 클릭할 수 있어야 한다.

---

# 5.9 공고 지원 화면

## FE-J01. 공고 입력

입력:

* 회사명
* 직무명
* 공고 원문
* 자기소개서 문항

필수:

* 공고 원문

버튼:

```text
[공고 분석하기]
```

요청:

```http
POST /api/jobs/analyze
```

---

## FE-J02. 공고 요구사항 표시

AI 엔진이 반환한 요구사항을 유형별로 표시한다.

유형:

* 주요 업무
* 필수 조건
* 우대 조건
* 기술
* 도메인 경험
* 협업 역량

각 요구사항은 개별 카드로 표시한다.

---

## FE-J03. 경험 대조 요청

버튼:

```text
[내 경험과 대조하기]
```

요청:

```http
POST /api/jobs/{jobId}/match
```

---

## FE-J04. 공고 대조 결과

요구사항별 표시:

* 요구사항
* 판정
* 관련 경험
* 관련 근거
* 부족한 정보
* 경험 선택

판정:

* 직접 근거
* 부분 근거
* 간접 근거
* 등록된 근거 없음
* 추가 확인 필요

---

# 5.10 자기소개서 UI

## FE-C01. 경험 선택

자기소개서에 사용할 경험 1~2개를 선택한다.

기능:

* 경험 체크
* 상세 보기
* 근거 보기
* 선택 해제
* 선택 개수 표시

## FE-C02. 생성 조건 입력

입력:

* 자기소개서 문항
* 최대 글자 수
* 문체

문체:

* 기본
* 간결
* 구체적

## FE-C03. 자기소개서 생성

요청:

```http
POST /api/cover-letters/generate
```

## FE-C04. 자기소개서 결과

표시:

* 생성 문서
* 현재 글자 수
* 사용한 경험
* 사용한 근거
* 부족한 정보 경고

기능:

* 직접 편집
* 복사
* 짧게 줄이기
* 더 구체적으로
* 자연스럽게
* 다시 작성

수정 요청:

```http
POST /api/cover-letters/revise
```

---

# 5.11 프론트엔드 컴포넌트

## 공통

* `AppLayout`
* `Sidebar`
* `Header`
* `LoadingState`
* `ErrorState`
* `EmptyState`
* `ConfirmModal`
* `Tag`

## 경험

* `ExperienceTextInput`
* `ExperienceFileUpload`
* `ParsedExperienceEditor`
* `DomainField`
* `ProjectField`
* `ExperienceCardEditor`
* `FactListEditor`
* `SkillTagEditor`
* `ProjectCandidateSelector`
* `ExperienceTree`
* `ExperienceDetail`
* `SourceModal`
* `ExperienceChat`
* `RetrievedExperienceCard`

## 공고

* `JobPostingForm`
* `RequirementList`
* `RequirementCard`
* `JobMatchResult`
* `MatchStatusBadge`
* `ExperienceSelector`

## 자기소개서

* `CoverLetterOptions`
* `CoverLetterEditor`
* `EvidencePanel`

---

# 5.12 프론트엔드 Mock 개발

AI 엔진 개발 전에도 프론트엔드 작업이 가능해야 한다.

권장 구조:

```text
src/
├─ api/
│  ├─ client.js
│  ├─ inputApi.js
│  ├─ experienceApi.js
│  ├─ jobApi.js
│  └─ coverLetterApi.js
│
├─ mocks/
│  ├─ inputParsed.json
│  ├─ experienceTree.json
│  ├─ experienceChat.json
│  ├─ jobAnalysis.json
│  ├─ jobMatch.json
│  └─ coverLetter.json
```

환경변수:

```text
VITE_USE_MOCK=true
VITE_API_BASE_URL=http://localhost:8000
```

원칙:

* `true`: Mock JSON 사용
* `false`: 실제 FastAPI 호출

---

# 5.13 프론트엔드 완료 기준

다음 조건을 만족하면 프론트엔드 작업을 완료한 것으로 본다.

* React Router가 적용되어 있다.
* 경험 텍스트를 입력할 수 있다.
* PDF·TXT 파일을 선택하고 업로드할 수 있다.
* Mock 구조화 결과를 표시한다.
* 구조화 결과를 항목별로 수정할 수 있다.
* 기존 프로젝트 또는 새 프로젝트를 선택할 수 있다.
* 저장된 경험 트리를 표시한다.
* 경험 상세와 원본을 확인할 수 있다.
* 경험 RAG 답변과 관련 경험 카드를 표시한다.
* 공고를 입력할 수 있다.
* 공고 요구사항을 표시한다.
* 요구사항별 경험 대조 결과를 표시한다.
* 경험을 선택할 수 있다.
* 자기소개서를 표시하고 직접 편집할 수 있다.
* Mock API와 실제 API를 전환할 수 있다.
* 로딩·오류·빈 상태가 구현되어 있다.

---

# 6. AI LLM 및 RAG 엔진 PRD

# 6.1 AI 엔진 목표

> 프론트엔드에서 전달받은 텍스트 또는 파일을 분석해 경험 구조를 생성하고, 저장된 경험을 RAG로 검색하여 공고 대조와 자기소개서 작성에 필요한 근거를 제공한다.

---

# 6.2 권장 기술

* Python
* FastAPI
* LangChain
* LangChain Community
* LangChain OpenAI
* LangChain Chroma
* Pydantic
* SQLite
* Chroma
* PyPDFLoader
* RecursiveCharacterTextSplitter
* BM25 선택 적용
* Gradio 테스트 UI

---

# 6.3 AI 엔진 전체 모듈

```text
backend/
├─ app/
│  ├─ main.py
│  │
│  ├─ api/
│  │  ├─ inputs.py
│  │  ├─ experiences.py
│  │  ├─ chat.py
│  │  ├─ jobs.py
│  │  └─ cover_letters.py
│  │
│  ├─ chains/
│  │  ├─ experience_parser_chain.py
│  │  ├─ experience_linker_chain.py
│  │  ├─ experience_rag_chain.py
│  │  ├─ job_parser_chain.py
│  │  ├─ job_match_chain.py
│  │  └─ cover_letter_chain.py
│  │
│  ├─ prompts/
│  │  ├─ experience_parser.txt
│  │  ├─ experience_linker.txt
│  │  ├─ experience_answer.txt
│  │  ├─ job_parser.txt
│  │  ├─ job_match.txt
│  │  └─ cover_letter.txt
│  │
│  ├─ schemas/
│  ├─ services/
│  │  ├─ file_service.py
│  │  ├─ database_service.py
│  │  ├─ embedding_service.py
│  │  ├─ retrieval_service.py
│  │  └─ rerank_service.py
│  │
│  ├─ repositories/
│  └─ evaluation/
│
├─ uploads/
├─ data/
└─ tests/
```

---

# 6.4 AI 파이프라인 구분

하나의 `rag_chain`으로 모든 작업을 처리하지 않는다.

초기 버전에서 다음 체인을 분리한다.

```text
1. experience_parser_chain
   자유 입력 또는 문서를 경험 구조로 변환

2. experience_linker_chain
   신규 경험과 기존 경험의 연결 후보 판정

3. experience_rag_chain
   저장된 경험에 대한 사용자 질문 답변

4. job_parser_chain
   채용공고를 요구사항 단위로 구조화

5. job_match_chain
   요구사항별 관련 경험 검색 및 판정

6. cover_letter_chain
   선택한 경험으로 자기소개서 생성·수정
```

---

# 6.5 입력 처리

## AI-I01. 텍스트 입력 수신

요청받은 텍스트를 원본 DB에 먼저 저장한다.

```text
텍스트 수신
→ Raw 데이터 저장
→ 구조화 체인 실행
```

## AI-I02. 파일 입력 수신

프론트엔드에서 전송한 파일을 서버가 처리한다.

처리:

```text
파일 수신
→ 파일 저장
→ 확장자 검증
→ PDF 또는 TXT 본문 추출
→ Raw 데이터 저장
→ 구조화 체인 실행
```

PDF:

```python
PyPDFLoader
```

TXT:

```python
일반 파일 읽기
```

프론트엔드는 파일 내용을 추출하지 않는다.

---

# 6.6 1단계 Raw 데이터

## AI-D01. 원본 저장

저장 대상:

* 사용자가 입력한 텍스트
* 추출된 파일 본문
* 원본 파일 경로
* 파일명
* 페이지
* 입력 시각
* 처리 상태

원칙:

* 원본을 수정하지 않는다.
* 신규 입력은 항상 추가한다.
* LLM이 정리한 문장과 원문을 분리한다.

---

# 6.7 경험 구조화 체인

## AI-P01. 역할

사용자의 무정형 입력을 다음 계층으로 정리한다.

```text
큰 영역
→ 프로젝트
→ 세부 경험
→ 상황·행동·결과·역할·사실
→ 관련 역량
→ 누락 정보
```

## AI-P02. Structured Output

Pydantic 기반 구조를 사용한다.

```python
class ExperienceItem(BaseModel):
    title: str
    summary: str
    situations: list[str]
    actions: list[str]
    results: list[str]
    roles: list[str]
    skills: list[str]
    missing_information: list[str]


class ParsedProject(BaseModel):
    domain_name: str
    project_name: str
    organization: str | None
    period_start: str | None
    period_end: str | None
    experiences: list[ExperienceItem]
```

## AI-P03. 구조화 규칙

* 입력에 없는 사실을 생성하지 않는다.
* 날짜를 임의로 추정하지 않는다.
* 수치를 생성하지 않는다.
* 팀 성과와 개인 역할을 구분한다.
* 결과 정보가 없으면 빈 배열로 둔다.
* 여러 프로젝트가 섞여 있으면 분리한다.
* 같은 프로젝트 안의 다른 행동은 세부 경험으로 구분한다.
* 불확실한 정보는 누락 정보로 표시한다.
* 기존 경험을 자동으로 덮어쓰지 않는다.

## AI-P04. 사용자 확인용 응답

구조화 결과는 즉시 확정 저장하지 않는다.

```text
원본 저장
→ LLM 구조화
→ 임시 구조 반환
→ 프론트엔드 사용자 수정
→ 최종 구조 저장
```

---

# 6.8 기존 경험 연결 체인

## AI-L01. 연결 후보 검색

구조화된 신규 경험으로 기존 프로젝트와 세부 경험을 검색한다.

검색 결과:

* 유사한 프로젝트
* 유사한 세부 경험
* 유사도
* 추천 관계

## AI-L02. 관계 유형

* `same_project`
* `related_to`
* `supports`
* `separate_experience`
* `unclear`

## AI-L03. 연결 원칙

* 자동 병합하지 않는다.
* 기존 경험을 덮어쓰지 않는다.
* 프론트엔드에 후보만 반환한다.
* 최종 저장 위치는 사용자가 결정한다.

---

# 6.9 경험 확정 저장

## AI-S01. 사용자 수정 결과 수신

프론트엔드에서 사용자가 수정한 최종 구조를 받는다.

처리:

```text
스키마 검증
→ 큰 영역 저장 또는 조회
→ 프로젝트 저장 또는 조회
→ 세부 경험 저장
→ 세부 사실 저장
→ 역량 저장 및 연결
→ 원본 연결
→ 검색 텍스트 생성
→ 임베딩
→ Chroma 저장
```

---

# 6.10 경험 청킹 및 임베딩

## AI-R01. 기본 청크 단위

기본 청크는 고정 토큰 단위가 아니라 **세부 경험 단위**로 한다.

예:

```text
큰 영역: 직장 경험
프로젝트: SBI저축은행 SNS 운영
세부 경험: SNS KPI 개선 제안
상황: 좋아요·댓글 중심 지표의 한계를 인식함
행동: 저장·공유 중심 KPI를 제안함
결과: 등록된 결과 없음
역량: KPI 설계, SNS 운영, 데이터 기반 개선
```

## AI-R02. RecursiveCharacterTextSplitter 사용 범위

사용 가능:

* 긴 PDF 원문
* 긴 프로젝트 문서
* 원본 근거 문서
* 하나의 경험 설명이 지나치게 긴 경우

기본 경험 데이터에는 무조건 적용하지 않는다.

## AI-R03. 임베딩 대상

필수:

* 세부 경험

선택:

* 세부 사실
* 긴 원본 문서 청크

## AI-R04. Chroma 저장

초기 벡터 DB:

```python
Chroma(
    collection_name="career_experiences",
    persist_directory="./data/chroma_experiences",
    embedding_function=embeddings
)
```

신규 경험은 다음 방식으로 추가한다.

```python
vector_db.add_documents(...)
```

---

# 6.11 경험 RAG 대화 체인

## AI-C01. 역할

사용자가 저장된 경험에 대해 질문하면 관련 경험을 검색해 답변한다.

## AI-C02. 기본 파이프라인

```text
사용자 질문
→ 질문 재작성
→ Retriever 검색
→ 관련 경험 조회
→ 세부 사실 조회
→ 원본 근거 조회
→ 프롬프트 구성
→ LLM 답변
```

## AI-C03. 기존 RAG 코드 활용

기존 금융 PDF RAG 구조를 경험 검색 기능에 재사용할 수 있다.

```python
retriever = vector_db.as_retriever(
    search_kwargs={"k": 5}
)

answer_chain = create_stuff_documents_chain(
    llm=model,
    prompt=experience_prompt
)

experience_rag_chain = create_retrieval_chain(
    retriever,
    answer_chain
)
```

## AI-C04. 답변 규칙

* 검색 결과에 없는 경험을 생성하지 않는다.
* 저장된 기록에서 확인되지 않는다고 답할 수 있다.
* 등록되지 않은 경험이 실제로 없다고 단정하지 않는다.
* 수치와 기간을 생성하지 않는다.
* 직접 근거와 간접 근거를 구분한다.
* 원본 출처를 반환한다.

---

# 6.12 채용공고 분석 체인

## AI-J01. 공고 입력

프론트엔드에서 공고 원문을 수신한다.

## AI-J02. 요구사항 구조화

추출 항목:

* 회사명
* 직무명
* 주요 업무
* 필수 조건
* 우대 조건
* 요구 기술
* 도메인 경험
* 협업 역량

## AI-J03. 요구사항 단위 분리

공고 전체를 하나의 검색 쿼리로 사용하지 않는다.

```text
공고 전체
→ 요구사항 1
→ 요구사항 2
→ 요구사항 3
```

각 요구사항을 별도로 검색한다.

---

# 6.13 공고와 경험 대조 체인

## AI-M01. 요구사항별 Retriever 검색

각 요구사항에 대해 경험 Top K를 검색한다.

```text
초기 검색: Top 5~10
최종 반환: Top 1~3
```

## AI-M02. 판정 유형

* `direct`
* `partial`
* `indirect`
* `no_evidence`
* `needs_confirmation`

## AI-M03. 금지 사항

* 합격률 계산 금지
* 실제 역량이 없다고 단정 금지
* 저장되지 않은 경험 추정 금지
* 근거 없는 적합도 과장 금지

## AI-M04. 반환 항목

* 공고 요구사항
* 판정
* 관련 경험
* 근거 사실
* 원본 출처
* 부족한 정보
* 추천 이유

---

# 6.14 자기소개서 생성 체인

## AI-W01. 입력

* 자기소개서 문항
* 글자 수
* 공고 요구사항
* 사용자가 선택한 경험 ID
* 선택 경험의 세부 사실
* 원본 근거

## AI-W02. 처리 방식

사용자가 경험을 선택한 뒤에는 전체 벡터 DB를 다시 검색하기보다 ID로 정확한 데이터를 조회한다.

```text
선택 경험 ID
→ SQLite 경험 조회
→ 사실 조회
→ 원본 조회
→ 공고 요구사항 조회
→ 프롬프트 입력
→ 자기소개서 생성
```

## AI-W03. 생성 규칙

* 선택한 경험만 사용한다.
* 검색된 사실만 사용한다.
* 원문에 없는 수치를 생성하지 않는다.
* 없던 행동을 생성하지 않는다.
* 팀 성과를 개인 성과로 바꾸지 않는다.
* 정보가 부족하면 과장하지 않는다.
* 글자 수를 준수한다.
* 사용 경험 ID를 저장한다.

## AI-W04. 수정 체인

수정 유형:

* `shorten`
* `expand`
* `natural`
* `rewrite`

수정 시에도 동일한 경험 근거를 제공한다.

---

# 6.15 Gradio 사용 범위

Gradio는 최종 사용자 웹 UI가 아니다.

사용 목적:

* 경험 구조화 프롬프트 테스트
* RAG 검색 테스트
* 공고 분석 테스트
* 자기소개서 생성 테스트
* 스트리밍 확인
* AI 체인 단독 디버깅

```text
Gradio
→ AI 엔진 내부 테스트

React
→ 최종 초기 버전 사용자 인터페이스
```

---

# 6.16 AI 엔진 완료 기준

다음 조건을 만족해야 한다.

* 텍스트 입력을 받을 수 있다.
* PDF와 TXT 파일을 받을 수 있다.
* 파일 내용을 서버에서 추출할 수 있다.
* 원본 데이터를 저장한다.
* LLM이 경험을 계층형 구조로 생성한다.
* Structured Output 스키마를 적용한다.
* 기존 프로젝트 연결 후보를 찾는다.
* 사용자 수정 결과를 저장할 수 있다.
* 경험 검색 텍스트를 생성한다.
* 경험 단위 임베딩을 Chroma에 저장한다.
* 자연어 질문으로 관련 경험을 검색한다.
* 답변에 근거와 원본 출처를 포함한다.
* 공고를 요구사항 단위로 분리한다.
* 요구사항별 관련 경험을 검색한다.
* 매칭 수준을 분류한다.
* 선택 경험으로 자기소개서 한 문항을 생성한다.
* 생성 내용에 없는 사실이 포함되지 않도록 제한한다.

---

# 7. API 계약

# 7.1 텍스트 입력 및 구조화

```http
POST /api/inputs/text
```

요청:

```json
{
  "content": "SBI저축은행 SNS를 운영하면서 저장과 공유 중심 KPI를 제안했어."
}
```

응답:

```json
{
  "raw_id": "RAW-001",
  "parsed": {
    "domain_name": "직장 경험",
    "project_name": "SBI저축은행 SNS 운영",
    "organization": "SBI저축은행",
    "experiences": [
      {
        "temp_id": "TEMP-001",
        "title": "SNS KPI 개선 제안",
        "summary": "저장과 공유 중심 KPI를 제안한 경험",
        "situations": [],
        "actions": [
          "저장과 공유 중심 KPI를 제안함"
        ],
        "results": [],
        "roles": [],
        "skills": [
          "KPI 설계",
          "SNS 운영"
        ],
        "missing_information": [
          "실제 반영 여부"
        ]
      }
    ]
  },
  "project_candidates": []
}
```

---

# 7.2 파일 입력 및 구조화

```http
POST /api/inputs/file
Content-Type: multipart/form-data
```

요청:

```text
file: PDF 또는 TXT
```

응답 구조는 텍스트 입력 응답과 동일하다.

추가 응답:

```json
{
  "file_id": "FILE-001",
  "filename": "portfolio.pdf",
  "page_count": 15
}
```

---

# 7.3 경험 확정 저장

```http
POST /api/experiences/commit
```

요청:

```json
{
  "raw_id": "RAW-001",
  "save_mode": "existing_project",
  "target_project_id": "PROJ-001",
  "domain_name": "직장 경험",
  "project": {
    "name": "SBI저축은행 SNS 운영",
    "organization": "SBI저축은행"
  },
  "experiences": []
}
```

---

# 7.4 경험 트리

```http
GET /api/experiences/tree
```

---

# 7.5 경험 상세

```http
GET /api/experiences/{experienceId}
```

---

# 7.6 경험 수정

```http
PATCH /api/experiences/{experienceId}
```

---

# 7.7 원본 조회

```http
GET /api/experiences/{experienceId}/sources
```

---

# 7.8 경험 RAG 대화

```http
POST /api/chat/experiences
```

요청:

```json
{
  "message": "데이터를 바탕으로 개선한 경험을 찾아줘."
}
```

응답:

```json
{
  "answer": "가장 관련 있는 경험은 SBI SNS KPI 개선 제안입니다.",
  "experiences": [],
  "evidence": [],
  "missing_information": []
}
```

---

# 7.9 공고 분석

```http
POST /api/jobs/analyze
```

---

# 7.10 공고 대조

```http
POST /api/jobs/{jobId}/match
```

---

# 7.11 자기소개서 생성

```http
POST /api/cover-letters/generate
```

요청:

```json
{
  "job_id": "JOB-001",
  "question": "데이터를 활용해 문제를 개선한 경험을 작성해 주세요.",
  "character_limit": 700,
  "experience_ids": [
    "EXP-001"
  ],
  "tone": "default"
}
```

---

# 7.12 자기소개서 수정

```http
POST /api/cover-letters/revise
```

요청:

```json
{
  "document_id": "DOC-001",
  "revision_type": "shorten",
  "content": "기존 자기소개서 내용"
}
```

---

# 8. 데이터 구조

## 8.1 원본 데이터

### `raw_records`

| 필드                | 설명             |
| ----------------- | -------------- |
| raw_id            | 원본 ID          |
| source_type       | text, pdf, txt |
| content           | 원본 또는 추출 본문    |
| file_id           | 파일 ID          |
| created_at        | 입력 시각          |
| processing_status | 처리 상태          |

### `source_files`

| 필드         | 설명     |
| ---------- | ------ |
| file_id    | 파일 ID  |
| filename   | 파일명    |
| file_path  | 저장 위치  |
| mime_type  | 파일 형식  |
| created_at | 업로드 시각 |

## 8.2 구조화 데이터

### `domains`

* domain_id
* name
* status

### `projects`

* project_id
* domain_id
* name
* organization
* period_start
* period_end
* description

### `experiences`

* experience_id
* project_id
* title
* summary
* search_text
* status
* created_at

### `experience_facts`

* fact_id
* experience_id
* raw_id
* fact_type
* fact_text
* confidence

### `skills`

* skill_id
* name
* category

### `experience_skills`

* experience_id
* skill_id
* directness
* evidence_strength

### `experience_relations`

* relation_id
* source_experience_id
* target_experience_id
* relation_type
* similarity_score

## 8.3 공고 및 생성 문서

### `job_postings`

* job_id
* company_name
* job_title
* raw_text
* created_at

### `job_requirements`

* requirement_id
* job_id
* requirement_type
* requirement_text
* importance

### `generated_documents`

* document_id
* job_id
* question
* used_experience_ids
* content
* created_at

---

# 9. RAG 품질 개선 범위

## 9.1 청킹 비교

다음 세 가지를 비교한다.

| 방식       | 설명                 |
| -------- | ------------------ |
| 고정 길이 청킹 | 일정 문자·토큰 단위        |
| 문단 기반 청킹 | 소제목·문단 단위          |
| 경험 단위 청킹 | LLM 구조화 후 세부 경험 단위 |

최종 기본 방식은 경험 단위 청킹으로 한다.

## 9.2 검색 방식

기준선:

* 벡터 검색만 사용

개선 방식:

* 벡터 검색 + BM25
* 질문 재작성
* 메타데이터 필터
* 리랭킹

## 9.3 평가 지표

* Hit@1
* Hit@3
* Hit@5
* MRR
* 관련 없는 검색 결과 비율
* Unsupported Claim Rate
* 원본 근거 일치율
* 자기소개서 사실 왜곡률

---

# 10. 개발 순서

## 10.1 Codex 프론트엔드 작업 순서

1. Vite React 프로젝트 구성
2. React Router 구성
3. 공통 레이아웃
4. Mock API 모듈
5. 경험 텍스트 입력
6. 파일 업로드
7. 구조화 결과 편집 UI
8. 경험 트리
9. 경험 RAG 답변 UI
10. 공고 입력
11. 공고 대조 결과
12. 자기소개서 에디터
13. 실제 FastAPI 연결
14. 오류·로딩 상태 정리

## 10.2 AI 엔진 직접 작업 순서

1. 기존 금융 PDF RAG 코드 복제 및 정리
2. FastAPI 기본 구성
3. SQLite 스키마 구성
4. 파일 수신·본문 추출
5. 경험 구조화 체인
6. Structured Output
7. 경험 연결 후보 검색
8. 사용자 수정 결과 저장
9. 경험 검색용 Document 생성
10. Chroma 동적 저장
11. 경험 RAG 체인
12. 공고 구조화 체인
13. 요구사항별 검색
14. 매칭 판정
15. 자기소개서 생성 체인
16. Gradio 테스트 화면
17. 품질 평가

## 10.3 통합 순서

1. API 요청·응답 스키마 확정
2. 프론트엔드 Mock JSON 작성
3. 프론트엔드와 AI 엔진 독립 개발
4. 텍스트 입력 API 연결
5. 파일 업로드 API 연결
6. 경험 저장 API 연결
7. 경험 RAG API 연결
8. 공고 API 연결
9. 자기소개서 API 연결
10. 전체 시나리오 테스트

---

# 11. 최종 시연 시나리오

## 시연 1. 자유 경험 입력

사용자가 정리하지 않은 경험을 입력한다.

## 시연 2. 파일 입력

사용자가 PDF 포트폴리오를 업로드한다.

## 시연 3. 경험 구조화

LLM이 다음 구조로 정리한다.

```text
큰 영역
→ 프로젝트
→ 세부 경험
→ 상황·행동·결과·역할
→ 역량
```

## 시연 4. 사용자 수정

사용자가 AI가 잘못 정리한 제목이나 행동을 수정한다.

## 시연 5. 기존 프로젝트 연결

새로운 짧은 입력이 기존 SBI 프로젝트와 연결된다.

## 시연 6. 경험 RAG 질문

사용자가 데이터 기반 개선 경험을 질문한다.

## 시연 7. 공고 대조

채용공고를 입력하고 요구사항별 관련 경험을 확인한다.

## 시연 8. 자기소개서

관련 경험을 선택해 한 문항의 자기소개서를 생성한다.

## 시연 9. RAG 품질 비교

고정 길이 청킹과 경험 단위 청킹의 결과를 비교한다.

---

# 12. 핵심 제품 원칙

1. 사용자는 경험을 미리 정리하지 않는다.
2. 프론트엔드는 AI 로직을 수행하지 않는다.
3. 파일 내용 추출은 Python AI 서버가 담당한다.
4. 사용자 원문은 변경하지 않는다.
5. AI 구조화 결과는 사용자가 확인한다.
6. 신규 경험은 기존 정보를 덮어쓰지 않고 추가한다.
7. 경험은 큰 영역·프로젝트·세부 경험·사실로 나눈다.
8. 기본 임베딩 단위는 세부 경험이다.
9. 공고는 요구사항별로 분리해 검색한다.
10. 자기소개서는 선택 경험과 원본 근거만 사용한다.
11. Gradio는 AI 엔진 테스트용으로 사용한다.
12. React는 최종 사용자 인터페이스로 사용한다.

---

# 13. 최종 정의

초기 1버전은 다음과 같이 정의한다.

> React 웹에서 사용자가 경험 텍스트나 파일을 입력하면 Python AI 엔진이 원문을 추출하고 LLM으로 경험을 계층형 데이터로 정리한다. 사용자는 React 화면에서 정리 결과를 확인하고 수정한다. 확정된 경험은 SQLite와 Chroma에 저장되며, 이후 LangChain RAG가 경험 질문과 채용공고 요구사항에 맞는 관련 경험 및 원본 근거를 검색한다. 사용자는 관련 경험을 선택해 근거 기반 자기소개서 한 문항을 생성한다.

## 프론트엔드의 최종 책임

> 입력하고, 보여주고, 수정하고, 선택하고, API에 전달한다.

## AI 엔진의 최종 책임

> 읽고, 구조화하고, 저장하고, 검색하고, 판단하고, 생성한다.
