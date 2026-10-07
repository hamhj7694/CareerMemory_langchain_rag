"""기존 Attachment DB BLOB을 LocalBlobStore로 안전하게 옮기는 도구.

기본 실행은 dry-run이다. ``--apply``를 지정한 경우에만 파일 저장과 DB 갱신을
수행하며, SHA-256 검증이 끝난 레코드만 DB BLOB을 비운다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass

from sqlalchemy import select

from AI_Engine.blob_store import BlobStoreError, get_blob_store
from AI_Engine.database.connection import SessionLocal, initialize_database
from AI_Engine.database.models import Attachment


@dataclass
class MigrationReport:
    mode: str
    examined: int = 0
    eligible: int = 0
    migrated: int = 0
    already_local: int = 0
    empty_legacy_blob: int = 0
    invalid_hash: int = 0
    errors: int = 0
    eligible_bytes: int = 0


def migrate_attachment_blobs(*, apply: bool = False) -> MigrationReport:
    """기존 DB 원본을 검사하고 선택적으로 로컬 blob 저장소로 이관한다."""

    report = MigrationReport(mode="apply" if apply else "dry-run")
    store = get_blob_store()
    with SessionLocal() as database:
        attachments = list(database.scalars(
            select(Attachment).order_by(Attachment.created_at.asc())
        ))
        for attachment in attachments:
            report.examined += 1
            if attachment.storage_backend == "local" and attachment.storage_key:
                report.already_local += 1
                continue

            content = bytes(attachment.content or b"")
            if not content:
                report.empty_legacy_blob += 1
                continue

            actual_hash = hashlib.sha256(content).hexdigest()
            if actual_hash != attachment.content_hash:
                report.invalid_hash += 1
                continue

            report.eligible += 1
            report.eligible_bytes += len(content)
            if not apply:
                continue

            stored_key: str | None = None
            try:
                stored = store.put(
                    user_id=attachment.user_id,
                    attachment_id=attachment.id,
                    filename=attachment.filename,
                    content=content,
                    content_hash=attachment.content_hash,
                )
                stored_key = stored.key
                if hashlib.sha256(store.read(stored.key)).hexdigest() != actual_hash:
                    raise BlobStoreError("이관된 원본의 SHA-256 검증에 실패했습니다.")

                attachment.storage_backend = stored.backend
                attachment.storage_key = stored.key
                attachment.content = b""
                database.commit()
                report.migrated += 1
            except (BlobStoreError, OSError, ValueError):
                database.rollback()
                report.errors += 1
                if stored_key:
                    try:
                        store.delete(stored_key)
                    except BlobStoreError:
                        pass
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Attachment DB BLOB을 LocalBlobStore로 이관합니다.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="검증된 원본을 실제로 이관합니다. 생략하면 dry-run만 수행합니다.",
    )
    args = parser.parse_args()
    initialize_database()
    report = migrate_attachment_blobs(apply=args.apply)
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 1 if report.errors or report.invalid_hash else 0


if __name__ == "__main__":
    raise SystemExit(main())
