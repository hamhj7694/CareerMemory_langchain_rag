"""첨부 원본 감지, 결정론적 파싱, OCR 품질 정보를 제공한다."""

from AI_Engine.file_extraction.detection import (
    ALLOWED_FILE_TYPES,
    MAX_FILE_BYTES,
    MAX_FILE_COUNT,
    MAX_FILES_TOTAL_BYTES,
    MAX_FILES_TOTAL_MIB,
    detect_and_validate_file,
)
from AI_Engine.file_extraction.models import (
    ExtractionSegment,
    FileExtractionError,
    FileExtractionResult,
    FileInputError,
    SourceFile,
)
from AI_Engine.file_extraction.ocr import OCRCapability, get_ocr_capability
from AI_Engine.file_extraction.parsers import extract_file, extract_files
from AI_Engine.file_extraction.runtime import (
    FILE_EXTRACTION_CONCURRENCY,
    run_file_extraction,
)

__all__ = [
    "ALLOWED_FILE_TYPES",
    "ExtractionSegment",
    "FileExtractionError",
    "FileExtractionResult",
    "FileInputError",
    "FILE_EXTRACTION_CONCURRENCY",
    "MAX_FILE_BYTES",
    "MAX_FILE_COUNT",
    "MAX_FILES_TOTAL_BYTES",
    "MAX_FILES_TOTAL_MIB",
    "OCRCapability",
    "SourceFile",
    "detect_and_validate_file",
    "extract_file",
    "extract_files",
    "get_ocr_capability",
    "run_file_extraction",
]
