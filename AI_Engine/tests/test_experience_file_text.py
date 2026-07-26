"""경험 근거 파일 원문 추출 테스트."""

from __future__ import annotations

import unittest
from io import BytesIO
from unittest.mock import patch

import fitz
from PIL import Image

from AI_Engine.experience_file_text import extract_experience_file_texts
from AI_Engine.job_file_text import JobFile


class ExperienceFileTextTests(unittest.TestCase):
    def test_txt_files_remain_separate_evidence_sources(self) -> None:
        sources = extract_experience_file_texts([
            JobFile("project.txt", "text/plain", "프로젝트를 기획했습니다.".encode()),
            JobFile("result.txt", "text/plain", "처리 시간을 30% 줄였습니다.".encode()),
        ])

        self.assertEqual([source.filename for source in sources], [
            "project.txt",
            "result.txt",
        ])
        self.assertIn("30%", sources[1].text)

    def test_image_files_use_local_ocr_and_remain_separate(self) -> None:
        image_buffer = BytesIO()
        Image.new("RGB", (100, 100), "white").save(image_buffer, format="PNG")
        with patch(
            "AI_Engine.experience_file_text._ocr_image",
            side_effect=["서비스 운영 자동화", "처리 시간 30% 단축"],
        ) as ocr:
            sources = extract_experience_file_texts([
                JobFile("page-1.png", "image/png", image_buffer.getvalue()),
                JobFile("page-2.png", "image/png", image_buffer.getvalue()),
            ])

        self.assertEqual(len(sources), 2)
        self.assertIn("서비스 운영 자동화", sources[0].text)
        self.assertIn("30%", sources[1].text)
        self.assertEqual(ocr.call_count, 2)

    def test_text_pdf_is_extracted_without_ocr(self) -> None:
        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), "Project dashboard reduced reporting time.")
        pdf_bytes = document.tobytes()
        document.close()

        with patch("AI_Engine.experience_file_text._ocr_image") as ocr:
            sources = extract_experience_file_texts([
                JobFile("report.pdf", "application/pdf", pdf_bytes),
            ])

        self.assertIn("reduced reporting time", sources[0].text)
        ocr.assert_not_called()


if __name__ == "__main__":
    unittest.main()
