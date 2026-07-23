# TODO

상태: `[ ] todo`, `[~] in-progress`, `[!] blocked`, `[?] review`, `[x] done`

## 현재 우선순위

- [x] `FE-000` 주요 사용자 흐름과 예외 상태 명세 — 사용자 승인 완료
- [x] `FE-001` API 요청/응답 DTO 및 공통 오류 형식 협의 — 추가 API 3개 승인 완료
- [x] `FE-002` Mock fixture 구조 확정 — 15 API × 4 시나리오 및 runtime 연결
- [x] `FE-003` 레퍼런스 조사·레이어 배치·톤앤매너·디자인 토큰·핵심 와이어프레임
- [x] `FE-100` Vite React 프로젝트 구성
- [x] `FE-110` React Router 및 AppLayout
- [x] `FE-120` 공통 상태/UI 컴포넌트
- [x] `FE-130` API client 및 Mock 전환
- [x] `FE-201` 텍스트 입력 및 파일 업로드
- [x] `FE-202` 구조화 결과 표시·편집·연결 선택
- [x] `FE-203` 경험 확정 저장
- [x] `FE-204` 경험 트리·상세·원본
- [x] `FE-205` 경험 RAG 대화
- [x] `FE-301` 공고 입력·요구사항
- [x] `FE-302` 경험 대조 결과
- [x] `FE-303` 자기소개서 생성 조건
- [x] `FE-304` 자기소개서 결과·편집
- [ ] `INT-401` 경험 관련 실API 통합
- [ ] `INT-402` RAG·공고·자기소개서 실API 통합
- [?] `QA-410` Mock 회귀·접근성 검증 — 자동·라우트·시각 smoke 완료, 실API 회귀 별도
- [x] Supervisor Mock Frontend V1 승인 — Blocker 0 / Major 0

## 사용자(AI 엔진)와 협의 필요

- [ ] 공통 오류 응답 형식과 HTTP status 규칙
- [ ] 각 endpoint의 nullable/optional 필드 및 빈 배열 규칙
- [ ] 파일 크기 제한과 중복 파일 판정 결과
- [ ] 장시간 분석 요청의 timeout 또는 비동기 처리 방식
- [ ] ID/날짜 형식과 수정 API의 응답 본문
- [ ] CORS 및 로컬 개발 base URL

## 추후 업데이트 백로그

- [ ] `FUT-JC01~08` 여러 채용공고 비교 — 현재 V1 제외, `docs/roadmap/FUTURE_UPDATES.md` 참조

## 완료 기록 규칙

항목 완료 시 체크만 하지 말고 관련 PR/커밋 또는 변경 파일, QA 결과, 남은 계약 가정을 하위 메모로 남긴다.
# V2 Chat-first 리모델링

- [x] V2 PRD·사용자 흐름·디자인·API 계약
- [x] `/chat` 기본 진입과 통합 composer
- [x] 구조화 제안 수정·승인·거절
- [x] 승인 경험과 경험 관리 공유 상태 연결
- [x] 경험 검색·필터·관계 보기·수정·삭제
- [x] 대화 URL 및 새로고침 복구
- [x] QA Blocker 수정과 재검증
- [ ] 사용자 AI 엔진 연결
- [ ] 챗 공고 분석과 공고 상세 직접 연결
- [ ] 브라우저 E2E 자동화
