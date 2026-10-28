# Career Memory 개발 안내

이 파일은 Codex가 저장소를 읽을 때의 짧은 안내다. 사용자의 최신 요청과 실제 코드가 우선한다.

- 실행·환경 변수·검증 명령: `README.md`, `.env.example`, `package.json`
- 원본, Evidence, 승인 데이터, 검색 인덱스의 설계 원칙: `docs/AI_DATA_ARCHITECTURE.md`
- API 구현: `AI_Engine/router.py`, `AI_Engine/api/`, `AI_Engine/schemas/`
- 화면과 API 연결: `src/pages/`, `src/features/`, `src/api/`
- 배포 작업: `docs/EC2_DEPLOYMENT.md`, `docs/AWS_CICD_SETUP.md`, `docs/DEPLOYMENT_VERIFICATION.md`
- 누적 개발 작업 로그: `docs/DEVELOPMENT_LOG.md`

작업 전 변경 범위의 코드와 테스트를 확인한다. API 필드는 서버 스키마와 프론트 어댑터를 함께 살핀다. AI 분석의 원문·근거·사용자 승인 경계는 데이터 아키텍처 문서를 따른다. 완료 후에는 변경 범위에 맞는 테스트를 실행하고, 문서에 적힌 상태나 명령이 코드와 다르면 문서를 함께 고친다.

개발 작업을 마치면 `docs/DEVELOPMENT_LOG.md` 맨 위에 날짜, 변경 결과, 확인 근거, 검증 결과와 남은 문제를 짧게 기록한다. 미커밋 작업은 그렇게 표시하고 비밀 값이나 개인정보는 적지 않는다.
