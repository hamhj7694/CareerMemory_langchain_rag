"""비밀번호와 임의 인증 토큰을 안전하게 처리하는 함수."""

from __future__ import annotations

import hashlib
import secrets
import unicodedata

from pwdlib import PasswordHash


# 1. pwdlib 권장 설정은 Argon2id를 사용한다.
password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """비밀번호 원문을 복구할 수 없는 Argon2id 해시로 변환한다."""

    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """입력 비밀번호와 저장된 해시를 안전하게 비교한다."""

    return password_hasher.verify(password, password_hash)


def create_secret_token() -> str:
    """세션과 비밀번호 재설정에 사용할 예측 불가능한 토큰을 만든다."""

    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """DB 유출 시 원본 토큰을 바로 사용할 수 없도록 SHA-256 해시만 저장한다."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_recovery_answer(answer: str) -> str:
    """대소문자·연속 공백 차이로 정답 확인이 실패하지 않도록 정규화한다."""

    normalized = unicodedata.normalize("NFKC", answer)
    return " ".join(normalized.split()).casefold()


__all__ = [
    "create_secret_token",
    "hash_password",
    "hash_token",
    "normalize_recovery_answer",
    "verify_password",
]
