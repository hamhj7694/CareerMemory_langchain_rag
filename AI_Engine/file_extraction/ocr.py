"""Tesseract 실행 상태와 품질 기반 OCR 프로필을 관리한다."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
import os
from pathlib import Path
import re
import shutil
from statistics import fmean, median
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
    length_factor = min(1.0, len(re.sub(r"\s+", "", text)) / 160)
    quality = round((average * 0.9) + (length_factor * 0.1), 4)
    return OCRResult(
        text=text,
        confidence=quality,
        profile=profile,
        word_boxes=tuple(boxes),
    )


def _candidate_selection_score(result: OCRResult, longest_text: int) -> float:
    """confidence만 높고 본문을 거의 놓친 OCR 후보를 선택하지 않는다."""

    compact_lines = [re.sub(r"\s+", "", line) for line in result.text.splitlines()]
    compact_lines = [line for line in compact_lines if line]
    compact_length = sum(len(line) for line in compact_lines)
    coverage = min(1.0, compact_length / max(1, longest_text))
    coherent_characters = sum(len(line) for line in compact_lines if len(line) >= 3)
    coherence = coherent_characters / max(1, compact_length)
    fragmented_lines = sum(1 for line in compact_lines if len(line) <= 2)
    fragmentation = fragmented_lines / max(1, len(compact_lines))
    numeric_tokens = len(re.findall(r"(?<!\w)[+-]?\d[\d,.]*(?:%|%p|건|회|초)?", result.text))
    numeric_signal = min(1.0, numeric_tokens / 8)
    return (
        (result.confidence * 0.55)
        + (coverage * 0.25)
        + (coherence * 0.15)
        + (numeric_signal * 0.05)
        - (fragmentation * 0.15)
    )


def _dark_horizontal_runs(image: Image.Image) -> list[tuple[int, int]]:
    """페이지 너비 대부분을 가로지르는 어두운 선/영역을 저해상도로 찾는다."""

    grayscale = ImageOps.grayscale(_flatten_transparency(image))
    scale = min(1.0, 1_200 / max(1, grayscale.width))
    analysis = grayscale.resize(
        (max(1, round(grayscale.width * scale)), max(1, round(grayscale.height * scale))),
        Image.Resampling.BILINEAR,
    )
    width, height = analysis.size
    pixels = analysis.load()
    dark_rows: list[int] = []
    for y in range(height):
        dark = sum(1 for x in range(width) if pixels[x, y] < 95)
        if dark / max(1, width) >= 0.65:
            dark_rows.append(y)
    if not dark_rows:
        return []
    runs: list[tuple[int, int]] = []
    start = previous = dark_rows[0]
    for current in dark_rows[1:]:
        if current > previous + 1:
            runs.append((start, previous))
            start = current
        previous = current
    runs.append((start, previous))
    return [
        (round(start / scale), round(end / scale))
        for start, end in runs
    ]


def _table_row_ranges(image: Image.Image) -> tuple[tuple[int, int], ...]:
    """반복되는 얇은 가로 구분선을 사용해 표의 데이터 행 범위를 찾는다."""

    runs = _dark_horizontal_runs(image)
    max_thickness = max(5, round(image.height * 0.006))
    separators = [
        round((start + end) / 2)
        for start, end in runs
        if end - start + 1 <= max_thickness
    ]
    if len(separators) < 4:
        return ()

    gaps = [right - left for left, right in zip(separators, separators[1:])]
    useful_gaps = [gap for gap in gaps if gap >= max(24, round(image.height * 0.012))]
    if len(useful_gaps) < 3:
        return ()
    typical_gap = median(useful_gaps)
    max_gap = max(80, typical_gap * 2.2)

    clusters: list[list[int]] = []
    cluster = [separators[0]]
    for separator in separators[1:]:
        gap = separator - cluster[-1]
        if max(24, round(image.height * 0.012)) <= gap <= max_gap:
            cluster.append(separator)
        else:
            if len(cluster) >= 4:
                clusters.append(cluster)
            cluster = [separator]
    if len(cluster) >= 4:
        clusters.append(cluster)
    if not clusters:
        return ()

    boundaries = max(clusters, key=len)
    boundary_gaps = [
        right - left for left, right in zip(boundaries, boundaries[1:])
    ]
    first_height = round(median(boundary_gaps[: min(5, len(boundary_gaps))]))
    inferred_start = max(0, boundaries[0] - first_height)
    boundaries = [inferred_start, *boundaries]

    trim = max(2, round(image.height * 0.0015))
    ranges = []
    for top, bottom in zip(boundaries, boundaries[1:]):
        row_top = min(image.height, top + trim)
        row_bottom = max(row_top, min(image.height, bottom - trim))
        if row_bottom - row_top >= 28:
            ranges.append((row_top, row_bottom))
    return tuple(ranges[:30]) if len(ranges) >= 3 else ()


def _merge_ocr_lines(preferred: str, fallback: str) -> str:
    """행 단위 결과를 우선하고 유사한 전체 페이지 문장은 중복시키지 않는다."""

    lines = [line.strip() for line in preferred.splitlines() if line.strip()]
    normalized = [re.sub(r"\s+", "", line).casefold() for line in lines]
    for line in fallback.splitlines():
        line = line.strip()
        if not line:
            continue
        candidate = re.sub(r"\s+", "", line).casefold()
        duplicate = any(
            candidate == existing
            or (min(len(candidate), len(existing)) >= 8 and (
                candidate in existing
                or existing in candidate
                or SequenceMatcher(None, candidate, existing).ratio() >= 0.78
            ))
            for existing in normalized
        )
        if not duplicate:
            lines.append(line)
            normalized.append(candidate)
    return "\n".join(lines).strip()


def _table_row_ocr(
    image: Image.Image,
    *,
    languages: list[str],
) -> tuple[str, tuple[dict[str, Any], ...], float | None]:
    ranges = _table_row_ranges(image)
    if not ranges:
        return "", (), None

    results: list[OCRResult] = []
    boxes: list[dict[str, Any]] = []
    for row_index, (top, bottom) in enumerate(ranges, start=1):
        row = image.crop((0, top, image.width, bottom))
        prepared = prepare_image(row)
        data = pytesseract.image_to_data(
            prepared,
            lang="+".join(languages),
            config="--oem 1 --psm 6",
            output_type=Output.DICT,
            timeout=OCR_TIMEOUT_SECONDS,
        )
        result = _data_to_result(data, "--oem 1 --psm 6 table-row")
        if not result.text:
            continue
        results.append(result)
        for box in result.word_boxes:
            boxes.append({**box, "table_row": row_index, "row_top": top, "row_bottom": bottom})
    if len(results) < 3:
        return "", (), None
    return (
        "\n".join(result.text for result in results),
        tuple(boxes[:5_000]),
        round(fmean(result.confidence for result in results), 4),
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

    image.load()
    source = _flatten_transparency(ImageOps.exif_transpose(image))
    prepared = prepare_image(source)
    prepared, rotation_warning = _rotate_from_osd(prepared, capability)
    profiles = (
        "--oem 1 --psm 3",
        "--oem 1 --psm 4",
        "--oem 1 --psm 6",
        "--oem 1 --psm 11",
    )
    candidates: list[OCRResult] = []
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
            candidates.append(result)
        longest_text = max(
            (len(re.sub(r"\s+", "", result.text)) for result in candidates),
            default=0,
        )
        best = max(
            candidates,
            key=lambda result: _candidate_selection_score(result, longest_text),
            default=None,
        )
        table_text, table_boxes, table_confidence = _table_row_ocr(
            source,
            languages=languages,
        )
        if best is not None and table_text:
            best = OCRResult(
                text=_merge_ocr_lines(table_text, best.text),
                confidence=round(fmean([
                    best.confidence,
                    table_confidence or best.confidence,
                ]), 4),
                profile=f"{best.profile}+table-rows-psm6",
                word_boxes=tuple([*table_boxes, *best.word_boxes])[:5_000],
                warnings=best.warnings,
            )
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
