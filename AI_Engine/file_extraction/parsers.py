"""파일 형식별 결정론적 텍스트 추출기와 파서 레지스트리."""

from __future__ import annotations

from io import BytesIO
import os
from pathlib import PurePosixPath
import posixpath
import re
from statistics import fmean
from typing import Callable
import xml.etree.ElementTree as ET
import zipfile

import pymupdf
from PIL import Image, UnidentifiedImageError

from AI_Engine.file_extraction.detection import (
    DOCX_MIME,
    HWPX_MIME,
    IMAGE_MIME_TYPES,
    LEGACY_DOCUMENT_MIME_TYPES,
    MAX_FILE_COUNT,
    MAX_FILES_TOTAL_BYTES,
    MAX_FILES_TOTAL_MIB,
    MEDIA_MIME_TYPES,
    PPTX_MIME,
    detect_and_validate_file,
    inspect_zip_container,
)
from AI_Engine.file_extraction.external_tools import convert_legacy_document
from AI_Engine.file_extraction.media import parse_media
from AI_Engine.file_extraction.models import (
    ExtractionSegment,
    FileExtractionError,
    FileExtractionResult,
    FileInputError,
    SourceFile,
)
from AI_Engine.file_extraction.ocr import run_ocr


PARSER_VERSION = "career-file-parser-v2"
MAX_PDF_PAGES = max(1, int(os.getenv("AI_MAX_PDF_PAGES", "100")))
MAX_XML_BYTES = 20 * 1024 * 1024
MIN_NATIVE_PDF_TEXT_LENGTH = 20


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _normalise_text(value: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _native_text_quality(text: str) -> float:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return 0.0
    printable = sum(character.isprintable() and character != "�" for character in compact)
    replacement_penalty = min(0.5, compact.count("�") / max(1, len(compact)))
    length_factor = min(1.0, len(compact) / 80)
    return round(max(0.0, (printable / len(compact)) * 0.8 + length_factor * 0.2 - replacement_penalty), 4)


def _merge_unique_lines(*texts: str) -> str:
    seen: set[str] = set()
    lines: list[str] = []
    for text in texts:
        for line in text.splitlines():
            normalized = " ".join(line.split()).casefold()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            lines.append(line.strip())
    return "\n".join(lines).strip()


def _decode_text(file: SourceFile) -> str:
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp949"):
        try:
            text = file.content.decode(encoding).strip()
            if text:
                return text
        except UnicodeDecodeError:
            continue
    raise FileInputError(f"{file.filename}: 텍스트 문자 인코딩을 읽을 수 없습니다.")


def parse_text(file: SourceFile) -> FileExtractionResult:
    text = _decode_text(file)
    segments = tuple(
        ExtractionSegment(
            text=line,
            locator={"line": index},
        )
        for index, line in enumerate(text.splitlines(), start=1)
        if line.strip()
    )
    return FileExtractionResult(
        filename=file.filename,
        mime_type=file.mime_type,
        text=text,
        segments=segments,
        quality_score=1.0,
        parser_name="markdown" if file.mime_type == "text/markdown" else "plain-text",
        parser_version=PARSER_VERSION,
    )


def parse_image(file: SourceFile) -> FileExtractionResult:
    try:
        with Image.open(BytesIO(file.content)) as image:
            frame_count = int(getattr(image, "n_frames", 1))
            if frame_count > 1:
                image.seek(0)
            ocr = run_ocr(image)
    except (UnidentifiedImageError, OSError) as error:
        raise FileExtractionError(f"{file.filename}: 이미지 파일을 열 수 없습니다.") from error
    warnings = list(ocr.warnings)
    if frame_count > 1:
        warnings.append("움직이는 이미지는 첫 번째 프레임만 OCR했습니다.")
    return FileExtractionResult(
        filename=file.filename,
        mime_type=file.mime_type,
        text=ocr.text,
        segments=(ExtractionSegment(
            text=ocr.text,
            locator={"frame": 1, "word_boxes": list(ocr.word_boxes)},
            method="ocr",
            confidence=ocr.confidence,
        ),),
        extraction_method="ocr",
        quality_score=ocr.confidence,
        warnings=tuple(warnings),
        parser_name="image-ocr",
        parser_version=PARSER_VERSION,
        metadata={"ocr_profile": ocr.profile, "frame_count": frame_count},
    )


def _page_image_coverage(page: pymupdf.Page) -> float:
    try:
        blocks = page.get_text("dict", sort=True).get("blocks", [])
    except Exception:
        return 0.0
    page_area = max(1.0, float(page.rect.width * page.rect.height))
    image_area = 0.0
    for block in blocks:
        if block.get("type") != 1:
            continue
        x0, y0, x1, y1 = block.get("bbox", (0, 0, 0, 0))
        image_area += max(0.0, x1 - x0) * max(0.0, y1 - y0)
    return min(1.0, image_area / page_area)


def _native_page_text(page: pymupdf.Page) -> str:
    blocks = page.get_text("blocks", sort=True)
    return _normalise_text("\n".join(
        str(block[4])
        for block in blocks
        if len(block) < 7 or block[6] == 0
    ))


def parse_pdf(file: SourceFile) -> FileExtractionResult:
    try:
        document = pymupdf.open(stream=file.content, filetype="pdf")
    except Exception as error:
        raise FileExtractionError(f"{file.filename}: PDF 파일을 열 수 없습니다.") from error

    if document.page_count > MAX_PDF_PAGES:
        document.close()
        raise FileExtractionError(
            f"{file.filename}: PDF는 최대 {MAX_PDF_PAGES}페이지까지 읽을 수 있습니다."
        )

    segments: list[ExtractionSegment] = []
    warnings: list[str] = []
    methods: set[str] = set()
    try:
        for index, page in enumerate(document, start=1):
            try:
                native_text = _native_page_text(page)
                native_quality = _native_text_quality(native_text)
                image_coverage = _page_image_coverage(page)
                should_ocr = (
                    len(re.sub(r"\s+", "", native_text)) < MIN_NATIVE_PDF_TEXT_LENGTH
                    or native_quality < 0.70
                    or (image_coverage >= 0.35 and len(native_text) < 200)
                )
                ocr_text = ""
                ocr_confidence: float | None = None
                ocr_boxes: list[dict] = []
                if should_ocr:
                    try:
                        pixmap = page.get_pixmap(dpi=300, alpha=False)
                        with Image.open(BytesIO(pixmap.tobytes("png"))) as image:
                            ocr = run_ocr(image)
                        ocr_text = ocr.text
                        ocr_confidence = ocr.confidence
                        ocr_boxes = list(ocr.word_boxes)
                        warnings.extend(f"{index}페이지: {warning}" for warning in ocr.warnings)
                    except FileExtractionError as error:
                        if not native_text:
                            warnings.append(f"{index}페이지 OCR 실패: {error}")
                            continue
                        warnings.append(f"{index}페이지 OCR 보완 실패: {error}")

                if native_text and ocr_text:
                    page_text = _merge_unique_lines(native_text, ocr_text)
                    method = "hybrid"
                    confidence = round(fmean([native_quality, ocr_confidence or 0.0]), 4)
                elif ocr_text:
                    page_text = ocr_text
                    method = "ocr"
                    confidence = ocr_confidence
                else:
                    page_text = native_text
                    method = "native"
                    confidence = native_quality
                if not page_text:
                    warnings.append(f"{index}페이지에서 텍스트를 찾지 못했습니다.")
                    continue
                methods.add(method)
                segments.append(ExtractionSegment(
                    text=f"[{index}페이지]\n{page_text}",
                    locator={
                        "page": index,
                        "image_coverage": round(image_coverage, 4),
                        "ocr_word_boxes": ocr_boxes,
                    },
                    method=method,
                    confidence=confidence,
                ))
            except Exception as error:  # 페이지 하나가 전체 원본을 잃게 하지 않는다.
                warnings.append(f"{index}페이지 처리 실패: {error}")
    finally:
        document.close()

    if not segments:
        detail = f" ({'; '.join(warnings[:3])})" if warnings else ""
        raise FileExtractionError(
            f"{file.filename}: PDF에서 읽을 수 있는 글자를 찾지 못했습니다.{detail}"
        )
    qualities = [segment.confidence for segment in segments if segment.confidence is not None]
    overall_method = "hybrid" if len(methods) > 1 or "hybrid" in methods else next(iter(methods))
    return FileExtractionResult(
        filename=file.filename,
        mime_type=file.mime_type,
        text="\n\n".join(segment.text for segment in segments),
        segments=tuple(segments),
        extraction_method=overall_method,
        quality_score=round(fmean(qualities), 4) if qualities else None,
        warnings=tuple(warnings),
        parser_name="pdf-native-ocr",
        parser_version=PARSER_VERSION,
        metadata={"page_count": len(segments)},
    )


def _safe_archive(content: bytes) -> zipfile.ZipFile:
    inspect_zip_container(content)
    return zipfile.ZipFile(BytesIO(content))


def _read_xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    try:
        info = archive.getinfo(name)
        if info.file_size > MAX_XML_BYTES:
            raise FileExtractionError(f"{name}: XML 항목이 너무 큽니다.")
        return ET.fromstring(archive.read(name))
    except KeyError as error:
        raise FileExtractionError(f"문서 내부의 {name} 항목을 찾을 수 없습니다.") from error
    except ET.ParseError as error:
        raise FileExtractionError(f"{name}: XML 구조가 손상되었습니다.") from error


def _element_text(element: ET.Element) -> str:
    pieces: list[str] = []
    for node in element.iter():
        name = _local_name(node.tag)
        if name == "t" and node.text:
            pieces.append(node.text)
        elif name == "tab":
            pieces.append("\t")
        elif name in {"br", "lineBreak"}:
            pieces.append("\n")
    return _normalise_text("".join(pieces))


def _embedded_image_results(
    archive: zipfile.ZipFile,
    names: list[str],
    *,
    locator_key: str,
) -> tuple[list[ExtractionSegment], list[str]]:
    segments: list[ExtractionSegment] = []
    warnings: list[str] = []
    for index, name in enumerate(names[:20], start=1):
        suffix = PurePosixPath(name).suffix.casefold()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
        }.get(suffix)
        if not mime:
            continue
        try:
            result = parse_image(SourceFile(name, mime, archive.read(name)))
            segments.append(ExtractionSegment(
                text=result.text,
                locator={locator_key: name, "index": index},
                method="ocr",
                confidence=result.quality_score,
            ))
            warnings.extend(result.warnings)
        except (FileExtractionError, KeyError) as error:
            warnings.append(f"{name} 이미지 OCR 실패: {error}")
    return segments, warnings


