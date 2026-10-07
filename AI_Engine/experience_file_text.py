"""경험 근거 파일 추출 API의 하위 호환 어댑터."""

from __future__ import annotations

from PIL import Image

from AI_Engine.file_extraction.models import FileExtractionResult
from AI_Engine.file_extraction.ocr import get_ocr_capability, prepare_image, run_ocr
from AI_Engine.file_extraction.parsers import MAX_PDF_PAGES, extract_files
from AI_Engine.job_file_text import JobFile, JobFileExtractionError, MAX_JOB_FILE_COUNT


ExtractedExperienceFile = FileExtractionResult


def configure_tesseract() -> str:
    capability = get_ocr_capability()
    if not capability.available or not capability.command:
        raise JobFileExtractionError(
            capability.error
            or "Tesseract OCR이 설치되지 않았습니다. 서버에 Tesseract와 kor 언어팩을 설치해 주세요."
        )
    return capability.command


def _prepare_image(image: Image.Image) -> Image.Image:
    return prepare_image(image)


def _ocr_image(image: Image.Image) -> str:
    return run_ocr(image).text


def extract_experience_file_texts(
    files: list[JobFile],
) -> list[ExtractedExperienceFile]:
    """파일별 근거와 locator·품질 정보를 함께 반환한다."""

    return extract_files(files, max_count=MAX_JOB_FILE_COUNT)


__all__ = [
    "ExtractedExperienceFile",
    "MAX_PDF_PAGES",
    "configure_tesseract",
    "extract_experience_file_texts",
]
