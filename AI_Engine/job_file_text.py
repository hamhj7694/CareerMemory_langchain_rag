"""채용공고 파일 추출 API의 하위 호환 어댑터."""

from __future__ import annotations

from AI_Engine.file_extraction import (
    ALLOWED_FILE_TYPES,
    FileExtractionError,
    FileInputError,
    MAX_FILE_BYTES,
    MAX_FILE_COUNT,
    MAX_FILES_TOTAL_BYTES,
    MAX_FILES_TOTAL_MIB,
    SourceFile,
    detect_and_validate_file,
    extract_files,
)
from AI_Engine.file_extraction.detection import MAX_FILE_MIB
from AI_Engine.file_extraction.parsers import parse_text


JobFile = SourceFile
JobFileInputError = FileInputError
JobFileExtractionError = FileExtractionError
MAX_JOB_FILE_MIB = MAX_FILE_MIB
MAX_JOB_FILE_COUNT = MAX_FILE_COUNT
MAX_JOB_FILES_TOTAL_MIB = MAX_FILES_TOTAL_MIB
MAX_JOB_FILE_BYTES = MAX_FILE_BYTES
MAX_JOB_FILES_TOTAL_BYTES = MAX_FILES_TOTAL_BYTES
ALLOWED_JOB_FILE_TYPES = set(ALLOWED_FILE_TYPES)


def validate_job_file(file: JobFile) -> None:
    detect_and_validate_file(file)


def decode_text_file(file: JobFile) -> str:
    return parse_text(detect_and_validate_file(file)).text


def extract_job_file_text(files: list[JobFile]) -> str:
    """허용된 문서·PDF·이미지를 읽어 하나의 공고 원문으로 합친다."""

    if not files:
        raise JobFileInputError("채용공고 파일을 선택해 주세요.")
    results = extract_files(files, max_count=MAX_JOB_FILE_COUNT)
    return "\n\n".join(
        f"[파일: {item.filename}]\n{item.text}"
        for item in results
    ).strip()


__all__ = [
    "ALLOWED_JOB_FILE_TYPES",
    "JobFile",
    "JobFileExtractionError",
    "JobFileInputError",
    "MAX_JOB_FILE_BYTES",
    "MAX_JOB_FILE_COUNT",
    "MAX_JOB_FILE_MIB",
    "MAX_JOB_FILES_TOTAL_BYTES",
    "MAX_JOB_FILES_TOTAL_MIB",
    "decode_text_file",
    "extract_job_file_text",
    "validate_job_file",
]
