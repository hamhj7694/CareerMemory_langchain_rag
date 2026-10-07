# Career Memory 데이터 흐름

## 1. 문서 목적

이 문서는 사용자의 대화·파일·채용공고가 Career Memory 안에서 어떻게 저장되고,
분석되고, 사용자 승인 지식과 검색 인덱스로 변환되는지 설명한다.

세부 기준은 다음 문서를 따른다.

- 데이터 구조: `docs/AI_DATA_ARCHITECTURE.md`
- 기억 범위: `AI_MEMORY_CONTEXT_POLICY.md`
- AI 구현 원칙: `AI_Engine/AI_ENGINE_DEVELOPMENT_GUIDE.md`
- AI·화면 계약: `AI_Engine/AI_FRONTEND_CONTRACT_MAPPING.md`
- 현재 작업: `AI_Engine/AI_ENGINE_WORK_MAP.md`, `docs/TODO.md`

## 2. 데이터 계층

```text
Bronze: 사용자 원본
  대화 · 첨부파일 · 직접 입력 · 채용공고
              ↓
Silver: 근거와 분석 결과
  추출 텍스트 · Evidence · SkillMention · Metric · ontology concept
              ↓
Gold: 사용자 승인 지식
  confirmed Experience · JobRequirement · RequirementExperienceLink
              ↓
Serving: 검색과 응답
  Experience index · Evidence index · RAG · 공고 매칭
```

원본은 AI 결과로 덮어쓰지 않는다. Silver와 Serving 데이터는 원본과 버전 정보로
재생성할 수 있어야 한다. AI 초안은 사용자가 승인하기 전까지 Gold가 아니다.

## 3. 기억 범위

### 세션별 단기 기억

- 현재 `conversation_id`의 사용자·AI 메시지
- 현재 대화에 첨부한 파일
- 현재 대화의 미확정 Proposal

다른 대화 세션의 메시지 원문은 자동으로 섞지 않는다.

### 계정 공통 장기 기억

- 사용자가 검토·승인하여 경험 관리에 저장한 확정 Experience
- Experience에 연결된 원본 근거

장기 기억은 질문과 관련된 항목만 `user_id` 필터가 적용된 RAG로 검색한다.

## 4. 공통 저장 경계

```text
AI 분석 결과
  -> ExperienceDraft 또는 Job 분석 결과
  -> 사용자 미리보기·수정
  -> 사용자 승인
  -> 백엔드 검증과 트랜잭션
  -> 확정 데이터 저장
  -> 검색 인덱스 갱신
```

AI는 확정 Experience를 직접 저장하지 않는다. 동일한 `client_request_id`의 재시도는
중복 데이터를 만들지 않아야 한다.

## 5. 대화형 챗봇 흐름

```text
로그인 사용자 확인
  -> 대화 소유권 확인
  -> 사용자 메시지·첨부 저장
  -> 현재 대화 문맥 복원
  -> 질문과 관련된 확정 경험·Evidence 검색
  -> 챗봇 실행
  -> 답변·인용·후속 행동 저장
  -> HTTP 또는 SSE 응답
```

일반 질문은 별도 구조화 분석 없이 대화형 챗봇으로 처리한다. 자동 모드에서 경험
정리나 공고 분석 실행 의도가 명시된 경우에만 해당 체인으로 라우팅한다.

## 6. 대화 내용 경험 정리 흐름

```text
[대화내용으로 경험 정리하기]
  -> 마지막 성공 분석 이후의 사용자 원문 범위 계산
  -> 사용자 원문을 경험·공고·혼합·무관·불확실로 분류
  -> 공고 원문은 경험 근거에서 분리
  -> 직전 AI 질문은 짧은 사용자 답변의 문맥으로만 제한 사용
  -> ExperienceDraft[] 0..N 생성
  -> exact citation과 source ID 검증
  -> 사용자 검토·수정·개별 또는 전체 승인
  -> Domain · Project · Experience 저장
```

AI 답변은 사용자의 짧은 답변이 무엇을 가리키는지 복원하는 문맥으로 사용할 수 있지만,
AI 답변에만 존재하는 주장은 경험 사실의 증거로 사용할 수 없다.

## 7. 직접 입력·파일 경험 정리 흐름

```text
직접 입력 텍스트 + 첨부파일
  -> 원본 파일·해시 저장
  -> TXT/PDF 텍스트 추출 또는 이미지 OCR
  -> 파일별 근거와 exact quote 생성
  -> 텍스트와 파일 분석 결과 통합
  -> ExperienceDraft[] 0..N
  -> 사용자 승인 후 확정 Experience 저장
```

파일 추출 텍스트는 원본 바이너리를 대체하지 않는다. 파서 버전과 해시를 기록하여
파서가 바뀌었을 때 재처리 여부를 판단한다.

## 8. 채용공고 분석 흐름

```text
공고 원문 또는 추출된 파일 텍스트
  -> 사용자가 원문 확인·수정
  -> JobRequirement[] 추출
  -> source_excerpt와 위치 검증
  -> 확정 Experience index에서 후보 검색
  -> 후보의 Evidence와 명시적 조건 재검증
  -> RequirementExperienceLink[] 생성
  -> 분석 결과 저장 및 화면 제공
```

임베딩은 후보를 찾는 데 사용한다. 필수 기술은 sourced canonical concept ID가 같거나
검증된 alias일 때만 충족한다. `related` 관계는 검색 확장에는 사용할 수 있지만 필수
조건 충족으로 판정하지 않는다. 수치 조건은 exact quote에서 다시 파싱해 비교한다.

## 9. 검색 인덱스 흐름

두 종류의 검색 문서를 분리한다.

1. Experience search document
   - 확정 경험의 제목·요약·행동·결과·기술·정량 성과
2. Evidence chunk
   - 원본 확인과 인용을 위한 텍스트 청크

```text
저장·수정·삭제 이벤트
  -> 검색 문서 생성
  -> content_hash 비교
  -> 신규·변경 문서만 임베딩
  -> stale vector 삭제
  -> 인덱스 버전 기록
```

Chroma는 파생 인덱스다. 인덱스가 없어져도 DB와 원본 근거에서 다시 구축할 수 있어야 한다.

## 10. 주요 구조화 결과

### ExperienceDraft

```text
domain · project · title · summary · situation
actions[] · results[] · role
skills[] · skill_mentions[]
facts[] · metrics[]
missing_information[]
source_ref_ids[] · field_citations{}
```

### JobRequirement

```text
id · type · title · summary
source_excerpt · source_locator
importance · keywords[]
skill_mentions[] · metrics[]
```

### RequirementExperienceLink

```text
requirement_id · experience_id
source · status · similarity_score
reason · evidence_ids[] · skill_matches[]
model_version · index_version
```

## 11. 완료 조건

- 원본, AI 초안, 사용자 승인 데이터가 구분된다.
- 한 입력에서 경험 0개·1개·여러 개를 처리한다.
- 모든 확정 사실과 추천이 원본 근거로 추적된다.
- 다른 사용자와 다른 대화 세션의 원문이 섞이지 않는다.
- 재시도와 반복 분석이 중복 저장을 만들지 않는다.
- 벡터 인덱스는 변경된 데이터만 갱신하고 전체 재구축할 수 있다.
- 규격 밖 기술과 표현이 정규화 실패 때문에 사라지지 않는다.
