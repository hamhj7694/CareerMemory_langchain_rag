# 배포 준비 검증 기록

## 시작 상태 (2026-10-14, Asia/Seoul)

- 브랜치: `main`, 작업 시작 시 `git status --short` 출력 없음.
- 로컬 HEAD: `dda88b0044b7c6e572870c2514147d7255a6a559`.
- fetch 후 원격 main: `181115d907cb2f0dddfd1aad102424e45dd0cb51`.
- 로컬은 원격보다 1커밋 뒤. 원격 변경은 문서·포트폴리오 대량 정리와 README 변경이며 애플리케이션 소스는 동일.
- 기존 파일을 보존하기 위해 자동 pull/reset/삭제를 하지 않았다.
- GitHub Desktop 내장 Git을 찾았으며, Git safe.directory는 각 명령에 해당 저장소만 지정했다. 전역 설정은 변경하지 않았다.
- 이 PC에는 실행 가능한 Python·Node·Docker가 기본 PATH에 없었다. Python 3.12.10·Node 22.14.0을 임시 폴더에 설치해 검증했다. Docker daemon은 설치하지 않았다.

## 실행 구조 분석

- React/Vite는 원래 개발 서버를 사용했다. 운영에서는 Nginx 정적 배포, same-origin API 프록시를 사용한다.
- 서버 진입점: `AI_Engine.router:app`, DB startup 초기화와 사용자별 쿠키/CSRF 인증.
- Worker 진입점: `python -m AI_Engine.file_processing_worker`, SQLite queue와 작업 claim/lease/stale recovery가 이미 존재했다.
- 업로드 API는 원래 즉시 추출했다. `FILE_PROCESSING_MODE=worker`에서는 큐에 저장하고 브라우저가 완료를 확인한다.
- 기존 동기 분석 API는 별도 Worker가 처리할 때까지 기다리므로 같은 작업을 경쟁해서 실행하지 않는다.
- SQLite, Chroma jobs/evidence, 업로드 파일 경로를 같은 볼륨 아래로 모았다.
- 운영 SDK 접근에 글로벌 일일 예산, 출력·입력·미디어 한도, 저장 용량 검사와 reverse proxy 요청 제한을 추가했다.

## 검증 범위

프론트엔드 단위 테스트·빌드·lint, 백엔드 회귀 테스트, AI 예산 경쟁 예약과 실제 provider 호출 전 차단,
Worker 큐 업로드/완료/원본 다운로드, 실제 브라우저 stub AI 흐름을 실행한다.
OpenAI/Gemini 실제 유료 호출과 AWS 자원 생성은 하지 않는다.

Docker image build·Compose health·컨테이너 재생성 후 데이터 보존은 로컬 Docker 부재로
GitHub Actions containers job의 실제 Docker smoke test에서 검증했다.
운영 TLS 발급과 AWS 인증·ECR·SSM 실연동은 AWS 계정 접근 불가로 아직 검증하지 못했다.
이 파일 아래 결과는 실제 완료된 검사만 기록한다.

## 완료 결과

| 검사 | 결과 |
| --- | --- |
| Python unittest | 249개 실행, 실패 0, skip 1 |
| Vitest | 36개 파일, 130개 테스트 통과 |
| Production Vite build | 통과 (bundle 크기 경고 있음) |
| ESLint | 통과 |
| Playwright + 실제 FastAPI + stub AI | 9개 통과, 유료 live smoke 1개 skip |
| npm audit | 취약점 0건 |
| YAML 파싱 및 API/Worker 저장 경로 일치 | 통과 |
| Python compile / git diff --check | 통과 |

브라우저 텍스트 선택 검사는 문단 박스 가운데 대신 실제 글자 위치를 사용하고 AI 응답 완료를 기다리도록 보완했다.
기존 테스트의 브라우저 줄바꿈·화면 이동에 따른 실패를 해결했으며 앱의 텍스트 선택 동작을 제거하지 않았다.
마지막 Worker heartbeat 변경은 프로세스 생존을 표시하며 작업 진척을 보장하지 않는다. 작업 실패·stale lease는 DB 큐에서 별도로 확인한다.

## OIDC·ECR·SSM 자동 배포 전환

작업 시작 브랜치는 `codex/ec2-deployment-prep`, HEAD는 `2cbe42f`, 미커밋 변경은 없었다.
기존 main을 삭제·초기화하거나 직접 변경하지 않고 PR #4의 작업 브랜치에서 구현했다.

- SSH 전송을 제거하고 OIDC 단기 인증, ECR digest 배포, 제한된 SSM 문서 실행으로 전환했다.
- SSM 접수 후 실행 완료까지 조회하고 비정상 종료·시간 초과를 실패로 처리한다.
- 배포 파일을 API 이미지에 포함해 이미지와 Compose·스크립트의 버전을 함께 고정했다.
- 호스트 잠금, 백업, 자동·수동 롤백, 운영 환경변수 보존을 구현했다.
- AWS 설정 전에는 Repository variable `DEPLOY_ENABLED` 조건으로 게시·배포 job을 건너뛴다.

로컬에서는 SSM 제어 테스트 5개, JSON/YAML 파싱, Bash 구문 검사를 통과했다.
Linux에서 실제 Bash 스크립트를 실행하는 테스트 10개도 GitHub CI에서 통과했다(SSM 제어 테스트와 합계 15개).
이 10개는 Docker/AWS CLI를 대역으로 바꾸어 다운로드·설정·백업·컨테이너 및 공개 health 실패,
첫 배포 실패, 롤백 실패 보고, 동시 배포 잠금, 수동 롤백과 release ID 변조 거부를 확인한다.
또한 검증한 이미지의 ECR 게시, digest 전달, 게시 실패·잘못된 digest 차단을 검사한다.
실제 AWS 연동 성공을 의미하지는 않는다.

반복 CI에서 텍스트 선택 E2E가 채팅 route 전환 중 DOM 교체와 경쟁하는 현상을 발견했다.
현재 대화의 복원 API 완료와 입력 가능 상태를 기다리도록 수정했고, 로컬 실제 브라우저에서 해당 테스트를 5회 연속 통과했다.

기존 Docker 검증: [CI run 38568825964](https://github.com/hamhj7694/CareerMemory_langchain_rag/actions/runs/38568825964).
이번 구현 `0038ad3`의 검증: [CI run 38571987312](https://github.com/hamhj7694/CareerMemory_langchain_rag/actions/runs/38571987312).
