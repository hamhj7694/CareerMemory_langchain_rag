"""클라이언트 MIME을 신뢰하지 않고 확장자·시그니처·컨테이너를 함께 확인한다."""

from __future__ import annotations

from io import BytesIO
import os
from pathlib import PurePosixPath
import zipfile

from AI_Engine.file_extraction.models import FileInputError, SourceFile


MAX_FILE_MIB = max(1, int(os.getenv("AI_MAX_FILE_MIB", "25")))
MAX_FILE_COUNT = 10
MAX_FILES_TOTAL_MIB = max(
    MAX_FILE_MIB,
    int(os.getenv("AI_MAX_FILES_TOTAL_MIB", "100")),
)
MAX_FILE_BYTES = MAX_FILE_MIB * 1024 * 1024
MAX_FILES_TOTAL_BYTES = MAX_FILES_TOTAL_MIB * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 5_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 200 * 1024 * 1024

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
HWPX_MIME = "application/vnd.hancom.hwpx"
DOC_MIME = "application/msword"
PPT_MIME = "application/vnd.ms-powerpoint"
HWP_MIME = "application/x-hwp"

EXTENSION_MIME_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".docx": DOCX_MIME,
    ".pptx": PPTX_MIME,
    ".hwpx": HWPX_MIME,
    ".doc": DOC_MIME,
    ".ppt": PPT_MIME,
    ".hwp": HWP_MIME,
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".mpeg": "video/mpeg",
    ".mpg": "video/mpeg",
}

ALLOWED_FILE_TYPES = frozenset(EXTENSION_MIME_TYPES.values())
TEXT_MIME_TYPES = frozenset({"text/plain", "text/markdown"})
IMAGE_MIME_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp", "image/tiff"}
)
LEGACY_DOCUMENT_MIME_TYPES = frozenset({DOC_MIME, PPT_MIME, HWP_MIME})
MEDIA_MIME_TYPES = frozenset(
    mime_type
    for mime_type in EXTENSION_MIME_TYPES.values()
    if mime_type.startswith(("audio/", "video/"))
)


def _extension(filename: str) -> str:
    suffix = PurePosixPath(filename.replace("\\", "/")).suffix
    return suffix.casefold()


def inspect_zip_container(content: bytes) -> tuple[str | None, tuple[str, ...]]:
    """ZIP 기반 오피스 파일 종류와 안전한 엔트리 목록을 반환한다."""

    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise FileInputError("압축 문서 내부 파일 개수가 너무 많습니다.")
            if any(info.flag_bits & 0x1 for info in infos):
                raise FileInputError("암호화된 문서는 아직 읽을 수 없습니다.")
            if sum(info.file_size for info in infos) > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise FileInputError("압축 해제된 문서 크기가 허용 범위를 초과합니다.")
            names = tuple(info.filename.replace("\\", "/") for info in infos)
    except zipfile.BadZipFile as error:
        raise FileInputError("압축 기반 문서의 내부 구조가 손상되었습니다.") from error

    lowered = {name.casefold() for name in names}
    if "word/document.xml" in lowered:
        return DOCX_MIME, names
    if "ppt/presentation.xml" in lowered:
        return PPTX_MIME, names
    if any(name.endswith("content.hpf") for name in lowered) or any(
        name.startswith("contents/section") and name.endswith(".xml")
        for name in lowered
    ):
        return HWPX_MIME, names
    return None, names


def detect_file_mime(file: SourceFile) -> str:
    content = file.content
    extension_mime = EXTENSION_MIME_TYPES.get(_extension(file.filename))
    declared = (file.mime_type or "").split(";", 1)[0].strip().casefold()

    detected: str | None = None
    if content.startswith(b"%PDF-"):
        detected = "application/pdf"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
    elif content.startswith(b"\xff\xd8\xff"):
        detected = "image/jpeg"
    elif content.startswith((b"GIF87a", b"GIF89a")):
        detected = "image/gif"
    elif content.startswith(b"BM"):
        detected = "image/bmp"
    elif content.startswith((b"II*\x00", b"MM\x00*")):
        detected = "image/tiff"
    elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        detected = "image/webp"
    elif content.startswith(b"RIFF") and content[8:12] == b"WAVE":
        detected = "audio/wav"
    elif content.startswith(b"fLaC"):
        detected = "audio/flac"
    elif content.startswith(b"OggS"):
        detected = "audio/ogg"
    elif content.startswith(b"ID3") or (
        len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0
    ):
        detected = "audio/mpeg"
    elif len(content) >= 12 and content[4:8] == b"ftyp":
        detected = extension_mime if extension_mime in {
            "audio/mp4", "video/mp4", "video/quicktime"
        } else (declared if declared in MEDIA_MIME_TYPES else "video/mp4")
    elif content.startswith(b"\x1aE\xdf\xa3"):
        detected = extension_mime if extension_mime in {
            "video/webm", "video/x-matroska"
        } else (declared if declared in MEDIA_MIME_TYPES else "video/webm")
    elif content.startswith((b"\x00\x00\x01\xba", b"\x00\x00\x01\xb3")):
        detected = "video/mpeg"
    elif content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        detected = extension_mime if extension_mime in LEGACY_DOCUMENT_MIME_TYPES else None
    elif content.startswith(b"PK\x03\x04"):
        detected, _ = inspect_zip_container(content)

    if detected and extension_mime and detected != extension_mime:
        raise FileInputError(
            f"{file.filename}: 확장자와 실제 파일 형식이 일치하지 않습니다."
        )
    if detected:
        return detected
    if extension_mime in TEXT_MIME_TYPES:
        return extension_mime
    if declared in TEXT_MIME_TYPES and extension_mime in (None, declared):
        return declared
    if extension_mime in ALLOWED_FILE_TYPES:
        raise FileInputError(
            f"{file.filename}: 파일 시그니처 또는 문서 내부 구조를 확인할 수 없습니다."
        )
    raise FileInputError(
        f"{file.filename}: 지원하지 않는 파일 형식입니다."
    )


def detect_and_validate_file(file: SourceFile) -> SourceFile:
    if not file.content:
        raise FileInputError(f"{file.filename}: 파일 내용이 비어 있습니다.")
    if len(file.content) > MAX_FILE_BYTES:
        raise FileInputError(
            f"{file.filename}: 파일 크기는 {MAX_FILE_MIB}MiB 이하여야 합니다."
        )
    mime_type = detect_file_mime(file)
    if mime_type not in ALLOWED_FILE_TYPES:
        raise FileInputError(f"{file.filename}: 지원하지 않는 파일 형식입니다.")
    return SourceFile(
        filename=file.filename,
        mime_type=mime_type,
        content=file.content,
    )


__all__ = [
    "ALLOWED_FILE_TYPES",
    "DOCX_MIME",
    "DOC_MIME",
    "EXTENSION_MIME_TYPES",
    "HWPX_MIME",
    "HWP_MIME",
    "IMAGE_MIME_TYPES",
    "LEGACY_DOCUMENT_MIME_TYPES",
    "MAX_FILE_BYTES",
    "MAX_FILE_COUNT",
    "MAX_FILE_MIB",
    "MAX_FILES_TOTAL_BYTES",
    "MAX_FILES_TOTAL_MIB",
    "MEDIA_MIME_TYPES",
    "PPT_MIME",
    "PPTX_MIME",
    "TEXT_MIME_TYPES",
    "detect_and_validate_file",
    "detect_file_mime",
    "inspect_zip_container",
]
