# Career Memory AI 엔진 작업 매핑

## 1. 문서 책임

이 문서는 AI 엔진의 현재 구현 상태, 다음 작업, 완료 조건을 관리하는 단일 체크리스트다.

상태:

- `[ ]` todo
- `[~]` in progress
- `[!]` blocked
- `[?]` review
- `[x]` done

설계 원칙은 `AI_ENGINE_DEVELOPMENT_GUIDE.md`, 데이터 구조는
`../docs/AI_DATA_ARCHITECTURE.md`, 전체 우선순위는 `../docs/TODO.md`를 따른다.

## 2. 현재 실행 구조

```text
React
  -> FastAPI / authenticated user
  -> AI_langchain.py
       ├─ ChatbotAI
       ├─ ExperienceAI
       └─ JobAnalysisAI
  -> Pydantic validation
  -> Proposal / confirmed persistence / RAG index
```

자동 대화 분석:

```text
content routing
  -> complete job guard and deduplication
  -> job analysis
  -> experience analysis
  -> partial failure collection
```

## 3. 구현된 기준선

| ID | 상태 | 기능 | 주요 위치 | 완료 기준 |
|---|---|---|---|---|
| AI-100 | `[x]` | 역할별 AI 엔진과 공통 조립 | `chatbot_ai.py`, `experience_ai.py`, `job_analysis_ai.py`, `AI_langchain.py` | 세 엔진이 공통 Provider·schema 경계로 실행됨 |
| AI-110 | `[x]` | 대화 저장·복원·스트리밍 | `api/conversations.py`, `chatbot_ai.py` | 사용자별 대화 복원, HTTP/SSE, 오류 저장 |
| AI-120 | `[x]` | 자동 의도 분류 | `intent_classifier.py`, `router.py` | 명시 모드 직접 실행, 낮은 확신 chat fallback |
| AI-130 | `[x]` | 통합 콘텐츠 라우팅 | `conversation_content_router.py`, `conversation_analysis_workflow.py` | 경험·공고·혼합·무관·불확실 분류와 부분 실패 처리 |
| AI-200 | `[x]` | 대화·직접 입력 경험 구조화 | `experience_ai.py`, `api/experience_extractions.py` | 경험 0..N, Proposal, 사용자 승인 저장 |
| AI-210 | `[x]` | 경험 파일 추출과 선행 분석 | `experience_file_text.py`, `experience_file_analysis_ai.py` | TXT/PDF/image 처리와 exact quote 검증 |
| AI-220 | `[x]` | 증분 대화 경험 분석 | `api/conversation_experiences.py` | 마지막 성공 범위 이후 분석, 반복 실행 중복 방지 |
| AI-230 | `[x]` | 경험 원본 보존과 인용 검증 | `schemas/evidence.py`, `schemas/experience.py` | source ID, quote, citation 유효성 검증 |
| AI-300 | `[x]` | 채용공고 요구사항 추출 | `job_analysis_ai.py`, `api/jobs.py` | 완전한 공고만 저장, source excerpt 검증 |
| AI-310 | `[x]` | 요구사항별 경험 RAG | `job_analysis_ai.py`, `chat_retrieval.py` | 사용자별 confirmed experience 후보 검색과 근거 연결 |
| AI-320 | `[x]` | 사용자 공고–경험 연결 관리 | `api/jobs.py` | AI 추천과 사용자 직접 연결, 선택·거절 보존 |
| AI-400 | `[x]` | 기술명 무손실 정규화 | `skill_normalization.py`, `schemas/normalization.py` | exact·alias·related·unresolved 구분과 raw 보존 |
| AI-410 | `[x]` | 수치 추출과 검증 | `metric_normalization.py` | exact quote 재파싱, 값·단위·방향·범위 구분 |
| AI-420 | `[x]` | 기술·수치 기반 최종 매칭 | `job_analysis_ai.py` | 임베딩 후보 후 canonical ID와 수치 조건 검증 |
| AI-500 | `[x]` | 토큰·비용·시간 계측 | `analysis_metrics.py`, `benchmarks/` | 실제 usage와 단계별 시간을 결과에 기록 |
| AI-510 | `[x]` | 합성 정답 세트 평가 | `benchmarks/fixtures/`, `evaluate_conversation_analysis.py` | 사실·문맥·공고·인용·오염·정규화 KPI 계산 |
| AI-520 | `[x]` | 통합 파일 형식 판별·파서 | `file_extraction/` | 시그니처 검증과 TXT/MD/PDF/image/DOCX/PPTX/HWPX 추출 |
| AI-530 | `[x]` | 모든 파일 진입점 통합 | `attachment_service.py`, `api/` | 채팅·경험·공고가 같은 원본 저장·검증·파싱 경로 사용 |
| AI-540 | `[x]` | OCR capability·품질 처리 | `file_extraction/ocr.py`, `router.py` | Tesseract 5.4.0 kor+eng+osd, 전처리·전체 PSM 비교·실환경 smoke 통과 |
| AI-550 | `[x]` | 채팅 다중 첨부 UX | `ChatComposer.jsx`, `attachmentIngress.js` | 선택·붙여넣기·드롭, 상태·오류·재시도 카드, 최대 10개 |
| AI-560 | `[x]` | 파일 추출 정답 세트 | `evaluate_file_extraction.py`, `file_extraction_gold_v1.json` | 형식별 본문·수치·순서·CER 평가와 실제 OCR smoke test |
| AI-570 | `[x]` | LocalBlobStore·additive migration | `blob_store.py`, `migrate_attachment_blobs.py` | 신규 DB BLOB 0, SHA-256 검증, 기본 dry-run 이관 |
| AI-580 | `[x]` | 재시작 가능한 DB 파일 큐 | `file_processing_worker.py`, `FileProcessingJob` | lease 만료 복구, 최대 시도 제한, 수동 재처리 |
| AI-590 | `[!]` | DOC/PPT/HWP 격리 변환 | `file_extraction/external_tools.py` | 코드는 완료, 개발 PC의 LibreOffice·한컴 변환기 설치 필요 |
| AI-600 | `[?]` | 음성·영상 FFmpeg·STT | `file_extraction/media.py`, `TranscriptionSegment` | mock STT·timestamp 저장 통과, 현재 FFmpeg 미탐지·실제 음성 API smoke 미실행 |
| AI-610 | `[x]` | 첨부 파이프라인 benchmark | `evaluate_attachment_pipeline.py` | 10개 원본 해시·DB BLOB 0·작업 완료·stale 복구 측정 |
| AI-620 | `[x]` | 요청·스트림 운영 안정화 | `operational_metrics.py`, `api/conversations.py` | 원문 없는 route P50/P95·오류율, request ID, SSE snapshot 재접속·중복 호출 방지 |

