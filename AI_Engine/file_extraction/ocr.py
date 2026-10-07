"""Tesseract 실행 상태와 품질 기반 OCR 프로필을 관리한다."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
import re
import shutil
from typing import Any

import pytesseract
from PIL import Image, ImageOps, ImageStat
from pytesseract import Output

from AI_Engine.file_extraction.models import FileExtractionError


WINDOWS_TESSERACT_PATHS = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)
MAX_IMAGE_PIXELS = 50_000_000
OCR_TIMEOUT_SECONDS = max(5, int(os.getenv("AI_OCR_TIMEOUT_SECONDS", "60")))
OCR_MIN_CONFIDENCE = min(1.0, max(0.0, float(os.getenv("AI_OCR_MIN_CONFIDENCE", "0.65"))))


@dataclass(frozen=True)
class OCRCapability:
    available: bool
    command: str | None
    version: str | None
    languages: tuple[str, ...]
    missing_recommended_languages: tuple[str, ...]
    tessdata_dir: str | None = None
    error: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "engine": "tesseract",
            "command": self.command,
            "version": self.version,
            "languages": list(self.languages),
            "missing_recommended_languages": list(self.missing_recommended_languages),
            "tessdata_dir": self.tessdata_dir,
            "error": self.error,
        }


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float
    profile: str
    word_boxes: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...] = ()


def _tesseract_command() -> str | None:
    configured = os.getenv("TESSERACT_CMD", "").strip()
    if configured:
        path = Path(configured)
        return str(path) if path.is_file() else None
    command = shutil.which("tesseract")
    if command:
        return command
    return next((str(path) for path in WINDOWS_TESSERACT_PATHS if path.is_file()), None)


def _tessdata_directory() -> str | None:
    configured = os.getenv("TESSDATA_PREFIX", "").strip()
    if configured:
        return configured if Path(configured).is_dir() else None
    local_app_data = os.getenv("LOCALAPPDATA", "").strip()
    if not local_app_data:
        return None
    managed = Path(local_app_data) / "CareerMemory" / "tessdata"
    return str(managed) if managed.is_dir() else None


@lru_cache(maxsize=1)
def get_ocr_capability() -> OCRCapability:
    command = _tesseract_command()
    tessdata_dir = _tessdata_directory()
    if not command:
        return OCRCapability(
            available=False,
            command=None,
            version=None,
            languages=(),
            missing_recommended_languages=("kor", "eng", "osd"),
            tessdata_dir=tessdata_dir,
            error="Tesseract 실행 파일을 찾을 수 없습니다.",
        )
    pytesseract.pytesseract.tesseract_cmd = command
    if tessdata_dir:
        os.environ["TESSDATA_PREFIX"] = tessdata_dir
    try:
        version = str(pytesseract.get_tesseract_version()).splitlines()[0]
        languages = tuple(sorted(pytesseract.get_languages(config="")))
    except Exception as error:  # pragma: no cover - 설치 손상 환경에서만 발생
        return OCRCapability(
            available=False,
            command=command,
            version=None,
            languages=(),
            missing_recommended_languages=("kor", "eng", "osd"),
            tessdata_dir=tessdata_dir,
            error=str(error),
        )
    missing = tuple(language for language in ("kor", "eng", "osd") if language not in languages)
    return OCRCapability(
        available=bool(languages),
        command=command,
        version=version,
        languages=languages,
        missing_recommended_languages=missing,
        tessdata_dir=tessdata_dir,
        error=(
            f"TESSDATA_PREFIX={tessdata_dir}에서 언어 데이터를 일부 찾지 못했습니다."
            if tessdata_dir and missing
            else None
        ),
    )


def clear_ocr_capability_cache() -> None:
    get_ocr_capability.cache_clear()


def _flatten_transparency(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        background.alpha_composite(rgba)
        return background.convert("RGB")
    return image.convert("RGB")


def prepare_image(image: Image.Image) -> Image.Image:
    image.load()
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise FileExtractionError("이미지 해상도가 너무 큽니다.")
    normalized = ImageOps.exif_transpose(image)
    normalized = _flatten_transparency(normalized)
    grayscale = ImageOps.grayscale(normalized)
    if ImageStat.Stat(grayscale).mean[0] < 105:
        grayscale = ImageOps.invert(grayscale)
    contrasted = ImageOps.autocontrast(grayscale, cutoff=1)
    if contrasted.width < 1_600:
        ratio = 1_600 / max(1, contrasted.width)
        contrasted = contrasted.resize(
            (1_600, max(1, int(contrasted.height * ratio))),
            Image.Resampling.LANCZOS,
        )
    return ImageOps.expand(contrasted, border=12, fill="white")


def _rotate_from_osd(image: Image.Image, capability: OCRCapability) -> tuple[Image.Image, str | None]:
    if "osd" not in capability.languages:
        return image, None
    try:
        osd = pytesseract.image_to_osd(
            image,
            output_type=Output.DICT,
            timeout=min(20, OCR_TIMEOUT_SECONDS),
        )
        rotation = int(osd.get("rotate") or 0)
        if rotation in {90, 180, 270}:
            return image.rotate(rotation, expand=True, fillcolor="white"), f"OSD로 {rotation}도 회전 보정"
    except (pytesseract.TesseractError, RuntimeError, ValueError):
        return image, None
    return image, None


def _data_to_result(data: dict[str, list[Any]], profile: str) -> OCRResult:
    line_words: dict[tuple[int, int, int, int], list[str]] = {}
    confidences: list[float] = []
    boxes: list[dict[str, Any]] = []
    size = len(data.get("text", []))
    for index in range(size):
        word = str(data["text"][index] or "").strip()
        if not word:
            continue
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            confidence = -1
        if confidence >= 0:
            confidences.append(confidence)
        key = (
            int(data.get("page_num", [1] * size)[index]),
            int(data.get("block_num", [0] * size)[index]),
            int(data.get("par_num", [0] * size)[index]),
            int(data.get("line_num", [0] * size)[index]),
        )
        line_words.setdefault(key, []).append(word)
        if len(boxes) < 5_000:
            boxes.append({
                "text": word,
                "confidence": max(0.0, confidence) / 100,
                "left": int(data.get("left", [0] * size)[index]),
                "top": int(data.get("top", [0] * size)[index]),
                "width": int(data.get("width", [0] * size)[index]),
                "height": int(data.get("height", [0] * size)[index]),
            })
    text = "\n".join(" ".join(words) for words in line_words.values()).strip()
    average = (sum(confidences) / len(confidences) / 100) if confidences else 0.0
    length_factor = min(1.0, len(re.sub(r"\s+", "", text)) / 40)
    quality = round((average * 0.85) + (length_factor * 0.15), 4)
    return OCRResult(
        text=text,
        confidence=quality,
        profile=profile,
        word_boxes=tuple(boxes),
    )


def run_ocr(image: Image.Image) -> OCRResult:
    capability = get_ocr_capability()
    if not capability.available:
        raise FileExtractionError(
            capability.error or "Tesseract OCR을 사용할 수 없습니다."
        )
    languages = [language for language in ("kor", "eng") if language in capability.languages]
    if not languages:
        raise FileExtractionError("Tesseract에 kor 또는 eng 언어 데이터가 없습니다.")

    prepared = prepare_image(image)
    prepared, rotation_warning = _rotate_from_osd(prepared, capability)
    profiles = ("--oem 1 --psm 3", "--oem 1 --psm 6", "--oem 1 --psm 11")
    best: OCRResult | None = None
    try:
        for profile in profiles:
            data = pytesseract.image_to_data(
                prepared,
                lang="+".join(languages),
                config=profile,
                output_type=Output.DICT,
                timeout=OCR_TIMEOUT_SECONDS,
            )
            result = _data_to_result(data, profile)
            if rotation_warning:
                result = OCRResult(
                    text=result.text,
                    confidence=result.confidence,
                    profile=result.profile,
                    word_boxes=result.word_boxes,
                    warnings=(rotation_warning,),
                )
            if best is None or result.confidence > best.confidence:
                best = result
    except RuntimeError as error:
        raise FileExtractionError("이미지 OCR 처리 시간이 초과되었습니다.") from error
    except pytesseract.TesseractError as error:
        raise FileExtractionError("Tesseract가 이미지 글자를 읽지 못했습니다.") from error

    if best is None or not best.text:
        raise FileExtractionError("이미지에서 읽을 수 있는 글자를 찾지 못했습니다.")
    warnings = list(best.warnings)
    if "kor" not in capability.languages:
        warnings.append("kor 언어팩이 없어 한글 정확도가 낮을 수 있습니다.")
    if best.confidence < OCR_MIN_CONFIDENCE:
        warnings.append("OCR 신뢰도가 낮아 원본 확인이 필요합니다.")
    return OCRResult(
        text=best.text,
        confidence=best.confidence,
        profile=best.profile,
        word_boxes=best.word_boxes,
        warnings=tuple(warnings),
    )


__all__ = [
    "OCRCapability",
    "OCRResult",
    "clear_ocr_capability_cache",
    "get_ocr_capability",
    "prepare_image",
    "run_ocr",
]
