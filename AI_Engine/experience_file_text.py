"""경험정리 파일을 외부 AI 없이 로컬 텍스트와 OCR로 읽는다."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
import shutil

import fitz
import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError

from AI_Engine.job_file_text import (
    JobFile,
    JobFileExtractionError,
    MAX_JOB_FILE_COUNT,
    MAX_JOB_FILES_TOTAL_BYTES,
    MAX_JOB_FILES_TOTAL_MIB,
    decode_text_file,
    validate_job_file,
)


MAX_PDF_PAGES = max(1, int(os.getenv("AI_MAX_PDF_PAGES", "100")))
MIN_NATIVE_PDF_TEXT_LENGTH = 20
WINDOWS_TESSERACT_PATHS = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)


@dataclass(frozen=True)
class ExtractedExperienceFile:
    """AI가 인용할 수 있도록 파일 이름과 추출 원문을 함께 보존한다."""

    filename: str
    mime_type: str
    text: str


def configure_tesseract() -> str:
    """PATH 또는 Windows 기본 설치 위치에서 Tesseract 실행 파일을 찾는다."""

    command = shutil.which("tesseract")
    if command:
        pytesseract.pytesseract.tesseract_cmd = command
        return command
    for path in WINDOWS_TESSERACT_PATHS:
        if path.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(path)
            return str(path)
    raise JobFileExtractionError(
        "Tesseract OCR이 설치되지 않았습니다. 서버에 Tesseract와 kor 언어팩을 설치해 주세요."
    )


def _prepare_image(image: Image.Image) -> Image.Image:
    """화면 캡처의 대비를 높여 한글과 숫자 인식률을 보완한다."""

    image.load()
    if image.width * image.height > 50_000_000:
        raise JobFileExtractionError("이미지 해상도가 너무 큽니다.")
    grayscale = ImageOps.grayscale(image)
    contrasted = ImageOps.autocontrast(grayscale)
    if contrasted.width < 1200:
        ratio = 1200 / contrasted.width
        contrasted = contrasted.resize(
            (1200, max(1, int(contrasted.height * ratio))),
            Image.Resampling.LANCZOS,
        )
    return contrasted


def _ocr_image(image: Image.Image) -> str:
    configure_tesseract()
    try:
        return pytesseract.image_to_string(
            _prepare_image(image),
            lang="kor+eng",
            # 채용 사이트와 이력서 캡처는 하나의 정렬된 텍스트 블록인 경우가 많아
            # 자동 페이지 분할보다 단일 블록 모드가 한글·숫자 누락이 적다.
            config="--oem 1 --psm 6",
            timeout=60,
        ).strip()
    except RuntimeError as error:
        raise JobFileExtractionError(
            "이미지 OCR 처리 시간이 초과되었습니다."
        ) from error
    except pytesseract.TesseractError as error:
        raise JobFileExtractionError(
            "Tesseract가 이미지 글자를 읽지 못했습니다."
        ) from error


def _extract_image(file: JobFile) -> str:
    try:
        with Image.open(BytesIO(file.content)) as image:
            text = _ocr_image(image)
    except (UnidentifiedImageError, OSError) as error:
        raise JobFileExtractionError(
            f"{file.filename}: 이미지 파일을 열 수 없습니다."
        ) from error
    if not text:
        raise JobFileExtractionError(
            f"{file.filename}: 이미지에서 읽을 수 있는 글자를 찾지 못했습니다."
        )
    return text


def _extract_pdf(file: JobFile) -> str:
    try:
        document = fitz.open(stream=file.content, filetype="pdf")
    except Exception as error:
        raise JobFileExtractionError(
            f"{file.filename}: PDF 파일을 열 수 없습니다."
        ) from error
    try:
        if document.page_count > MAX_PDF_PAGES:
            raise JobFileExtractionError(
                f"{file.filename}: PDF는 최대 {MAX_PDF_PAGES}페이지까지 읽을 수 있습니다."
            )
        page_texts: list[str] = []
        for index, page in enumerate(document):
            native_text = page.get_text("text").strip()
            if len(native_text) >= MIN_NATIVE_PDF_TEXT_LENGTH:
                page_texts.append(f"[{index + 1}페이지]\n{native_text}")
                continue
            # 텍스트가 없는 스캔 페이지만 200dpi 이미지로 바꿔 OCR한다.
            pixmap = page.get_pixmap(dpi=200, alpha=False)
            image = Image.open(BytesIO(pixmap.tobytes("png")))
            ocr_text = _ocr_image(image)
            if ocr_text:
                page_texts.append(f"[{index + 1}페이지]\n{ocr_text}")
        text = "\n\n".join(page_texts).strip()
    finally:
        document.close()
    if not text:
        raise JobFileExtractionError(
            f"{file.filename}: PDF에서 읽을 수 있는 글자를 찾지 못했습니다."
        )
    return text


def extract_experience_file_texts(
    files: list[JobFile],
) -> list[ExtractedExperienceFile]:
    """TXT·PDF·이미지를 파일별 근거 텍스트로 변환한다."""

    if not files:
        return []
    if len(files) > MAX_JOB_FILE_COUNT:
        raise ValueError(
            f"경험 근거 파일은 최대 {MAX_JOB_FILE_COUNT}개까지 선택할 수 있습니다."
        )
    if sum(len(file.content) for file in files) > MAX_JOB_FILES_TOTAL_BYTES:
        raise ValueError(
            "선택한 경험 근거 파일의 전체 크기는 "
            f"{MAX_JOB_FILES_TOTAL_MIB}MiB 이하여야 합니다."
        )

    extracted: list[ExtractedExperienceFile] = []
    for file in files:
        validate_job_file(file)
        if file.mime_type == "text/plain":
            text = decode_text_file(file)
        elif file.mime_type == "application/pdf":
            text = _extract_pdf(file)
        else:
            text = _extract_image(file)
        extracted.append(ExtractedExperienceFile(
            filename=file.filename,
            mime_type=file.mime_type,
            text=text,
        ))
    return extracted


__all__ = [
    "ExtractedExperienceFile",
    "configure_tesseract",
    "extract_experience_file_texts",
]