def parse_docx(file: SourceFile) -> FileExtractionResult:
    segments: list[ExtractionSegment] = []
    warnings: list[str] = []
    with _safe_archive(file.content) as archive:
        root = _read_xml(archive, "word/document.xml")
        body = next((node for node in root.iter() if _local_name(node.tag) == "body"), root)
        block_index = 0
        for child in body:
            name = _local_name(child.tag)
            if name not in {"p", "tbl"}:
                continue
            block_index += 1
            if name == "tbl":
                rows: list[str] = []
                for row in (node for node in child.iter() if _local_name(node.tag) == "tr"):
                    cells = [
                        _element_text(cell)
                        for cell in row
                        if _local_name(cell.tag) == "tc"
                    ]
                    if any(cells):
                        rows.append(" | ".join(cells))
                text = "\n".join(rows)
                block_type = "table"
            else:
                text = _element_text(child)
                block_type = "paragraph"
            if text:
                segments.append(ExtractionSegment(
                    text=text,
                    locator={"block": block_index, "block_type": block_type},
                ))

        if len("".join(segment.text for segment in segments)) < 20:
            image_names = [name for name in archive.namelist() if name.casefold().startswith("word/media/")]
            image_segments, image_warnings = _embedded_image_results(
                archive,
                image_names,
                locator_key="embedded_image",
            )
            segments.extend(image_segments)
            warnings.extend(image_warnings)
    if not segments:
        raise FileExtractionError(f"{file.filename}: DOCX에서 읽을 수 있는 내용을 찾지 못했습니다.")
    methods = {segment.method for segment in segments}
    return FileExtractionResult(
        filename=file.filename,
        mime_type=file.mime_type,
        text="\n\n".join(segment.text for segment in segments),
        segments=tuple(segments),
        extraction_method="hybrid" if len(methods) > 1 else next(iter(methods)),
        quality_score=1.0 if methods == {"native"} else 0.8,
        warnings=tuple(warnings),
        parser_name="docx-ooxml",
        parser_version=PARSER_VERSION,
    )


