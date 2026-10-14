# GitHub main → ECR → SSM → EC2 자동 배포

AWS 계정 복구 후 아래 설정을 한 번 완료하면, `main` push/merge마다 테스트 성공 후 같은 공개 URL에 자동 배포한다.
지금은 `DEPLOY_ENABLED`가 없거나 `false`이면 AWS 인증·ECR 업로드·SSM 실행을 모두 건너뛴다.
PR은 테스트와 빌드만 실행한다. 운영 서버에 GitHub runner를 설치하지 않는다.

## 배포 흐름

1. `frontend`: lint, 130개 단위 테스트, Vite production build.
2. `backend`: Python 회귀 테스트, 배포 제어 테스트, Playwright E2E.
3. `containers`: API/Worker와 Nginx 이미지를 빌드하고, 실제 파일 Worker 처리와 Compose 재생성 후 데이터 보존을 검사한다.
4. 활성화된 main 실행만 **검증한 이미지 그대로** 임시 GitHub artifact에 담아 `deploy` job에 전달한다. 다시 빌드하지 않는다.
5. `production` 환경의 job이 OIDC로 1시간짜리 AWS 권한을 받고 두 ECR 저장소에 업로드한다.
6. `<commit SHA>-<run ID>-<attempt>` 태그와 각각의 `sha256` digest를 기록한다. 재실행도 새 태그를 사용한다.
7. 지정한 버전의 `CareerMemory-Deploy` SSM 문서에 release ID와 digest 두 개만 전달한다. 임의 shell 명령을 전달하지 않는다.
8. EC2의 bootstrap이 instance role로 ECR에 로그인하고 digest로 이미지를 가져온다. API 이미지에 포함된 동일 버전의 Compose·배포 스크립트를 꺼낸다.
9. 데이터 백업 → Compose 갱신 → API/Worker/Nginx health → 공개 HTTPS `/health` 검사를 수행한다. 실패하면 이전 release의 이미지·Compose로 복구하며 Actions는 실패로 표시한다.

GitHub workflow의 ref별 concurrency와 EC2 `flock` 두 곳에서 중복 실행을 제어한다.
배포 중인 workflow를 자동 취소하지 않는다. 대기 중인 과거 실행은 GitHub 정책에 따라 최신 대기 실행으로 대체될 수 있다.
SSM 성공 접수만으로 성공 처리하지 않고 실제 `Status=Success`, `ResponseCode=0`까지 기다린다.

## 1. 리전과 ECR 저장소

예시는 서울 `ap-northeast-2`, 동일 계정의 Linux x86_64 EC2 한 대다. ARM 인스턴스는 이 빌드와 맞지 않는다.
관리자용 AWS CLI는 IAM Identity Center 등으로 인증한다. GitHub에 관리자 Access Key를 등록하지 않는다.

```bash
aws ecr create-repository --region ap-northeast-2 --repository-name career-memory-api \
  --image-tag-mutability IMMUTABLE --image-scanning-configuration scanOnPush=true
aws ecr create-repository --region ap-northeast-2 --repository-name career-memory-web \
  --image-tag-mutability IMMUTABLE --image-scanning-configuration scanOnPush=true
```

두 저장소 이름과 `<계정ID>.dkr.ecr.ap-northeast-2.amazonaws.com`을 기록한다.
활성 버전과 직전 정상 버전의 태그를 lifecycle policy로 삭제하지 않는다. 이미지를 지우면 해당 버전의 재배포가 불가능할 수 있다.
이미지 검사 결과는 ECR에서 확인하며, 현재 workflow는 검사 결과에 따른 취약점 차단까지 자동화하지 않는다.

## 2. GitHub OIDC와 배포 IAM role

IAM → Identity providers → OpenID Connect를 추가한다.

