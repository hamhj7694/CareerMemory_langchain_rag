"""Additive normalization for existing experiences without changing raw fields."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from AI_Engine.database.connection import SessionLocal, initialize_database
from AI_Engine.database.models import Experience
from AI_Engine.metric_normalization import extract_metrics
from AI_Engine.schemas import QuantifiedMetric
from AI_Engine.skill_normalization import normalize_skill_list


def structured_fields_for_experience(
    skills: Sequence[str],
    facts: Sequence[str],
    *,
    skill_mentions: Sequence[Mapping[str, Any]] = (),
    metrics: Sequence[Mapping[str, Any]] = (),
    source_refs: Sequence[Mapping[str, Any]] = (),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return additive projections while leaving skills and facts untouched."""

    source_text_by_id: dict[str, str] = {}
    for source in source_refs:
        source_id = str(source.get("id") or source.get("source_ref_id") or "").strip()
        source_text = str(source.get("text") or source.get("original_text") or "")
        if source_id and source_text:
            source_text_by_id[source_id] = source_text
    normalized_skills = normalize_skill_list(
        skills,
        source_text_by_id=source_text_by_id,
        proposed_mentions=skill_mentions,
    )

    normalized_metrics: list[QuantifiedMetric] = []
    seen_metrics: set[tuple[str, str, str]] = set()
    for raw in metrics:
        try:
            metric = QuantifiedMetric.model_validate(raw)
        except (TypeError, ValueError):
            continue
        key = (
            metric.source_ref_id or "",
            metric.quote,
            metric.raw_expression,
        )
        if key not in seen_metrics:
            seen_metrics.add(key)
            normalized_metrics.append(metric)
    for fact in facts:
        for metric in extract_metrics(str(fact)):
            key = ("", "", metric.raw_expression)
            if key not in seen_metrics:
                seen_metrics.add(key)
                normalized_metrics.append(metric)

    return (
        [item.model_dump(mode="json") for item in normalized_skills],
        [item.model_dump(mode="json") for item in normalized_metrics],
    )


def backfill_experiences(
    database: Session,
    *,
    user_id: str | None = None,
    apply_changes: bool = False,
) -> dict[str, int | bool]:
    """Backfill projections idempotently; dry-run unless explicitly applied."""

    statement = select(Experience).where(Experience.deleted_at.is_(None))
    if user_id:
        statement = statement.where(Experience.user_id == user_id)
    experiences = list(database.scalars(statement))
    changed = 0
    for experience in experiences:
        skill_mentions, metrics = structured_fields_for_experience(
            experience.skills or [],
            experience.facts or [],
            skill_mentions=experience.skill_mentions or [],
            metrics=experience.metrics or [],
            source_refs=experience.source_refs or [],
        )
        if (
            skill_mentions == list(experience.skill_mentions or [])
            and metrics == list(experience.metrics or [])
        ):
            continue
        changed += 1
        if apply_changes:
            experience.skill_mentions = skill_mentions
            experience.metrics = metrics
    if apply_changes:
        database.commit()
    else:
        database.rollback()
    return {
        "scanned": len(experiences),
        "changed": changed,
        "applied": apply_changes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill skill and metric projections without rewriting raw data."
    )
    parser.add_argument("--user-id")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes. The default is a dry run.",
    )
    args = parser.parse_args()
    initialize_database()
    with SessionLocal() as database:
        print(backfill_experiences(
            database,
            user_id=args.user_id,
            apply_changes=args.apply,
        ))


if __name__ == "__main__":
    main()


__all__ = ["backfill_experiences", "structured_fields_for_experience"]
