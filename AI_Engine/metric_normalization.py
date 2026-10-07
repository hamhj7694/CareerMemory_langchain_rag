"""Deterministic extraction and validation for quantitative source evidence."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from AI_Engine.schemas.normalization import (
    MetricDirection,
    MetricOperator,
    NormalizationStatus,
    QuantifiedMetric,
)


_KOREAN_NUMBERS = {
    "영": 0.0,
    "한": 1.0,
    "하나": 1.0,
    "일": 1.0,
    "두": 2.0,
    "둘": 2.0,
    "이": 2.0,
    "세": 3.0,
    "셋": 3.0,
    "삼": 3.0,
    "네": 4.0,
    "넷": 4.0,
    "사": 4.0,
    "오": 5.0,
    "육": 6.0,
    "칠": 7.0,
    "팔": 8.0,
    "구": 9.0,
    "십": 10.0,
    "이십": 20.0,
    "삼십": 30.0,
    "사십": 40.0,
    "오십": 50.0,
    "육십": 60.0,
    "칠십": 70.0,
    "팔십": 80.0,
    "구십": 90.0,
    "백": 100.0,
}

_NUMBER_TEXT = r"(?:-?\d+(?:\.\d+)?|" + "|".join(
    sorted(_KOREAN_NUMBERS, key=len, reverse=True)
) + r")"
_UNIT_TEXT = (
    r"(?:%|퍼센트|프로|배|밀리초|ms|초|분|시간|일|주|개월|달|년|건|명|회|개)"
)
_VALUE_UNIT_PATTERN = re.compile(
    rf"(?P<number>{_NUMBER_TEXT})\s*(?P<unit>{_UNIT_TEXT})",
    re.IGNORECASE,
)
_BEFORE_AFTER_PATTERN = re.compile(
    rf"(?P<before>{_NUMBER_TEXT})\s*(?P<unit1>{_UNIT_TEXT})\s*(?:에서|부터)\s*"
    rf"(?P<after>{_NUMBER_TEXT})\s*(?P<unit2>{_UNIT_TEXT})",
    re.IGNORECASE,
)
_RANGE_PATTERN = re.compile(
    rf"(?P<minimum>{_NUMBER_TEXT})\s*(?:~|～|에서|부터)\s*"
    rf"(?P<maximum>{_NUMBER_TEXT})\s*(?P<unit>{_UNIT_TEXT})",
    re.IGNORECASE,
)
_HALF_PATTERN = re.compile(r"(?:거의\s*)?(?:절반|반)\s*(?:수준|정도)?")


def _number(value: str) -> float | None:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    if normalized in _KOREAN_NUMBERS:
        return _KOREAN_NUMBERS[normalized]
    try:
        return float(normalized.replace(",", ""))
    except ValueError:
        return None


def _unit(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return {
        "%": "percent",
        "퍼센트": "percent",
        "프로": "percent",
        "배": "times",
        "밀리초": "millisecond",
        "ms": "millisecond",
        "초": "second",
        "분": "minute",
        "시간": "hour",
        "일": "day",
        "주": "week",
        "개월": "month",
        "달": "month",
        "년": "year",
        "건": "count",
        "명": "person",
        "회": "count",
        "개": "count",
    }.get(normalized, normalized)


def _direction(text: str) -> MetricDirection:
    normalized = text.casefold()
    decrease_markers = (
        "감소", "줄", "단축", "낮", "절감", "축소", "개선되어 내려",
    )
    increase_markers = (
        "증가", "높", "향상", "개선되어 올라", "상승", "늘", "달성",
    )
    if any(marker in normalized for marker in decrease_markers):
        return MetricDirection.DECREASE
    if any(marker in normalized for marker in increase_markers):
        return MetricDirection.INCREASE
    return MetricDirection.UNKNOWN


def _operator(text: str) -> MetricOperator:
    normalized = text.casefold()
    if any(marker in normalized for marker in ("약", "대략", "거의", "정도", "내외")):
        return MetricOperator.APPROXIMATE
    if any(marker in normalized for marker in ("이상", "최소", "적어도")):
        return MetricOperator.AT_LEAST
    if any(marker in normalized for marker in ("이하", "최대", "많아도")):
        return MetricOperator.AT_MOST
    return MetricOperator.EXACT


def _metric_name(fact_text: str, raw_expression: str) -> str:
    candidate = fact_text.replace(raw_expression, " ")
    candidate = re.sub(
        r"\b(?:증가|감소|향상|단축|절감|달성|개선)\b.*$",
        "",
        candidate,
    )
    candidate = " ".join(candidate.split()).strip(" -:,.()[]")
    return candidate[:100]


def extract_metrics(
    fact_text: str,
    *,
    source_ref_id: str | None = None,
    quote: str | None = None,
) -> list[QuantifiedMetric]:
    """Extract values only from the exact quote; use fact text for the label."""

    evidence = (quote if quote is not None else fact_text).strip()
    if not evidence:
        return []
    context = f"{fact_text}\n{evidence}"
    direction = _direction(context)
    result: list[QuantifiedMetric] = []
    occupied: list[tuple[int, int]] = []

    for match in _BEFORE_AFTER_PATTERN.finditer(evidence):
        before = _number(match.group("before"))
        after = _number(match.group("after"))
        unit1 = _unit(match.group("unit1"))
        unit2 = _unit(match.group("unit2"))
        if before is None or after is None or unit1 != unit2:
            continue
        raw = match.group(0)
        inferred_direction = direction
        if inferred_direction == MetricDirection.UNKNOWN:
            inferred_direction = (
                MetricDirection.DECREASE
                if after < before
                else MetricDirection.INCREASE
                if after > before
                else MetricDirection.NEUTRAL
            )
        result.append(QuantifiedMetric(
            metric_name=_metric_name(fact_text, raw),
            raw_expression=raw,
            before_value=before,
            after_value=after,
            unit=unit1,
            direction=inferred_direction,
            operator=_operator(context),
            normalization_status=NormalizationStatus.RESOLVED,
            source_ref_id=source_ref_id,
            quote=evidence if source_ref_id else "",
            confidence=1.0,
        ))
        occupied.append(match.span())

    for match in _RANGE_PATTERN.finditer(evidence):
        if any(match.start() < end and match.end() > start for start, end in occupied):
            continue
        minimum = _number(match.group("minimum"))
        maximum = _number(match.group("maximum"))
        if minimum is None or maximum is None:
            continue
        raw = match.group(0)
        result.append(QuantifiedMetric(
            metric_name=_metric_name(fact_text, raw),
            raw_expression=raw,
            range_min=min(minimum, maximum),
            range_max=max(minimum, maximum),
            unit=_unit(match.group("unit")),
            direction=direction,
            operator=MetricOperator.RANGE,
            normalization_status=NormalizationStatus.RESOLVED,
            source_ref_id=source_ref_id,
            quote=evidence if source_ref_id else "",
            confidence=1.0,
        ))
        occupied.append(match.span())

    for match in _VALUE_UNIT_PATTERN.finditer(evidence):
        if any(match.start() < end and match.end() > start for start, end in occupied):
            continue
        value = _number(match.group("number"))
        if value is None:
            continue
        normalized_unit = _unit(match.group("unit"))
        if normalized_unit == "year" and value >= 1900:
            # Calendar years belong to the period field, not performance metrics.
            continue
        raw = match.group(0)
        result.append(QuantifiedMetric(
            metric_name=_metric_name(fact_text, raw),
            raw_expression=raw,
            value=value,
            unit=normalized_unit,
            direction=direction,
            operator=_operator(context),
            normalization_status=NormalizationStatus.RESOLVED,
            source_ref_id=source_ref_id,
            quote=evidence if source_ref_id else "",
            confidence=1.0,
        ))
        occupied.append(match.span())

    for match in _HALF_PATTERN.finditer(evidence):
        if any(match.start() < end and match.end() > start for start, end in occupied):
            continue
        raw = match.group(0)
        result.append(QuantifiedMetric(
            metric_name=_metric_name(fact_text, raw),
            raw_expression=raw,
            value=0.5,
            unit="ratio",
            direction=direction,
            operator=_operator(context),
            normalization_status=NormalizationStatus.RESOLVED,
            source_ref_id=source_ref_id,
            quote=evidence if source_ref_id else "",
            confidence=1.0,
        ))
    return result


def validate_proposed_metrics(
    proposed_metrics: Sequence[Mapping[str, Any]],
    *,
    source_text_by_id: Mapping[str, str],
) -> list[QuantifiedMetric]:
    """Recompute numeric values from source quotes; never trust model numbers."""

    result: list[QuantifiedMetric] = []
    seen: set[tuple[str, str, str]] = set()
    for proposed in proposed_metrics:
        source_ref_id = proposed.get("source_ref_id")
        quote = proposed.get("quote")
        raw_expression = proposed.get("raw_expression")
        if not all(isinstance(item, str) for item in (source_ref_id, quote, raw_expression)):
            continue
        source_text = source_text_by_id.get(source_ref_id)
        if source_text is None or quote not in source_text or raw_expression not in quote:
            continue
        metric_name = str(proposed.get("metric_name") or "").strip()
        parsed = extract_metrics(
            metric_name or quote,
            source_ref_id=source_ref_id,
            quote=quote,
        )
        matching = [item for item in parsed if item.raw_expression == raw_expression]
        if matching:
            metric = matching[0]
            if metric_name:
                metric = metric.model_copy(update={"metric_name": metric_name})
        else:
            metric = QuantifiedMetric(
                metric_name=metric_name,
                raw_expression=raw_expression,
                normalization_status=NormalizationStatus.UNRESOLVED,
                source_ref_id=source_ref_id,
                quote=quote,
            )
        key = (source_ref_id, quote, raw_expression)
        if key not in seen:
            seen.add(key)
            result.append(metric)
    return result


def merge_metrics(
    facts: Sequence[str],
    citations: Mapping[str, Sequence[Any]],
    *,
    source_text_by_id: Mapping[str, str],
    proposed_metrics: Sequence[Mapping[str, Any]] = (),
) -> list[QuantifiedMetric]:
    """Combine validated model labels with deterministic extraction from facts."""

    result = validate_proposed_metrics(
        proposed_metrics,
        source_text_by_id=source_text_by_id,
    )
    seen = {
        (item.source_ref_id or "", item.quote, item.raw_expression)
        for item in result
    }
    for index, fact in enumerate(facts):
        for citation in citations.get(f"facts.{index}", ()):
            source_ref_id = getattr(citation, "source_ref_id", None)
            quote = getattr(citation, "quote", "")
            for metric in extract_metrics(
                fact,
                source_ref_id=source_ref_id,
                quote=quote,
            ):
                key = (metric.source_ref_id or "", metric.quote, metric.raw_expression)
                if key not in seen:
                    seen.add(key)
                    result.append(metric)
    return result


def metric_satisfies_requirement(
    requirement: QuantifiedMetric,
    candidate: QuantifiedMetric,
) -> bool:
    """Compare validated values deterministically, never by embedding distance."""

    requirement_unit = requirement.unit
    candidate_unit = candidate.unit
    requirement_value = requirement.value
    candidate_value = candidate.value
    if candidate_value is None:
        return False
    if requirement_unit == "percent" and candidate_unit == "ratio":
        candidate_value *= 100
        candidate_unit = "percent"
    elif requirement_unit == "ratio" and candidate_unit == "percent":
        candidate_value /= 100
        candidate_unit = "ratio"
    if requirement_unit != candidate_unit:
        return False

    operator = requirement.operator
    if operator == MetricOperator.RANGE.value:
        if requirement.range_min is None or requirement.range_max is None:
            return False
        return requirement.range_min <= candidate_value <= requirement.range_max
    if requirement_value is None:
        return False
    if operator == MetricOperator.AT_LEAST.value:
        return candidate_value >= requirement_value
    if operator == MetricOperator.AT_MOST.value:
        return candidate_value <= requirement_value
    if operator == MetricOperator.APPROXIMATE.value:
        tolerance = max(abs(requirement_value) * 0.05, 0.01)
        return abs(candidate_value - requirement_value) <= tolerance
    return candidate_value == requirement_value


__all__ = [
    "extract_metrics",
    "metric_satisfies_requirement",
    "merge_metrics",
    "validate_proposed_metrics",
]