- Provider URL: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`

`deploy/iam/github-trust.json`의 `ACCOUNT_ID`를 바꾸어 `CareerMemory-GitHubDeploy` role을 만든다.
신뢰 조건은 이 저장소의 **production environment**로 제한되어 있다.
따라서 6단계에서 GitHub environment의 배포 가능 브랜치를 반드시 `main`으로 제한한다.
저장소를 이전하면 trust policy의 owner/repo도 변경해야 한다.

EC2 생성 후 `deploy/iam/github-deploy-policy.json`의 `ACCOUNT_ID`, `AWS_REGION`, `INSTANCE_ID`를 치환해 role의 inline policy로 추가한다.
이 policy는 두 ECR 저장소 push와 단일 EC2·단일 배포 문서 실행만 허용한다.
`AWS-RunShellScript`, 문서 생성/변경, IAM 변경 권한을 이 role에 추가하지 않는다.
인증 토큰과 명령 결과 조회의 `Resource: *`는 해당 API의 권한 범위에 필요하다.

GitHub OIDC role을 EC2에 연결하지 않는다. 다음 instance role과 별개다.

## 3. EC2 instance role·서버·네트워크

`deploy/iam/ec2-trust.json`으로 `CareerMemory-EC2` role을 만들고 다음 권한을 연결한다.

- AWS 관리 policy `AmazonSSMManagedInstanceCore`
- `deploy/iam/ec2-ecr-pull-policy.json`의 계정·리전 치환본

이 role의 instance profile을 Ubuntu 24.04 x86_64 EC2에 연결한다. RAM 8GiB 이상을 시작점으로 보고 OCR 부하를 측정한다.
EBS 암호화, 충분한 이미지·백업 여유 공간, 종료 시 데이터 볼륨 삭제 여부를 설정한다.
IMDSv2를 필수로 설정하고 metadata response hop limit은 `1`로 둔다. 호스트 SSM/AWS CLI가 role을 사용하고 앱 컨테이너에는 AWS 키를 넣지 않는다.

보안 그룹 inbound는 공개 웹의 80/443만 연다. SSH 22, API 8000, Nginx 8080은 열지 않는다.
Elastic IP와 도메인 A 레코드를 연결한다. DNS와 EIP를 유지하므로 이미지 교체 후에도 URL은 같다.

SSM Agent를 설치/업데이트하고 실행 상태를 확인한다. **환경변수 파라미터 보간을 지원하는 Agent 3.3.2746.0 이상**이 필요하다. [AWS 요구 버전](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-troubleshooting.html)
Systems Manager의 Managed nodes에서 Online인지 확인하고 Session Manager로 접속한다.
SSM Agent는 outbound HTTPS 연결을 사용한다. 인터넷 egress 또는 리전별 SSM/ssmmessages VPC endpoint가 필요하다.
ECR image pull에는 ECR API/DKR 및 S3 접근이 필요하다. 이 구성은 Caddy 이미지 다운로드, 인증서 발급, AI 호출에도 인터넷 egress가 필요하다.

호스트에 다음 도구를 설치하고 확인한다.

```bash
docker --version
docker compose version
aws --version
bash --version
flock --version
```

Docker는 공식 Ubuntu 설치 절차의 Engine + Compose v2 plugin, AWS CLI는 v2를 사용한다.
Compose는 `--wait`, 여러 `--env-file` 옵션을 지원하는 최신 v2를 설치한다. Docker 서비스의 부팅 시 자동 시작을 활성화한다.

## 4. 호스트 초기 설치와 운영 환경변수

Session Manager 세션에서 검토한 커밋의 저장소를 내려받는다. 아래 `REVIEWED_COMMIT_SHA`를 실제 승인한 40자리 SHA로 바꾼다.
bootstrap은 호스트의 신뢰 진입점이므로 최초 설치와 후속 변경 때 관리자가 검토해 설치한다.
일상적인 앱 배포에는 이 수동 작업이 필요 없다.

```bash
git clone https://github.com/hamhj7694/CareerMemory_langchain_rag.git /tmp/career-memory-setup
cd /tmp/career-memory-setup
git checkout REVIEWED_COMMIT_SHA
sudo install -d -m 0700 /opt/career-memory
sudo install -o root -g root -m 0755 deploy/bootstrap-release.sh /usr/local/sbin/career-memory-deploy
sudo install -o root -g root -m 0600 deploy/host.conf.example /etc/career-memory-deploy.conf
sudo install -o root -g root -m 0600 deploy/.env.deploy.example /opt/career-memory/.env.deploy
sudoedit /etc/career-memory-deploy.conf
sudoedit /opt/career-memory/.env.deploy
```

위 `install` 명령은 **최초 설치용**이다. 기존 `.env.deploy`를 예시 파일로 덮어쓰지 않는다.
host.conf에는 실제 계정의 registry, 리전, 두 repository 이름을 입력한다.
`.env.deploy`에는 `APP_ENV=production`, `SITE_DOMAIN=실제도메인`, `FRONTEND_URL=https://실제도메인`과 필요한 AI 키를 넣는다.
`AI_ENABLED=false`로 첫 배포를 검증한 후 provider 결제 한도와 API 예산을 설정하고 활성화한다.
Vite 변수, GitHub 변수, SSM 파라미터에는 AI 키를 넣지 않는다. 배포 스크립트는 이 파일을 덮어쓰지 않는다.

