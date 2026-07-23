# FE-002 Mock fixture 명세

- 상태: 완료
- 기준: `FE-001_API_SCREEN_MODEL_SPEC.md`, 사용자 승인 추가 API 3개
- 범위: 15개 API의 UI 개발·QA용 wire fixture
- 구현 위치: `mocks/manifest.json`, `mocks/scenarios/*.json`

## 사용 원칙

fixture는 HTTP adapter가 받는 것과 같은 `snake_case` wire DTO다. 각 항목은 `{ status, body }` 구조이며, `body`는 성공 resource 또는 공통 `error` envelope다. UI adapter는 `manifest.json`의 route `key`로 시나리오 응답을 찾는다.

시나리오는 다음 네 종류다.

| 시나리오 | 파일 | 목적 |
|---|---|---|
| 정상 | `success.json` | 전체 핵심 흐름과 상세 데이터 |
| 빈 상태 | `empty.json` | 목록·근거·검색 결과 없음, 입력 부족 |
| 부분 성공 | `partial-success.json` | 보완 정보, 경고, 매칭 일부 실패, 글자 수 초과 |
| 오류 | `error.json` | 검증·404·409·429·5xx·timeout 처리 |

## API 매핑

| ID | Endpoint | fixture key | 주요 검증 |
|---|---|---|---|
| API-01 | `POST /api/inputs/text` | `parse_text` | 구조화·경고·필드 오류 |
| API-02 | `POST /api/inputs/file` | `parse_file` | 파일 메타·부분 추출·크기 오류 |
| API-03 | `POST /api/experiences/commit` | `commit_experiences` | 저장·빈 경험·재시도 오류 |
| API-04 | `GET /api/experiences/tree` | `experience_tree` | 중첩·empty·재시도 |
| API-05 | `GET /api/experiences/{experienceId}` | `experience_detail` | 상세·404 |
| API-06 | `PATCH /api/experiences/{experienceId}` | `update_experience` | version 증가·충돌 |
| API-07 | `GET /api/experiences/{experienceId}/sources` | `experience_sources` | text/file/empty/error |
| API-08 | `POST /api/chat/experiences` | `experience_chat` | 근거 있음/없음·timeout |
| API-09 | `POST /api/jobs/analyze` | `analyze_job` | 요구사항·경고·검증 오류 |
| API-10 | `POST /api/jobs/{jobId}/match` | `match_job` | 전체·부분 성공·서비스 오류 |
| API-11 | `POST /api/cover-letters/generate` | `generate_cover_letter` | 생성·보완 경고·rate limit |
| API-12 | `POST /api/cover-letters/revise` | `revise_cover_letter` | 이전 내용·초과 경고·충돌 |
| API-13 | `GET /api/jobs/{jobId}` | `job_detail` | 새로고침 복구·404 |
| API-14 | `GET /api/documents/{documentId}` | `document_detail` | 새로고침 복구·404/5xx |
| API-15 | `PATCH /api/documents/{documentId}` | `update_document` | 직접 편집 저장·초과 경고·충돌 |

## 부분 성공 규칙

API-10은 HTTP 200을 유지하면서 `matches`에 성공 항목, `failures`에 실패 항목을 함께 반환한다. 다른 AI 응답은 resource를 반환하되 `warnings`와 `missing_information`으로 불완전성을 표현한다. 자기소개서 글자 수 초과는 자동 절삭하지 않고 실제 `character_count`와 경고를 반환한다.

## 연동 메모

- 프론트엔드 mock adapter는 `manifest.json`만 route registry로 사용한다.
- 기본 시나리오는 `success`이며 개발 설정 또는 테스트별로 시나리오를 교체한다.
- 동적 ID는 fixture의 대표 ID(`EXP-001`, `JOB-001`, `DOC-001`)에 매핑한다.
- 지연·AbortController 검증은 adapter에서 latency를 주입하며 fixture 본문에는 포함하지 않는다.
- FE-001 원문의 한글 인코딩 손상은 별도 문서 문제다. 본 fixture는 판독 가능한 계약 구조와 승인된 추가 API를 기준으로 작성했다.

## 완료 조건

- 15개 route와 네 시나리오에 동일한 fixture key가 존재한다.
- 모든 JSON이 파싱 가능하다.
- 공통 오류 envelope 필수 필드가 포함된다.
- `src` 및 package 구성은 수정하지 않는다.