현재 측정값과 테스트 결과는 `benchmarks/RESULTS.md`를 기준으로 한다.

개발 PC에는 Tesseract 5.4.0과 `kor+eng+osd`가 준비돼 있다. 2026-10-08 현재
capability 검사에서는 FFmpeg/FFprobe, LibreOffice, 한컴 HWP→HWPX 변환기를 찾지
못했으므로 해당 형식은 원본을 보존하고 정확한 capability 오류를 반환한다. STT는
타임스탬프 계약과 mock 통합 테스트까지 검증했으며 실제 사용자 음성에 대한 유료 API
smoke test는 아직 실행하지 않았다.

## 4. 현재 우선 작업 — 온톨로지와 계층형 데이터

### Phase A. 문서와 계약

| ID | 상태 | 작업 | 산출물·완료 조건 |
|---|---|---|---|
| ARCH-100 | `[x]` | 문서 체계 통합 | 문서 인덱스, 단일 데이터 아키텍처, 중복 문서 제거 |
| ARCH-110 | `[x]` | ontology·Evidence API 노출 범위 확정 | 내부 전용 ID와 공개 필드 구분, 계약 변경 목록 |
| ARCH-120 | `[x]` | migration·rollback 설계 | additive migration, dry-run, 재실행 기준 |

### Phase B. 경량 온톨로지

| ID | 상태 | 작업 | 주요 위치 | 완료 조건 |
|---|---|---|---|---|
| ONT-100 | `[x]` | ontology DB 모델 | `database/models.py`, `connection.py` | concept·alias·relation 테이블과 제약조건 |
| ONT-110 | `[x]` | 기존 기술 seed | `ontology_seed.py`, `ontology_repository.py` | 현재 registry와 같은 stable ID·별칭·관계를 멱등 재현 |
| ONT-120 | `[x]` | ontology repository | `ontology_repository.py` | DB 우선 조회, 버전, curated 장애 fallback |
| ONT-130 | `[x]` | 정규화 연결 | `skill_normalization.py` | raw 보존, DB concept projection, unresolved 유지 |
| ONT-140 | `[x]` | 매칭 정책 분리 | `ontology_repository.py`, `job_analysis_ai.py` | alias 충족, related 후보 전용, 관계 설명 반환 |
| ONT-150 | `[x]` | ontology version 기록 | schemas, job persistence | 분석·매칭 결과에서 사용 버전 추적 |

### Phase C. Evidence 영속화

| ID | 상태 | 작업 | 주요 위치 | 완료 조건 |
|---|---|---|---|---|
| EVD-100 | `[x]` | EvidenceDocument 모델 | `database/models.py` | 원본 종류·레코드·해시·파서 버전 저장 |
| EVD-110 | `[x]` | EvidenceChunk 모델 | `database/models.py`, `evidence_repository.py` | offset·해시·청커 버전과 문서 관계 저장 |
| EVD-120 | `[x]` | EmbeddingRecord 모델 | `database/models.py` | 대상·모델·해시·index version 추적 |
| EVD-130 | `[x]` | 기존 source ref 호환 | `evidence_repository.py`, experience APIs | 기존 ID와 신규 Evidence ID가 손실 없이 연결 |
| EVD-140 | `[x]` | stale 판정 | `evidence_repository.py`, `evidence_index.py` | 원본 변경·연결 해제 시 파생 데이터 stale 처리 |

