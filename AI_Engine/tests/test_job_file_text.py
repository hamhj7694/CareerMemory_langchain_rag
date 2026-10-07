"""채용공고 파일 텍스트 추출 테스트."""

from __future__ import annotations

import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image

from AI_Engine.file_extraction.ocr import OCRResult
from AI_Engine.job_file_text import (
    JobFile,
    JobFileInputError,
    extract_job_file_text,
)


class JobFileTextTests(unittest.TestCase):
    def test_utf8_and_cp949_text_files_are_decoded(self) -> None:
        text = extract_job_file_text([
            JobFile("공고1.txt", "text/plain", "주요 업무\n서비스 기획".encode()),
            JobFile("공고2.txt", "text/plain", "우대 사항\n데이터 분석".encode("cp949")),
        ])

        self.assertIn("서비스 기획", text)
        self.assertIn("데이터 분석", text)
        self.assertIn("[파일: 공고1.txt]", text)

    def test_unsupported_file_type_is_rejected(self) -> None:
        with self.assertRaises(JobFileInputError):
            extract_job_file_text([
                JobFile("공고.zip", "application/zip", b"not-a-job"),
            ])

    def test_more_than_ten_files_are_rejected(self) -> None:
        with self.assertRaises(JobFileInputError):
            extract_job_file_text([
                JobFile(f"{index}.txt", "text/plain", b"job")
                for index in range(11)
            ])

    def test_image_uses_shared_local_extractor(self) -> None:
        image_buffer = BytesIO()
        Image.new("RGB", (100, 100), "white").save(image_buffer, format="PNG")
        with patch(
            "AI_Engine.file_extraction.parsers.run_ocr",
            return_value=OCRResult("주요 업무\n서비스 개선", 0.9, "--psm 6", ()),
        ) as extractor:
            text = extract_job_file_text([
                JobFile("capture.png", "image/png", image_buffer.getvalue()),
            ])

        self.assertIn("서비스 개선", text)
        extractor.assert_called_once()


if __name__ == "__main__":
    unittest.main()
