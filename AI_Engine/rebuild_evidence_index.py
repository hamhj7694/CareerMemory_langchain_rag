"""DB EvidenceChunk에서 사용자별 Chroma 인덱스를 전체 재구축한다."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json

from sqlalchemy import select

from AI_Engine.chat_retrieval import EVIDENCE_VECTOR_ROOT
from AI_Engine.database.connection import SessionLocal, initialize_database
from AI_Engine.database.models import EvidenceDocument
from AI_Engine.evidence_index import (
    build_persisted_evidence_documents,
    sync_evidence_index,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", help="특정 사용자만 재구축합니다.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="실제 벡터 삭제·재생성을 수행합니다. 기본은 dry-run입니다.",
    )
    args = parser.parse_args()
    # dry-run에서는 누락된 테이블 생성 외에 ontology seed나 vector를 쓰지 않는다.
    initialize_database(seed_ontology_data=args.apply)
    with SessionLocal() as database:
        if args.user_id:
            user_ids = [args.user_id]
        else:
            user_ids = list(database.scalars(
                select(EvidenceDocument.user_id).distinct()
            ))
        reports = []
        for user_id in user_ids:
            if not args.apply:
                reports.append({
                    "user_id": user_id,
                    "mode": "dry-run",
                    "desired": len(build_persisted_evidence_documents(database, user_id)),
                })
                continue
            _store, report = sync_evidence_index(
                database,
                user_id,
                persist_directory=EVIDENCE_VECTOR_ROOT,
                rebuild=True,
            )
            reports.append({"user_id": user_id, "mode": "apply", **asdict(report)})
        if args.apply:
            database.commit()
        else:
            database.rollback()
    print(json.dumps({"users": reports}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
