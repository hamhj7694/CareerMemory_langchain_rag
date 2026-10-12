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

    def test_guest_starts_without_signup_fields_and_receives_isolated_session(
        self,
    ) -> None:
        response = self.client.post("/api/v2/auth/guest")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["user"]["account_type"], "guest")
        self.assertIsNone(response.json()["user"]["email"])
        self.assertIsNone(response.json()["user"]["username"])
        self.assertTrue(response.json()["csrf_token"])
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        with self.session_factory() as database:
            user = database.query(models.User).one()
        self.assertEqual(user.account_type, "guest")
        self.assertIsNotNone(user.guest_expires_at)

    def test_simple_identifier_creates_then_reopens_same_space(self) -> None:
        profile_required = self.client.post(
            "/api/v2/auth/simple",
            json={"identifier": "함형준", "pin": "123456"},
        )
        with self.session_factory() as database:
            user_count_before_profile = database.query(models.User).count()

        created = self.client.post(
            "/api/v2/auth/simple",
            json={
                "identifier": "함형준",
                "pin": "123456",
                "display_name": "형준님",
                "recovery_question": "recovery_keyword",
                "recovery_answer": "나만의 복구 단어",
            },
        )
        user_id = created.json()["user"]["id"]
        self.client.cookies.clear()

        reopened = self.client.post(
            "/api/v2/auth/simple",
            json={"identifier": "함형준", "pin": "123456"},
        )

        self.assertEqual(profile_required.status_code, 200)
        self.assertTrue(profile_required.json()["profile_required"])
        self.assertEqual(profile_required.json()["identifier"], "함형준")
        self.assertEqual(user_count_before_profile, 0)
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["user"]["account_type"], "simple")
        self.assertEqual(created.json()["user"]["username"], "함형준")
        self.assertEqual(created.json()["user"]["display_name"], "형준님")
        self.assertIsNone(created.json()["user"]["email"])
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.json()["user"]["id"], user_id)
        with self.session_factory() as database:
            user = database.get(models.User, user_id)
        self.assertNotEqual(user.password_hash, "123456")
        self.assertTrue(user.password_hash.startswith("$argon2"))
        self.assertEqual(user.recovery_question, "recovery_keyword")
        self.assertNotEqual(user.recovery_answer_hash, "나만의 복구 단어")
        self.assertTrue(user.recovery_answer_hash.startswith("$argon2"))

    def test_simple_identifier_requires_six_digit_pin(self) -> None:
        response = self.client.post(
            "/api/v2/auth/simple",
            json={"identifier": "easy_user", "pin": "1234"},
        )

        self.assertEqual(response.status_code, 422)

    def test_wrong_simple_pin_returns_login_specific_error(self) -> None:
        self.client.post(
            "/api/v2/auth/simple",
            json={
                "identifier": "easy_user",
                "pin": "123456",
                "display_name": "쉬운 사용자",
                "recovery_question": "favorite_work",
                "recovery_answer": "어린 왕자",
            },
        )
        self.client.cookies.clear()

        response = self.client.post(
            "/api/v2/auth/simple",
            json={"identifier": "easy_user", "pin": "000000"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "SIMPLE_LOGIN_FAILED")
        self.assertEqual(
            response.json()["error"]["message"],
            "간단 아이디 또는 PIN이 올바르지 않습니다.",
        )

    def test_guest_can_keep_current_records_with_simple_identifier(self) -> None:
        guest = self.client.post("/api/v2/auth/guest")
        guest_id = guest.json()["user"]["id"]

        claimed = self.client.put(
            "/api/v2/auth/simple/claim",
            headers={"X-CSRF-Token": guest.json()["csrf_token"]},
            json={
                "identifier": "my_memory",
                "pin": "654321",
                "display_name": "나의 커리어",
                "recovery_question": "memorable_place",
                "recovery_answer": "부산 바닷가",
            },
        )

        self.assertEqual(claimed.status_code, 200)
        self.assertEqual(claimed.json()["user"]["id"], guest_id)
        self.assertEqual(claimed.json()["user"]["account_type"], "simple")
        self.assertEqual(claimed.json()["user"]["username"], "my_memory")
        self.assertEqual(claimed.json()["user"]["display_name"], "나의 커리어")
        with self.session_factory() as database:
            user = database.get(models.User, guest_id)
        self.assertIsNone(user.guest_expires_at)

    def test_simple_login_temporarily_locks_after_five_wrong_pins(self) -> None:
        self.client.post(
            "/api/v2/auth/simple",
            json={
                "identifier": "locked_user",
                "pin": "123456",
                "display_name": "잠금 테스트",
                "recovery_question": "private_nickname",
                "recovery_answer": "잠금 별명",
            },
        )
        self.client.cookies.clear()

        responses = [
            self.client.post(
                "/api/v2/auth/simple",
                json={"identifier": "locked_user", "pin": "000000"},
            )
            for _ in range(5)
        ]
        locked = self.client.post(
            "/api/v2/auth/simple",
            json={"identifier": "locked_user", "pin": "123456"},
        )

        self.assertTrue(all(response.status_code == 401 for response in responses))
        self.assertEqual(locked.status_code, 429)
        self.assertEqual(
            locked.json()["error"]["code"],
            "SIMPLE_LOGIN_LOCKED",
        )

    def test_simple_nickname_can_be_shared_by_different_identifiers(self) -> None:
        first = self.client.post(
            "/api/v2/auth/simple",
            json={
                "identifier": "first_user",
                "pin": "123456",
                "display_name": "같은 호칭",
                "recovery_question": "first_skill",
                "recovery_answer": "파이썬",
            },
        )
        self.client.cookies.clear()
        second = self.client.post(
            "/api/v2/auth/simple",
            json={
                "identifier": "second_user",
                "pin": "654321",
                "display_name": "같은 호칭",
                "recovery_question": "childhood_dream",
                "recovery_answer": "개발자",
            },
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(
            first.json()["user"]["username"],
            second.json()["user"]["username"],
        )
        self.assertEqual(first.json()["user"]["display_name"], "같은 호칭")
        self.assertEqual(second.json()["user"]["display_name"], "같은 호칭")

    def test_existing_simple_identifier_cannot_be_created_again(self) -> None:
        created = self.client.post(
            "/api/v2/auth/simple",
            json={
                "identifier": "unique_user",
                "pin": "123456",
                "display_name": "첫 번째 사용자",
                "recovery_question": "recovery_keyword",
                "recovery_answer": "첫 번째 답변",
            },
        )
        self.client.cookies.clear()

        duplicate = self.client.post(
            "/api/v2/auth/simple",
            json={
                "identifier": "unique_user",
                "pin": "654321",
                "display_name": "두 번째 사용자",
                "recovery_question": "favorite_work",
                "recovery_answer": "두 번째 답변",
            },
        )

        self.assertEqual(created.status_code, 200)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(
            duplicate.json()["error"]["code"],
            "SIMPLE_IDENTIFIER_TAKEN",
        )
        with self.session_factory() as database:
            self.assertEqual(database.query(models.User).count(), 1)

    def test_simple_pin_can_be_reset_with_saved_recovery_answer(self) -> None:
        created = self.client.post(
            "/api/v2/auth/simple",
            json={
                "identifier": "recover_user",
                "pin": "123456",
                "display_name": "복구 사용자",
                "recovery_question": "favorite_work",
                "recovery_answer": "어린 왕자",
            },
        )
        question = self.client.post(
            "/api/v2/auth/simple/pin/recovery-question",
            json={"identifier": "recover_user"},
        )
        wrong = self.client.post(
            "/api/v2/auth/simple/pin/reset",
            json={
                "identifier": "recover_user",
                "recovery_answer": "틀린 답변",
                "pin": "654321",
                "pin_confirm": "654321",
            },
        )
        reset = self.client.post(
            "/api/v2/auth/simple/pin/reset",
            json={
                "identifier": "recover_user",
                "recovery_answer": "  어린   왕자  ",
                "pin": "654321",
                "pin_confirm": "654321",
            },
        )
        revoked_session = self.client.get("/api/v2/auth/me")
        self.client.cookies.clear()
        old_pin = self.client.post(
            "/api/v2/auth/simple",
            json={"identifier": "recover_user", "pin": "123456"},
        )
        new_pin = self.client.post(
            "/api/v2/auth/simple",
            json={"identifier": "recover_user", "pin": "654321"},
        )

        self.assertEqual(created.status_code, 200)
        self.assertEqual(question.status_code, 200)
        self.assertEqual(question.json()["recovery_question"], "favorite_work")
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(
            wrong.json()["error"]["code"],
            "SIMPLE_PIN_RECOVERY_FAILED",
        )
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(revoked_session.status_code, 401)
        self.assertEqual(old_pin.status_code, 401)
        self.assertEqual(new_pin.status_code, 200)

    def test_simple_pin_recovery_locks_after_five_wrong_answers(self) -> None:
        self.client.post(
            "/api/v2/auth/simple",
            json={
                "identifier": "recovery_locked",
                "pin": "123456",
                "display_name": "복구 잠금",
                "recovery_question": "recovery_keyword",
                "recovery_answer": "정답 단어",
            },
        )

        responses = [
            self.client.post(
                "/api/v2/auth/simple/pin/reset",
                json={
                    "identifier": "recovery_locked",
                    "recovery_answer": "틀린 답변",
                    "pin": "654321",
                    "pin_confirm": "654321",
                },
            )
            for _ in range(5)
        ]

        self.assertTrue(all(response.status_code == 400 for response in responses[:4]))
        self.assertEqual(responses[4].status_code, 429)
        self.assertEqual(
            responses[4].json()["error"]["code"],
            "SIMPLE_PIN_RECOVERY_LOCKED",
        )

    def test_register_hashes_password_and_sets_httponly_cookie(self) -> None:
        response = self.register()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["user"]["email"], "user@example.com")
        self.assertEqual(
            response.json()["user"]["recovery_question"],
            "father_name",
        )
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
        me = self.client.get("/api/v2/auth/me")
        self.assertEqual(
            me.json()["user"]["recovery_question"],
            "elementary_school",
        )

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

    def test_recovery_lookup_returns_only_the_saved_question(self) -> None:
        self.register()

        response = self.client.post(
            "/api/v2/auth/password/recovery-question",
            json={
                "email": "user@example.com",
                "username": "test_user",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"recovery_question": "father_name"},
        )
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_recovery_lookup_does_not_reveal_unknown_account(self) -> None:
        response = self.client.post(
            "/api/v2/auth/password/recovery-question",
            json={
                "email": "unknown@example.com",
                "username": "unknown_user",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            response.json()["recovery_question"],
            {
                "father_name",
                "mother_name",
                "birthplace",
                "childhood_nickname",
                "elementary_school",
                "first_company",
                "favorite_work",
                "memorable_place",
                "private_nickname",
                "first_skill",
                "childhood_dream",
                "recovery_keyword",
            },
        )

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
