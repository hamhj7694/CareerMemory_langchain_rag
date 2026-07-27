# Career Memory RAG

Career Memory RAG는 사용자와의 대화, 직접 입력한 글, 첨부 파일을 바탕으로 흩어진 경험을 구조화하고 채용공고와 연결하는 커리어 관리 서비스입니다.

- GitHub: https://github.com/hamhj7694/CareerMemory_langchain_rag
- Frontend: React, Vite
- Backend: FastAPI, SQLAlchemy
- AI/RAG: LangChain, OpenAI 또는 Gemini, Chroma
- 기본 모델: `gpt-4o-mini`
- 기본 임베딩 모델: `text-embedding-3-small`

## 1. 주요 기능

### 커리어 챗

- 대화 세션 생성·검색·수정·삭제
- 대화와 PDF/TXT/이미지 첨부 파일 누적
- 저장된 경험과 원본 근거를 RAG로 검색하여 답변
- 오래된 대화 요약 메모리와 토큰 예산 관리
- 사용자의 실행 의도를 일반 대화, 경험 정리, 공고 분석으로 자동 분류

### 경험 관리

- 한 번의 입력에서 0개 이상의 경험 초안 추출
- `경험 분류 → 프로젝트·활동 → 상세 경험` 구조로 관리
- 상세 경험의 요약, 상황, 행동, 결과, 역할, 역량, 근거에서 확인된 내용 저장
- 초안 수정·삭제·개별 저장·전체 저장
- 원본 대화·텍스트·파일 근거 연결 및 휴지통 관리

### 채용공고 분석

- 공고 원문을 요구사항 카드로 구조화
- 요구사항별 확정 경험 RAG 검색
- AI 추천 경험과 사용자가 직접 연결한 경험 구분

## 2. Prompt 설계 문서

### Persona

대화형 챗봇의 Persona는 단순 질의응답 도구가 아니라, 사용자가 자신의 경험을 편하게 이야기하도록 먼저 대화를 이끄는 **친절한 커리어 대화 파트너**입니다.

- 사용자의 질문에 먼저 직접 답합니다.
- 사용자가 무엇을 말해야 할지 모르면 서비스의 역할과 시작 예시를 안내합니다.
- 사용자가 말한 핵심을 짚고, 필요한 후속 질문은 한 번에 하나만 제시합니다.
- 확인되지 않은 경험, 역할, 성과는 만들지 않습니다.

### System Prompt

실제 시스템 프롬프트는 [chatbot_ai.py](AI_Engine/chatbot_ai.py)의 `CHATBOT_SYSTEM_PROMPT`에 있습니다. 핵심 구성은 다음과 같습니다.

```text
[역할]
흩어진 기억에서 강점과 경력 자산을 발견하도록 대화를 이끄는 커리어 파트너

[목표]
질문에 직접 답하고, 필요한 경우 답하기 쉬운 질문 하나로 경험을 구체화

[문맥]
같은 대화의 최근 원문과 요약 메모리, 검색된 경험·근거, 첨부 파일만 사용

[제약조건]
확인되지 않은 사실을 생성하지 않고, 실행하지 않은 저장·수정을 완료했다고 말하지 않음

[형식]
한국어로 답변하며 문단, Markdown bullet, 굵은 글씨를 사용해 가독성 확보
```

경험정리 AI와 채용공고 분석 AI는 별도의 역할과 출력 규칙을 사용합니다.

- 경험정리 Prompt: [experience_ai.py](AI_Engine/experience_ai.py)의 `EXPERIENCE_SYSTEM_PROMPT`
- 공고 요구사항 Prompt: [job_analysis_ai.py](AI_Engine/job_analysis_ai.py)의 `JOB_REQUIREMENT_SYSTEM_PROMPT`
- 요구사항별 경험 매칭 Prompt: [job_analysis_ai.py](AI_Engine/job_analysis_ai.py)의 `JOB_MATCH_SYSTEM_PROMPT`
- 자동 의도 분류 Prompt: [intent_classifier.py](AI_Engine/intent_classifier.py)의 `AUTO_INTENT_PROMPT`
- 대화 요약 Prompt: [conversation_memory.py](AI_Engine/conversation_memory.py)의 `CONVERSATION_MEMORY_SYSTEM_PROMPT`

### Prompt 설계 의도

초기 프롬프트는 `temperature=0`에서 짧고 수동적인 답변을 생성했습니다. 현재는 다음 방향으로 개선했습니다.

- `temperature=0.3`으로 조정하여 안정성을 유지하면서 자연스러운 대화 유도
- 첫 대화에서 서비스 설명과 시작 선택지를 능동적으로 제시
- 단어 포함 여부가 아니라 요청 문맥으로 AI 기능 실행 여부 판단
- 여러 경험이 섞인 긴 글과 파일을 각각의 경험 초안으로 분리
- 모르는 정보는 추측하지 않고 빈 값 또는 `missing_information`으로 반환
- 원본 근거 ID를 유지하여 결과가 어떤 대화·텍스트·파일에서 나왔는지 추적
- 구조화 결과는 사용자가 확인하고 저장한 뒤에만 정식 경험으로 확정

## 3. LangChain 구성 설명

### Chain 구조

