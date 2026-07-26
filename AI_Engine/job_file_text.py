"""채용공고 PDF·이미지·TXT에서 분석 가능한 원문을 추출한다."""

from __future__ import annotations

import os
from dataclasses import dataclass

from google import genai
from google.genai import types

from AI_Engine.llm_provider import get_chat_model_name


MAX_JOB_FILE_BYTES = 10 * 1024 * 1024
MAX_JOB_FILE_COUNT = 5
MAX_JOB_FILES_TOTAL_BYTES = 14 * 1024 * 1024
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
    """파일은 정상이지만 Gemini가 글자를 읽지 못한 경우."""


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
            f"{file.filename}: 파일 크기는 10MB 이하여야 합니다."
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
    """TXT는 직접 읽고 PDF·스크린샷은 Gemini의 시각 인식으로 옮긴다."""

    if not files:
        raise JobFileInputError("채용공고 파일을 선택해 주세요.")
    if len(files) > MAX_JOB_FILE_COUNT:
        raise JobFileInputError("채용공고 파일은 최대 5개까지 선택할 수 있습니다.")
    if sum(len(file.content) for file in files) > MAX_JOB_FILES_TOTAL_BYTES:
        raise JobFileInputError("선택한 파일의 전체 크기는 14MB 이하여야 합니다.")
    for file in files:
        validate_job_file(file)

    sections: list[str] = []
    visual_files: list[JobFile] = []
    for file in files:
        if file.mime_type == "text/plain":
            sections.append(
                f"[파일: {file.filename}]\n{decode_text_file(file)}"
            )
        else:
            visual_files.append(file)

    if visual_files:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise JobFileExtractionError("GEMINI_API_KEY가 설정되지 않았습니다.")

        parts: list[types.Part] = []
        for file in visual_files:
            parts.extend([
                types.Part.from_text(
                    text=f"다음 파일의 이름은 {file.filename}입니다."
                ),
                types.Part.from_bytes(
                    data=file.content,
                    mime_type=file.mime_type,
                ),
            ])
        parts.append(types.Part.from_text(text="""
첨부된 채용공고 PDF 또는 이미지에 실제로 보이는 글자를 빠짐없이 옮겨 적어 주세요.

규칙:
- 요약하거나 새로운 내용을 만들지 마세요.
- 회사명, 공고 제목, 직무명, 주요 업무, 자격 요건, 우대 사항, 근무 조건을 보이는 순서대로 적으세요.
- 여러 파일이 이어지는 화면이면 중복 문장은 한 번만 적으세요.
- 메뉴, 브라우저 버튼, 광고처럼 채용공고와 관계없는 글자는 제외하세요.
- 표와 목록은 읽기 쉬운 일반 텍스트와 불릿 목록으로 바꾸세요.
- 결과에는 설명을 붙이지 말고 추출한 채용공고 원문만 반환하세요.
""".strip()))
        try:
            response = genai.Client(api_key=api_key).models.generate_content(
                model=get_chat_model_name("gemini"),
                contents=parts,
            )
        except Exception as error:
            raise JobFileExtractionError(str(error)) from error
        extracted = (response.text or "").strip()
        if not extracted:
            raise JobFileExtractionError(
                "이미지 또는 PDF에서 채용공고 글자를 찾지 못했습니다."
            )
        names = ", ".join(file.filename for file in visual_files)
        sections.append(f"[파일: {names}]\n{extracted}")

    return "\n\n".join(sections).strip()


__all__ = [
    "ALLOWED_JOB_FILE_TYPES",
    "JobFile",
    "JobFileExtractionError",
    "JobFileInputError",
    "MAX_JOB_FILE_BYTES",
    "MAX_JOB_FILE_COUNT",
    "MAX_JOB_FILES_TOTAL_BYTES",
    "extract_job_file_text",
    "decode_text_file",
    "validate_job_file",
]
