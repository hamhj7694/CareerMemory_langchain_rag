# AWS EC2 배포 준비 및 운영

AWS 접근 없이 준비하는 구성이다. 실제 EC2 생성·DNS 연결·HTTPS 발급은 계정 복구 후 진행한다.

## 구성

```text
브라우저 → Caddy(HTTPS :443) → Nginx(React 정적 파일 + /api 프록시)
                                    → FastAPI :8000 (1 process)
                                    → SQLite 작업 큐 → 파일 Worker (1 process)
```

FastAPI와 Worker는 같은 `career-memory-data` Docker 볼륨을 `/state`에 연결한다.
SQLite는 `/state/data/career_memory.db`, Chroma는 `/state/data/vector_store`,
업로드 원본은 `/state/data/uploads`, AI 사용량은 `/state/data/ai_budget.db`에 저장된다.
API·Worker 포트는 호스트에 공개하지 않는다. Nginx 포트는 호스트 loopback만 허용한다.
소스·API 키·데이터는 프론트엔드 이미지에 포함하지 않는다.

API가 DB 생성과 기존 스키마 보완을 마친 뒤 Worker를 시작한다. 재배포에서도 볼륨 이름은 고정된다.
SQLite와 로컬 Chroma를 사용하므로 **API 1개, Worker 1개, EC2 1대** 구성을 유지한다.
여러 인스턴스로 확장할 때에는 DB와 벡터 저장소를 먼저 외부 서비스로 분리한다.
Docker 볼륨은 컨테이너 재생성을 견디지만 EC2/EBS 삭제·장애까지 보호하지는 않는다.

## 로컬 Docker 실행

Docker Engine/Desktop과 Compose v2가 필요하다. 프로젝트 루트에서:

```bash
cp deploy/.env.deploy.example .env.deploy
# 로컬 HTTP 검증에 한해서 APP_ENV=development, FRONTEND_URL=http://localhost:8080
# AI_ENABLED=false를 유지하면 인증·업로드·파일 추출 검증은 AI 비용 없이 진행된다.
docker compose --env-file .env.deploy config --quiet
docker compose --env-file .env.deploy up -d --build --wait --wait-timeout 240
```

`http://localhost:8080`에서 시작 화면을 열고 게스트 체험, 계정 전환, 텍스트 업로드를 확인한다.
API 상태는 `/health`, OCR·문서 변환·미디어 준비 상태는 `/capabilities`에서 확인한다.
Docker 이미지에는 Tesseract 영어/한국어, LibreOffice, FFmpeg가 포함된다.
HWP→HWPX 전용 변환기는 포함하지 않는다. HWP 변환 지원 여부는 실제 파일로 따로 검증한다.
JS 렌더링이 필수인 일부 웹 문서는 브라우저 fallback을 꺼 둔 운영 기본값에서 추출이 제한된다.

영속성 smoke test는 **테스트용 데이터 볼륨**에서만 실행한다:

```bash
python scripts/smoke-deployment.py create
docker compose --env-file .env.deploy down
docker compose --env-file .env.deploy up -d --wait
python scripts/smoke-deployment.py verify
```

이 검사는 실제 업로드 → Worker 추출 → 컨테이너 재생성 → 세션·첨부·원본 해시 보존을 확인한다.
AI 호출은 하지 않는다. `down -v`, `docker volume rm career-memory-data`는 데이터를 삭제하므로 운영에 사용하지 않는다.
브라우저 단위 흐름은 `npm run test:e2e`, AI 비용 보호·인증·데이터 소유권은 Python 테스트로 검증한다.

## 공개 서비스 보호

- 운영 쿠키: 기존 HttpOnly·SameSite 쿠키에 `APP_ENV=production`의 Secure 옵션을 적용한다. 공개 서비스는 HTTPS로 접속한다.
- 기존 CSRF 검사, 사용자별 데이터 접근 검사, Argon2 해시, 간단 PIN 로그인 실패 잠금 유지.
- 운영 CORS는 `FRONTEND_URL` 한 곳만 허용하고 Swagger/OpenAPI 공개 경로를 닫는다.
- Nginx는 상태 변경 요청을 IP별 6회/분, 순간 burst 10회, 동시 연결 10개로 제한한다. 업로드 본문은 26MiB다.
- 실제 클라이언트 IP는 고정 IP `172.30.88.2`의 Caddy에서만 신뢰한다. 외부에서 보낸 X-Forwarded-For를 직접 신뢰하지 않는다.
- CSP·프레임 차단·MIME sniffing 차단·리퍼러 정책을 적용한다. 외부 이미지 표시 등은 CSP로 제한될 수 있다.
- 운영 업로드 저장량: 사용자당 100MiB, 전체 2048MiB, 디스크 여유 1024MiB 검사. 동시 업로드에서는 용량 검사 후 쓰기 사이에 소폭 초과할 수 있으므로 디스크 알람도 설정한다.
- 컨테이너 로그는 파일당 10MB, 3개로 회전한다. backend는 UID 10001, capability 제거로 실행한다.
- 기존 URL 수집은 사설·loopback·link-local 대상 등을 차단한다. EC2에서는 IMDSv2를 필수로 설정한다.

