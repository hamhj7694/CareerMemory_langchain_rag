"""통합 파일 감지·문서 파서·품질 KPI 테스트."""

from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image, ImageDraw, ImageFont

from AI_Engine.file_extraction import FileInputError, SourceFile, extract_file
from AI_Engine.file_extraction.media import MediaCapability, _transcribe, parse_media
from AI_Engine.file_extraction.models import ExtractionSegment
from AI_Engine.file_extraction.metrics import (
    character_error_rate,
    numeric_token_recall,
    word_error_rate,
)
from AI_Engine.file_extraction.ocr import get_ocr_capability, run_ocr


def zip_bytes(files: dict[str, str | bytes]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


class FileExtractionTests(unittest.TestCase):
    def test_markdown_preserves_headings_and_numeric_text(self) -> None:
        result = extract_file(SourceFile(
            "성과.md",
            "",
            "# 결제 개선\n- 완료율 49% → 50%".encode(),
        ))

        self.assertEqual(result.mime_type, "text/markdown")
        self.assertIn("49%", result.text)
        self.assertEqual(result.parser_name, "markdown")

    def test_docx_parses_paragraphs_and_table_cells_in_document_order(self) -> None:
        content = zip_bytes({
            "[Content_Types].xml": "<Types/>",
            "word/document.xml": """
                <w:document xmlns:w="urn:w"><w:body>
                  <w:p><w:r><w:t>프로젝트 성과</w:t></w:r></w:p>
                  <w:tbl><w:tr>
                    <w:tc><w:p><w:r><w:t>전환율</w:t></w:r></w:p></w:tc>
                    <w:tc><w:p><w:r><w:t>50%</w:t></w:r></w:p></w:tc>
                  </w:tr></w:tbl>
                </w:body></w:document>
            """,
        })

        result = extract_file(SourceFile("resume.docx", "", content))

        self.assertIn("프로젝트 성과", result.text)
        self.assertIn("전환율 | 50%", result.text)
        self.assertEqual(result.segments[1].locator["block_type"], "table")

    def test_pptx_uses_presentation_relationship_order(self) -> None:
        content = zip_bytes({
            "[Content_Types].xml": "<Types/>",
            "ppt/presentation.xml": """
              <p:presentation xmlns:p="urn:p" xmlns:r="urn:r">
                <p:sldIdLst><p:sldId r:id="rId2"/><p:sldId r:id="rId1"/></p:sldIdLst>
              </p:presentation>
            """,
            "ppt/_rels/presentation.xml.rels": """
              <Relationships>
                <Relationship Id="rId1" Target="slides/slide1.xml"/>
                <Relationship Id="rId2" Target="slides/slide2.xml"/>
              </Relationships>
            """,
            "ppt/slides/slide1.xml": "<p:sld xmlns:p='urn:p' xmlns:a='urn:a'><a:t>두 번째</a:t></p:sld>",
            "ppt/slides/slide2.xml": "<p:sld xmlns:p='urn:p' xmlns:a='urn:a'><a:t>첫 번째</a:t></p:sld>",
        })

        result = extract_file(SourceFile("portfolio.pptx", "application/zip", content))

        self.assertLess(result.text.index("첫 번째"), result.text.index("두 번째"))
        self.assertEqual(result.metadata["slide_count"], 2)

    def test_hwpx_parses_section_paragraphs(self) -> None:
        content = zip_bytes({
            "Contents/content.hpf": """
              <package><manifest><item id="s0" href="section0.xml"/></manifest>
              <spine><itemref idref="s0"/></spine></package>
            """,
            "Contents/section0.xml": """
              <hs:section xmlns:hs="urn:hs" xmlns:hp="urn:hp">
                <hp:p><hp:run><hp:t>고객 문의 30% 감소</hp:t></hp:run></hp:p>
              </hs:section>
            """,
        })

        result = extract_file(SourceFile("career.hwpx", "", content))

        self.assertIn("고객 문의 30% 감소", result.text)
        self.assertEqual(result.segments[0].locator["section"], 1)

    def test_legacy_doc_is_converted_in_isolated_adapter_then_parsed(self) -> None:
        converted = SourceFile(
            "legacy.docx",
            "",
            zip_bytes({
                "[Content_Types].xml": "<Types/>",
                "word/document.xml": """
                    <w:document xmlns:w="urn:w"><w:body>
                      <w:p><w:r><w:t>레거시 문서 성과 50%</w:t></w:r></w:p>
                    </w:body></w:document>
                """,
            }),
        )
        ole_header = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"legacy-doc"
        with patch(
            "AI_Engine.file_extraction.parsers.convert_legacy_document",
            return_value=converted,
        ) as converter:
            result = extract_file(SourceFile("legacy.doc", "application/msword", ole_header))

        converter.assert_called_once()
        self.assertEqual(result.extraction_method, "converted")
        self.assertIn("성과 50%", result.text)

    def test_media_pipeline_normalizes_audio_and_preserves_timestamps(self) -> None:
        capability = MediaCapability(
            ffmpeg="ffmpeg",
            ffprobe="ffprobe",
            stt_provider="openai",
            stt_model="whisper-1",
            api_key_configured=True,
        )
        segments = (ExtractionSegment(
            text="전환율 50% 개선",
            locator={"start_ms": 1000, "end_ms": 2400},
            method="stt",
        ),)

        def make_audio(_command, _input_path, output_path):
            output_path.write_bytes(b"normalized-audio")

        with (
            patch("AI_Engine.file_extraction.media.get_media_capability", return_value=capability),
            patch(
                "AI_Engine.file_extraction.media._probe",
                return_value={
                    "format": {"duration": "2.5"},
                    "streams": [{"codec_type": "audio", "codec_name": "pcm_s16le"}],
                },
            ),
            patch("AI_Engine.file_extraction.media._normalise_audio", side_effect=make_audio),
            patch(
                "AI_Engine.file_extraction.media._transcribe",
                return_value=(
                    "전환율 50% 개선",
                    segments,
                    {"provider": "openai", "model": "whisper-1", "language": "ko"},
                ),
            ),
        ):
            result = parse_media(
                SourceFile("meeting.wav", "audio/wav", b"RIFF0000WAVEfmt "),
                parser_version="test-v1",
            )

        self.assertEqual(result.extraction_method, "stt")
        self.assertEqual(result.metadata["duration_ms"], 2500)
        self.assertEqual(result.segments[0].locator["start_ms"], 1000)

    def test_openai_verbose_transcription_maps_segment_timestamps(self) -> None:
        response = SimpleNamespace(
            text="고객 문의 30% 감소",
            language="ko",
            duration=3.0,
            segments=[SimpleNamespace(
                text="고객 문의 30% 감소",
                start=0.4,
                end=2.8,
            )],
        )
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
            patch("AI_Engine.file_extraction.media.OpenAI") as openai_client,
        ):
            openai_client.return_value.audio.transcriptions.create.return_value = response
            text, segments, metadata = _transcribe(BytesIO(b"audio"), "audio.mp3")

        self.assertEqual(text, "고객 문의 30% 감소")
        self.assertEqual(segments[0].locator, {"start_ms": 400, "end_ms": 2800})
        self.assertEqual(metadata["model"], "whisper-1")

    def test_extension_and_binary_signature_mismatch_is_rejected(self) -> None:
        image = BytesIO()
        Image.new("RGB", (20, 20), "white").save(image, format="PNG")

        with self.assertRaises(FileInputError):
            extract_file(SourceFile("fake.pdf", "application/pdf", image.getvalue()))

    def test_quality_metrics_protect_numeric_tokens(self) -> None:
        expected = "처리 시간을 3시간에서 1시간으로 줄여 전환율 50%를 달성했습니다."
        actual = "처리 시간을 3시간에서 1시간으로 줄여 전환율 49%를 달성했습니다."

        self.assertGreater(character_error_rate(expected, actual), 0)
        self.assertGreater(word_error_rate(expected, actual), 0)
        self.assertEqual(numeric_token_recall(expected, actual), 2 / 3)

    def test_real_ocr_smoke_when_runtime_is_available(self) -> None:
        capability = get_ocr_capability()
        if not capability.available or "kor" not in capability.languages:
            self.skipTest(capability.error or "kor OCR language is unavailable")
        font_paths = (
            r"C:\Windows\Fonts\malgun.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        )
        try:
            font_path = next(path for path in font_paths if Path(path).is_file())
            font = ImageFont.truetype(font_path, 52)
        except (OSError, StopIteration):
            self.skipTest("Korean OCR smoke test font is unavailable")
        image = Image.new("RGB", (720, 160), "white")
        ImageDraw.Draw(image).text((30, 45), "경력 성과 50%", fill="black", font=font)

        result = run_ocr(image)

        self.assertIn("50", result.text)
        self.assertIn("성과", result.text)


if __name__ == "__main__":
    unittest.main()