def _pptx_slide_paths(archive: zipfile.ZipFile) -> list[str]:
    presentation = _read_xml(archive, "ppt/presentation.xml")
    relationships = _read_xml(archive, "ppt/_rels/presentation.xml.rels")
    relationship_targets = {
        node.attrib.get("Id", ""): node.attrib.get("Target", "")
        for node in relationships
        if _local_name(node.tag) == "Relationship"
    }
    paths: list[str] = []
    for node in presentation.iter():
        if _local_name(node.tag) != "sldId":
            continue
        relationship_id = next((value for key, value in node.attrib.items() if _local_name(key) == "id"), "")
        target = relationship_targets.get(relationship_id)
        if target:
            paths.append(posixpath.normpath(posixpath.join("ppt", target)))
    if paths:
        return paths
    slide_names = [
        name for name in archive.namelist()
        if re.fullmatch(r"ppt/slides/slide\d+\.xml", name, flags=re.IGNORECASE)
    ]
    return sorted(slide_names, key=lambda value: int(re.search(r"(\d+)", value).group(1)))


def _slide_image_names(archive: zipfile.ZipFile, slide_path: str) -> list[str]:
    directory, filename = posixpath.split(slide_path)
    rel_path = posixpath.join(directory, "_rels", f"{filename}.rels")
    if rel_path not in archive.namelist():
        return []
    relationships = _read_xml(archive, rel_path)
    names: list[str] = []
    for node in relationships:
        if _local_name(node.tag) != "Relationship":
            continue
        target = node.attrib.get("Target", "")
        if "media/" in target.replace("\\", "/"):
            names.append(posixpath.normpath(posixpath.join(directory, target)))
    return names


