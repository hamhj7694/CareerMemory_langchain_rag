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

## AWS CI/CD

ECR·GitHub OIDC·IAM·EC2·SSM 설정, GitHub 변수, 자동 배포 활성화와 롤백 절차는
[AWS_CICD_SETUP.md](AWS_CICD_SETUP.md)를 참고한다.

PR에서는 테스트와 빌드만 실행한다. AWS 설정을 마친 뒤 **Repository variable**
`DEPLOY_ENABLED=true`를 등록하면 검증한 main 이미지를 ECR과 SSM을 통해 자동 배포한다.
AWS 장기 Access Key와 서버 SSH 개인키는 사용하지 않는다.

운영 환경변수는 `/opt/career-memory/.env.deploy`에 유지한다.
고정 볼륨 `career-memory-data`가 SQLite·Chroma·업로드·AI 예산을 보존한다.
배포 전 이 볼륨을 백업하고, health 실패 시 이전 이미지와 Compose를 복구한다.
DB 스키마는 자동으로 되돌리지 않는다. 복구 범위와 제한은 위 설정 문서에 정리했다.
