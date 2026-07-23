# API 계약 협업 문서

이 문서는 프론트엔드와 사용자 담당 AI 엔진 사이의 살아 있는 계약 기록이다. PRD 7장이 초기 기준이며, 확정 변경은 여기에 먼저 기록한다.

## Endpoint 목록

| 영역 | Method | Endpoint | 상태 |
|---|---|---|---|
| 입력 | POST | `/api/inputs/text` | FE-001 기준안·AI 확인 필요 |
| 입력 | POST | `/api/inputs/file` | FE-001 기준안·AI 확인 필요 |
| 경험 | POST | `/api/experiences/commit` | FE-001 기준안·AI 확인 필요 |
| 경험 | GET | `/api/experiences/tree` | FE-001 기준안·AI 확인 필요 |
| 경험 | GET | `/api/experiences/{experienceId}` | FE-001 기준안·AI 확인 필요 |
| 경험 | PATCH | `/api/experiences/{experienceId}` | FE-001 기준안·AI 확인 필요 |
| 경험 | GET | `/api/experiences/{experienceId}/sources` | FE-001 기준안·AI 확인 필요 |
| RAG | POST | `/api/chat/experiences` | FE-001 기준안·AI 확인 필요 |
| 공고 | POST | `/api/jobs/analyze` | FE-001 기준안·AI 확인 필요 |
| 공고 | POST | `/api/jobs/{jobId}/match` | FE-001 기준안·AI 확인 필요 |
| 자소서 | POST | `/api/cover-letters/generate` | FE-001 기준안·AI 확인 필요 |
| 자소서 | POST | `/api/cover-letters/revise` | FE-001 기준안·AI 확인 필요 |
| 공고 | GET | `/api/jobs/{jobId}` | 사용자 추가 승인·상세 계약은 FE-002 fixture 기준 |
| 자소서 | GET | `/api/documents/{documentId}` | 사용자 추가 승인·상세 계약은 FE-002 fixture 기준 |
| 자소서 | PATCH | `/api/documents/{documentId}` | 사용자 추가 승인·상세 계약은 FE-002 fixture 기준 |
| 원본 | PATCH | `/api/sources/{sourceId}` | 텍스트 원본 수정 |
| 원본 | DELETE | `/api/sources/{sourceId}` | 원본·근거 연결 삭제 |
| 원본 | GET | `/api/sources/{sourceId}/download` | 업로드 파일 다운로드 |

## FE-001 프론트엔드 기준안

파일 입력은 동일 endpoint에서 단일 `file`과 다중 `files`를 모두 허용한다. 다중 입력은 `files` 필드를 반복 전송하며 기본 제한은 PDF/TXT 최대 5개, 파일당 25MiB, 요청 전체 100MiB다. 응답은 여러 원본을 통합한 하나의 구조화 초안과 각 파일 메타데이터 배열을 반환한다.

상세 DTO와 화면 모델은 `docs/api/FE-001_API_SCREEN_MODEL_SPEC.md`를 기준으로 한다. AI 엔진 담당자 확인 전에는 아래를 프론트 기본값으로 사용한다.

- 성공 resource는 envelope 없이 반환, 오류는 `{ error: ... }` envelope
- 오류 필드: `code`, `message`, `field_errors`, `request_id`, `retryable`
- 날짜는 timezone 포함 ISO 8601, ID는 opaque string
- optional은 원칙적으로 생략, 의미 있는 명시적 부재만 `null`, 배열은 항상 배열
- 장시간 호출은 동기 HTTP, GET 15초·일반 mutation 30초·AI 120초·파일 180초 timeout
- AI POST 자동 재시도 없음; 동일 사용자 동작의 수동 재시도에는 같은 `client_request_id`
- 파일 기본 사전검증은 PDF/TXT, 10 MiB
- match는 항목별 부분 성공을 지원하고, 나머지는 요청 전체 성공/실패

## 결정 로그

| 날짜 | 항목 | 결정 | 결정자 | 영향 작업 |
|---|---|---|---|---|
| 2026-07-22 | FE-001 프론트 기준안 | 12 API DTO·오류·adapter·화면 모델 제안 | API Integration Agent | FE-002, FE-100 이후 |
| 2026-07-22 | 상세 복구·문서 저장 API | 공고 GET, 문서 GET/PATCH 3개 추가 승인 | 사용자 | FE-002, FE-130, INT-402 |

## 열린 질문

1. 장시간 endpoint가 동기 방식과 제안 timeout을 지원하는가?
2. mutation의 `client_request_id` 멱등성을 서버가 보장하는가?
3. PDF/TXT MIME·최대 크기·암호화 PDF 정책은 무엇인가?
4. 자기소개서 글자 수 계산 기준은 무엇인가?
5. 공고/문서 GET과 직접 편집 저장 API를 V1에 추가할 것인가?
6. 경험 숨기기·복원과 프로젝트 연결 보류를 영속화할 것인가?
7. job match 항목별 부분 성공 schema를 지원하는가?
8. 개발 CORS origin과 API base URL은 무엇인가?

## 변경 규칙

계약 변경 시 이전/새 예시, 영향 endpoint, 영향을 받는 fixture·adapter·화면, 적용 날짜를 함께 남긴다. UI는 이 문서에서 확정되지 않은 서버 동작에 직접 의존하지 않는다.