환경변수만 바꾼 경우 현재 release를 같은 digest로 다시 활성화하면 Compose가 변경을 반영한다(아래 수동 재배포 명령).
운영 `.env.deploy`와 host.conf의 암호화된 별도 백업도 준비한다. 자동 데이터 백업에는 이 호스트 파일들이 포함되지 않는다.

## 5. 제한된 SSM 문서 생성

관리자 CLI에서 저장소의 `deploy/ssm-document.json`으로 생성한다.

```bash
aws ssm create-document --region ap-northeast-2 --name CareerMemory-Deploy \
  --document-type Command --document-format JSON --content file://deploy/ssm-document.json
```

생성된 숫자 document version(최초 `1`)을 기록한다. GitHub는 `$LATEST` 대신 이 숫자 버전을 사용한다.
문서를 수정할 때 관리자만 새 버전을 만들고 검토한 뒤 GitHub의 version 변수를 갱신한다.
문서는 허용된 release ID와 digest 형식만 받으며 환경변수로 전달한다. 오래된 Agent에서는 누락된 변수가 오류가 되어 실행을 중단한다.

## 6. GitHub 설정과 안전한 활성화

Repository Settings → Environments → `production`을 생성한다.
Deployment branches and tags는 **Selected branches and tags → Branch `main`만** 허용한다.
자동 배포가 목표이므로 required reviewer와 wait timer는 설정하지 않는다.
Settings → Branch protection 또는 Ruleset에서 PR 리뷰와 `frontend`, `backend`, `containers` 성공을 main 반영 조건으로 설정한다.
workflow·deploy 파일 변경도 리뷰한다. main 작성 권한은 운영 코드 실행 권한과 연결된다.

다음 값을 **production Environment variables**로 등록한다(Secrets가 아닌 Variables).

| 이름 | 예시 |
| --- | --- |
| `AWS_REGION` | `ap-northeast-2` |
| `AWS_ROLE_ARN` | `arn:aws:iam::<계정ID>:role/CareerMemory-GitHubDeploy` |
| `ECR_API_REPOSITORY` | `career-memory-api` |
| `ECR_WEB_REPOSITORY` | `career-memory-web` |
| `EC2_INSTANCE_ID` | `i-`로 시작하는 실제 인스턴스 ID |
| `SSM_DOCUMENT_NAME` | `CareerMemory-Deploy` |
| `SSM_DOCUMENT_VERSION` | `1` |

마지막에 **Repository variable** `DEPLOY_ENABLED=true`를 등록한다.
이 값은 job 실행 여부 판단에 쓰이므로 Environment variable로 두지 않는다.
AWS 설정이 끝나기 전에는 미설정 또는 `false`로 유지한다. 초기 설정이 빠지면 AWS 인증 전에 검증 단계에서 실패한다.
기존 SSH 기반 설정을 사용했다면 `EC2_SSH_KEY`, `EC2_KNOWN_HOSTS`, `EC2_HOST`, `EC2_USER` secrets는 이 workflow에서 사용하지 않는다.

이제 main에 merge/push하면 자동 배포된다. 최초에는 Actions → Validate, build and deploy → Run workflow → **main**으로 검증해도 된다.
feature branch 수동 실행과 PR 실행은 운영 배포 조건을 통과하지 않는다.

## 7. 첫 배포 확인과 운영

Actions summary에서 release ID, 이미지 digest, SSM command ID를 확인한다.
SSM Run Command 상세 로그의 `Activated release`와 Actions deploy 성공을 확인한다.
공개 URL의 HTTPS, 게스트 로그인, 텍스트 업로드 → Worker 완료 → 원본 다운로드를 직접 확인한다.
AI 사용을 켠 뒤에는 별도로 실제 provider 기능과 비용을 확인한다.