def parse_pptx(file: SourceFile) -> FileExtractionResult:
    segments: list[ExtractionSegment] = []
    warnings: list[str] = []
    with _safe_archive(file.content) as archive:
        slide_paths = _pptx_slide_paths(archive)
        for index, slide_path in enumerate(slide_paths, start=1):
            root = _read_xml(archive, slide_path)
            text = _normalise_text("\n".join(
                node.text or ""
                for node in root.iter()
                if _local_name(node.tag) == "t" and (node.text or "").strip()
            ))
            if text:
                segments.append(ExtractionSegment(
                    text=f"[{index}슬라이드]\n{text}",
                    locator={"slide": index, "path": slide_path},
                ))
            if len(text) < 20:
                image_segments, image_warnings = _embedded_image_results(
                    archive,
                    _slide_image_names(archive, slide_path),
                    locator_key="slide_image",
                )
                for image_segment in image_segments:
                    segments.append(ExtractionSegment(
                        text=f"[{index}슬라이드 이미지]\n{image_segment.text}",
                        locator={"slide": index, **image_segment.locator},
                        method="ocr",
                        confidence=image_segment.confidence,
                    ))
                warnings.extend(image_warnings)
    if not segments:
        raise FileExtractionError(f"{file.filename}: PPTX에서 읽을 수 있는 내용을 찾지 못했습니다.")
    methods = {segment.method for segment in segments}
    qualities = [segment.confidence for segment in segments if segment.confidence is not None]
    return FileExtractionResult(
        filename=file.filename,
        mime_type=file.mime_type,
        text="\n\n".join(segment.text for segment in segments),
        segments=tuple(segments),
        extraction_method="hybrid" if len(methods) > 1 else next(iter(methods)),
        quality_score=round(fmean(qualities), 4) if qualities else 1.0,
        warnings=tuple(warnings),
        parser_name="pptx-ooxml",
        parser_version=PARSER_VERSION,
        metadata={"slide_count": len(slide_paths)},
    )


def _hwpx_section_paths(archive: zipfile.ZipFile) -> list[str]:
    names = archive.namelist()
    content_hpf = next((name for name in names if name.casefold().endswith("content.hpf")), None)
    if content_hpf:
        root = _read_xml(archive, content_hpf)
        manifest = {
            node.attrib.get("id", ""): node.attrib.get("href", "")
            for node in root.iter()
            if _local_name(node.tag) == "item"
        }
        base = posixpath.dirname(content_hpf)
        ordered: list[str] = []
        for node in root.iter():
            if _local_name(node.tag) != "itemref":
                continue
            identifier = node.attrib.get("idref", "")
            href = manifest.get(identifier, "")
            if href and "section" in href.casefold() and href.casefold().endswith(".xml"):
                ordered.append(posixpath.normpath(posixpath.join(base, href)))
        if ordered:
            return ordered
    section_names = [
        name for name in names
        if re.search(r"(?:^|/)section\d+\.xml$", name, flags=re.IGNORECASE)
    ]
    return sorted(section_names, key=lambda value: int(re.search(r"(\d+)\.xml$", value).group(1)))


