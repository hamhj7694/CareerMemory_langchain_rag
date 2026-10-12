"""회원가입·로그인·로그아웃·계정 복구 API."""

from __future__ import annotations

import os
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import get_args
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from AI_Engine.auth.dependencies import (
    SESSION_COOKIE_NAME,
    get_current_session,
    require_csrf_user,
)
from AI_Engine.auth.schemas import (
    AuthResponse,
    EmailInput,
    GenericMessageResponse,
    LoginRequest,
    PasswordChangeRequest,
    PasswordResetRequest,
    ProfileUpdateRequest,
    RecoveryQuestion,
    RecoveryQuestionLookupRequest,
    RecoveryQuestionResponse,
    RecoveryQuestionSetupRequest,
    RegisterRequest,
    SimplePinQuestionRequest,
    SimplePinResetRequest,
    SimpleProfileRequiredResponse,
    SimpleSessionRequest,
    UserResponse,
    UsernameFindResponse,
    UsernameSetupRequest,
)
from AI_Engine.auth.security import (
    create_secret_token,
    hash_password,
    hash_token,
    normalize_recovery_answer,
    verify_password,
)
from AI_Engine.database.connection import get_database_session
from AI_Engine.database.models import (
    AuthSession,
    Conversation,
    User,
    utc_now,
)


router = APIRouter(prefix="/api/v2/auth", tags=["auth"])
SESSION_LIFETIME_HOURS = int(os.getenv("SESSION_LIFETIME_HOURS", "168"))
GUEST_SESSION_LIFETIME_HOURS = int(
    os.getenv("GUEST_SESSION_LIFETIME_HOURS", "24")
)
COOKIE_SECURE = os.getenv("APP_ENV", "development").lower() == "production"
RECOVERY_FAILURE_MESSAGE = "이메일, 아이디 또는 복구 답변이 올바르지 않습니다."
SIMPLE_LOGIN_FAILURE_MESSAGE = "간단 아이디 또는 PIN이 올바르지 않습니다."
SIMPLE_LOGIN_MAX_FAILURES = 5
SIMPLE_LOGIN_LOCK_MINUTES = 15

# 존재하지 않는 이메일도 비밀번호 검증 시간을 비슷하게 맞추기 위한 고정 해시다.
DUMMY_PASSWORD_HASH = hash_password("not-a-real-user-password")
RECOVERY_LOOKUP_SECRET = secrets.token_bytes(32)
RECOVERY_QUESTION_VALUES = get_args(RecoveryQuestion)


def fallback_recovery_question(email: str, username: str) -> str:
    """Return a stable plausible question without revealing account existence."""

    digest = hmac.digest(
        RECOVERY_LOOKUP_SECRET,
        f"{email}\0{username}".encode("utf-8"),
        "sha256",
    )
    return RECOVERY_QUESTION_VALUES[digest[0] % len(RECOVERY_QUESTION_VALUES)]


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def user_response(user: User) -> UserResponse:
    account_type = (
        user.account_type
        if user.account_type in {"guest", "simple", "legacy"}
        else "legacy"
    )
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email if account_type == "legacy" else None,
        display_name=user.display_name,
        account_type=account_type,
        has_recovery_question=bool(
            user.recovery_question and user.recovery_answer_hash
        ),
        recovery_question=user.recovery_question,
        created_at=user.created_at,
    )


def issue_session(
    user: User,
    response: Response,
    database: Session,
    *,
    lifetime_hours: int = SESSION_LIFETIME_HOURS,
) -> AuthResponse:
    """원본 세션 토큰은 쿠키에, 해시는 DB에 저장한다."""

    raw_token = create_secret_token()
    csrf_token = create_secret_token()
    expires_at = utc_now() + timedelta(hours=lifetime_hours)
    database.add(
        AuthSession(
            id=f"SESSION-{uuid4()}",
            user_id=user.id,
            token_hash=hash_token(raw_token),
            csrf_token=csrf_token,
            expires_at=expires_at,
        )
    )
    database.commit()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=lifetime_hours * 60 * 60,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return AuthResponse(user=user_response(user), csrf_token=csrf_token)


@router.post("/guest", response_model=AuthResponse, status_code=201)
def start_guest_session(
    response: Response,
    database: Session = Depends(get_database_session),
) -> AuthResponse:
    """가입 입력 없이 격리된 단기 체험 공간과 세션을 만든다."""

    guest_id = uuid4()
    expires_at = utc_now() + timedelta(hours=GUEST_SESSION_LIFETIME_HOURS)
    user = User(
        id=f"USER-{guest_id}",
        username=None,
        email=f"guest-{guest_id}@career-memory.invalid",
        display_name="체험 사용자",
        password_hash=hash_password(create_secret_token()),
        account_type="guest",
        guest_expires_at=expires_at,
    )
    database.add(user)
    database.commit()
    database.refresh(user)
    return issue_session(
        user,
        response,
        database,
        lifetime_hours=GUEST_SESSION_LIFETIME_HOURS,
    )


