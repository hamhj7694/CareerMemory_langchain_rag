"""채용공고 파일 텍스트 추출 테스트."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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

    def test_more_than_five_files_are_rejected(self) -> None:
        with self.assertRaises(JobFileInputError):
            extract_job_file_text([
                JobFile(f"{index}.txt", "text/plain", b"job")
                for index in range(6)
            ])

    def test_image_is_sent_to_gemini_and_text_is_returned(self) -> None:
        model_api = MagicMock()
        model_api.generate_content.return_value = SimpleNamespace(
            text="주요 업무\n서비스 개선"
        )
        client = SimpleNamespace(models=model_api)

        with (
            patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
            patch("AI_Engine.job_file_text.genai.Client", return_value=client),
        ):
            text = extract_job_file_text([
                JobFile("capture.png", "image/png", b"fake-image-bytes"),
            ])

        self.assertIn("서비스 개선", text)
        call = model_api.generate_content.call_args.kwargs
        self.assertTrue(call["model"])
        self.assertGreaterEqual(len(call["contents"]), 3)


if __name__ == "__main__":
    unittest.main()
