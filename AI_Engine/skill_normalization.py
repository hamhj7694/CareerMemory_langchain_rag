"""Deterministic, lossless skill normalization and relationship checks."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from AI_Engine.ontology_repository import get_default_ontology_repository
from AI_Engine.ontology_seed import SKILL_REGISTRY, SkillDefinition
from AI_Engine.schemas.normalization import (
    NormalizationStatus,
    SkillMatchEvidence,
    SkillMatchType,
    SkillMention,
)


def _nfkc(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def _exact_key(value: str) -> str:
    return " ".join(_nfkc(value).casefold().split())


def _alias_key(value: str) -> str:
    return re.sub(r"[\s._-]+", "", _exact_key(value))


_BY_ID = {item.id: item for item in SKILL_REGISTRY}
_CANONICAL_EXACT = {
    _exact_key(item.canonical_name): item for item in SKILL_REGISTRY
}
_ALIASES: dict[str, SkillDefinition] = {}
for _definition in SKILL_REGISTRY:
    _ALIASES[_alias_key(_definition.canonical_name)] = _definition
    for _alias in _definition.aliases:
        _ALIASES[_alias_key(_alias)] = _definition


def normalize_skill_mention(
    raw_name: str,
    *,
    source_ref_id: str | None = None,
    quote: str = "",
) -> SkillMention:
    """Normalize a skill only through canonical names or curated aliases."""

    raw = _nfkc(raw_name)
    resolution = get_default_ontology_repository().resolve(raw)
    if resolution.concept_id is None:
        return SkillMention(
            raw_name=raw,
            match_type=SkillMatchType.UNRESOLVED,
            normalization_status=NormalizationStatus.UNRESOLVED,
            source_ref_id=source_ref_id,
            quote=quote,
            ontology_version=resolution.ontology_version,
        )
    return SkillMention(
        raw_name=raw,
        normalized_name=resolution.canonical_name,
        canonical_skill_id=resolution.concept_id,
        match_type=SkillMatchType(resolution.match_type),
        normalization_status=NormalizationStatus.RESOLVED,
        source_ref_id=source_ref_id,
        quote=quote,
        confidence=1.0,
        ontology_version=resolution.ontology_version,
    )


def _literal_pattern(value: str) -> re.Pattern[str]:
    escaped = re.escape(value)
    if value and value[0].isascii() and value[0].isalnum():
        escaped = rf"(?<![A-Za-z0-9]){escaped}"
    if value and value[-1].isascii() and value[-1].isalnum():
        escaped = rf"{escaped}(?![A-Za-z0-9])"
    return re.compile(escaped, re.IGNORECASE)


def extract_registered_skill_mentions(
    text: str,
    *,
    source_ref_id: str | None = None,
) -> list[SkillMention]:
    """Find registry-backed mentions while retaining the exact source spelling."""

    candidates: list[tuple[int, int, str]] = []
    names = {
        name
        for definition in SKILL_REGISTRY
        for name in (definition.canonical_name, *definition.aliases)
    }
    for name in sorted(names, key=len, reverse=True):
        for match in _literal_pattern(name).finditer(text):
            candidates.append((match.start(), match.end(), match.group(0)))
    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0])))

    mentions: list[SkillMention] = []
    occupied: list[tuple[int, int]] = []
    seen: set[tuple[str, str | None]] = set()
    for start, end, raw in candidates:
        if any(start < used_end and end > used_start for used_start, used_end in occupied):
            continue
        mention = normalize_skill_mention(
            raw,
            source_ref_id=source_ref_id,
            quote=raw if source_ref_id else "",
        )
        key = (str(mention.canonical_skill_id), source_ref_id)
        if key in seen:
            continue
        seen.add(key)
        occupied.append((start, end))
        mentions.append(mention)
    return mentions


def _valid_proposed_mention(
    value: Mapping[str, Any],
    source_text_by_id: Mapping[str, str],
) -> SkillMention | None:
    raw_name = value.get("raw_name")
    source_ref_id = value.get("source_ref_id")
    quote = value.get("quote")
    if not isinstance(raw_name, str) or not raw_name.strip():
        return None
    if not isinstance(source_ref_id, str) or not isinstance(quote, str):
        return None
    source_text = source_text_by_id.get(source_ref_id)
    if source_text is None or not quote or quote not in source_text:
        return None
    if _alias_key(raw_name) not in _alias_key(quote):
        return None
    return normalize_skill_mention(
        raw_name,
        source_ref_id=source_ref_id,
        quote=quote,
    )


def normalize_skill_list(
    raw_skills: Sequence[str],
    *,
    source_text_by_id: Mapping[str, str] | None = None,
    proposed_mentions: Sequence[Mapping[str, Any]] = (),
) -> list[SkillMention]:
    """Preserve every raw skill and attach canonical data only when verified."""

    sources = source_text_by_id or {}
    result: list[SkillMention] = []
    seen: set[tuple[str, str | None]] = set()
    seen_raw: set[str] = set()

    for proposed in proposed_mentions:
        mention = _valid_proposed_mention(proposed, sources)
        if mention is None:
            continue
        key = (_exact_key(mention.raw_name), mention.source_ref_id)
        if key not in seen:
            seen.add(key)
            seen_raw.add(_exact_key(mention.raw_name))
            result.append(mention)

    for raw_skill in raw_skills:
        raw = str(raw_skill).strip()
        if not raw:
            continue
        if _exact_key(raw) in seen_raw:
            continue
        source_ref_id = None
        quote = ""
        for candidate_source_id, source_text in sources.items():
            match = _literal_pattern(raw).search(source_text)
            if match:
                source_ref_id = candidate_source_id
                quote = match.group(0)
                break
        mention = normalize_skill_mention(
            raw,
            source_ref_id=source_ref_id,
            quote=quote,
        )
        if mention.canonical_skill_id and any(
            item.canonical_skill_id == mention.canonical_skill_id
            for item in result
        ):
            continue
        key = (_exact_key(mention.raw_name), mention.source_ref_id)
        if key not in seen:
            seen.add(key)
            seen_raw.add(_exact_key(mention.raw_name))
            result.append(mention)
    return result


def skill_relationship(
    requirement: SkillMention,
    experience: SkillMention,
) -> SkillMatchType:
    """Return exact only for the same canonical skill; related never satisfies it."""

    left = requirement.canonical_skill_id
    right = experience.canonical_skill_id
    if not left or not right:
        return SkillMatchType.UNRESOLVED
    if left == right:
        return SkillMatchType.EXACT
    decision = get_default_ontology_repository().relationship(left, right)
    if decision.relationship == "related_to":
        return SkillMatchType.RELATED
    return SkillMatchType.UNRESOLVED


def build_skill_match_evidence(
    requirements: Sequence[SkillMention],
    experiences: Sequence[SkillMention],
) -> list[SkillMatchEvidence]:
    matches: list[SkillMatchEvidence] = []
    for requirement in requirements:
        if not requirement.canonical_skill_id:
            continue
        for experience in experiences:
            relationship = skill_relationship(requirement, experience)
            if relationship == SkillMatchType.UNRESOLVED:
                continue
            matches.append(SkillMatchEvidence(
                requirement_skill_id=requirement.canonical_skill_id,
                experience_skill_id=experience.canonical_skill_id or "unresolved",
                relationship=relationship,
                requirement_raw_name=requirement.raw_name,
                experience_raw_name=experience.raw_name,
                matching_policy=(
                    "satisfies"
                    if relationship == SkillMatchType.EXACT
                    else "candidate_only"
                ),
                satisfies_requirement=relationship == SkillMatchType.EXACT,
                ontology_version=(
                    requirement.ontology_version
                    or experience.ontology_version
                ),
            ))
    return matches


__all__ = [
    "SKILL_REGISTRY",
    "SkillDefinition",
    "build_skill_match_evidence",
    "extract_registered_skill_mentions",
    "normalize_skill_list",
    "normalize_skill_mention",
    "skill_relationship",
]
