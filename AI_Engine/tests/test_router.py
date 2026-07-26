"""최소 FastAPI 서버와 상태 확인 API 테스트."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from AI_Engine.router import app


class HealthApiTests(unittest.TestCase):
    # 실제 포트를 열지 않고 FastAPI 애플리케이션에 HTTP 요청을 전달한다.
    # 이 테스트는 Gemini API 키나 외부 네트워크를 사용하지 않는다.
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_returns_server_status(self) -> None:
        """서버가 실행 가능하면 약속한 상태와 서비스 이름을 반환한다."""

        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "service": "career-memory-ai-api",
            },
        )

    def test_local_frontend_origin_is_allowed(self) -> None:
        """Vite 개발 서버에서 보내는 브라우저 요청에 CORS 헤더를 반환한다."""

        response = self.client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://localhost:5173",
        )


if __name__ == "__main__":
    unittest.main()