@router.post(
    "/simple",
    response_model=AuthResponse | SimpleProfileRequiredResponse,
)
def start_simple_session(
    request: SimpleSessionRequest,
    response: Response,
    database: Session = Depends(get_database_session),
) -> AuthResponse | SimpleProfileRequiredResponse:
    """기존 아이디는 로그인하고 신규 아이디는 닉네임 입력을 요청한다."""

    user = database.scalar(
        select(User).where(User.username == request.identifier)
    )
    if user is None:
        if request.display_name is None:
            return SimpleProfileRequiredResponse(identifier=request.identifier)
        user_id = uuid4()
        user = User(
            id=f"USER-{user_id}",
            username=request.identifier,
            email=f"simple-{user_id}@career-memory.invalid",
            display_name=request.display_name,
            password_hash=hash_password(request.pin),
            account_type="simple",
            recovery_question=request.recovery_question,
            recovery_answer_hash=hash_password(
                normalize_recovery_answer(request.recovery_answer or "")
            ),
        )
        database.add(user)
        try:
            database.commit()
        except IntegrityError as error:
            database.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "SIMPLE_IDENTIFIER_TAKEN",
                    "message": "이미 사용 중인 간단 아이디입니다. 다시 시도해 주세요.",
                },
            ) from error
        database.refresh(user)
        return issue_session(user, response, database)

    locked_until = user.login_locked_until
    if locked_until and as_utc(locked_until) > utc_now():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "SIMPLE_LOGIN_LOCKED",
                "message": "PIN을 여러 번 잘못 입력했어요. 15분 뒤 다시 시도해 주세요.",
            },
        )
    if locked_until:
        user.login_locked_until = None
        user.login_failed_attempts = 0

    if not user.is_active or not verify_password(request.pin, user.password_hash):
        if request.display_name is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "SIMPLE_IDENTIFIER_TAKEN",
                    "message": "이미 사용 중인 간단 아이디입니다. 다른 아이디를 입력해 주세요.",
                },
            )
        user.login_failed_attempts += 1
        if user.login_failed_attempts >= SIMPLE_LOGIN_MAX_FAILURES:
            user.login_failed_attempts = 0
            user.login_locked_until = utc_now() + timedelta(
                minutes=SIMPLE_LOGIN_LOCK_MINUTES
            )
        database.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "SIMPLE_LOGIN_FAILED",
                "message": SIMPLE_LOGIN_FAILURE_MESSAGE,
            },
        )

    user.login_failed_attempts = 0
    user.login_locked_until = None
    database.commit()
    return issue_session(user, response, database)


@router.put("/simple/claim", response_model=AuthResponse)
def claim_guest_session(
    request: SimpleSessionRequest,
    auth_session: AuthSession = Depends(get_current_session),
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> AuthResponse:
    """현재 게스트 공간을 간단 아이디와 PIN으로 계속 사용할 수 있게 한다."""

    if current_user.account_type != "guest":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="체험 기록만 간단 아이디로 저장할 수 있어요.",
        )
    if request.display_name is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="체험 기록을 저장할 닉네임을 입력해 주세요.",
        )
    current_user.username = request.identifier
    current_user.display_name = request.display_name
    current_user.password_hash = hash_password(request.pin)
    current_user.account_type = "simple"
    current_user.guest_expires_at = None
    current_user.recovery_question = request.recovery_question
    current_user.recovery_answer_hash = hash_password(
        normalize_recovery_answer(request.recovery_answer or "")
    )
    current_user.recovery_failed_attempts = 0
    current_user.recovery_locked_until = None
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SIMPLE_IDENTIFIER_TAKEN",
                "message": "이미 사용 중인 간단 아이디입니다.",
            },
        ) from error
    database.refresh(current_user)
    return AuthResponse(
        user=user_response(current_user),
        csrf_token=auth_session.csrf_token,
    )


@router.post(
    "/simple/pin/recovery-question",
    response_model=RecoveryQuestionResponse,
)
def get_simple_pin_recovery_question(
    request: SimplePinQuestionRequest,
    response: Response,
    database: Session = Depends(get_database_session),
) -> RecoveryQuestionResponse:
    """간단 아이디에 저장된 단일 PIN 복구 질문을 반환한다."""

    user = database.scalar(
        select(User).where(
            User.username == request.identifier,
            User.account_type == "simple",
            User.is_active.is_(True),
        )
    )
    if user is None or not user.recovery_question or not user.recovery_answer_hash:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SIMPLE_PIN_RECOVERY_NOT_FOUND",
                "message": "PIN 복구 정보를 찾을 수 없는 아이디예요.",
            },
        )
    response.headers["Cache-Control"] = "no-store"
    return RecoveryQuestionResponse(recovery_question=user.recovery_question)


