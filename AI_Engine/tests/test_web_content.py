"""공개 URL 수집·HTML 추출·Attachment 연결의 안전 경계를 검증한다."""

from __future__ import annotations

from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from AI_Engine.blob_store import clear_blob_store_cache
from AI_Engine.database.connection import Base
from AI_Engine.database.models import Attachment
from AI_Engine.html_extraction import extract_html
from AI_Engine.web_content import (
    WebContentError,
    WebContentService,
    WebFetchResult,
    extract_http_urls,
    validate_public_url,
)


class HtmlExtractionTests(unittest.TestCase):
    def test_visible_text_metadata_and_image_candidates_are_preserved(self) -> None:
        result = extract_html(b"""
            <html><head>
              <title>Backend Engineer</title>
              <meta charset="utf-8">
              <meta name="description" content="FastAPI platform role">
              <script type="application/ld+json">
                {"hiringOrganization": {"name": "Career Memory"}}
              </script>
            </head><body>
              <nav>menu</nav>
              <main><h1>Backend Engineer</h1><p>Build APIs with FastAPI.</p>
              <img src="/poster.png" alt="Recruiting poster"></main>
              <script>alert('ignored')</script>
              <div hidden>secret</div>
            </body></html>
        """)

        self.assertEqual(result.title, "Backend Engineer")
        self.assertIn("Build APIs with FastAPI.", result.text)
        self.assertIn("Career Memory", result.text)
        self.assertNotIn("alert", result.text)
        self.assertNotIn("secret", result.text)
        self.assertEqual(result.image_sources, ("/poster.png",))


class PublicUrlSafetyTests(unittest.TestCase):
    def test_extract_urls_trims_chat_punctuation_and_deduplicates(self) -> None:
        urls = extract_http_urls(
            "확인해 줘: https://example.com/jobs/1). 그리고 https://example.com/jobs/1",
        )
        self.assertEqual(urls, ["https://example.com/jobs/1"])

    def test_private_and_nonstandard_port_urls_are_rejected(self) -> None:
        with self.assertRaises(WebContentError):
            validate_public_url("http://127.0.0.1/private")
        with self.assertRaises(WebContentError):
            validate_public_url("https://example.com:8443/private")

    def test_all_dns_results_must_be_public(self) -> None:
        def mixed_resolver(*_args, **_kwargs):
            return [
                (2, 1, 6, "", ("93.184.216.34", 443)),
                (2, 1, 6, "", ("10.0.0.10", 443)),
            ]

        with self.assertRaises(WebContentError):
            validate_public_url(
                "https://example.com/jobs",
                resolver=mixed_resolver,
            )


class WebContentAttachmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = TemporaryDirectory()
        self.environment = patch.dict(
            "os.environ",
            {"ATTACHMENT_STORAGE_ROOT": self.storage.name},
        )
        self.environment.start()
        clear_blob_store_cache()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def tearDown(self) -> None:
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()
        clear_blob_store_cache()
        self.environment.stop()
        self.storage.cleanup()

    def test_html_snapshot_uses_existing_attachment_pipeline(self) -> None:
        content = (
            "<html><head><title>공개 채용공고</title></head><body>"
            "<main><h1>백엔드 개발자</h1><p>FastAPI 서비스 운영 경험이 필요합니다.</p>"
            f"<p>{'공개 공고 본문 ' * 80}</p></main></body></html>"
        ).encode()
        fetched = WebFetchResult(
            requested_url="https://example.com/jobs/1",
            final_url="https://example.com/jobs/1",
            filename="공개 채용공고.html",
            mime_type="text/html",
            content=content,
            status_code=200,
            title="공개 채용공고",
        )
        service = WebContentService(fetcher=lambda _url: fetched)

        with self.session_factory() as database:
            result = service.ingest(
                database,
                user_id="test-user",
                texts=("https://example.com/jobs/1",),
            )
            self.assertEqual(len(result.attachment_ids), 1)
            attachment = database.get(Attachment, result.attachment_ids[0])
            self.assertIsNotNone(attachment)
            self.assertEqual(attachment.parse_status, "ready")
            self.assertIn("FastAPI 서비스 운영 경험", attachment.extracted_text)
            self.assertEqual(attachment.extraction_metadata["source_type"], "web_url")
            self.assertEqual(
                attachment.extraction_metadata["web_sources"][0]["final_url"],
                "https://example.com/jobs/1",
            )


if __name__ == "__main__":
    unittest.main()
