"""DB에 남은 파일 처리 작업을 재시작 가능한 방식으로 실행한다."""

from __future__ import annotations

import argparse
import socket
import time
from uuid import uuid4

from AI_Engine.attachment_service import attachment_service
from AI_Engine.database.connection import SessionLocal, initialize_database


def process_available_jobs(*, once: bool = False, poll_seconds: float = 2.0) -> int:
    processed = 0
    worker_id = f"{socket.gethostname()}:{uuid4().hex[:8]}"
    while True:
        with SessionLocal() as database:
            attachment_service.recover_stale_jobs(database)
            job = attachment_service.claim_next_queued_job(
                database,
                worker_id=worker_id,
            )
            if job is not None:
                attachment_service.process_job(
                    database,
                    job.id,
                    worker_id=worker_id,
                )
                processed += 1
        if once:
            return processed
        if job is None:
            time.sleep(max(0.2, poll_seconds))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    initialize_database()
    count = process_available_jobs(
        once=args.once,
        poll_seconds=args.poll_seconds,
    )
    if args.once:
        print(f"processed_jobs={count}")


if __name__ == "__main__":
    main()
