"""영속 경량 온톨로지 조회, seed, 관계 판정 서비스."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import re
import unicodedata
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from AI_Engine.database.models import (
    OntologyAlias,
    OntologyConcept,
    OntologyRelation,
)
from AI_Engine.ontology_seed import (
    ONTOLOGY_RELATIONS,
    ONTOLOGY_VERSION,
    SKILL_REGISTRY,
)


def exact_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).strip().casefold().split())


def alias_key(value: str) -> str:
    return re.sub(r"[\s._-]+", "", exact_key(value))


@dataclass(frozen=True)
class ConceptResolution:
    raw_name: str
    concept_id: str | None
    canonical_name: str | None
    match_type: str
    ontology_version: str | None


@dataclass(frozen=True)
class RelationshipDecision:
    relationship: str
    matching_policy: str
    satisfies_requirement: bool
    ontology_version: str | None


@dataclass(frozen=True)
class OntologySeedReport:
    concepts_created: int = 0
    concepts_updated: int = 0
    aliases_created: int = 0
    aliases_updated: int = 0
    relations_created: int = 0
    relations_updated: int = 0
    would_write: bool = False


class OntologyRepository:
    """DB를 우선 조회하고 장애 시 curated seed로만 안전하게 fallback한다."""

    def __init__(
        self,
        session_factory: Callable[[], Session] | None = None,
        *,
        fallback_enabled: bool = True,
    ) -> None:
        self.session_factory = session_factory
        self.fallback_enabled = fallback_enabled

    def resolve(self, raw_name: str) -> ConceptResolution:
        raw = unicodedata.normalize("NFKC", raw_name).strip()
        if self.session_factory is not None:
            try:
                with self.session_factory() as database:
                    resolved = self._resolve_database(database, raw)
                if resolved is not None:
                    return resolved
            except SQLAlchemyError:
                if not self.fallback_enabled:
                    raise
        if self.fallback_enabled:
            return self._resolve_fallback(raw)
        return ConceptResolution(raw, None, None, "unresolved", None)

    def relationship(self, source_id: str, target_id: str) -> RelationshipDecision:
        if not source_id or not target_id:
            return RelationshipDecision("unresolved", "candidate_only", False, None)
        if source_id == target_id:
            return RelationshipDecision("exact", "satisfies", True, ONTOLOGY_VERSION)
        if self.session_factory is not None:
            try:
                with self.session_factory() as database:
                    relation = database.scalar(select(OntologyRelation).where(or_(
                        (
                            (OntologyRelation.source_concept_id == source_id)
                            & (OntologyRelation.target_concept_id == target_id)
                        ),
                        (
                            (OntologyRelation.source_concept_id == target_id)
                            & (OntologyRelation.target_concept_id == source_id)
                            & (OntologyRelation.relation_type == "related_to")
                        ),
                    )))
                if relation is not None:
                    return RelationshipDecision(
                        relation.relation_type,
                        relation.matching_policy,
                        relation.matching_policy == "satisfies",
                        relation.ontology_version,
                    )
            except SQLAlchemyError:
                if not self.fallback_enabled:
                    raise
        return self._fallback_relationship(source_id, target_id)

    @staticmethod
    def _resolve_database(
        database: Session,
        raw: str,
    ) -> ConceptResolution | None:
        canonical = database.scalar(select(OntologyConcept).where(
            OntologyConcept.concept_type == "skill",
            OntologyConcept.normalization_key == exact_key(raw),
            OntologyConcept.status == "active",
        ))
        if canonical is not None:
            return ConceptResolution(
                raw,
                canonical.id,
                canonical.canonical_name,
                "exact",
                canonical.ontology_version,
            )
        alias = database.execute(
            select(OntologyAlias, OntologyConcept)
            .join(OntologyConcept, OntologyConcept.id == OntologyAlias.concept_id)
            .where(
                OntologyAlias.normalization_key == alias_key(raw),
                OntologyConcept.status == "active",
            )
        ).first()
        if alias is None:
            return None
        _alias, concept = alias
        return ConceptResolution(
            raw,
            concept.id,
            concept.canonical_name,
            "alias",
            concept.ontology_version,
        )

    @staticmethod
    def _resolve_fallback(raw: str) -> ConceptResolution:
        for definition in SKILL_REGISTRY:
            if exact_key(raw) == exact_key(definition.canonical_name):
                return ConceptResolution(
                    raw,
                    definition.id,
                    definition.canonical_name,
                    "exact",
                    ONTOLOGY_VERSION,
                )
            if alias_key(raw) in {alias_key(alias) for alias in definition.aliases}:
                return ConceptResolution(
                    raw,
                    definition.id,
                    definition.canonical_name,
                    "alias",
                    ONTOLOGY_VERSION,
                )
        return ConceptResolution(raw, None, None, "unresolved", ONTOLOGY_VERSION)

    @staticmethod
    def _fallback_relationship(source_id: str, target_id: str) -> RelationshipDecision:
        for definition in SKILL_REGISTRY:
            if definition.id == source_id and target_id in definition.related_skill_ids:
                return RelationshipDecision(
                    "related_to", "candidate_only", False, ONTOLOGY_VERSION
                )
            if definition.id == target_id and source_id in definition.related_skill_ids:
                return RelationshipDecision(
                    "related_to", "candidate_only", False, ONTOLOGY_VERSION
                )
        for relation in ONTOLOGY_RELATIONS:
            if (
                relation.source_concept_id == source_id
                and relation.target_concept_id == target_id
            ):
                return RelationshipDecision(
                    relation.relation_type,
                    relation.matching_policy,
                    relation.matching_policy == "satisfies",
                    ONTOLOGY_VERSION,
                )
        return RelationshipDecision("unresolved", "candidate_only", False, ONTOLOGY_VERSION)


_default_repository = OntologyRepository()


def configure_default_ontology_repository(
    session_factory: Callable[[], Session] | None,
) -> None:
    global _default_repository
    _default_repository = OntologyRepository(session_factory)


def get_default_ontology_repository() -> OntologyRepository:
    return _default_repository


def _stable_id(prefix: str, value: str) -> str:
    digest = uuid5(NAMESPACE_URL, f"career-memory:{prefix}:{value}")
    return f"{prefix}-{digest}"


def seed_ontology(database: Session, *, dry_run: bool = False) -> OntologySeedReport:
    counts = {
        "concepts_created": 0,
        "concepts_updated": 0,
        "aliases_created": 0,
        "aliases_updated": 0,
        "relations_created": 0,
        "relations_updated": 0,
    }
    seed_alias_owners: dict[tuple[str, str], str] = {}
    for definition in SKILL_REGISTRY:
        concept = database.get(OntologyConcept, definition.id)
        concept_values = {
            "concept_type": "skill",
            "canonical_name": definition.canonical_name,
            "normalization_key": exact_key(definition.canonical_name),
            "description": "",
            "status": "active",
            "ontology_version": ONTOLOGY_VERSION,
        }
        if concept is None:
            counts["concepts_created"] += 1
            if not dry_run:
                database.add(OntologyConcept(id=definition.id, **concept_values))
        elif any(getattr(concept, key) != value for key, value in concept_values.items()):
            counts["concepts_updated"] += 1
            if not dry_run:
                for key, value in concept_values.items():
                    setattr(concept, key, value)

        for alias in definition.aliases:
            key = alias_key(alias)
            alias_identity = (key, "und")
            prior_owner = seed_alias_owners.get(alias_identity)
            if prior_owner == definition.id:
                # 공백·점 표기만 다른 별칭은 같은 normalization key이므로 한 번만 seed한다.
                continue
            if prior_owner is not None:
                raise ValueError(
                    "동일한 ontology alias normalization key가 여러 concept에 "
                    f"할당됐습니다: {key} ({prior_owner}, {definition.id})"
                )
            seed_alias_owners[alias_identity] = definition.id
            existing = database.scalar(select(OntologyAlias).where(
                OntologyAlias.normalization_key == key,
                OntologyAlias.locale == "und",
            ))
            values = {
                "concept_id": definition.id,
                "alias": alias,
                "normalization_key": key,
                "locale": "und",
                "provenance": "curated-seed",
            }
            if existing is None:
                counts["aliases_created"] += 1
                if not dry_run:
                    database.add(OntologyAlias(
                        id=_stable_id("OA", f"{definition.id}:{key}"),
                        **values,
                    ))
            elif any(getattr(existing, name) != value for name, value in values.items()):
                counts["aliases_updated"] += 1
                if not dry_run:
                    for name, value in values.items():
                        setattr(existing, name, value)

        for target_id in definition.related_skill_ids:
            relation_key = f"{definition.id}:related_to:{target_id}"
            relation_id = _stable_id("OR", relation_key)
            relation = database.get(OntologyRelation, relation_id)
            values = {
                "source_concept_id": definition.id,
                "relation_type": "related_to",
                "target_concept_id": target_id,
                "matching_policy": "candidate_only",
                "provenance": "curated-seed",
                "ontology_version": ONTOLOGY_VERSION,
            }
            if relation is None:
                counts["relations_created"] += 1
                if not dry_run:
                    database.add(OntologyRelation(id=relation_id, **values))
            elif any(getattr(relation, name) != value for name, value in values.items()):
                counts["relations_updated"] += 1
                if not dry_run:
                    for name, value in values.items():
                        setattr(relation, name, value)

    for definition in ONTOLOGY_RELATIONS:
        relation_key = (
            f"{definition.source_concept_id}:{definition.relation_type}:"
            f"{definition.target_concept_id}"
        )
        relation_id = _stable_id("OR", relation_key)
        relation = database.get(OntologyRelation, relation_id)
        values = {
            "source_concept_id": definition.source_concept_id,
            "relation_type": definition.relation_type,
            "target_concept_id": definition.target_concept_id,
            "matching_policy": definition.matching_policy,
            "provenance": "curated-seed",
            "ontology_version": ONTOLOGY_VERSION,
        }
        if relation is None:
            counts["relations_created"] += 1
            if not dry_run:
                database.add(OntologyRelation(id=relation_id, **values))
        elif any(getattr(relation, name) != value for name, value in values.items()):
            counts["relations_updated"] += 1
            if not dry_run:
                for name, value in values.items():
                    setattr(relation, name, value)

    if not dry_run:
        database.flush()
    return OntologySeedReport(
        **counts,
        would_write=any(counts.values()),
    )


def ontology_seed_checksum() -> str:
    payload = "|".join(
        f"{item.id}:{item.canonical_name}:{','.join(item.aliases)}:"
        f"{','.join(item.related_skill_ids)}"
        for item in SKILL_REGISTRY
    )
    payload += "|" + "|".join(
        f"{item.source_concept_id}:{item.relation_type}:"
        f"{item.target_concept_id}:{item.matching_policy}"
        for item in ONTOLOGY_RELATIONS
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "ConceptResolution",
    "OntologyRepository",
    "OntologySeedReport",
    "RelationshipDecision",
    "alias_key",
    "configure_default_ontology_repository",
    "exact_key",
    "get_default_ontology_repository",
    "ontology_seed_checksum",
    "seed_ontology",
]
