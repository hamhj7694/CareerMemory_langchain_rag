"""HttpOnly 쿠키 세션에서 현재 로그인 사용자를 확인한다."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from AI_Engine.auth.security import hash_token
from AI_Engine.database.connection import get_database_session
from AI_Engine.database.models import AuthSession, User


SESSION_COOKIE_NAME = os.getenv(
    "SESSION_COOKIE_NAME",
    "career_memory_session",
).strip()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_current_session(
    request: Request,
    database: Session = Depends(get_database_session),
) -> AuthSession:
    """쿠키 토큰의 해시와 만료·폐기 상태를 확인한다."""

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다.",
        )
    auth_session = database.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == hash_token(token),
            AuthSession.revoked_at.is_(None),
        )
    )
    if (
        auth_session is None
        or _as_utc(auth_session.expires_at) <= datetime.now(timezone.utc)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 만료되었습니다. 다시 로그인해 주세요.",
        )
    return auth_session


def get_current_user(
    auth_session: AuthSession = Depends(get_current_session),
    database: Session = Depends(get_database_session),
) -> User:
    """현재 세션의 활성 사용자를 반환한다."""

    user = database.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용할 수 없는 계정입니다.",
        )
    return user


def require_csrf_user(
    request: Request,
    auth_session: AuthSession = Depends(get_current_session),
    database: Session = Depends(get_database_session),
) -> User:
    """상태를 변경하는 요청에서 세션과 CSRF 헤더가 함께 일치하는지 확인한다."""

    csrf_token = request.headers.get("X-CSRF-Token", "")
    if not csrf_token or not secrets.compare_digest(
        csrf_token,
        auth_session.csrf_token,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="요청 보안 토큰이 올바르지 않습니다.",
        )
    user = database.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용할 수 없는 계정입니다.",
        )
    return user


__all__ = [
    "SESSION_COOKIE_NAME",
    "get_current_session",
    "get_current_user",
    "require_csrf_user",
]
