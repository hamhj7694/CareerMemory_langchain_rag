"""LocalBlobStore, 영속 작업 큐, STT 근거 구간의 회귀 테스트."""

from __future__ import annotations

from datetime import timedelta
import hashlib
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from AI_Engine.attachment_service import AttachmentService
from AI_Engine.blob_store import clear_blob_store_cache, get_blob_store
from AI_Engine.database import models  # noqa: F401
from AI_Engine.database.connection import Base
from AI_Engine.database.models import (
    Attachment,
    FileProcessingJob,
    TranscriptionSegment,
    utc_now,
)
from AI_Engine.file_extraction.models import (
    ExtractionSegment,
    FileExtractionResult,
)
from AI_Engine.migrate_attachment_blobs import migrate_attachment_blobs


class AttachmentPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {"ATTACHMENT_STORAGE_ROOT": self.temporary.name},
        )
        self.environment.start()
        clear_blob_store_cache()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )
        Base.metadata.create_all(bind=self.engine)
        self.service = AttachmentService()

    def tearDown(self) -> None:
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()
        clear_blob_store_cache()
        self.environment.stop()
        self.temporary.cleanup()

    def test_ingest_preserves_original_outside_database_and_completes_job(self) -> None:
        content = "성과 50% 개선".encode()
        with self.session_factory() as database:
            ingested = self.service.ingest(
                database,
                user_id="USER-1",
                filename="career.txt",
                mime_type="text/plain",
                content=content,
            )

            self.assertEqual(ingested.attachment.content, b"")
            self.assertEqual(ingested.attachment.storage_backend, "local")
            self.assertTrue(get_blob_store().exists(ingested.attachment.storage_key))
            self.assertEqual(ingested.job.status, "queued")

            self.service.process_job(database, ingested.job.id, worker_id="test-worker")
            database.refresh(ingested.attachment)
            database.refresh(ingested.job)

            self.assertEqual(ingested.attachment.parse_status, "ready")
            self.assertIn("50%", ingested.attachment.extracted_text)
            self.assertEqual(ingested.job.status, "completed")
            self.assertEqual(ingested.job.attempt_count, 1)

    def test_stale_job_is_requeued_but_exhausted_job_is_failed(self) -> None:
        with self.session_factory() as database:
            first = self.service.ingest(
                database,
                user_id="USER-1",
                filename="first.txt",
                mime_type="text/plain",
                content=b"first",
            )
            second = self.service.ingest(
                database,
                user_id="USER-1",
                filename="second.txt",
                mime_type="text/plain",
                content=b"second",
            )
            for job in (first.job, second.job):
                job.status = "processing"
                job.lease_until = utc_now() - timedelta(minutes=1)
            first.job.attempt_count = 1
            second.job.attempt_count = second.job.max_attempts
            database.commit()

            recovered = self.service.recover_stale_jobs(database)
            database.refresh(first.job)
            database.refresh(second.job)

            self.assertEqual(recovered, 2)
            self.assertEqual(first.job.status, "queued")
            self.assertEqual(second.job.status, "failed")
            self.assertEqual(second.job.error_code, "MAX_ATTEMPTS_EXCEEDED")

    def test_worker_claim_is_atomic_and_does_not_double_increment_attempt(self) -> None:
        with self.session_factory() as database:
            ingested = self.service.ingest(
                database,
                user_id="USER-1",
                filename="atomic.txt",
                mime_type="text/plain",
                content=b"atomic claim",
            )

            claimed = self.service.claim_next_queued_job(
                database,
                worker_id="worker-1",
            )
            duplicate = self.service.claim_next_queued_job(
                database,
                worker_id="worker-2",
            )

            self.assertEqual(claimed.id, ingested.job.id)
            self.assertEqual(claimed.status, "processing")
            self.assertEqual(claimed.attempt_count, 1)
            self.assertIsNone(duplicate)

            completed = self.service.process_job(
                database,
                claimed.id,
                worker_id="worker-1",
            )
            self.assertEqual(completed.status, "completed")
            self.assertEqual(completed.attempt_count, 1)

    def test_stt_segments_are_persisted_with_timestamps(self) -> None:
        extracted = FileExtractionResult(
            filename="meeting.wav",
            mime_type="audio/wav",
            text="성과를 50% 개선했습니다.",
            segments=(ExtractionSegment(
                text="성과를 50% 개선했습니다.",
                locator={"start_ms": 1200, "end_ms": 3500},
                method="stt",
                confidence=0.93,
            ),),
            extraction_method="stt",
            quality_score=None,
            warnings=(),
            parser_name="openai-stt",
            parser_version="test-v1",
            metadata={
                "provider": "openai",
                "model": "whisper-1",
                "duration_ms": 4000,
            },
        )
        with self.session_factory() as database:
            ingested = self.service.ingest(
                database,
                user_id="USER-1",
                filename="meeting.wav",
                mime_type="audio/wav",
                content=b"RIFF0000WAVEfmt ",
            )
            with patch("AI_Engine.attachment_service.extract_file", return_value=extracted):
                self.service.process_job(database, ingested.job.id)

            segment = database.scalar(select(TranscriptionSegment).where(
                TranscriptionSegment.attachment_id == ingested.attachment.id,
            ))
            self.assertIsNotNone(segment)
            self.assertEqual(segment.start_ms, 1200)
            self.assertEqual(segment.end_ms, 3500)
            self.assertEqual(segment.model, "whisper-1")
            self.assertEqual(ingested.attachment.duration_ms, 4000)

    def test_blob_migration_is_dry_run_by_default_and_hash_verified_on_apply(self) -> None:
        content = b"legacy original"
        with self.session_factory() as database:
            database.add(Attachment(
                id="ATT-LEGACY",
                user_id="USER-1",
                filename="legacy.txt",
                normalized_filename="legacy.txt",
                mime_type="text/plain",
                size_bytes=len(content),
                content_hash=hashlib.sha256(content).hexdigest(),
                content=content,
                storage_backend="database",
                storage_key=None,
                extracted_text="legacy original",
                parse_status="ready",
                parser_version="legacy-v1",
                extraction_metadata={},
            ))
            database.commit()

        with patch(
            "AI_Engine.migrate_attachment_blobs.SessionLocal",
            self.session_factory,
        ):
            dry_run = migrate_attachment_blobs()
            applied = migrate_attachment_blobs(apply=True)

        self.assertEqual(dry_run.eligible, 1)
        self.assertEqual(dry_run.migrated, 0)
        self.assertEqual(applied.migrated, 1)
        with self.session_factory() as database:
            attachment = database.get(Attachment, "ATT-LEGACY")
            self.assertEqual(attachment.storage_backend, "local")
            self.assertEqual(attachment.content, b"")
            stored = get_blob_store().read(attachment.storage_key)
            self.assertEqual(stored, content)


if __name__ == "__main__":
    unittest.main()
