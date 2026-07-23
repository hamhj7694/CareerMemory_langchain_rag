# Career Memory RAG — Frontend

React + Vite 기반 Career Memory RAG 프론트엔드다. 현재 Mock Frontend V1이 완료됐으며 `VITE_USE_MOCK=false`로 FastAPI 전환이 가능하다.

## 실행

```powershell
npm.cmd install
Copy-Item .env.example .env
npm.cmd run dev
```

## Mock 시나리오

`.env`의 `VITE_MOCK_SCENARIO`를 `success`, `empty`, `partial-success`, `error` 중 하나로 설정한다.

## 검증

```powershell
npm.cmd run lint
npm.cmd test
npm.cmd run build
```

## 주요 문서

- 제품 요구사항: `PRD.md`
- 사용자 흐름: `docs/product/FE-000_USER_FLOW_SPEC.md`
- API·화면 모델: `docs/api/FE-001_API_SCREEN_MODEL_SPEC.md`
- Mock fixture: `docs/api/FE-002_MOCK_FIXTURE_SPEC.md`
- 디자인: `docs/design/`
- 작업 상태: `docs/TODO.md`
- 추후 업데이트: `docs/roadmap/FUTURE_UPDATES.md`
