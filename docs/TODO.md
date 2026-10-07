# Career Memory TODO

이 문서는 저장소 전체의 현재 우선순위만 관리한다. AI 세부 작업은
`../AI_Engine/AI_ENGINE_WORK_MAP.md`에서 관리한다.

상태: `[ ]` todo, `[~]` in progress, `[!]` blocked, `[?]` review, `[x]` done

## 1. 현재 기준선

- [x] React/Vite 주요 화면과 공통 상태 구현
- [x] 사용자 인증과 사용자별 데이터 격리
- [x] 대화 저장·복원·스트리밍
- [x] 직접 입력·파일·대화 범위 경험 구조화
- [x] 경험 Proposal 검토와 확정 저장
- [x] 채용공고 요구사항 구조화와 경험 RAG 매칭
- [x] 기술 별칭·관계·미등록 표현의 무손실 정규화
- [x] exact quote 기반 수치 추출과 검증
- [x] 합성 정답 세트와 성능 benchmark
- [x] AI·데이터 문서 체계 통합

현재 테스트와 benchmark 결과는 `../AI_Engine/benchmarks/RESULTS.md`를 기준으로 한다.

## 2. 현재 우선순위

### P0 — 경량 온톨로지와 Evidence 기반

- [ ] `ARCH-110` ontology·Evidence의 내부/공개 필드 경계 확정
- [ ] `ARCH-120` additive migration과 rollback 설계
- [ ] `ONT-100~150` 기술 concept·alias·relation 영속화와 매칭 정책 분리
- [ ] `EVD-100~140` EvidenceDocument·Chunk·EmbeddingRecord 영속화
- [ ] `IDX-100~140` content hash 기반 증분 인덱싱과 전체 재구축
- [ ] `MIG-100~110` 기존 데이터 dry-run 백필
- [ ] `QA-520~550` 온톨로지·lineage·인덱스 평가와 benchmark

세부 완료 조건: `../AI_Engine/AI_ENGINE_WORK_MAP.md`

### P1 — 현재 제품 품질

- [ ] AI DTO와 공개 API DTO의 자동 계약 테스트 확대
- [ ] 정상·빈 결과·부분 성공·오류 fixture 정리
- [ ] 핵심 사용자 흐름 브라우저 E2E 자동화
- [ ] SSE heartbeat와 스트림 재연결 정책
- [ ] AI 오류의 공개 오류 envelope 일관성 검증
- [ ] 실제·익명화 NLU/RAG 평가 세트 확대
- [ ] Retrieval Recall@K, Precision@K, MRR 측정

### P2 — 미완성 제품 기능

- [ ] 자기소개서 생성·수정 실제 API와 저장 연결
- [ ] 여러 채용공고 비교 기능
- [ ] 경험 프로젝트·활동 메타데이터 개선
- [ ] 프론트 route 단위 lazy loading과 대형 컴포넌트 분리

## 3. 운영 전 백로그

- [ ] 요청별 P50/P95 지연시간, 토큰, 비용, 오류율 관측
- [ ] 민감 원문을 남기지 않는 로그 정책
- [ ] DB migration·백업·복구 검증
- [ ] rate limit과 비용 한도
- [ ] 장시간 AI 작업의 비동기 queue와 상태 조회
- [ ] 계정 삭제 시 DB·Evidence·vector 연쇄 삭제 검증
- [ ] 첨부파일 객체 저장소 전환 검토
- [ ] 부하·장애·보안 테스트

## 4. 장기 검토 항목

- [ ] Skill 외 Role·Organization·Industry·Certificate ontology 확장
- [ ] 실제 그래프 질의 필요성 검증 후 Neo4j 또는 RDF 검토
- [ ] 다국어 정규화와 NLU 평가
- [ ] 사용자가 unresolved concept을 검토·승인하는 관리 흐름

장기 제품 기능의 상세 내용은 `roadmap/FUTURE_UPDATES.md`에 기록한다.

## 5. 작업 완료 기록 규칙

- 관련 코드와 문서를 함께 갱신한다.
- 테스트 명령과 결과를 작업 보고 또는 benchmark 문서에 남긴다.
- 실제 모델 평가는 fixture, 모델, 실행 횟수, 비용을 기록한다.
- 일부만 구현한 작업은 `[x]`로 표시하지 않는다.
- 완료된 작업의 긴 이력은 이 문서에 누적하지 않고 `reports/`로 옮긴다.
