"""회원가입·로그인·계정 복구 API의 입력과 출력 형식."""

from __future__ import annotations

import re
from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_PATTERN = re.compile(r"^[a-z0-9_]{4,30}$")
SIMPLE_IDENTIFIER_PATTERN = re.compile(r"^[0-9a-zA-Z가-힣_-]{2,20}$")
SIMPLE_PIN_PATTERN = re.compile(r"^\d{6}$")
RecoveryQuestion = Literal[
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


class SimpleSessionRequest(BaseModel):
    identifier: str = Field(min_length=2, max_length=20)
    pin: str = Field(min_length=6, max_length=6)
    display_name: str | None = Field(default=None, min_length=1, max_length=40)
    recovery_question: RecoveryQuestion | None = None
    recovery_answer: str | None = Field(default=None, min_length=2, max_length=100)

    @field_validator("identifier")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not SIMPLE_IDENTIFIER_PATTERN.fullmatch(normalized):
            raise ValueError(
                "간단 아이디는 한글, 영문, 숫자, 밑줄, 하이픈으로 2~20자여야 합니다."
            )
        return normalized

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, value: str) -> str:
        if not SIMPLE_PIN_PATTERN.fullmatch(value):
            raise ValueError("PIN은 숫자 6자리로 입력해 주세요.")
        return value

    @field_validator("display_name")
    @classmethod
    def normalize_optional_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("닉네임을 입력해 주세요.")
        return normalized

    @field_validator("recovery_answer")
    @classmethod
    def normalize_optional_recovery_answer(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("PIN 복구 답변은 2자 이상 입력해 주세요.")
        return normalized

    @model_validator(mode="after")
    def setup_fields_must_be_complete(self) -> "SimpleSessionRequest":
        setup_fields = (
            self.display_name,
            self.recovery_question,
            self.recovery_answer,
        )
        if any(value is not None for value in setup_fields) and not all(
            value is not None for value in setup_fields
        ):
            raise ValueError("닉네임과 PIN 복구 질문·답변을 모두 입력해 주세요.")
        return self


class SimplePinQuestionRequest(BaseModel):
    identifier: str = Field(min_length=2, max_length=20)

    @field_validator("identifier")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        return SimpleSessionRequest.normalize_identifier(value)


class SimplePinResetRequest(SimplePinQuestionRequest):
    recovery_answer: str = Field(min_length=2, max_length=100)
    pin: str = Field(min_length=6, max_length=6)
    pin_confirm: str = Field(min_length=6, max_length=6)

    @field_validator("recovery_answer")
    @classmethod
    def normalize_answer(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("복구 답변은 2자 이상 입력해 주세요.")
        return normalized

    @field_validator("pin", "pin_confirm")
    @classmethod
    def validate_pin(cls, value: str) -> str:
        return SimpleSessionRequest.validate_pin(value)

    @model_validator(mode="after")
    def pins_must_match(self) -> "SimplePinResetRequest":
        if self.pin != self.pin_confirm:
            raise ValueError("새 PIN과 PIN 확인이 일치하지 않습니다.")
        return self


class UsernameSetupRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=4, max_length=30)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return RegisterRequest.normalize_username(value)


class ProfileUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=40)

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


class RecoveryQuestionLookupRequest(EmailInput):
    username: str = Field(min_length=4, max_length=30)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return RegisterRequest.normalize_username(value)


class RecoveryQuestionResponse(BaseModel):
    recovery_question: RecoveryQuestion


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
    email: str | None
    display_name: str
    account_type: Literal["guest", "simple", "legacy"]
    has_recovery_question: bool
    recovery_question: RecoveryQuestion | None = None
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserResponse
    csrf_token: str


class SimpleProfileRequiredResponse(BaseModel):
    profile_required: Literal[True] = True
    identifier: str


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
    "RecoveryQuestion",
    "RecoveryQuestionLookupRequest",
    "RecoveryQuestionResponse",
    "RecoveryQuestionSetupRequest",
    "RegisterRequest",
    "SimpleProfileRequiredResponse",
    "SimplePinQuestionRequest",
    "SimplePinResetRequest",
    "SimpleSessionRequest",
    "UsernameFindResponse",
    "UsernameSetupRequest",
    "UserResponse",
]
