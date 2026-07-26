"""회원가입·쿠키 세션·계정 복구 API 테스트."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from AI_Engine.database import models  # noqa: F401
from AI_Engine.database.connection import Base, get_database_session
from AI_Engine.router import app


class AuthApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.session_factory = sessionmaker(
            bind=cls.engine,
            expire_on_commit=False,
        )
        Base.metadata.create_all(bind=cls.engine)

        def get_test_session():
            database = cls.session_factory()
            try:
                yield database
            finally:
                database.close()

        app.dependency_overrides[get_database_session] = get_test_session

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self) -> None:
        with self.session_factory() as database:
            for table in reversed(Base.metadata.sorted_tables):
                database.execute(table.delete())
            database.commit()
        self.client = TestClient(app)

    def register(self, email: str = "user@example.com"):
        return self.client.post(
            "/api/v2/auth/register",
            json={
                "email": email,
                "username": "test_user",
                "display_name": "테스트 사용자",
                "password": "안전한 테스트 비밀번호 1234",
                "password_confirm": "안전한 테스트 비밀번호 1234",
                "recovery_question": "father_name",
                "recovery_answer": "홍길동",
            },
        )

    def test_register_hashes_password_and_sets_httponly_cookie(self) -> None:
        response = self.register()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["user"]["email"], "user@example.com")
        self.assertTrue(response.json()["csrf_token"])
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        with self.session_factory() as database:
            user = database.query(models.User).one()
        self.assertNotEqual(user.password_hash, "안전한 테스트 비밀번호 1234")
        self.assertTrue(user.password_hash.startswith("$argon2"))
        self.assertNotEqual(user.recovery_answer_hash, "홍길동")
        self.assertTrue(user.recovery_answer_hash.startswith("$argon2"))

    def test_six_character_password_is_allowed(self) -> None:
        response = self.client.post(
            "/api/v2/auth/register",
            json={
                "email": "short-password@example.com",
                "username": "short_user",
                "display_name": "여섯 글자",
                "password": "abc123",
                "password_confirm": "abc123",
                "recovery_question": "elementary_school",
                "recovery_answer": "몽이",
            },
        )

        self.assertEqual(response.status_code, 201)

    def test_existing_user_can_change_recovery_question(
        self,
    ) -> None:
        csrf_token = self.register().json()["csrf_token"]

        response = self.client.put(
            "/api/v2/auth/recovery-question",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "current_password": "안전한 테스트 비밀번호 1234",
                "recovery_question": "elementary_school",
                "recovery_answer": "초코",
            },
        )

        self.assertEqual(response.status_code, 200)
        with self.session_factory() as database:
            user = database.query(models.User).one()
        self.assertEqual(user.recovery_question, "elementary_school")
        self.assertNotEqual(user.recovery_answer_hash, "초코")

    def test_first_local_account_claims_pre_authentication_conversations(
        self,
    ) -> None:
        with self.session_factory() as database:
            database.add(
                models.Conversation(
                    id="CONV-legacy",
                    client_request_id="legacy-request",
                    title="기존 로컬 대화",
                    user_id=None,
                )
            )
            database.commit()

        user_id = self.register().json()["user"]["id"]

        with self.session_factory() as database:
            conversation = database.get(
                models.Conversation,
                "CONV-legacy",
            )
        self.assertEqual(conversation.user_id, user_id)

    def test_me_requires_session_and_returns_csrf_token(self) -> None:
        anonymous = self.client.get("/api/v2/auth/me")
        self.register()
        authenticated = self.client.get("/api/v2/auth/me")

        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(authenticated.status_code, 200)
        self.assertTrue(authenticated.json()["csrf_token"])

    def test_login_uses_same_message_for_unknown_email_and_bad_password(self) -> None:
        self.register()
        self.client.cookies.clear()

        unknown = self.client.post(
            "/api/v2/auth/login",
            json={"identifier": "unknown_user", "password": "wrong"},
        )
        wrong_password = self.client.post(
            "/api/v2/auth/login",
            json={"identifier": "test_user", "password": "wrong"},
        )

        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(
            unknown.json()["error"]["message"],
            wrong_password.json()["error"]["message"],
        )

    def test_existing_account_can_still_login_with_email(self) -> None:
        self.register()
        self.client.cookies.clear()

        response = self.client.post(
            "/api/v2/auth/login",
            json={
                "identifier": "user@example.com",
                "password": "안전한 테스트 비밀번호 1234",
            },
        )

        self.assertEqual(response.status_code, 200)

    def test_find_username_returns_username_for_registered_email(self) -> None:
        self.register()

        response = self.client.post(
            "/api/v2/auth/username/find",
            json={"email": "user@example.com"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "test_user")

    def test_authenticated_user_can_set_unique_username(self) -> None:
        registration = self.register()
        csrf_token = registration.json()["csrf_token"]
        with self.session_factory() as database:
            user = database.query(models.User).one()
            user.username = None
            database.commit()

        response = self.client.put(
            "/api/v2/auth/username",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "current_password": "안전한 테스트 비밀번호 1234",
                "username": "new_user",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], "new_user")

    def test_authenticated_user_can_change_display_name(self) -> None:
        registration = self.register()
        csrf_token = registration.json()["csrf_token"]

        response = self.client.put(
            "/api/v2/auth/profile",
            headers={"X-CSRF-Token": csrf_token},
            json={"display_name": "변경한 이름"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["user"]["display_name"],
            "변경한 이름",
        )
        with self.session_factory() as database:
            user = database.query(models.User).one()
        self.assertEqual(user.display_name, "변경한 이름")

    def test_authenticated_user_can_change_password(self) -> None:
        registration = self.register()
        csrf_token = registration.json()["csrf_token"]

        response = self.client.put(
            "/api/v2/auth/password",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "current_password": "안전한 테스트 비밀번호 1234",
                "password": "new123",
                "password_confirm": "new123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.client.get("/api/v2/auth/me").status_code,
            200,
        )
        self.client.cookies.clear()
        old_login = self.client.post(
            "/api/v2/auth/login",
            json={
                "identifier": "test_user",
                "password": "안전한 테스트 비밀번호 1234",
            },
        )
        new_login = self.client.post(
            "/api/v2/auth/login",
            json={"identifier": "test_user", "password": "new123"},
        )
        self.assertEqual(old_login.status_code, 401)
        self.assertEqual(new_login.status_code, 200)

    def test_logout_requires_csrf_and_revokes_session(self) -> None:
        csrf_token = self.register().json()["csrf_token"]

        rejected = self.client.post("/api/v2/auth/logout")
        accepted = self.client.post(
            "/api/v2/auth/logout",
            headers={"X-CSRF-Token": csrf_token},
        )
        after_logout = self.client.get("/api/v2/auth/me")

        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(accepted.status_code, 204)
        self.assertEqual(after_logout.status_code, 401)

    def test_recovery_answer_resets_password_and_revokes_sessions(
        self,
    ) -> None:
        self.register()
        reset = self.client.post(
            "/api/v2/auth/password/recover",
            json={
                "email": "user@example.com",
                "username": "test_user",
                "recovery_question": "father_name",
                "recovery_answer": "홍길동",
                "password": "새로운 안전한 비밀번호 5678",
                "password_confirm": "새로운 안전한 비밀번호 5678",
            },
        )
        old_session = self.client.get("/api/v2/auth/me")
        old_password = self.client.post(
            "/api/v2/auth/login",
            json={
                "identifier": "test_user",
                "password": "안전한 테스트 비밀번호 1234",
            },
        )
        new_password = self.client.post(
            "/api/v2/auth/login",
            json={
                "identifier": "test_user",
                "password": "새로운 안전한 비밀번호 5678",
            },
        )

        self.assertEqual(reset.status_code, 200)
        self.assertEqual(old_session.status_code, 401)
        self.assertEqual(old_password.status_code, 401)
        self.assertEqual(new_password.status_code, 200)

    def test_recovery_is_locked_after_five_wrong_answers(self) -> None:
        self.register()
        request = {
            "email": "user@example.com",
            "username": "test_user",
            "recovery_question": "father_name",
            "recovery_answer": "틀린 답변",
            "password": "새비밀번호1",
            "password_confirm": "새비밀번호1",
        }

        responses = [
            self.client.post(
                "/api/v2/auth/password/recover",
                json=request,
            )
            for _ in range(5)
        ]
        correct_while_locked = self.client.post(
            "/api/v2/auth/password/recover",
            json={
                **request,
                "recovery_answer": "홍길동",
            },
        )

        self.assertTrue(all(response.status_code == 400 for response in responses))
        self.assertEqual(correct_while_locked.status_code, 400)

if __name__ == "__main__":
    unittest.main()
