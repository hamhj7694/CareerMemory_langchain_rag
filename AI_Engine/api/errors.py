"""FastAPI 오류를 프론트엔드 공통 error 봉투로 변환한다."""

from __future__ import annotations

# 1. Python 기본 기능
from uuid import uuid4

# 2. FastAPI 오류와 JSON 응답
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


# 3. HTTP 상태별 공개 오류 코드
ERROR_CODE_BY_STATUS = {
    400: "INVALID_REQUEST",
    401: "AUTHENTICATION_REQUIRED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "VERSION_CONFLICT",
    422: "VALIDATION_ERROR",
    501: "NOT_IMPLEMENTED",
    502: "AI_PROVIDER_ERROR",
}


# 4. 공통 오류 응답 생성
def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    retryable: bool = False,
    field_errors: list[dict[str, object]] | None = None,
) -> JSONResponse:
    """프론트엔드 AppError가 읽는 공통 error 객체를 반환한다."""

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "field_errors": field_errors or [],
                "request_id": request_id,
                "retryable": retryable,
            }
        },
    )


# 5. 요청 추적 ID
def get_request_id(request: Request) -> str:
    """요청 헤더의 ID를 사용하거나 서버에서 새 추적 ID를 만든다."""

    header_id = request.headers.get("X-Request-ID", "").strip()
    return header_id or str(uuid4())


# 6. FastAPI 오류 처리기 등록
def register_error_handlers(app: FastAPI) -> None:
    """HTTP 오류와 입력 검증 오류를 프론트엔드 계약 형식으로 등록한다."""

    @app.exception_handler(HTTPException)
    async def handle_http_error(
        request: Request,
        error: HTTPException,
    ) -> JSONResponse:
        message = (
            error.detail
            if isinstance(error.detail, str)
            else "요청을 처리하지 못했습니다."
        )
        return error_response(
            status_code=error.status_code,
            code=ERROR_CODE_BY_STATUS.get(
                error.status_code,
                "HTTP_ERROR",
            ),
            message=message,
            request_id=get_request_id(request),
            retryable=error.status_code in {502, 503, 504},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        field_errors = [
            {
                "field": ".".join(
                    str(part)
                    for part in item["loc"]
                    if part != "body"
                ),
                "message": item["msg"],
            }
            for item in error.errors()
        ]
        return error_response(
            status_code=422,
            code="VALIDATION_ERROR",
            message="요청 입력값을 확인해 주세요.",
            request_id=get_request_id(request),
            field_errors=field_errors,
        )


__all__ = [
    "ERROR_CODE_BY_STATUS",
    "error_response",
    "get_request_id",
    "register_error_handlers",
]
