# V2 통합 QA 재검증 보고

- 점검일: 2026-07-22
- 최종 판정: **조건부 승인 — Blocker 0건**
- 범위: `/chat`, `/memory`, `/jobs`, V2 Mock API, 핵심 상태 전이, 회귀 검증

## 핵심 결과

| Acceptance criteria | 결과 | 근거 |
|---|---|---|
| `/`가 챗으로 진입하고 챗이 주 기능으로 표시된다 | 통과 | `/` → `/chat`, 첫 메뉴 `커리어 챗` |
| 챗에서 경험·질문·공고·복수 파일을 입력한다 | 통과 | 단일 composer, 3개 모드, PDF/TXT 복수 첨부 |
| 구조화 제안을 검토·수정·승인·거절한다 | 통과 | `updateProposal`로 수정 payload/version 저장 후 최신 version 승인 |
| 승인한 경험이 `/memory`에 표시된다 | 통과 | ExperienceManager가 `v2ChatApi.listExperiences`를 조회하며 공유 store 사용 |
| 경험을 검색·수정·삭제한다 | 통과 | API 기반 목록/검색, `updateExperience`, `deleteExperience` 연결 |
| `/chat/:conversationId`에서 대화를 복구한다 | 통과 | param으로 conversation과 messages 조회, pending proposal 복구 |
| `/jobs`에서 공고를 분석한다 | 통과(V1) | 기존 공고 분석·경험 비교 경로 유지 |
| 중간/모바일 폭에 대응한다 | 통과(정적) | Chat 1279/900/767px, Memory 1279/767px, Jobs 1100/700px 규칙 확인 |

## 이전 Blocker 재검증

### V2-QA-B01 — 해결

- 이전: 챗 승인 경험과 `/memory`의 로컬 샘플 상태가 분리됨.
- 현재: 경험 관리가 V2 API 목록을 로드하고 수정·삭제도 동일 store에 반영한다.
- Mock smoke: proposal 승인 후 수정한 경험 제목으로 검색되어 1건 반환됨.

### V2-QA-B02 — 해결

- 이전: 제안 수정값이 화면에만 반영됨.
- 현재: UI 편집값을 wire payload로 역매핑하고 `base_version`과 함께 `updateProposal` 호출 후 새 version으로 승인한다.
- Mock smoke: version `1 → 2`, 수정 제목·요약이 승인 경험에 그대로 저장됨.

### `/chat/:conversationId` 복구 — 해결

- `useParams`로 세션을 조회하고 저장된 메시지와 미처리 proposal을 복구한다.
- Mock smoke: 동일 conversation ID와 메시지 2건 조회 확인.
- 잘못된 ID는 빈 화면과 오류 notice로 안전하게 처리한다.

## 잔여 Major

1. **V2-QA-M02 — 챗 공고와 공고 상세의 직접 연계 부족**
   - 챗은 공고 intent를 분류하고 `analyze_job` proposal을 만들지만 현재 경험 proposal 전용 패널에는 표시하지 않는다.
   - 기존 `/jobs`에서 공고 분석·경험 비교가 가능하므로 데이터 손실·핵심 관리 차단은 아니며 **V2 출시 Blocker가 아닌 Major**로 재분류한다.
   - 후속: 공고 proposal 카드와 `/jobs/{jobId}` 이동 action 연결.

2. **V2-QA-M03 — 첫 메시지 직후 중복 표시 가능성**
   - 새 세션 첫 전송에서 `/chat/{id}`로 이동하며 restore effect와 로컬 assistant append가 겹칠 수 있다.
   - 후속: route 전환 시 메시지를 서버 결과 한 경로로만 갱신하거나 message ID로 중복 제거.

## 접근성·품질 후속

- 경험 수정 모달에 `role="dialog"`, `aria-modal`, 제목 연결, Escape 닫기와 focus trap 추가.
- 파일 유형·크기 초과 시 조용히 제외하지 말고 오류 안내 제공.
- 실제 브라우저에서 390/768/1440px와 키보드-only 전수 검사 수행.

## 자동 검증

- ESLint: 통과
- Vitest: **5 files, 15 tests 통과**
- Production build: 통과
- Mock smoke: `대화 생성 → 메시지 → proposal 수정 → 승인 → 경험 검색 → 대화/메시지 복구` 통과

Blocker는 해소되었으므로 V2 Mock 공개 범위는 조건부 승인한다. 잔여 Major는 실API 통합 전 처리하는 것을 권장한다.
