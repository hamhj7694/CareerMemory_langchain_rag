"""채용공고 PDF·이미지·TXT에서 분석 가능한 원문을 추출한다."""

from __future__ import annotations

import os
from dataclasses import dataclass

MAX_JOB_FILE_MIB = max(1, int(os.getenv("AI_MAX_FILE_MIB", "25")))
MAX_JOB_FILE_COUNT = 5
MAX_JOB_FILES_TOTAL_MIB = max(
    MAX_JOB_FILE_MIB,
    int(os.getenv("AI_MAX_FILES_TOTAL_MIB", "100")),
)
MAX_JOB_FILE_BYTES = MAX_JOB_FILE_MIB * 1024 * 1024
MAX_JOB_FILES_TOTAL_BYTES = MAX_JOB_FILES_TOTAL_MIB * 1024 * 1024
ALLOWED_JOB_FILE_TYPES = {
    "application/pdf",
    "text/plain",
    "image/png",
    "image/jpeg",
    "image/webp",
}


class JobFileInputError(ValueError):
    """사용자가 올린 파일의 형식이나 크기가 잘못된 경우."""


class JobFileExtractionError(RuntimeError):
    """파일은 정상이지만 텍스트 추출기가 글자를 읽지 못한 경우."""


@dataclass(frozen=True)
class JobFile:
    filename: str
    mime_type: str
    content: bytes


def validate_job_file(file: JobFile) -> None:
    if file.mime_type not in ALLOWED_JOB_FILE_TYPES:
        raise JobFileInputError(
            f"{file.filename}: PDF, TXT, PNG, JPG, WEBP 파일만 사용할 수 있습니다."
        )
    if not file.content:
        raise JobFileInputError(f"{file.filename}: 파일 내용이 비어 있습니다.")
    if len(file.content) > MAX_JOB_FILE_BYTES:
        raise JobFileInputError(
            f"{file.filename}: 파일 크기는 {MAX_JOB_FILE_MIB}MiB 이하여야 합니다."
        )


def decode_text_file(file: JobFile) -> str:
    # 국내 채용 사이트에서 내려받은 TXT는 UTF-8 또는 CP949인 경우가 많다.
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            text = file.content.decode(encoding).strip()
            if text:
                return text
        except UnicodeDecodeError:
            continue
    raise JobFileInputError(f"{file.filename}: TXT 문자 인코딩을 읽을 수 없습니다.")


def extract_job_file_text(files: list[JobFile]) -> str:
    """TXT·PDF·이미지를 로컬 추출기로 읽어 하나의 공고 원문으로 합친다."""

    if not files:
        raise JobFileInputError("채용공고 파일을 선택해 주세요.")
    if len(files) > MAX_JOB_FILE_COUNT:
        raise JobFileInputError("채용공고 파일은 최대 5개까지 선택할 수 있습니다.")
    if sum(len(file.content) for file in files) > MAX_JOB_FILES_TOTAL_BYTES:
        raise JobFileInputError(
            "선택한 파일의 전체 크기는 "
            f"{MAX_JOB_FILES_TOTAL_MIB}MiB 이하여야 합니다."
        )
    for file in files:
        validate_job_file(file)

    # 경험 근거와 동일한 PDF/TXT/OCR 추출 규칙을 재사용한다.
    # 지연 import로 job_file_text ↔ experience_file_text 순환 import를 피한다.
    from AI_Engine.experience_file_text import extract_experience_file_texts

    extracted_files = extract_experience_file_texts(files)
    return "\n\n".join(
        f"[파일: {item.filename}]\n{item.text}"
        for item in extracted_files
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
    "extract_job_file_text",
    "decode_text_file",
    "validate_job_file",
]
