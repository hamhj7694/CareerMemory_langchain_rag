# `/chat` Playwright E2E 가이드

## 목적

수동으로 확인하던 로그인, 채팅 스트리밍, 첨부 파싱, 붙여넣기·드래그앤드롭,
새로고침 복원을 실제 Chrome에서 반복 검증한다.

E2E 실행기는 운영·개발 데이터와 분리된 다음 자원을 매 실행마다 새로 만든다.

- SQLite DB
- LocalBlobStore 첨부 경로
- 경험·Evidence vector 경로
- 테스트 사용자와 대화

실행이 끝나면 서버 프로세스를 종료한 뒤 해당 임시 데이터만 자동 삭제한다.

## 기본 실행

프로젝트 루트에서 실행한다.

```powershell
npm run test:e2e
```

기본 모드는 결정론적 `E2EChatbot`을 사용하므로 OpenAI API 비용이 발생하지 않는다.
Chrome 화면을 보면서 실행하려면 다음 명령을 사용한다.

```powershell
npm run test:e2e:headed
```

기본 포트는 프론트엔드 `14173`, 백엔드 `18100`이다. 다른 포트가 필요하면 실행 전에
환경변수를 지정한다.

```powershell
$env:E2E_FRONTEND_PORT="14174"
$env:E2E_BACKEND_PORT="18101"
npm run test:e2e
```

Chrome이 기본 설치 경로에 없다면 실행 파일을 명시한다.

```powershell
$env:PLAYWRIGHT_EXECUTABLE_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"
npm run test:e2e
```

## 실제 모델 smoke test

이 테스트는 실제 API 비용이 발생하므로 명시적으로 live 모드를 켠 경우에만 실행한다.
`.env`의 `OPENAI_API_KEY`가 유효해야 한다.

```powershell
$env:E2E_AI_MODE="live"
npm run test:e2e -- --grep "@live"
Remove-Item Env:E2E_AI_MODE
```

기본 `npm run test:e2e`에서는 live 테스트를 skip한다.

## 현재 자동 검증 범위

- UI 로그인과 인증 쿠키
- 대화 생성과 SSE 토큰 스트리밍
- 새로고침 후 사용자·AI 메시지 복원
- `+` 버튼을 통한 TXT 첨부와 파싱 완료 상태
- 첨부 근거 기반 답변과 원래 파일명 복원
- 클립보드 파일 붙여넣기
- 파일 드래그앤드롭
- 첨부 제거와 서버 원본 삭제 요청

## 실패 산출물

실패 시 다음 위치에서 원인을 확인한다.

- `test-results/e2e-artifacts/`: screenshot과 trace
- `playwright-report/`: HTML 보고서

```powershell
npx playwright show-trace "test-results/e2e-artifacts/<실패 테스트>/trace.zip"
```

두 디렉터리는 Git에 포함하지 않는다.