@router.post("/simple/pin/reset", response_model=GenericMessageResponse)
def reset_simple_pin(
    request: SimplePinResetRequest,
    database: Session = Depends(get_database_session),
) -> GenericMessageResponse:
    """복구 답변을 확인하고 원래 PIN을 노출하지 않은 채 새 PIN으로 바꾼다."""

    user = database.scalar(
        select(User).where(
            User.username == request.identifier,
            User.account_type == "simple",
        )
    )
    is_locked = bool(
        user
        and user.recovery_locked_until
        and as_utc(user.recovery_locked_until) > utc_now()
    )
    if is_locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "SIMPLE_PIN_RECOVERY_LOCKED",
                "message": "복구 답변을 여러 번 잘못 입력했어요. 15분 뒤 다시 시도해 주세요.",
            },
        )

    answer_hash = (
        user.recovery_answer_hash
        if user and user.recovery_answer_hash
        else DUMMY_PASSWORD_HASH
    )
    answer_matches = verify_password(
        normalize_recovery_answer(request.recovery_answer),
        answer_hash,
    )
    if user is None or not user.is_active or not answer_matches:
        if user is not None:
            user.recovery_failed_attempts += 1
            locked_now = user.recovery_failed_attempts >= 5
            if locked_now:
                user.recovery_failed_attempts = 0
                user.recovery_locked_until = utc_now() + timedelta(minutes=15)
            database.commit()
            if locked_now:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "code": "SIMPLE_PIN_RECOVERY_LOCKED",
                        "message": "복구 답변을 여러 번 잘못 입력했어요. 15분 뒤 다시 시도해 주세요.",
                    },
                )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "SIMPLE_PIN_RECOVERY_FAILED",
                "message": "복구 답변이 올바르지 않아요. 다시 확인해 주세요.",
            },
        )

    user.password_hash = hash_password(request.pin)
    user.recovery_failed_attempts = 0
    user.recovery_locked_until = None
    database.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == user.id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=utc_now())
    )
    database.commit()
    return GenericMessageResponse(
        message="새 PIN으로 변경했어요. 새 PIN으로 내 기록을 불러와 주세요."
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(
    request: RegisterRequest,
    response: Response,
    database: Session = Depends(get_database_session),
) -> AuthResponse:
    is_first_user = database.scalar(select(User.id).limit(1)) is None
    user = User(
        id=f"USER-{uuid4()}",
        username=request.username,
        email=request.email,
        display_name=request.display_name,
        password_hash=hash_password(request.password),
        recovery_question=request.recovery_question,
        recovery_answer_hash=hash_password(
            normalize_recovery_answer(request.recovery_answer)
        ),
    )
    database.add(user)
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 아이디 또는 이메일입니다.",
        ) from error
    database.refresh(user)

    # 인증 도입 전에 만든 로컬 대화는 개발 환경의 첫 계정에만 한 번 귀속한다.
    # 운영 환경에서는 무소유 데이터를 자동으로 넘기지 않는다.
    if is_first_user and not COOKIE_SECURE:
        database.execute(
            update(Conversation)
            .where(Conversation.user_id.is_(None))
            .values(user_id=user.id)
        )
        database.commit()
    return issue_session(user, response, database)


@router.post("/login", response_model=AuthResponse)
def login(
    request: LoginRequest,
    response: Response,
    database: Session = Depends(get_database_session),
) -> AuthResponse:
    user = database.scalar(
        select(User).where(
            or_(
                User.username == request.identifier,
                User.email == request.identifier,
            )
        )
    )
    password_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
    password_matches = verify_password(request.password, password_hash)
    if user is None or not password_matches or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )
    return issue_session(user, response, database)


@router.get("/me", response_model=AuthResponse)
def me(
    auth_session: AuthSession = Depends(get_current_session),
    database: Session = Depends(get_database_session),
) -> AuthResponse:
    user = database.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return AuthResponse(
        user=user_response(user),
        csrf_token=auth_session.csrf_token,
    )


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    auth_session: AuthSession = Depends(get_current_session),
    _user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> Response:
    auth_session.revoked_at = utc_now()
    database.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    response.headers["Cache-Control"] = "no-store"
    return response


