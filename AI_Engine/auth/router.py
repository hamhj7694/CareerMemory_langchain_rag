"""회원가입·로그인·로그아웃·계정 복구 API."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
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
    RecoveryQuestionSetupRequest,
    RegisterRequest,
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
COOKIE_SECURE = os.getenv("APP_ENV", "development").lower() == "production"
RECOVERY_FAILURE_MESSAGE = "이메일, 복구 질문 또는 답변이 올바르지 않습니다."

# 존재하지 않는 이메일도 비밀번호 검증 시간을 비슷하게 맞추기 위한 고정 해시다.
DUMMY_PASSWORD_HASH = hash_password("not-a-real-user-password")


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        has_recovery_question=bool(
            user.recovery_question and user.recovery_answer_hash
        ),
        created_at=user.created_at,
    )


def issue_session(
    user: User,
    response: Response,
    database: Session,
) -> AuthResponse:
    """원본 세션 토큰은 쿠키에, 해시는 DB에 저장한다."""

    raw_token = create_secret_token()
    csrf_token = create_secret_token()
    expires_at = utc_now() + timedelta(hours=SESSION_LIFETIME_HOURS)
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
        max_age=SESSION_LIFETIME_HOURS * 60 * 60,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return AuthResponse(user=user_response(user), csrf_token=csrf_token)


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
    question_matches = bool(
        user
        and user.recovery_question == request.recovery_question
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
        or not question_matches
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