def parse_hwpx(file: SourceFile) -> FileExtractionResult:
    segments: list[ExtractionSegment] = []
    with _safe_archive(file.content) as archive:
        section_paths = _hwpx_section_paths(archive)
        for section_index, section_path in enumerate(section_paths, start=1):
            root = _read_xml(archive, section_path)
            paragraph_index = 0
            for paragraph in (node for node in root.iter() if _local_name(node.tag) == "p"):
                text = _element_text(paragraph)
                if not text:
                    continue
                paragraph_index += 1
                segments.append(ExtractionSegment(
                    text=text,
                    locator={
                        "section": section_index,
                        "paragraph": paragraph_index,
                        "path": section_path,
                    },
                ))
    if not segments:
        raise FileExtractionError(f"{file.filename}: HWPX에서 읽을 수 있는 내용을 찾지 못했습니다.")
    return FileExtractionResult(
        filename=file.filename,
        mime_type=file.mime_type,
        text="\n\n".join(segment.text for segment in segments),
        segments=tuple(segments),
        quality_score=1.0,
        parser_name="hwpx-owpml",
        parser_version=PARSER_VERSION,
        metadata={"section_count": len({segment.locator["section"] for segment in segments})},
    )


Parser = Callable[[SourceFile], FileExtractionResult]


def parse_legacy_document(file: SourceFile) -> FileExtractionResult:
    converted = convert_legacy_document(file)
    parsed = extract_file(converted)
    return FileExtractionResult(
        filename=file.filename,
        mime_type=file.mime_type,
        text=parsed.text,
        segments=parsed.segments,
        extraction_method="converted",
        quality_score=parsed.quality_score,
        warnings=parsed.warnings,
        parser_name=f"legacy-converter+{parsed.parser_name}",
        parser_version=PARSER_VERSION,
        metadata={
            **parsed.metadata,
            "converted_filename": converted.filename,
            "converted_mime_type": parsed.mime_type,
        },
    )


def parse_media_file(file: SourceFile) -> FileExtractionResult:
    return parse_media(file, parser_version=PARSER_VERSION)
PARSERS: dict[str, Parser] = {
    "text/plain": parse_text,
    "text/markdown": parse_text,
    "application/pdf": parse_pdf,
    DOCX_MIME: parse_docx,
    PPTX_MIME: parse_pptx,
    HWPX_MIME: parse_hwpx,
    **{mime: parse_image for mime in IMAGE_MIME_TYPES},
    **{mime: parse_legacy_document for mime in LEGACY_DOCUMENT_MIME_TYPES},
    **{mime: parse_media_file for mime in MEDIA_MIME_TYPES},
}


def extract_file(file: SourceFile) -> FileExtractionResult:
    normalized = detect_and_validate_file(file)
    parser = PARSERS.get(normalized.mime_type)
    if parser is None:
        raise FileInputError(f"{file.filename}: 사용할 수 있는 파서가 없습니다.")
    return parser(normalized)


def extract_files(
    files: list[SourceFile],
    *,
    max_count: int = MAX_FILE_COUNT,
) -> list[FileExtractionResult]:
    if not files:
        return []
    if len(files) > max_count:
        raise FileInputError(f"파일은 최대 {max_count}개까지 선택할 수 있습니다.")
    if sum(len(file.content) for file in files) > MAX_FILES_TOTAL_BYTES:
        raise FileInputError(
            f"선택한 파일의 전체 크기는 {MAX_FILES_TOTAL_MIB}MiB 이하여야 합니다."
        )
    return [extract_file(file) for file in files]


__all__ = [
    "PARSER_VERSION",
    "PARSERS",
    "extract_file",
    "extract_files",
    "parse_docx",
    "parse_hwpx",
    "parse_image",
    "parse_legacy_document",
    "parse_media_file",
    "parse_pdf",
    "parse_pptx",
    "parse_text",
]