`AI_ENABLED=false`가 운영 초기값이다. 실제 키와 provider별 결제 제한을 설정한 후 `true`로 바꾼다.
일일 글로벌 한도는 기본 100 operation이며 UTC 자정에 갱신한다. API와 Worker가 SQLite로 원자적으로 예약하므로
새 계정, 프로세스 재시작, 재배포로 초기화되지 않는다. 실패한 시도도 차감한다.
채팅 모델 실행·구조화 호출·STT는 1회, 임베딩은 입력 텍스트 수만큼 차감한다.
OpenAI 자동 재시도는 운영에서 끈다. Gemini SDK 내부 호출 수는 operation과 일대일로 일치한다고 보장하지 않는다.
이 한도는 **청구 금액 한도가 아니다**. Provider 프로젝트 결제 한도와 사용량 알림을 별도로 설정한다.
채팅 출력 2000토큰, 구조화 출력 8000토큰, 구조화 입력 100000자, 미디어 120초 제한을 함께 적용한다.
한도 초과는 새 provider 호출 전에 차단하며 기존 API 오류 처리 경로에 따라 429 또는 분석 실패 안내로 표시된다.

## AWS 복구 후 준비

1. 루트 MFA를 복구한 뒤 운영용 IAM 권한을 분리하고, EC2 관리에 루트 계정을 사용하지 않는다.
2. Ubuntu 24.04 x86_64 EC2를 생성한다. 이 Compose의 메모리 상한 합계를 고려해 RAM 8GiB 이상을 시작점으로 잡고 실제 OCR·문서 변환 부하를 측정한다.
3. EBS는 암호화하고 충분한 저장 공간을 확보한다. 종료 시 볼륨 삭제 설정을 확인하고 별도 백업·스냅샷 정책을 설정한다.
4. 보안 그룹: 80/443 공개, SSH 22는 관리자/배포 접근 경로만 허용. 8000/8080/SQLite/Chroma는 공개하지 않는다.
5. Elastic IP와 도메인 A 레코드를 연결한다. IPv6를 구성하지 않았다면 AAAA 레코드를 추가하지 않는다.
6. Docker 공식 Ubuntu 설치 문서로 Docker Engine과 Compose plugin을 설치한다.
7. 전용 배포 계정에 `/opt/career-memory` 쓰기 권한과 Docker 실행 권한을 부여한다. Docker 그룹은 호스트 관리 권한에 준하므로 계정과 SSH 키를 보호한다.
8. 서버에 `/opt/career-memory/.env.deploy`를 직접 생성하고 권한을 `600`으로 설정한다. SITE_DOMAIN·FRONTEND_URL·키를 채운다. API 키를 GitHub/Vite 변수로 전달하지 않는다.
9. 공개 HTTPS, 게스트 로그인, CSRF 거부, 사용자 간 접근 차단, 파일 원본 다운로드, AI 한도 동작을 확인한다.
10. EBS 용량·EC2 메모리·컨테이너 재시작·백업 실패·Provider 사용량 알림을 설정한다.

GitHub-hosted runner의 IP는 고정되지 않는다. SSH를 전체 공개하는 방식 대신 고정 egress 배포 runner 또는 VPN 경로를 준비한다.
EC2 인스턴스에 PR을 실행하는 self-hosted runner를 설치하지 않는다.

## GitHub Actions

`.github/workflows/deploy.yml`은 PR/main push/수동 실행에서 다음을 수행한다:

1. 프론트엔드 lint·단위 테스트·production build.
2. 백엔드 회귀 테스트와 stub AI 기반 브라우저 E2E.
3. Docker API·web 이미지 빌드, 실제 Worker 처리와 down/up 영속성 smoke test.
4. main/수동 실행은 commit SHA로 이미지와 배포 묶음을 artifact로 보관한다.
5. `DEPLOY_ENABLED=true`인 main 실행만 SSH로 검증한 이미지를 EC2에 반영한다.

