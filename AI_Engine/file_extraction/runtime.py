"""CPU·외부 프로세스 기반 파일 추출을 제한된 worker thread에서 실행한다."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import ParamSpec, TypeVar

import anyio


P = ParamSpec("P")
R = TypeVar("R")

FILE_EXTRACTION_CONCURRENCY = max(
    1,
    int(os.getenv("AI_FILE_EXTRACTION_CONCURRENCY", "2")),
)
_FILE_EXTRACTION_LIMITER = anyio.CapacityLimiter(FILE_EXTRACTION_CONCURRENCY)


async def run_file_extraction(
    function: Callable[P, R],
    *args: P.args,
) -> R:
    """파일 추출 함수를 event loop 밖에서 전역 동시성 제한과 함께 실행한다."""

    return await anyio.to_thread.run_sync(
        function,
        *args,
        limiter=_FILE_EXTRACTION_LIMITER,
    )


__all__ = ["FILE_EXTRACTION_CONCURRENCY", "run_file_extraction"]
