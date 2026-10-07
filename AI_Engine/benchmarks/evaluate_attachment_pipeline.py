"""LocalBlobStore와 재시작 가능한 파일 작업 큐를 격리 환경에서 측정한다."""

from __future__ import annotations

import argparse
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from AI_Engine.attachment_service import AttachmentService
from AI_Engine.blob_store import clear_blob_store_cache, get_blob_store
from AI_Engine.database import models  # noqa: F401
from AI_Engine.database.connection import Base
from AI_Engine.database.models import Attachment, FileProcessingJob, utc_now


def evaluate(*, file_count: int = 10) -> dict:
    with TemporaryDirectory(prefix="career-memory-attachment-benchmark-") as temporary:
        with patch.dict(os.environ, {"ATTACHMENT_STORAGE_ROOT": temporary}):
            clear_blob_store_cache()
            engine = create_engine(
                "sqlite://",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
            session_factory = sessionmaker(bind=engine, expire_on_commit=False)
            Base.metadata.create_all(bind=engine)
            service = AttachmentService()
            started = time.perf_counter()
            ingest_started = started
            attachment_ids: list[str] = []
            job_ids: list[str] = []
            expected_hashes: dict[str, str] = {}
            with session_factory() as database:
                for index in range(file_count):
                    content = (
                        f"파일 {index + 1}\n전환율 {40 + index}% 개선\n" * 128
                    ).encode()
                    result = service.ingest(
                        database,
                        user_id="BENCHMARK-USER",
                        filename=f"evidence-{index + 1}.txt",
                        mime_type="text/plain",
                        content=content,
                    )
                    attachment_ids.append(result.attachment.id)
                    job_ids.append(result.job.id)
                    expected_hashes[result.attachment.id] = hashlib.sha256(content).hexdigest()
                ingest_ms = (time.perf_counter() - ingest_started) * 1000

                parse_started = time.perf_counter()
                for job_id in job_ids:
                    service.process_job(database, job_id, worker_id="benchmark-worker")
                parse_ms = (time.perf_counter() - parse_started) * 1000

                stale_attachment = service.ingest(
                    database,
                    user_id="BENCHMARK-USER",
                    filename="stale-job.txt",
                    mime_type="text/plain",
                    content=b"restartable queue",
                )
                stale_attachment.job.status = "processing"
                stale_attachment.job.attempt_count = 1
                stale_attachment.job.lease_until = utc_now() - timedelta(seconds=1)
                database.commit()
                recovered = service.recover_stale_jobs(database)

                attachments = list(database.scalars(select(Attachment).where(
                    Attachment.id.in_(attachment_ids),
                )))
                jobs = list(database.scalars(select(FileProcessingJob).where(
                    FileProcessingJob.id.in_(job_ids),
                )))
                db_blob_bytes = database.scalar(select(
                    func.coalesce(func.sum(func.length(Attachment.content)), 0)
                ))
                hash_verified = all(
                    hashlib.sha256(get_blob_store().read(item.storage_key)).hexdigest()
                    == expected_hashes[item.id]
                    for item in attachments
                )
                total_ms = (time.perf_counter() - started) * 1000
                report = {
                    "fixture_version": "attachment-pipeline-v1",
                    "file_count": file_count,
                    "local_blob_count": sum(item.storage_backend == "local" for item in attachments),
                    "database_blob_bytes": int(db_blob_bytes or 0),
                    "hash_verified": hash_verified,
                    "completed_jobs": sum(job.status == "completed" for job in jobs),
                    "stale_jobs_recovered": recovered,
                    "recovered_job_status": stale_attachment.job.status,
                    "ingest_duration_ms": round(ingest_ms, 3),
                    "parse_duration_ms": round(parse_ms, 3),
                    "total_duration_ms": round(total_ms, 3),
                    "persistent_database_writes": 0,
                }
            Base.metadata.drop_all(bind=engine)
            engine.dispose()
            clear_blob_store_cache()
            return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file-count", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(file_count=max(1, args.file_count))
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
