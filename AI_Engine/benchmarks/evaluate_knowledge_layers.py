"""온톨로지·Evidence lineage·증분 인덱스의 결정론적 품질 평가."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from AI_Engine.database.connection import Base
from AI_Engine.database.models import (
    EvidenceChunk,
    EvidenceDocument,
    Experience,
    ExperienceDomain,
    ExperienceProject,
    OntologyConcept,
    User,
)
from AI_Engine.evidence_index import sync_evidence_index
from AI_Engine.evidence_repository import find_citation_lineage, sync_source_refs
from AI_Engine.ontology_repository import OntologyRepository, seed_ontology


FIXTURE = Path(__file__).parent / "fixtures" / "knowledge_layers_gold_v1.json"


class MemoryVectorStore:
    def __init__(self) -> None:
        self.documents = {}
        self.embedding_writes = 0
        self.deletes = 0

    def get(self, *, include):
        del include
        ids = list(self.documents)
        return {
            "ids": ids,
            "metadatas": [self.documents[item].metadata for item in ids],
        }

    def add_documents(self, *, ids, documents):
        self.embedding_writes += len(ids)
        self.documents.update(zip(ids, documents, strict=True))

    def update_documents(self, *, ids, documents):
        self.embedding_writes += len(ids)
        self.documents.update(zip(ids, documents, strict=True))

    def delete(self, *, ids):
        self.deletes += len(ids)
        for item in ids:
            self.documents.pop(item, None)


def _seed_owner(database) -> None:
    database.add(User(
        id="benchmark-user",
        email="benchmark@example.com",
        display_name="Benchmark",
        password_hash="not-used",
    ))
    database.add(ExperienceDomain(
        id="benchmark-domain",
        user_id="benchmark-user",
        name="개발",
    ))
    database.add(ExperienceProject(
        id="benchmark-project",
        user_id="benchmark-user",
        domain_id="benchmark-domain",
        name="API 개선",
    ))
    database.add(Experience(
        id="benchmark-experience",
        user_id="benchmark-user",
        project_id="benchmark-project",
        title="응답 시간 개선",
        status="confirmed",
    ))
    database.commit()


def evaluate() -> dict:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as database:
        _seed_owner(database)
    try:
        with Session() as database:
            before = {
                "concepts": database.scalar(
                    select(func.count()).select_from(OntologyConcept)
                ),
                "documents": database.scalar(
                    select(func.count()).select_from(EvidenceDocument)
                ),
            }
            ontology_dry_run = seed_ontology(database, dry_run=True)
            database.rollback()
            after_dry_run = {
                "concepts": database.scalar(
                    select(func.count()).select_from(OntologyConcept)
                ),
                "documents": database.scalar(
                    select(func.count()).select_from(EvidenceDocument)
                ),
            }
            seed_ontology(database)
            database.commit()

        repository = OntologyRepository(Session, fallback_enabled=False)
        concept_results = [
            repository.resolve(case["raw_name"])
            for case in fixture["concept_cases"]
        ]
        concept_correct = sum(
            result.concept_id == expected["concept_id"]
            and result.match_type == expected["match_type"]
            for result, expected in zip(
                concept_results, fixture["concept_cases"], strict=True
            )
        )
        unresolved = [
            result for result, expected in zip(
                concept_results, fixture["concept_cases"], strict=True
            )
            if expected["concept_id"] is None
        ]
        relation_results = [
            repository.relationship(case["source_id"], case["target_id"])
            for case in fixture["relation_cases"]
        ]
        relation_correct = sum(
            result.relationship == expected["relationship"]
            and result.satisfies_requirement == expected["satisfies"]
            for result, expected in zip(
                relation_results, fixture["relation_cases"], strict=True
            )
        )

        evidence = fixture["evidence"]
        source = {
            "id": evidence["source_ref_id"],
            "source_type": "manual_text",
            "manual_input_id": "benchmark-manual",
            "text": evidence["text"],
        }
        vector_store = MemoryVectorStore()
        with Session() as database:
            evidence_dry_run = sync_source_refs(
                database,
                "benchmark-user",
                [source],
                dry_run=True,
                experience_id="benchmark-experience",
            )
            database.rollback()
            dry_run_evidence_count = database.scalar(
                select(func.count()).select_from(EvidenceDocument)
            )
            sync_source_refs(
                database,
                "benchmark-user",
                [source],
                experience_id="benchmark-experience",
            )
            database.flush()
            valid_lineage = find_citation_lineage(
                database,
                "benchmark-user",
                evidence["source_ref_id"],
                evidence["valid_quote"],
            )
            invalid_lineage = find_citation_lineage(
                database,
                "benchmark-user",
                evidence["source_ref_id"],
                evidence["invalid_quote"],
            )
            _store, first_index = sync_evidence_index(
                database,
                "benchmark-user",
                persist_directory=Path("unused"),
                vector_db=vector_store,
            )
            writes_after_first = vector_store.embedding_writes
            _store, repeated_index = sync_evidence_index(
                database,
                "benchmark-user",
                persist_directory=Path("unused"),
                vector_db=vector_store,
            )
            database.commit()
            documents = database.scalar(
                select(func.count()).select_from(EvidenceDocument)
            )
            chunks = database.scalar(
                select(func.count()).select_from(EvidenceChunk)
            )

        return {
            "fixture_id": fixture["fixture_id"],
            "concept_resolution_accuracy": concept_correct / len(concept_results),
            "relation_classification_accuracy": relation_correct / len(relation_results),
            "unresolved_preservation_rate": sum(
                result.concept_id is None and result.raw_name == "사내 FluxEngine"
                for result in unresolved
            ) / max(1, len(unresolved)),
            "evidence_lineage_completeness": 1.0 if valid_lineage else 0.0,
            "invalid_quote_rejection": invalid_lineage is None,
            "dry_run_database_writes": {
                "ontology": before != after_dry_run,
                "evidence": dry_run_evidence_count != 0,
            },
            "ontology_dry_run": asdict(ontology_dry_run),
            "evidence_dry_run": asdict(evidence_dry_run),
            "persisted_documents": documents,
            "persisted_chunks": chunks,
            "initial_embedding_writes": writes_after_first,
            "repeated_embedding_writes": (
                vector_store.embedding_writes - writes_after_first
            ),
            "first_index": asdict(first_index),
            "repeated_index": asdict(repeated_index),
        }
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def main() -> int:
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