@router.put("/recovery-question", response_model=GenericMessageResponse)
def set_recovery_question(
    request: RecoveryQuestionSetupRequest,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> GenericMessageResponse:
    if not verify_password(
        request.current_password,
        current_user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재 비밀번호가 올바르지 않습니다.",
        )
    current_user.recovery_question = request.recovery_question
    current_user.recovery_answer_hash = hash_password(
        normalize_recovery_answer(request.recovery_answer)
    )
    current_user.recovery_failed_attempts = 0
    current_user.recovery_locked_until = None
    database.commit()
    return GenericMessageResponse(
        message="비밀번호 복구 질문이 저장되었습니다."
    )


@router.put("/password", response_model=GenericMessageResponse)
def change_password(
    request: PasswordChangeRequest,
    auth_session: AuthSession = Depends(get_current_session),
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> GenericMessageResponse:
    """현재 비밀번호를 확인한 뒤 새 비밀번호를 안전한 해시로 저장한다."""

    if not verify_password(
        request.current_password,
        current_user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재 비밀번호가 올바르지 않습니다.",
        )

    current_user.password_hash = hash_password(request.password)

    # 비밀번호 변경 후 현재 브라우저만 유지하고 다른 기기의 세션은 종료한다.
    database.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == current_user.id,
            AuthSession.id != auth_session.id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=utc_now())
    )
    database.commit()
    return GenericMessageResponse(
        message="비밀번호가 변경되었습니다."
    )


@router.put("/username", response_model=AuthResponse)
def set_username(
    request: UsernameSetupRequest,
    auth_session: AuthSession = Depends(get_current_session),
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> AuthResponse:
    if not verify_password(
        request.current_password,
        current_user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재 비밀번호가 올바르지 않습니다.",
        )
    current_user.username = request.username
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 아이디입니다.",
        ) from error
    database.refresh(current_user)
    return AuthResponse(
        user=user_response(current_user),
        csrf_token=auth_session.csrf_token,
    )


@router.put("/profile", response_model=AuthResponse)
def update_profile(
    request: ProfileUpdateRequest,
    auth_session: AuthSession = Depends(get_current_session),
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> AuthResponse:
    """화면과 AI 응답에서 사용하는 사용자의 표시 이름을 변경한다."""

    current_user.display_name = request.display_name
    database.commit()
    database.refresh(current_user)
    return AuthResponse(
        user=user_response(current_user),
        csrf_token=auth_session.csrf_token,
    )


@router.post("/username/find", response_model=UsernameFindResponse)
def find_username(
    request: EmailInput,
    database: Session = Depends(get_database_session),
) -> UsernameFindResponse:
    user = database.scalar(
        select(User).where(
            User.email == request.email,
            User.is_active.is_(True),
        )
    )
    if user is None or not user.username:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 이메일로 등록된 아이디를 찾을 수 없습니다.",
        )
    return UsernameFindResponse(username=user.username)


@router.post(
    "/password/recovery-question",
    response_model=RecoveryQuestionResponse,
)
def get_password_recovery_question(
    request: RecoveryQuestionLookupRequest,
    response: Response,
    database: Session = Depends(get_database_session),
) -> RecoveryQuestionResponse:
    """Return the single question stored for the account recovery flow."""

    user = database.scalar(
        select(User).where(
            User.email == request.email,
            User.username == request.username,
            User.is_active.is_(True),
        )
    )
    recovery_question = (
        user.recovery_question
        if user and user.recovery_question and user.recovery_answer_hash
        else fallback_recovery_question(request.email, request.username)
    )
    response.headers["Cache-Control"] = "no-store"
    return RecoveryQuestionResponse(
        recovery_question=recovery_question,
    )


@router.post("/password/recover", response_model=GenericMessageResponse)
def recover_password(
    request: PasswordResetRequest,
    database: Session = Depends(get_database_session),
) -> GenericMessageResponse:
    user = database.scalar(select(User).where(User.email == request.email))
    answer_hash = (
        user.recovery_answer_hash
        if user and user.recovery_answer_hash
        else DUMMY_PASSWORD_HASH
    )
    answer_matches = verify_password(
        normalize_recovery_answer(request.recovery_answer),
        answer_hash,
    )
    username_matches = bool(user and user.username == request.username)
    is_locked = bool(
        user
        and user.recovery_locked_until
        and as_utc(user.recovery_locked_until) > utc_now()
    )

    if (
        user is None
        or not user.is_active
        or not answer_matches
        or not username_matches
        or is_locked
    ):
        if user is not None and not is_locked:
            user.recovery_failed_attempts += 1
            if user.recovery_failed_attempts >= 5:
                user.recovery_locked_until = utc_now() + timedelta(
                    minutes=15
                )
                user.recovery_failed_attempts = 0
            database.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=RECOVERY_FAILURE_MESSAGE,
        )

    user.password_hash = hash_password(request.password)
    user.recovery_failed_attempts = 0
    user.recovery_locked_until = None
    database.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == user.id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=utc_now())
    )
    database.commit()
    return GenericMessageResponse(
        message="비밀번호가 변경되었습니다. 새 비밀번호로 로그인해 주세요."
    )


__all__ = ["router"]