AWS 접근 키는 필요하지 않는다. 계정 복구 전에는 `DEPLOY_ENABLED`를 설정하지 않아 배포 job을 건너뛴다.
PR에는 EC2 secrets가 전달되지 않는다. GitHub `production` Environment에서 main 제한과 필요 시 reviewer 규칙을 설정한다.

| GitHub 설정 | 값 |
| --- | --- |
| Repository variable `DEPLOY_ENABLED` | 준비가 끝난 뒤 `true` |
| Environment secret `EC2_HOST` | EC2 DNS/IP, SSH 접속 가능한 주소 |
| `EC2_USER` | 전용 배포 계정 |
| `EC2_SSH_KEY` | 전용 private key |
| `EC2_KNOWN_HOSTS` | 신뢰할 수 있는 경로로 확인한 서버 host key를 포함한 known_hosts 줄 |

워크플로는 StrictHostKeyChecking을 켜고 임의 `ssh-keyscan` 결과를 자동 신뢰하지 않는다.
SSH secrets만 Environment에 저장하고 AI 키는 서버의 `.env.deploy`에만 둔다.
main branch protection에서 frontend/backend/containers checks를 필수로 지정한다.
Actions 버전 태그와 Docker base image 태그는 향후 업데이트될 수 있다. 검증한 이미지 artifact는 SHA별로 보존하며,
더 강한 공급망 고정이 필요하면 action SHA·base image digest와 Linux용 Python lock을 추가한다.
배포 묶음에는 이미지가 포함되어 크기가 크므로 artifact 저장 공간과 보존 기간을 확인한다.
artifact 보관은 GitHub 저장량에 포함된다. [공식 저장량 안내](https://docs.github.com/en/billing/concepts/product-billing/github-actions)를 참고한다.

## 백업과 롤백

자동 배포는 기존 API·Worker를 중지하고 `career-memory-data` 전체를
`/opt/career-memory/backups/<UTC시간>-<SHA>.tar.gz`로 백업한 뒤 새 컨테이너를 시작한다.
SQLite·Chroma·업로드·AI 사용량을 함께 보존한다. 백업에는 개인정보가 포함되므로 접근을 제한한다.
서버 밖 암호화 저장소로 복사하고 보존 기간·복구 테스트를 운영한다. 이 저장소에는 아직 S3 자동 업로드를 구성하지 않았다.
디스크가 부족하면 백업이 실패할 수 있으며 배포를 중단한다. 자동 배포 중에는 짧은 서비스 중단이 발생한다.

health 실패 시 이전 release 이미지로 돌아간다. **DB 스키마는 자동으로 되돌리지 않는다.**
기존 startup migration은 컬럼을 보완하므로 코드 롤백만으로 충분한지 확인해야 한다.
데이터 복구가 필요하면 사용자 입력을 중단하고 현재 상태도 별도 보관한 뒤 검증한 백업을 새 볼륨에 복원한다.
기존 볼륨을 삭제하지 말고 임시 Compose override로 복원 볼륨을 연결해 검증한 후 교체한다.

수동 이미지 롤백 예시(이전 SHA는 보관된 release 디렉터리 이름):

```bash
cd /opt/career-memory/releases/<이전_SHA>
export IMAGE_TAG=<이전_SHA> DEPLOY_ENV_FILE=/opt/career-memory/.env.deploy
docker compose --env-file "$DEPLOY_ENV_FILE" -f compose.yaml -f compose.production.yaml up -d --no-build --wait
```

기존 로컬 데이터를 옮길 때에는 로컬 API·Worker를 중지하고 SQLite와 uploads/vector_store를 함께 복사한다.
실사용 개인정보를 공개 체험 서버에 자동으로 넣지 않는다. 기존 DB 내부 blob은 필요하면
`python -m AI_Engine.migrate_attachment_blobs`의 dry run 결과를 먼저 검토한다.

## 공식 참고

- [Compose startup order와 health 조건](https://docs.docker.com/compose/how-tos/startup-order/)
- [Docker 볼륨](https://docs.docker.com/compose-file/volumes/)
- [Docker Engine Ubuntu 설치](https://docs.docker.com/engine/install/ubuntu/)
- [GitHub deployment environments](https://docs.github.com/en/actions/concepts/workflows-and-actions/deployment-environments)
- [Caddy forwarded headers](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
- [EC2 security groups](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/creating-security-group.html)
