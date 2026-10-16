# Career Memory — AI Application & RAG

대화·문서·채용공고에 흩어진 커리어 원본을 근거와 함께 보존하고, AI가 추출한 경험 초안을 사용자가 검토·승인한 후 RAG로 재사용하는 개인 AI 서비스입니다.

- **Frontend:** React · Vite
- **Backend:** FastAPI · SQLAlchemy · SQLite
- **AI:** OpenAI/Gemini · LangChain/LangGraph · ChromaDB
- **핵심 설계:** Bronze/Silver/Gold/Serving, source ID + exact quote, 경량 기술 온톨로지, 사용자 승인형 지식
- **배포·서빙:** AWS EC2 · Docker Compose · Nginx · Caddy(HTTPS)
- **CI/CD:** GitHub Actions · AWS ECR · OIDC · SSM

## 로컬 개발 실행

Python과 Node.js 설치 후 저장소 루트에서 진행합니다.

```bash
python -m venv .venv
# 가상 환경을 활성화한 뒤
pip install -r requirements.txt
npm ci
cp .env.example .env
```

`.env`에 `AI_PROVIDER=openai`, `OPENAI_API_KEY` 등 필요한 비밀 설정을 입력합니다. **실제 API 키는 Git에 올리지 않습니다.**

서로 다른 터미널에서 다음 프로세스를 실행합니다.

```bash
# 1. Backend
python -m uvicorn AI_Engine.router:app --host 127.0.0.1 --port 8000

# 2. 첨부 처리 worker
python -m AI_Engine.file_processing_worker --poll-seconds 2

# 3. Frontend (환경변수 설정 후 실행)
VITE_USE_MOCK=false VITE_API_BASE_URL=same-origin VITE_PROXY_TARGET=http://127.0.0.1:8000 npm run dev
```

웹: http://localhost:5173 · API 상태: http://127.0.0.1:8000/health

## 테스트

```bash
python -m unittest discover -s AI_Engine/tests -p 'test_*.py'
npm test
npm run lint
npm run build
npm run test:e2e
```

## 기술 검증 자료

- [AI 데이터 아키텍처](docs/AI_DATA_ARCHITECTURE.md)
- [벤치마크 결과와 평가 조건](AI_Engine/benchmarks/RESULTS.md)

## AWS EC2 · Docker Compose 배포 및 서빙

React/Nginx, FastAPI/Uvicorn, 파일 처리 Worker를 Docker 컨테이너로 분리해 **AWS EC2에서 Docker Compose로 통합 배포**했습니다. Caddy 기반 HTTPS 공개 환경과 SQLite·ChromaDB·업로드 파일의 Docker 볼륨 영속성 구조를 구성했습니다.

**GitHub Actions → AWS ECR → SSM → EC2** 배포 워크플로우를 구현했습니다. GitHub OIDC 인증으로 ECR에 이미지를 업로드하고 SSM을 통해 배포하는 흐름이며, **2026-10-16 `main` 대상 수동 실행(`workflow_dispatch`)에서 Frontend·Backend·Containers·Deploy 작업이 모두 성공**한 기록을 확인했습니다. 이 기록은 배포 파이프라인의 성공을 나타내며, 모든 `main` push의 자동 배포 성공이나 장기간 운영 안정성을 검증했다는 의미는 아닙니다.

- [자동 배포 성공 실행 기록](https://github.com/hamhj7694/CareerMemory_langchain_rag/actions/runs/38906826122)
- [EC2 배포 구성](docs/EC2_DEPLOYMENT.md) · [CI/CD 설정 및 절차](docs/AWS_CICD_SETUP.md)

## 운영 범위 및 주의사항

이 저장소의 `main`은 애플리케이션 소스와 테스트·검증에 필요한 파일 중심으로 정리되어 있습니다. 이전의 포트폴리오 원본 및 개발 작업 기록은 `archive/pre-deploy-cleanup-20261014` 브랜치에서 확인할 수 있습니다.

HTTPS 공개 및 배포 파이프라인 구성과 별개로, **비용·호출 제한, 게스트 기록 삭제 정책, DB/파일/벡터 백업과 복구, 장애 대응 및 장기간 안정성**은 운영 환경에 맞춰 지속적으로 점검해야 합니다. Docker 볼륨은 EC2·EBS 장애에 대한 독립 백업을 대체하지 않습니다.

이 프로젝트는 Foundation Model을 직접 학습한 프로젝트나 상용 규모의 데이터레이크가 아니라, 경량 지식 구조와 원문 근거 검증을 갖춘 AI 애플리케이션 PoC입니다.