### Phase D. 증분 인덱싱

| ID | 상태 | 작업 | 주요 위치 | 완료 조건 |
|---|---|---|---|---|
| IDX-100 | `[x]` | 저장 projection·검색 전 동기화 | `chat_retrieval.py`, experience APIs | 저장·수정·삭제 시 Evidence 갱신, 검색 전 vector reconcile |
| IDX-110 | `[x]` | hash 기반 임베딩 생략 | `evidence_index.py` | 같은 content hash는 다시 임베딩하지 않음 |
| IDX-120 | `[x]` | stale vector 제거 | `evidence_index.py` | 삭제·변경된 문서의 이전 벡터 제거 |
| IDX-130 | `[x]` | 전체 인덱스 재구축 명령 | `rebuild_evidence_index.py` | DB에서 사용자별 인덱스 dry-run·재생성 |
| IDX-140 | `[x]` | index version migration | `evidence_index.py` | 모델·문서 구성 변경 시 버전별 collection 분리 |

### Phase E. 백필과 검증

| ID | 상태 | 작업 | 완료 조건 |
|---|---|---|---|
| MIG-100 | `[x]` | ontology dry-run 백필 | 기존 raw field 불변, 변경 예정 값 보고 |
| MIG-110 | `[x]` | Evidence dry-run 백필 | source 누락·중복과 생성·stale 예정 건수 보고 |
| QA-520 | `[x]` | ontology 정답 세트 확장 | alias·related·상하위·unresolved 판정 100% |
| QA-530 | `[x]` | Evidence lineage 테스트 | fact에서 원본까지 추적, invalid quote 거부 |
| QA-540 | `[x]` | 증분 인덱스 테스트 | 동일·수정·삭제·재구축 시나리오 |
| QA-550 | `[x]` | 실제 모델 benchmark 재실행 | gpt-4o-mini 4/4 성공, 품질·usage 비용·시간·DB write 기록 |

## 5. 이후 백로그

| ID | 상태 | 작업 | 비고 |
|---|---|---|---|
| FUT-100 | `[ ]` | 실제·익명화 gold set 확대 | 소규모 합성 fixture의 일반화 한계 보완 |
| FUT-110 | `[ ]` | Retrieval Recall@K·MRR 측정 | experience/evidence index 별도 평가 |
| FUT-120 | `[ ]` | Role·Organization·Industry ontology | Skill ontology 안정화 후 진행 |
| FUT-130 | `[ ]` | 객체 저장소 전환 | 운영 배포 필요가 생길 때 검토 |
| FUT-140 | `[ ]` | 그래프 DB 또는 RDF 검토 | 실제 복잡한 그래프 질의가 생길 때만 검토 |
| FUT-150 | `[ ]` | 비동기 AI 작업 큐 | 장시간 분석과 운영 규모 증가 시 도입 |
| FUT-160 | `[!]` | 레거시 DOC/PPT/HWP 실환경 변환 검증 | LibreOffice·한컴 변환기 설치 후 실제 fixture 통과 필요 |
| FUT-170 | `[?]` | 실제 음성·영상 STT 품질 평가 | 익명화 음성 corpus, WER·숫자 재현율·비용 측정 |
| FUT-180 | `[x]` | 다중 worker 원자적 claim | UPDATE RETURNING 기반 claim·lease·worker 소유권 테스트 완료 |

## 6. 구현 순서

```text
ARCH-110~120
  -> ONT-100~150
  -> EVD-100~140
  -> IDX-100~140
  -> MIG-100~110
  -> QA-520~550
```

Ontology와 Evidence 스키마를 한 번에 파괴적으로 적용하지 않는다. 각 단계는 기존
raw field와 API를 유지한 상태로 테스트한 뒤 다음 단계로 이동한다.

## 7. 공통 완료 조건

- 기존 원문과 raw field가 보존된다.
- 사용자별 DB와 vector collection 격리가 유지된다.
- schema migration과 backfill이 재실행 가능하다.
- Chroma 없이도 DB에서 인덱스를 다시 만들 수 있다.
- invalid source, quote, relation이 저장되지 않는다.
- Python 전체 테스트와 관련 프론트 테스트가 통과한다.
- 실제 모델을 사용한 평가는 fixture, 실행 횟수, 비용을 함께 기록한다.
- 완료된 작업의 문서와 코드 상태가 일치한다.

## 8. 문서 갱신 규칙

- 상태 변경은 이 문서에서만 관리한다.
- 데이터 구조 변경은 `../docs/AI_DATA_ARCHITECTURE.md`에 반영한다.
- API 필드 변경은 `AI_FRONTEND_CONTRACT_MAPPING.md`에 반영한다.
- 저장소 전체 우선순위가 바뀌면 `../docs/TODO.md`를 갱신한다.
- 측정 결과는 `benchmarks/RESULTS.md`에 기록한다.