현재 AI 엔진은 LangChain Agent와 Retriever, OpenAI strict function calling, Pydantic 검증을 결합한 구조입니다.

```text
React Frontend
    ↓
FastAPI API
    ↓
CareerMemoryAI
    ├─ 대화 요약 메모리
    ├─ 첨부 파일 청크 나누기
    ├─ 저장 경험 RAG
    └─ 원본 근거 RAG
    ↓
요청별 AI
    ├─ ChatbotAI
    ├─ ExperienceAI
    └─ JobAnalysisAI
    ↓
Pydantic Schema 검증
    ↓
프론트엔드 응답 및 사용자 승인 저장
```

- `ChatbotAI`: LangChain `create_agent`로 모델, System Prompt, 대화 문맥을 조립합니다.
- `ExperienceAI`: 파일이 있으면 파일 내용을 먼저 읽고 요약한 뒤 전체 입력을 경험 스키마로 구조화합니다.
- `JobAnalysisAI`: 공고 요구사항 추출 → 확정 경험 검색 → 요구사항별 경험 추천 순서로 실행합니다.
- 전체 문맥 조립 진입점: [AI_langchain.py](AI_Engine/AI_langchain.py)

### Prompt

대화, 경험 정리, 공고 분석, 자동 라우팅, 장기 메모리는 각각 독립 Prompt를 사용합니다. Prompt에는 공통적으로 `role`, `task`, `context`, `constraint`, `format`을 구분하여 책임과 출력 범위를 명확히 했습니다.

### Retriever

- Vector Store: Chroma
- Embedding: 기본 `text-embedding-3-small`
- 경험 검색: 사용자의 확정 경험을 문서화하여 질문 또는 공고 요구사항과 유사한 경험 검색
- 근거 검색: 원본 텍스트를 위치 정보가 포함된 청크로 나누어 관련 근거 검색
- 사용자별 Collection을 사용하여 다른 사용자의 데이터가 섞이지 않도록 분리
- 벡터 검색이 실패할 경우 키워드 기반 검색으로 대체

관련 구현은 [chat_retrieval.py](AI_Engine/chat_retrieval.py)와 [job_analysis_ai.py](AI_Engine/job_analysis_ai.py)에 있습니다.

### Output Parser

별도의 `OutputParser` 클래스 대신 다음 방식으로 출력 파싱과 검증을 처리합니다.

- 일반 챗봇: Agent의 마지막 텍스트를 `ChatResponse`로 변환
- 자동 의도 분류: strict function calling 결과의 JSON arguments 파싱
- 경험 정리: `create_experience_drafts` 함수 호출 결과를 Pydantic 경험 스키마로 검증
- 공고 분석: 요구사항과 경험 연결 함수 호출 결과를 Pydantic 공고 스키마로 검증
- 형식 오류가 있으면 제한적으로 재요청하고, 계속 실패하면 사용자에게 오류 반환

공통 데이터 계약은 [schemas](AI_Engine/schemas/) 폴더에 분리되어 있습니다.

## 4. 설치 및 실행 방법

### 프로젝트 받기

```powershell
git clone https://github.com/hamhj7694/CareerMemory_langchain_rag.git
cd CareerMemory_langchain_rag
```

### 가상환경과 모듈 설치

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd install
Copy-Item .env.example .env
```

`.env`에서 `AI_PROVIDER`를 선택하고 해당 API 키를 입력합니다. 기본 설정은 OpenAI입니다.

```dotenv
AI_PROVIDER=openai
OPENAI_API_KEY=발급받은_API_KEY
```

Gemini 사용 시 `AI_PROVIDER=gemini`와 `GEMINI_API_KEY`를 설정합니다. 실제 `.env`와 API 키는 GitHub에 커밋하지 않습니다.

### 백엔드 실행

```powershell
.\.venv\Scripts\python.exe -m uvicorn AI_Engine.router:app --reload --host 127.0.0.1 --port 8000
```

### 프론트엔드 실행

새 PowerShell 창에서 실행합니다.

```powershell
npm.cmd run dev
```

브라우저에서 http://localhost:5173 에 접속합니다.

> 이미지와 스캔 PDF의 OCR이 필요하면 실행 PC에 Tesseract OCR과 `kor`, `eng` 언어 모델이 설치되어 있어야 합니다.

## 5. 검증 명령

```powershell
npm.cmd run lint
npm.cmd test
npm.cmd run build
.\.venv\Scripts\python.exe -m unittest discover -s AI_Engine\tests -v
```

## 6. 주요 문서

- 제품 요구사항: [PRD.md](PRD.md)
- AI 데이터 흐름: [Data_Flow_Summary.md](Data_Flow_Summary.md)
- AI 작업 매핑: [AI_ENGINE_WORK_MAP.md](AI_Engine/AI_ENGINE_WORK_MAP.md)
- AI·프론트엔드 계약: [AI_FRONTEND_CONTRACT_MAPPING.md](AI_Engine/AI_FRONTEND_CONTRACT_MAPPING.md)
- 스키마 개선 기록: [DATA_SCHEMA_AUDIT_improvement.md](docs/DATA_SCHEMA_AUDIT_improvement.md)
- 작업 목록: [TODO.md](docs/TODO.md)
