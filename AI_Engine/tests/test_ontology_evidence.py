"""경량 온톨로지, Evidence lineage, 증분 인덱스 회귀 테스트."""

from __future__ import annotations

from pathlib import Path
import unittest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from AI_Engine.database.connection import Base
from AI_Engine.database.models import (
    EmbeddingRecord,
    EvidenceChunk,
    EvidenceDocument,
    Experience,
    ExperienceDomain,
    ExperienceProject,
    OntologyConcept,
    User,
)
from AI_Engine.evidence_index import sync_evidence_index
from AI_Engine.evidence_repository import (
    find_citation_lineage,
    sync_source_refs,
)
from AI_Engine.ontology_repository import OntologyRepository, seed_ontology


class FakeVectorStore:
    def __init__(self) -> None:
        self.documents: dict[str, object] = {}
        self.add_calls: list[list[str]] = []
        self.update_calls: list[list[str]] = []
        self.delete_calls: list[list[str]] = []

    def get(self, *, include):
        del include
        ids = list(self.documents)
        return {
            "ids": ids,
            "metadatas": [self.documents[item].metadata for item in ids],
        }

    def add_documents(self, *, ids, documents):
        self.add_calls.append(list(ids))
        self.documents.update(zip(ids, documents, strict=True))

    def update_documents(self, *, ids, documents):
        self.update_calls.append(list(ids))
        self.documents.update(zip(ids, documents, strict=True))

    def delete(self, *, ids):
        self.delete_calls.append(list(ids))
        for item in ids:
            self.documents.pop(item, None)


class OntologyEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.Session() as database:
            database.add(User(
                id="user-1",
                email="ontology@example.com",
                display_name="Ontology Tester",
                password_hash="test",
            ))
            database.add(ExperienceDomain(
                id="domain-1",
                user_id="user-1",
                name="개발",
            ))
            database.add(ExperienceProject(
                id="project-1",
                user_id="user-1",
                domain_id="domain-1",
                name="프로젝트",
            ))
            database.add(Experience(
                id="experience-1",
                user_id="user-1",
                project_id="project-1",
                title="성능 개선",
                status="confirmed",
            ))
            database.commit()

    def tearDown(self) -> None:
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_ontology_seed_dry_run_then_resolves_alias_and_relation(self) -> None:
        with self.Session() as database:
            dry_run = seed_ontology(database, dry_run=True)
            self.assertTrue(dry_run.would_write)
            self.assertEqual(
                database.scalar(select(func.count()).select_from(OntologyConcept)),
                0,
            )

            applied = seed_ontology(database)
            database.commit()

        self.assertGreater(applied.concepts_created, 0)
        repository = OntologyRepository(self.Session, fallback_enabled=False)
        alias = repository.resolve("페스트API")
        related = repository.relationship("skill-fastapi", "skill-rest-api")
        narrower = repository.relationship(
            "skill-fastapi", "skill-python-web-framework"
        )
        broader = repository.relationship(
            "skill-python-web-framework", "skill-fastapi"
        )
        unknown = repository.resolve("사내 FluxEngine")

        self.assertEqual(alias.concept_id, "skill-fastapi")
        self.assertEqual(alias.match_type, "alias")
        self.assertEqual(related.relationship, "related_to")
        self.assertFalse(related.satisfies_requirement)
        self.assertEqual(narrower.relationship, "narrower_than")
        self.assertEqual(narrower.matching_policy, "explicit_only")
        self.assertFalse(narrower.satisfies_requirement)
        self.assertEqual(broader.relationship, "broader_than")
        self.assertFalse(broader.satisfies_requirement)
        self.assertIsNone(unknown.concept_id)

    def test_evidence_sync_is_idempotent_and_preserves_lineage(self) -> None:
        source = {
            "id": "source-1",
            "source_type": "manual_text",
            "manual_input_id": "manual-1",
            "title": "성과 원문",
            "text": "FastAPI로 처리 시간을 50% 줄였습니다.",
        }
        with self.Session() as database:
            first = sync_source_refs(
                database, "user-1", [source], experience_id="experience-1"
            )
            database.commit()
            second = sync_source_refs(
                database, "user-1", [source], experience_id="experience-1"
            )
            lineage = find_citation_lineage(
                database,
                "user-1",
                "source-1",
                "처리 시간을 50% 줄였습니다.",
            )
            database.commit()

            self.assertEqual(first.documents_created, 1)
            self.assertEqual(second.documents_reused, 1)
            self.assertEqual(second.chunks_reused, 1)
            self.assertIsNotNone(lineage)
            self.assertIsNone(find_citation_lineage(
                database,
                "user-1",
                "source-1",
                "원문에 없는 인용",
            ))
            self.assertEqual(
                database.scalar(select(func.count()).select_from(EvidenceDocument)),
                1,
            )
            self.assertEqual(
                database.scalar(select(func.count()).select_from(EvidenceChunk)),
                1,
            )

    def test_source_change_stales_prior_evidence_and_embedding(self) -> None:
        source = {
            "id": "source-1",
            "source_type": "manual_text",
            "manual_input_id": "manual-1",
            "text": "응답 시간을 50% 줄였습니다.",
        }
        vector_store = FakeVectorStore()
        with self.Session() as database:
            sync_source_refs(
                database, "user-1", [source], experience_id="experience-1"
            )
            database.flush()
            _store, first = sync_evidence_index(
                database,
                "user-1",
                persist_directory=Path("unused"),
                vector_db=vector_store,
            )
            database.commit()

            _store, repeated = sync_evidence_index(
                database,
                "user-1",
                persist_directory=Path("unused"),
                vector_db=vector_store,
            )
            changed_source = {**source, "text": "응답 시간을 49% 줄였습니다."}
            changed = sync_source_refs(
                database,
                "user-1",
                [changed_source],
                experience_id="experience-1",
            )
            _store, indexed = sync_evidence_index(
                database,
                "user-1",
                persist_directory=Path("unused"),
                vector_db=vector_store,
            )
            database.commit()

            self.assertEqual(first.added, 1)
            self.assertEqual(repeated.skipped_unchanged, 1)
            self.assertEqual(len(vector_store.add_calls), 2)
            self.assertEqual(changed.documents_staled, 1)
            self.assertEqual(indexed.deleted, 1)
            self.assertEqual(indexed.added, 1)
            current_records = database.scalars(select(EmbeddingRecord).where(
                EmbeddingRecord.status == "current"
            )).all()
            stale_records = database.scalars(select(EmbeddingRecord).where(
                EmbeddingRecord.status == "stale"
            )).all()
            self.assertEqual(len(current_records), 1)
            self.assertEqual(len(stale_records), 1)

            rebuilt_store, rebuilt = sync_evidence_index(
                database,
                "user-1",
                persist_directory=Path("unused"),
                vector_db=vector_store,
                rebuild=True,
            )
            self.assertIs(rebuilt_store, vector_store)
            self.assertTrue(rebuilt.rebuilt)
            self.assertEqual(rebuilt.deleted, 1)
            self.assertEqual(rebuilt.added, 1)

            removed = sync_source_refs(
                database,
                "user-1",
                [],
                experience_id="experience-1",
            )
            _store, emptied = sync_evidence_index(
                database,
                "user-1",
                persist_directory=Path("unused"),
                vector_db=vector_store,
            )
            database.commit()

            self.assertEqual(removed.links_removed, 1)
            self.assertEqual(emptied.desired, 0)
            self.assertEqual(emptied.deleted, 1)
            self.assertEqual(vector_store.documents, {})


if __name__ == "__main__":
    unittest.main()
