"""모든 파일 진입점이 공유하는 원본 저장·작업 큐·파생 텍스트 서비스."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import socket
import unicodedata
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from AI_Engine.blob_store import (
    BlobStoreError,
    get_blob_store,
    read_attachment_bytes,
)
from AI_Engine.database.models import (
    Attachment,
    FileProcessingJob,
    TranscriptionSegment,
    utc_now,
)
from AI_Engine.file_extraction import (
    FileExtractionError,
    FileInputError,
    SourceFile,
    detect_and_validate_file,
    extract_file,
)
from AI_Engine.file_extraction.parsers import PARSER_VERSION


ACTIVE_JOB_STATUSES = frozenset({"queued", "processing"})
MEDIA_MIME_PREFIXES = ("audio/", "video/")


@dataclass(frozen=True)
class AttachmentIngestResult:
    attachment: Attachment
    job: FileProcessingJob | None
    reused: bool


def normalized_filename(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def media_kind_for_mime(mime_type: str) -> str:
    if mime_type.startswith("audio/"):
        return "audio"
    if mime_type.startswith("video/"):
        return "video"
    return "document"


def job_type_for_attachment(attachment: Attachment) -> str:
    if attachment.media_kind in {"audio", "video"}:
        return "transcribe"
    if attachment.mime_type in {
        "application/msword",
        "application/vnd.ms-powerpoint",
        "application/x-hwp",
    }:
        return "convert"
    return "parse"


class AttachmentService:
    def ingest(
        self,
        database: Session,
        *,
        user_id: str,
        filename: str,
        mime_type: str,
        content: bytes,
        original_attachment_id: str | None = None,
    ) -> AttachmentIngestResult:
        source = detect_and_validate_file(SourceFile(filename, mime_type, content))
        content_hash = hashlib.sha256(content).hexdigest()
        existing = database.scalar(select(Attachment).where(
            Attachment.user_id == user_id,
            Attachment.content_hash == content_hash,
        ))
        if existing is not None:
            return AttachmentIngestResult(existing, self.latest_job(database, existing.id), True)

        attachment_id = f"ATT-{uuid4()}"
        stored = get_blob_store().put(
            user_id=user_id,
            attachment_id=attachment_id,
            filename=source.filename,
            content=source.content,
            content_hash=content_hash,
        )
        attachment = Attachment(
            id=attachment_id,
            user_id=user_id,
            filename=source.filename,
            normalized_filename=normalized_filename(source.filename),
            mime_type=source.mime_type,
            size_bytes=stored.size_bytes,
            content_hash=stored.content_hash,
            content=b"",
            storage_backend=stored.backend,
            storage_key=stored.key,
            media_kind=media_kind_for_mime(source.mime_type),
            extracted_text="",
            parse_status="queued",
            parse_error=None,
            parser_version=PARSER_VERSION,
            extraction_metadata={"source_of_truth": "blob_store"},
            original_attachment_id=original_attachment_id,
        )
        database.add(attachment)
        database.flush()
        job = self.enqueue(database, attachment)
        try:
            database.commit()
        except Exception:
            database.rollback()
            get_blob_store().delete(stored.key)
            raise
        database.refresh(attachment)
        database.refresh(job)
        return AttachmentIngestResult(attachment, job, False)

    def enqueue(
        self,
        database: Session,
        attachment: Attachment,
        *,
        reset_attempts: bool = False,
    ) -> FileProcessingJob:
        active = database.scalar(
            select(FileProcessingJob)
            .where(
                FileProcessingJob.attachment_id == attachment.id,
                FileProcessingJob.status.in_(ACTIVE_JOB_STATUSES),
            )
            .order_by(FileProcessingJob.created_at.desc())
        )
        if active is not None:
            return active
        job = FileProcessingJob(
            id=f"FPJ-{uuid4()}",
            attachment_id=attachment.id,
            job_type=job_type_for_attachment(attachment),
            status="queued",
            attempt_count=0 if reset_attempts else 0,
            max_attempts=3,
            available_at=utc_now(),
            lease_until=None,
            worker_id=None,
            processor_version=PARSER_VERSION,
            payload={},
        )
        attachment.parse_status = "queued"
        attachment.parse_error = None
        database.add(job)
        return job

    def latest_job(self, database: Session, attachment_id: str) -> FileProcessingJob | None:
        return database.scalar(
            select(FileProcessingJob)
            .where(FileProcessingJob.attachment_id == attachment_id)
            .order_by(FileProcessingJob.created_at.desc())
        )

    def process_job(
        self,
        database: Session,
        job_id: str,
        *,
        worker_id: str | None = None,
    ) -> FileProcessingJob:
        job = database.get(FileProcessingJob, job_id)
        if job is None:
            raise FileInputError("파일 처리 작업을 찾을 수 없습니다.")
        attachment = database.get(Attachment, job.attachment_id)
        if attachment is None:
            job.status = "failed"
            job.error_code = "ATTACHMENT_MISSING"
            job.error_message = "처리할 첨부 원본을 찾을 수 없습니다."
            job.completed_at = utc_now()
            database.commit()
            return job
        if job.status == "completed":
            return job
        if job.status == "failed":
            return job
        if job.status != "processing" and job.attempt_count >= job.max_attempts:
            job.status = "failed"
            job.error_code = "MAX_ATTEMPTS_EXCEEDED"
            job.error_message = "파일 처리 최대 재시도 횟수를 초과했습니다."
            job.completed_at = utc_now()
            attachment.parse_status = "failed"
            attachment.parse_error = job.error_message
            database.commit()
            return job

        resolved_worker_id = worker_id or f"{socket.gethostname()}:{uuid4().hex[:8]}"
        if job.status == "processing":
            if job.worker_id and job.worker_id != resolved_worker_id:
                raise FileInputError("다른 worker가 이미 처리 중인 파일 작업입니다.")
            job.worker_id = resolved_worker_id
            job.lease_until = utc_now() + timedelta(minutes=5)
        else:
            job.status = "processing"
            job.attempt_count += 1
            job.worker_id = resolved_worker_id
            job.lease_until = utc_now() + timedelta(minutes=5)
            job.error_code = None
            job.error_message = None
        attachment.parse_status = "processing"
        attachment.parse_error = None
        database.commit()

        try:
            content = read_attachment_bytes(attachment)
            if hashlib.sha256(content).hexdigest() != attachment.content_hash:
                raise BlobStoreError("저장된 원본의 SHA-256 해시가 변경되었습니다.")
            extracted = extract_file(SourceFile(
                filename=attachment.filename,
                mime_type=attachment.mime_type,
                content=content,
            ))
            attachment.mime_type = extracted.mime_type
            attachment.extracted_text = extracted.text
            attachment.parse_status = "partial" if extracted.is_partial else "ready"
            attachment.parse_error = None
            attachment.parser_version = extracted.parser_version
            attachment.extraction_metadata = {
                **extracted.metadata_payload(),
                "source_of_truth": attachment.storage_backend,
                "processing_job_id": job.id,
            }
            duration_ms = extracted.metadata.get("duration_ms")
            attachment.duration_ms = int(duration_ms) if duration_ms is not None else None
            self._replace_transcription_segments(database, attachment, extracted)
            job.status = "completed"
            job.completed_at = utc_now()
        except FileInputError as error:
            attachment.extracted_text = ""
            attachment.parse_status = "unsupported"
            attachment.parse_error = str(error)
            attachment.extraction_metadata = self._failure_metadata(job, error)
            job.status = "failed"
            job.error_code = "UNSUPPORTED_FILE"
            job.error_message = str(error)
            job.completed_at = utc_now()
        except (FileExtractionError, BlobStoreError, ValueError, OSError) as error:
            attachment.extracted_text = ""
            attachment.parse_status = "failed"
            attachment.parse_error = str(error)
            attachment.extraction_metadata = self._failure_metadata(job, error)
            job.status = "failed"
            job.error_code = type(error).__name__.upper()
            job.error_message = str(error)
            job.completed_at = utc_now()
        finally:
            job.lease_until = None
            database.commit()
        return job

    def retry(self, database: Session, attachment: Attachment) -> FileProcessingJob:
        active = self.latest_job(database, attachment.id)
        if active is not None and active.status in ACTIVE_JOB_STATUSES:
            return active
        job = self.enqueue(database, attachment, reset_attempts=True)
        database.commit()
        database.refresh(job)
        return job

    def recover_stale_jobs(self, database: Session) -> int:
        now = utc_now()
        stale = list(database.scalars(select(FileProcessingJob).where(
            FileProcessingJob.status == "processing",
            FileProcessingJob.lease_until.is_not(None),
            FileProcessingJob.lease_until < now,
        )))
        for job in stale:
            job.worker_id = None
            job.lease_until = None
            attachment = database.get(Attachment, job.attachment_id)
            if job.attempt_count >= job.max_attempts:
                job.status = "failed"
                job.error_code = "MAX_ATTEMPTS_EXCEEDED"
                job.error_message = "중단된 파일 작업이 최대 재시도 횟수를 초과했습니다."
                job.completed_at = now
                if attachment is not None:
                    attachment.parse_status = "failed"
                    attachment.parse_error = job.error_message
            else:
                job.status = "queued"
                job.available_at = now
            if attachment is not None and job.status == "queued":
                attachment.parse_status = "queued"
                attachment.parse_error = "중단된 파일 처리 작업을 다시 대기열에 넣었습니다."
        if stale:
            database.commit()
        return len(stale)

    def next_queued_job(self, database: Session) -> FileProcessingJob | None:
        return database.scalar(
            select(FileProcessingJob)
            .where(
                FileProcessingJob.status == "queued",
                FileProcessingJob.available_at <= utc_now(),
                FileProcessingJob.attempt_count < FileProcessingJob.max_attempts,
            )
            .order_by(FileProcessingJob.created_at.asc())
        )

    def claim_next_queued_job(
        self,
        database: Session,
        *,
        worker_id: str,
        lease_minutes: int = 5,
    ) -> FileProcessingJob | None:
        """대기 작업 하나를 단일 UPDATE로 원자적으로 점유한다."""

        now = utc_now()
        candidate = (
            select(FileProcessingJob.id)
            .where(
                FileProcessingJob.status == "queued",
                FileProcessingJob.available_at <= now,
                FileProcessingJob.attempt_count < FileProcessingJob.max_attempts,
            )
            .order_by(FileProcessingJob.created_at.asc())
            .limit(1)
            .scalar_subquery()
        )
        claimed_id = database.scalar(
            update(FileProcessingJob)
            .where(
                FileProcessingJob.id == candidate,
                FileProcessingJob.status == "queued",
            )
            .values(
                status="processing",
                attempt_count=FileProcessingJob.attempt_count + 1,
                worker_id=worker_id,
                lease_until=now + timedelta(minutes=max(1, lease_minutes)),
                error_code=None,
                error_message=None,
            )
            .returning(FileProcessingJob.id)
        )
        if claimed_id is None:
            database.rollback()
            return None
        job = database.get(FileProcessingJob, claimed_id)
        if job is None:
            database.rollback()
            return None
        attachment = database.get(Attachment, job.attachment_id)
        if attachment is not None:
            attachment.parse_status = "processing"
            attachment.parse_error = None
        database.commit()
        database.refresh(job)
        return job

    def delete_blob(self, attachment: Attachment) -> None:
        if attachment.storage_backend == "local" and attachment.storage_key:
            get_blob_store().delete(attachment.storage_key)

    @staticmethod
    def _failure_metadata(job: FileProcessingJob, error: Exception) -> dict:
        return {
            "parser_name": "unresolved",
            "parser_version": PARSER_VERSION,
            "warnings": [str(error)],
            "processing_job_id": job.id,
        }

    @staticmethod
    def _replace_transcription_segments(
        database: Session,
        attachment: Attachment,
        extracted: object,
    ) -> None:
        segments = [
            segment
            for segment in getattr(extracted, "segments", ())
            if getattr(segment, "method", "") == "stt"
        ]
        if not segments:
            return
        database.execute(delete(TranscriptionSegment).where(
            TranscriptionSegment.attachment_id == attachment.id,
        ))
        metadata = getattr(extracted, "metadata", {})
        provider = str(metadata.get("provider") or "unknown")
        model = str(metadata.get("model") or "unknown")
        for sequence, segment in enumerate(segments, start=1):
            locator = segment.locator
            database.add(TranscriptionSegment(
                id=f"TSG-{uuid4()}",
                attachment_id=attachment.id,
                sequence=sequence,
                start_ms=int(locator.get("start_ms") or 0),
                end_ms=int(locator.get("end_ms") or 0),
                speaker=locator.get("speaker"),
                text=segment.text,
                confidence=segment.confidence,
                provider=provider,
                model=model,
            ))


attachment_service = AttachmentService()


__all__ = [
    "ACTIVE_JOB_STATUSES",
    "AttachmentIngestResult",
    "AttachmentService",
    "attachment_service",
    "job_type_for_attachment",
    "media_kind_for_mime",
    "normalized_filename",
]