호스트 경로:

| 경로 | 용도 |
| --- | --- |
| `/opt/career-memory/.env.deploy` | 재배포 시 유지되는 운영 환경변수 |
| `/opt/career-memory/releases/<release ID>/` | 버전별 Compose·스크립트·`images.env` |
| `/opt/career-memory/current` | 마지막으로 health 검증에 성공한 버전 |
| `/opt/career-memory/previous` | 이전 정상 버전 |
| `/opt/career-memory/backups/` | 쓰기 중단 후 SQLite·Chroma·uploads·AI 예산 전체 백업 |
| Docker volume `career-memory-data` | `/state` 영속 데이터 |
| Docker volume `career-memory-certificates` | HTTPS 인증서 |

API/Worker는 1개씩 실행하며 단일 EC2에서 SQLite와 로컬 Chroma를 공유한다.
배포 때 쓰기를 중단하므로 짧은 서비스 중단이 있다. 무중단·다중 인스턴스 배포는 이 구성의 범위가 아니다.
Nginx가 React와 API 프록시를 담당하고, 기존 Caddy gateway가 TLS 자동 발급을 담당한다.

자동 롤백은 **이미지와 Compose 복구**이며 DB를 과거 상태로 덮어쓰지 않는다.
스키마 변경은 이전 앱에서도 읽을 수 있도록 설계해야 한다. 파괴적 migration은 별도 점검·복원 계획이 필요하다.
첫 배포 실패에는 이전 버전이 없어 컨테이너를 중지하고 데이터를 보존한다.
롤백까지 실패하면 SSM에 `ROLLBACK FAILED`가 출력되고 Actions도 실패한다.

Session Manager에서 수동 롤백(동일한 호스트 잠금·백업·health 검사를 사용):

```bash
sudo -i
previous=$(readlink -f /opt/career-memory/previous)
test -f "$previous/images.env"
release_id=$(basename "$previous")
api_digest=$(sed -n 's/^API_IMAGE=.*@//p' "$previous/images.env")
web_digest=$(sed -n 's/^WEB_IMAGE=.*@//p' "$previous/images.env")
/usr/local/sbin/career-memory-deploy "$release_id" "$api_digest" "$web_digest"
```

현재 버전 재시작/환경변수 반영은 위 첫 줄의 `previous` 경로를 `/opt/career-memory/current`로 바꾸어 실행한다.
자동 배포가 실패했는데 이전 버전으로 돌아왔다면 원인 수정 후 main에 새 커밋을 반영한다.
SSM 조회 제한 시간 초과나 runner 중단만으로 호스트 배포가 중단되었다고 판단하지 않는다.
command ID로 실제 실행 상태와 호스트 `current`를 확인한 뒤 재시도한다. 호스트 잠금은 동시에 들어온 배포를 거절한다.

`docker compose down -v`, 데이터 볼륨 삭제, 일괄 `docker system prune --volumes`는 운영에서 실행하지 않는다.
백업과 release는 자동 삭제하지 않는다. EBS 사용량 알림과 보존 정책을 운영하고 활성/직전 버전은 남긴다.
EBS 장애에 대비해 외부 암호화 백업과 복구 훈련을 준비한다. 이 구현은 S3 백업 업로드까지 자동화하지 않는다.

## 공식 참고

- [GitHub OIDC AWS 인증과 environment subject](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)
- [ECR push IAM 권한](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-push-iam.html)
- [ECR registry 인증](https://docs.aws.amazon.com/AmazonECR/latest/userguide/registry_auth.html)
- [SSM document 파라미터와 ENV_VAR](https://docs.aws.amazon.com/systems-manager/latest/userguide/documents-syntax-data-elements-parameters.html)
- [SSM Run Command](https://docs.aws.amazon.com/systems-manager/latest/userguide/run-command.html)
- [Docker Engine Ubuntu 설치](https://docs.docker.com/engine/install/ubuntu/)
- [SSM Agent 설치](https://docs.aws.amazon.com/systems-manager/latest/userguide/ssm-agent.html)
- [AWS CLI v2 설치](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
