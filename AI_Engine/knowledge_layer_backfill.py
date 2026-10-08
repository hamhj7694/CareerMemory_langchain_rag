"""Ontology seed와 기존 source_refs의 Evidence 백필. 기본은 dry-run이다."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from AI_Engine.database.connection import SessionLocal, initialize_database
from AI_Engine.database.models import Experience
from AI_Engine.evidence_repository import (
    EvidenceSyncReport,
    sync_experience_evidence,
    sync_source_refs,
)
from AI_Engine.ontology_repository import (
    OntologySeedReport,
    ontology_seed_checksum,
    seed_ontology,
)


@dataclass(frozen=True)
class KnowledgeBackfillReport:
    mode: str
    users_scanned: int
    experiences_scanned: int
    source_refs_scanned: int
    ontology_seed_checksum: str
    ontology: dict[str, Any]
    evidence: dict[str, Any]


def _sum_evidence_reports(reports: list[EvidenceSyncReport]) -> dict[str, Any]:
    keys = EvidenceSyncReport.__dataclass_fields__.keys()
    return {
        key: (
            any(getattr(report, key) for report in reports)
            if key == "would_write"
            else sum(int(getattr(report, key)) for report in reports)
        )
        for key in keys
    }


def backfill_knowledge_layers(
    database: Session,
    *,
    apply: bool = False,
) -> KnowledgeBackfillReport:
    ontology: OntologySeedReport = seed_ontology(database, dry_run=not apply)
    experiences = list(database.scalars(select(Experience).where(
        Experience.deleted_at.is_(None),
        Experience.status == "confirmed",
    )))
    sources_by_user: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    source_count = 0
    for experience in experiences:
        for source in experience.source_refs or []:
            if not isinstance(source, dict):
                continue
            source_count += 1
            source_id = str(source.get("id") or source.get("source_ref_id") or "")
            if not source_id:
                continue
            current = sources_by_user[experience.user_id].get(source_id)
            current_text = str((current or {}).get("text") or (current or {}).get("original_text") or "")
            candidate_text = str(source.get("text") or source.get("original_text") or "")
            if current is None or len(candidate_text) > len(current_text):
                sources_by_user[experience.user_id][source_id] = source

    if apply:
        evidence_reports = [
            sync_experience_evidence(database, experience)
            for experience in experiences
        ]
    else:
        # 문서·청크 예상치는 사용자별 source ID를 먼저 중복 제거해 계산한다.
        # 실제 apply에서는 경험별 link도 함께 생성한다.
        evidence_reports = [
            sync_source_refs(
                database,
                user_id,
                list(source_map.values()),
                dry_run=True,
            )
            for user_id, source_map in sources_by_user.items()
        ]
    if apply:
        database.commit()
    else:
        database.rollback()
    return KnowledgeBackfillReport(
        mode="apply" if apply else "dry-run",
        users_scanned=len(sources_by_user),
        experiences_scanned=len(experiences),
        source_refs_scanned=source_count,
        ontology_seed_checksum=ontology_seed_checksum(),
        ontology=asdict(ontology),
        evidence=_sum_evidence_reports(evidence_reports),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="검증된 ontology/Evidence projection을 실제 DB에 저장합니다.",
    )
    args = parser.parse_args()
    initialize_database(seed_ontology_data=args.apply)
    with SessionLocal() as database:
        report = backfill_knowledge_layers(database, apply=args.apply)
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
