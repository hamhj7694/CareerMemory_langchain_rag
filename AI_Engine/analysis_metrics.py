"""Request-scoped metrics for conversation analysis model calls."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from functools import wraps
from time import perf_counter
from typing import Any, Callable, TypeVar


LEGACY_ANALYSIS_ARCHITECTURE_VERSION = "combined-analysis-v1"
ANALYSIS_ARCHITECTURE_VERSION = "routed-analysis-v2"
PRICING_VERSION = "2026-10-07"
GPT_4O_MINI_PRICING = {
    "input_usd_per_million": 0.15,
    "cached_input_usd_per_million": 0.075,
    "output_usd_per_million": 0.60,
}


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _integer(item: Any, name: str) -> int:
    value = _value(item, name, 0)
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _round_ms(value: float) -> float:
    return round(max(0.0, value), 3)


@dataclass
class AnalysisMetricsCollector:
    """Collect token usage and timings without changing analysis behavior."""

    run_id: str
    provider: str
    model: str
    architecture_version: str = ANALYSIS_ARCHITECTURE_VERSION
    source_message_count: int = 0
    unique_source_tokens: int = 0
    unique_source_token_method: str = "heuristic-v1"
    calls: list[dict[str, Any]] = field(default_factory=list)
    stages: dict[str, dict[str, Any]] = field(default_factory=dict)
    status: str = "running"
    _started_at: float = field(default_factory=perf_counter, init=False, repr=False)
    _duration_ms: float = field(default=0.0, init=False, repr=False)

    def set_source_metrics(
        self,
        *,
        message_count: int,
        unique_source_tokens: int,
        token_method: str = "heuristic-v1",
    ) -> None:
        self.source_message_count = max(0, int(message_count))
        self.unique_source_tokens = max(0, int(unique_source_tokens))
        self.unique_source_token_method = token_method

    def record_call(
        self,
        *,
        stage: str,
        model: str,
        duration_ms: float,
        response: Any | None = None,
        status: str = "succeeded",
        error_type: str | None = None,
    ) -> None:
        usage = _value(response, "usage") if response is not None else None
        input_details = _value(usage, "input_tokens_details", {}) or {}
        output_details = _value(usage, "output_tokens_details", {}) or {}
        input_tokens = _integer(usage, "input_tokens")
        output_tokens = _integer(usage, "output_tokens")
        total_tokens = _integer(usage, "total_tokens")
        if not total_tokens:
            total_tokens = input_tokens + output_tokens
        self.calls.append({
            "call_index": len(self.calls) + 1,
            "stage": stage,
            "provider": self.provider,
            "model": str(model or self.model),
            "status": status,
            "usage_available": usage is not None,
            "input_tokens": input_tokens,
            "cached_tokens": _integer(input_details, "cached_tokens"),
            "cache_write_tokens": _integer(input_details, "cache_write_tokens"),
            "output_tokens": output_tokens,
            "reasoning_tokens": _integer(output_details, "reasoning_tokens"),
            "total_tokens": total_tokens,
            "duration_ms": _round_ms(duration_ms),
            **({"error_type": error_type} if error_type else {}),
        })

    def record_stage(
        self,
        name: str,
        duration_ms: float,
        *,
        status: str,
    ) -> None:
        current = self.stages.setdefault(name, {
            "count": 0,
            "duration_ms": 0.0,
            "status": "succeeded",
        })
        current["count"] += 1
        current["duration_ms"] = _round_ms(
            float(current["duration_ms"]) + duration_ms
        )
        if status != "succeeded":
            current["status"] = status

    def finish(self, *, status: str = "succeeded") -> None:
        if self.status != "running":
            return
        self.status = status
        self._duration_ms = (perf_counter() - self._started_at) * 1000

    def to_dict(self) -> dict[str, Any]:
        input_tokens = sum(call["input_tokens"] for call in self.calls)
        cached_tokens = sum(call["cached_tokens"] for call in self.calls)
        output_tokens = sum(call["output_tokens"] for call in self.calls)
        total_tokens = sum(call["total_tokens"] for call in self.calls)
        uncached_tokens = max(0, input_tokens - cached_tokens)
        pricing = GPT_4O_MINI_PRICING if self.model == "gpt-4o-mini" else None
        estimated_cost_usd = None
        if pricing is not None:
            estimated_cost_usd = round(
                (
                    uncached_tokens * pricing["input_usd_per_million"]
                    + cached_tokens * pricing["cached_input_usd_per_million"]
                    + output_tokens * pricing["output_usd_per_million"]
                ) / 1_000_000,
                8,
            )
        amplification = (
            round(input_tokens / self.unique_source_tokens, 3)
            if self.unique_source_tokens
            else None
        )
        source_ratio = (
            round(self.unique_source_tokens / input_tokens * 100, 3)
            if input_tokens
            else None
        )
        return {
            "architecture_version": self.architecture_version,
            "run_id": self.run_id,
            "status": self.status,
            "provider": self.provider,
            "model": self.model,
            "source_message_count": self.source_message_count,
            "unique_source_tokens": self.unique_source_tokens,
            "unique_source_token_method": self.unique_source_token_method,
            "llm_call_count": len(self.calls),
            "input_tokens": input_tokens,
            "cached_tokens": cached_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "token_amplification": amplification,
            "unique_source_ratio_pct": source_ratio,
            "total_duration_ms": _round_ms(
                self._duration_ms or (perf_counter() - self._started_at) * 1000
            ),
            "stages": self.stages,
            "calls": self.calls,
            "pricing": (
                {"version": PRICING_VERSION, **pricing}
                if pricing is not None
                else None
            ),
            "estimated_cost_usd": estimated_cost_usd,
        }


_CURRENT_METRICS: ContextVar[AnalysisMetricsCollector | None] = ContextVar(
    "conversation_analysis_metrics",
    default=None,
)


@contextmanager
def capture_analysis_metrics(
    collector: AnalysisMetricsCollector,
) -> Iterator[AnalysisMetricsCollector]:
    token: Token[AnalysisMetricsCollector | None] = _CURRENT_METRICS.set(
        collector
    )
    try:
        yield collector
    except Exception:
        collector.finish(status="failed")
        raise
    else:
        collector.finish(status="succeeded")
    finally:
        _CURRENT_METRICS.reset(token)


@contextmanager
def measure_analysis_stage(name: str) -> Iterator[None]:
    collector = _CURRENT_METRICS.get()
    if collector is None:
        yield
        return
    started_at = perf_counter()
    try:
        yield
    except Exception:
        collector.record_stage(
            name,
            (perf_counter() - started_at) * 1000,
            status="failed",
        )
        raise
    else:
        collector.record_stage(
            name,
            (perf_counter() - started_at) * 1000,
            status="succeeded",
        )


F = TypeVar("F", bound=Callable[..., Any])


def measured_analysis_stage(name: str) -> Callable[[F], F]:
    def decorate(function: F) -> F:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            with measure_analysis_stage(name):
                return function(*args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorate


def tracked_responses_create(
    client: Any,
    *,
    stage: str,
    **kwargs: Any,
) -> Any:
    """Call Responses API and record usage when a collector is active."""

    collector = _CURRENT_METRICS.get()
    if collector is None:
        return client.responses.create(**kwargs)
    started_at = perf_counter()
    try:
        response = client.responses.create(**kwargs)
    except Exception as error:
        collector.record_call(
            stage=stage,
            model=str(kwargs.get("model") or collector.model),
            duration_ms=(perf_counter() - started_at) * 1000,
            status="failed",
            error_type=error.__class__.__name__,
        )
        raise
    collector.record_call(
        stage=stage,
        model=str(kwargs.get("model") or collector.model),
        duration_ms=(perf_counter() - started_at) * 1000,
        response=response,
    )
    return response


__all__ = [
    "ANALYSIS_ARCHITECTURE_VERSION",
    "LEGACY_ANALYSIS_ARCHITECTURE_VERSION",
    "AnalysisMetricsCollector",
    "capture_analysis_metrics",
    "measure_analysis_stage",
    "measured_analysis_stage",
    "tracked_responses_create",
]
