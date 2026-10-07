"""합성 원본으로 파일 파서와 선택적 실제 OCR KPI를 재현한다."""

from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import time
import zipfile

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from AI_Engine.file_extraction import SourceFile, extract_file, get_ocr_capability
from AI_Engine.file_extraction.external_tools import (
    get_hwpx_converter_capability,
    get_libreoffice_capability,
)
from AI_Engine.file_extraction.media import get_media_capability
from AI_Engine.file_extraction.metrics import character_error_rate, numeric_token_recall


DEFAULT_GOLD = Path(__file__).resolve().parent / "fixtures" / "file_extraction_gold_v1.json"


def _zip(files: dict[str, str]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _source(case: dict) -> SourceFile:
    kind = case["kind"]
    if kind == "text":
        return SourceFile(case["filename"], case.get("mime_type", ""), case["content"].encode())
    if kind == "pdf":
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 72), "Project dashboard achieved 50% completion.")
        content = document.tobytes()
        document.close()
        return SourceFile(case["filename"], "application/pdf", content)
    if kind == "docx":
        return SourceFile(case["filename"], "", _zip({
            "[Content_Types].xml": "<Types/>",
            "word/document.xml": """
              <w:document xmlns:w="urn:w"><w:body>
                <w:p><w:r><w:t>프로젝트 성과</w:t></w:r></w:p>
                <w:tbl><w:tr><w:tc><w:p><w:r><w:t>전환율</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:r><w:t>50%</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
              </w:body></w:document>
            """,
        }))
    if kind == "pptx":
        return SourceFile(case["filename"], "", _zip({
            "[Content_Types].xml": "<Types/>",
            "ppt/presentation.xml": "<p:presentation xmlns:p='urn:p' xmlns:r='urn:r'><p:sldIdLst><p:sldId r:id='r2'/><p:sldId r:id='r1'/></p:sldIdLst></p:presentation>",
            "ppt/_rels/presentation.xml.rels": "<Relationships><Relationship Id='r1' Target='slides/slide1.xml'/><Relationship Id='r2' Target='slides/slide2.xml'/></Relationships>",
            "ppt/slides/slide1.xml": "<p:sld xmlns:p='urn:p' xmlns:a='urn:a'><a:t>두 번째 슬라이드</a:t></p:sld>",
            "ppt/slides/slide2.xml": "<p:sld xmlns:p='urn:p' xmlns:a='urn:a'><a:t>첫 번째 슬라이드</a:t></p:sld>",
        }))
    if kind == "hwpx":
        return SourceFile(case["filename"], "", _zip({
            "Contents/content.hpf": "<package><manifest><item id='s0' href='section0.xml'/></manifest><spine><itemref idref='s0'/></spine></package>",
            "Contents/section0.xml": "<hs:section xmlns:hs='urn:hs' xmlns:hp='urn:hp'><hp:p><hp:run><hp:t>고객 문의 30% 감소</hp:t></hp:run></hp:p></hs:section>",
        }))
    if kind == "ocr":
        font_paths = (
            Path(r"C:\Windows\Fonts\malgun.ttf"),
            Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        )
        font_path = next((path for path in font_paths if path.is_file()), None)
        if font_path is None:
            raise RuntimeError("Korean OCR fixture font is unavailable")
        image = Image.new("RGB", (900, 180), "white")
        ImageDraw.Draw(image).text((30, 45), case["content"], fill="black", font=ImageFont.truetype(str(font_path), 56))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return SourceFile(case["filename"], "image/png", buffer.getvalue())
    raise ValueError(f"Unknown fixture kind: {kind}")


def evaluate(gold_path: Path) -> dict:
    fixture = json.loads(gold_path.read_text(encoding="utf-8"))
    capability = get_ocr_capability()
    rows: list[dict] = []
    for case in fixture["cases"]:
        if case["kind"] == "ocr" and (not capability.available or "kor" not in capability.languages):
            rows.append({"id": case["id"], "status": "skipped", "reason": capability.error or "kor language unavailable"})
            continue
        started = time.perf_counter()
        try:
            result = extract_file(_source(case))
            required = case["required_fragments"]
            expected_text = case["expected_text"]
            recall = sum(fragment in result.text for fragment in required) / len(required)
            rows.append({
                "id": case["id"],
                "status": "passed" if recall == 1 else "failed",
                "required_fragment_recall": recall,
                "numeric_token_recall": numeric_token_recall(expected_text, result.text),
                "character_error_rate": character_error_rate(expected_text, result.text),
                "quality_score": result.quality_score,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "warnings": list(result.warnings),
            })
        except Exception as error:
            rows.append({
                "id": case["id"],
                "status": "error",
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "reason": str(error),
            })
    measured = [row for row in rows if row["status"] != "skipped"]
    return {
        "fixture_version": fixture["version"],
        "capabilities": {
            "ocr": capability.payload(),
            "libreoffice": get_libreoffice_capability().payload(),
            "hwp_to_hwpx": get_hwpx_converter_capability().payload(),
            "media": get_media_capability().payload(),
        },
        "parser_success_rate": (
            sum(row["status"] == "passed" for row in measured) / len(measured)
            if measured else 0.0
        ),
        "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(args.gold)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
