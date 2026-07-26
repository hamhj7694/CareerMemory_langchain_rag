"""회원가입·로그인·계정 복구 API의 입력과 출력 형식."""

from __future__ import annotations

import re
from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_PATTERN = re.compile(r"^[a-z0-9_]{4,30}$")
RecoveryQuestion = Literal[
    "father_name",
    "mother_name",
    "birthplace",
    "childhood_nickname",
    "elementary_school",
    "first_company",
]


class EmailInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("올바른 이메일 주소를 입력해 주세요.")
        return normalized


class RegisterRequest(EmailInput):
    username: str = Field(min_length=4, max_length=30)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=6, max_length=128)
    password_confirm: str = Field(min_length=6, max_length=128)
    recovery_question: RecoveryQuestion
    recovery_answer: str = Field(min_length=2, max_length=100)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not USERNAME_PATTERN.fullmatch(normalized):
            raise ValueError(
                "아이디는 영문 소문자, 숫자, 밑줄로 4~30자여야 합니다."
            )
        return normalized

    @model_validator(mode="after")
    def passwords_must_match(self) -> "RegisterRequest":
        if self.password != self.password_confirm:
            raise ValueError("비밀번호 확인이 일치하지 않습니다.")
        return self


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("identifier")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        return value.strip().lower()


class UsernameSetupRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=4, max_length=30)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return RegisterRequest.normalize_username(value)


class ProfileUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        return RegisterRequest.normalize_display_name(value)


class UsernameFindResponse(BaseModel):
    username: str


class RecoveryQuestionSetupRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    recovery_question: RecoveryQuestion
    recovery_answer: str = Field(min_length=2, max_length=100)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=6, max_length=128)
    password_confirm: str = Field(min_length=6, max_length=128)

    @model_validator(mode="after")
    def passwords_must_match(self) -> "PasswordChangeRequest":
        if self.password != self.password_confirm:
            raise ValueError("새 비밀번호와 비밀번호 확인이 일치하지 않습니다.")
        return self


class PasswordResetRequest(EmailInput):
    username: str = Field(min_length=4, max_length=30)
    recovery_question: RecoveryQuestion
    recovery_answer: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=6, max_length=128)
    password_confirm: str = Field(min_length=6, max_length=128)

    @model_validator(mode="after")
    def passwords_must_match(self) -> "PasswordResetRequest":
        if self.password != self.password_confirm:
            raise ValueError("비밀번호 확인이 일치하지 않습니다.")
        return self

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return RegisterRequest.normalize_username(value)


class UserResponse(BaseModel):
    id: str
    username: str | None
    email: str
    display_name: str
    has_recovery_question: bool
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserResponse
    csrf_token: str


class GenericMessageResponse(BaseModel):
    message: str


__all__ = [
    "AuthResponse",
    "EmailInput",
    "GenericMessageResponse",
    "LoginRequest",
    "PasswordChangeRequest",
    "PasswordResetRequest",
    "ProfileUpdateRequest",
    "RecoveryQuestionSetupRequest",
    "RegisterRequest",
    "UsernameFindResponse",
    "UsernameSetupRequest",
    "UserResponse",
]
