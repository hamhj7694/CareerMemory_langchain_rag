# 계정·AI·저장 데이터 소유권 점검

## 결론

현재 실제 서버에 저장되는 대화와 메시지는 로그인 사용자의 `user_id`로 분리된다. Gemini에 전달하는 과거 문맥도 먼저 사용자 소유 대화를 확인한 뒤 해당 `conversation_id`의 메시지만 조회하므로 다른 계정의 대화가 섞이지 않는다.

목표 기억 정책은 `AI_MEMORY_CONTEXT_POLICY.md`를 따른다. 대화 원문은 세션별 단기 기억으로 격리하고, 사용자 승인 후 경험 관리에 저장된 경험만 계정 공통 장기 기억으로 모든 세션에서 RAG 검색한다. 이 장기 기억 연결은 아직 구현 전이다.

경험 관리, 근거 파일, Proposal, 채용공고 본체는 아직 완전한 백엔드 저장 기능이 아니다. 화면용 Mock이나 브라우저 저장소를 사용하는 부분은 계정 전환 시 격리했지만, 배포용 영구 데이터로 간주하면 안 된다.

## 현재 연결 상태

| 데이터 | 현재 저장 위치 | 계정 연결 | 상태 |
|---|---|---|---|
| 사용자 | SQLAlchemy DB `users` | 사용자 본체 | 완료 |
| 로그인 세션 | DB `auth_sessions` | `user_id` FK | 완료 |
| 비밀번호 재설정 | DB `password_reset_tokens` | `user_id` FK | 완료 |
| 대화 세션 | DB `conversations` | `user_id` FK 및 API 소유권 검사 | 완료 |
| 대화 메시지 | DB `messages` | 소유권 확인된 `conversation_id` FK | 완료 |
| Gemini 대화 문맥 | DB 메시지를 요청마다 복원 | 사용자 소유 대화 확인 후 전달 | 완료 |
| 채용공고 화면 기록 | 브라우저 `localStorage` | 사용자 ID namespace | 임시 연결 |
| 경험 화면 정렬 순서 | 브라우저 `localStorage` | 사용자 ID namespace | 임시 연결 |
| 경험 저장 실패 초안 | 브라우저 `localStorage` | 사용자 ID namespace | 임시 연결 |
| 경험·분류·프로젝트 | 프론트 Mock 메모리 | 계정 전환 시 초기화 | 백엔드 전환 필요 |
| 첨부·근거·Proposal | 프론트 Mock 메모리 | 계정 전환 시 초기화 | 백엔드 전환 필요 |
| 채용공고 분석 결과 본체 | 화면 상태 및 브라우저 기록 | 브라우저 namespace만 적용 | 백엔드 전환 필요 |
| Chroma 경험 RAG | AI 함수와 테스트만 존재 | 운영 사용자 필터 없음 | 연결 전 |
| 챗봇 계정 공통 장기 기억 | 확정 경험 RAG 사용 예정 | `user_id` 필터 필수 | 연결 전 |

## AI 문맥 보안 경계

```text
HttpOnly 로그인 쿠키
  → 현재 사용자 확인
  → conversations.id + conversations.user_id 동시 조회
  → 해당 conversation_id의 messages 조회
  → 최근 메시지를 Gemini 문맥으로 전달
```

사용자가 다른 사람의 `conversation_id`를 주소나 API에 직접 넣어도 첫 소유권 조회에서 `404`가 발생한다.

## 다음 백엔드 전환 순서

1. `domains`, `projects`, `experiences` 테이블과 모든 테이블의 `user_id` 소유권 구현
2. `attachments`, `sources`, `proposals`, `extraction_runs` 테이블 구현
3. 경험 CRUD와 구조 관리 Mock API를 실제 FastAPI API로 교체
4. 채용공고·분석 결과·요구사항·경험 매칭 테이블 구현
5. Chroma collection을 사용자별로 분리하거나 모든 문서 메타데이터에 `user_id`를 넣고 검색 필터 강제
6. 챗봇 요청에서 현재 세션 메시지와 사용자별 확정 경험 검색 결과를 분리해 조립
7. 답변에 참고한 경험 ID와 근거 표시
8. 계정 삭제 시 관계형 DB·파일·벡터 문서 삭제 정책 적용

## 배포 전 확인

- 브라우저 채용공고 기록을 서버 DB로 이동
- 첨부 파일을 사용자별 디렉터리 또는 객체 스토리지 prefix로 분리
- RAG 검색에서 `user_id` 필터 없는 호출을 금지
- 운영 DB를 PostgreSQL로 전환하고 정식 migration 도구 적용
- 사용자 A/B 교차 접근 통합 테스트를 경험·공고·파일에도 확대
