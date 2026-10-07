"""Evaluate conversation-analysis benchmark output against versioned gold data."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any, Iterable, Mapping

from AI_Engine.benchmarks.conversation_analysis import (
    DEFAULT_GOLD_FIXTURE,
)


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _strings(nested)


def _search_text(value: Any) -> str:
    return "\n".join(_strings(value)).casefold()


def _percentage(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100, 3)


def _mean(values: Iterable[float | int | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return round(statistics.mean(clean), 3) if clean else None


def _citations(experience: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not experience:
        return []
    citations: list[dict[str, Any]] = []
    for draft in experience.get("experience_drafts", []):
        for items in (draft.get("field_citations") or {}).values():
            if not isinstance(items, list):
                continue
            citations.extend(item for item in items if isinstance(item, dict))
    return citations


def _used_source_ids(experience: dict[str, Any] | None) -> set[str]:
    if not experience:
        return set()
    return {
        str(source_id)
        for draft in experience.get("experience_drafts", [])
        for source_id in draft.get("source_ref_ids", [])
        if source_id
    }


def _structured_items(
    result: dict[str, Any],
    field_name: str,
) -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    experience = result.get("experience") or {}
    for draft in experience.get("experience_drafts", []):
        for item in draft.get(field_name, []):
            if isinstance(item, dict):
                items.append(("experience", item))
    for job in result.get("jobs", []):
        if not isinstance(job, dict):
            continue
        for requirement in job.get("requirements", []):
            if not isinstance(requirement, dict):
                continue
            for item in requirement.get(field_name, []):
                if isinstance(item, dict):
                    items.append(("job", item))
    return items


def _metric_matches(
    expected: Mapping[str, Any],
    scope: str,
    actual: Mapping[str, Any],
) -> bool:
    if expected.get("scope") and expected.get("scope") != scope:
        return False
    for key in ("value", "unit", "direction"):
        if key in expected and expected.get(key) != actual.get(key):
            return False
    return True


def evaluate_run(run: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    gold = fixture["gold"]
    result = run.get("result", {})
    experience = result.get("experience")
    experience_text = _search_text(
        (experience or {}).get("experience_drafts", [])
    )
    jobs_text = _search_text(result.get("jobs", []))

    fact_results = []
    for fact in gold.get("experience_facts", []):
        required_terms = [str(term) for term in fact.get("required_terms", [])]
        found = all(term.casefold() in experience_text for term in required_terms)
        fact_results.append({
            "id": fact["id"],
            "found": found,
            "context_required": bool(fact.get("context_required")),
            "required_terms": required_terms,
        })

    expected_jobs = gold.get("jobs", [])
    expected_job_sources = {
        str(item["source_message_id"]) for item in expected_jobs
    }
    candidates = result.get("job_candidates", [])
    actual_job_sources = {
        str(item.get("message_id"))
        for item in candidates
        if isinstance(item, dict) and item.get("message_id")
    }
    matched_job_sources = expected_job_sources & actual_job_sources

    job_terms = [
        str(term)
        for item in expected_jobs
        for term in item.get("required_terms", [])
    ]
    found_job_terms = [
        term for term in job_terms if term.casefold() in jobs_text
    ]

    messages = {
        f"source-{message['id']}": message
        for message in fixture.get("messages", [])
    }
    allowed_roles = set(gold.get("evidence_roles", ["user"]))
    citation_results = []
    for citation in _citations(experience):
        source_id = str(citation.get("source_ref_id") or "")
        quote = str(citation.get("quote") or "")
        message = messages.get(source_id)
        valid = bool(
            message
            and message.get("role") in allowed_roles
            and quote
            and quote in str(message.get("content") or "")
        )
        citation_results.append({
            "source_ref_id": source_id,
            "valid": valid,
            "role": message.get("role") if message else None,
        })

    expected_fact_sources = {
        f"source-{source_id}"
        for fact in gold.get("experience_facts", [])
        for source_id in fact.get("source_message_ids", [])
    }
    cited_sources = {
        item["source_ref_id"] for item in citation_results if item["valid"]
    }
    used_sources = _used_source_ids(experience)
    context_facts = [item for item in fact_results if item["context_required"]]
    forbidden_hits = [
        term
        for term in gold.get("forbidden_assistant_terms", [])
        if str(term).casefold() in experience_text
    ]
    irrelevant_hits = [
        term
        for term in gold.get("irrelevant_terms", [])
        if str(term).casefold() in experience_text
    ]
    structured_skills = _structured_items(result, "skill_mentions")
    expected_skills = gold.get("normalized_skills", [])
    found_skills = [
        expected
        for expected in expected_skills
        if any(
            (not expected.get("scope") or expected.get("scope") == scope)
            and expected.get("canonical_skill_id")
            == actual.get("canonical_skill_id")
            for scope, actual in structured_skills
        )
    ]
    structured_metrics = _structured_items(result, "metrics")
    expected_metrics = gold.get("metrics", [])
    found_metrics = [
        expected
        for expected in expected_metrics
        if any(
            _metric_matches(expected, scope, actual)
            for scope, actual in structured_metrics
        )
    ]
    forbidden_metric_values = {
        float(value) for value in gold.get("forbidden_metric_values", [])
    }
    hallucinated_metrics = [
        actual
        for _scope, actual in structured_metrics
        if isinstance(actual.get("value"), (int, float))
        and float(actual["value"]) in forbidden_metric_values
    ]

    return {
        "label": run.get("label"),
        "experience_fact_recall_pct": _percentage(
            sum(item["found"] for item in fact_results),
            len(fact_results),
        ),
        "context_fact_recall_pct": _percentage(
            sum(item["found"] for item in context_facts),
            len(context_facts),
        ),
        "expected_source_coverage_pct": _percentage(
            len(expected_fact_sources & used_sources),
            len(expected_fact_sources),
        ),
        "expected_source_citation_coverage_pct": _percentage(
            len(expected_fact_sources & cited_sources),
            len(expected_fact_sources),
        ),
        "exact_citation_validity_pct": _percentage(
            sum(item["valid"] for item in citation_results),
            len(citation_results),
        ),
        "job_detection_recall_pct": _percentage(
            len(matched_job_sources),
            len(expected_job_sources),
        ),
        "job_detection_precision_pct": _percentage(
            len(matched_job_sources),
            len(actual_job_sources),
        ),
        "job_requirement_term_recall_pct": _percentage(
            len(found_job_terms),
            len(job_terms),
        ),
        "assistant_contamination": bool(forbidden_hits),
        "assistant_contamination_terms": forbidden_hits,
        "irrelevant_leakage": bool(irrelevant_hits),
        "irrelevant_leakage_terms": irrelevant_hits,
        "skill_normalization_recall_pct": _percentage(
            len(found_skills),
            len(expected_skills),
        ),
        "metric_value_recall_pct": _percentage(
            len(found_metrics),
            len(expected_metrics),
        ),
        "numeric_hallucination": bool(hallucinated_metrics),
        "numeric_hallucination_metrics": hallucinated_metrics,
        "fact_results": fact_results,
        "citation_results": citation_results,
        "actual_job_source_ids": sorted(actual_job_sources),
    }


def evaluate_report(
    report: dict[str, Any],
    fixture: dict[str, Any],
) -> dict[str, Any]:
    run_results = [evaluate_run(run, fixture) for run in report.get("runs", [])]
    metric_names = (
        "experience_fact_recall_pct",
        "context_fact_recall_pct",
        "expected_source_coverage_pct",
        "expected_source_citation_coverage_pct",
        "exact_citation_validity_pct",
        "job_detection_recall_pct",
        "job_detection_precision_pct",
        "job_requirement_term_recall_pct",
        "skill_normalization_recall_pct",
        "metric_value_recall_pct",
    )
    return {
        "schema_version": "conversation-analysis-gold-evaluation-v1",
        "benchmark_version": report.get("benchmark_version"),
        "architecture_version": report.get("architecture_version"),
        "fixture_id": fixture.get("fixture_id"),
        "aggregate": {
            **{
                name: _mean(item.get(name) for item in run_results)
                for name in metric_names
            },
            "assistant_contamination_rate_pct": _percentage(
                sum(item["assistant_contamination"] for item in run_results),
                len(run_results),
            ),
            "irrelevant_leakage_rate_pct": _percentage(
                sum(item["irrelevant_leakage"] for item in run_results),
                len(run_results),
            ),
            "numeric_hallucination_rate_pct": _percentage(
                sum(item["numeric_hallucination"] for item in run_results),
                len(run_results),
            ),
        },
        "runs": run_results,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate a conversation-analysis benchmark against gold data."
    )
    parser.add_argument("report", type=Path)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_GOLD_FIXTURE)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    evaluation = evaluate_report(report, fixture)
    output = args.output or args.report.with_name(
        f"{args.report.stem}-evaluation.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "evaluation_path": str(output.resolve()),
        "aggregate": evaluation["aggregate"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
