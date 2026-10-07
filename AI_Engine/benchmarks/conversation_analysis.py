"""Run the current conversation-analysis workflow without database writes."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from AI_Engine.analysis_metrics import (
    ANALYSIS_ARCHITECTURE_VERSION,
    LEGACY_ANALYSIS_ARCHITECTURE_VERSION,
    AnalysisMetricsCollector,
    capture_analysis_metrics,
    measure_analysis_stage,
)
from AI_Engine.api.conversation_analysis import (
    _assistant_context_excerpt,
    _build_experience_sources,
    _route_id_for_evidence,
    _routing_sources,
    _needs_assistant_context,
)
from AI_Engine.api.conversation_experiences import (
    _unprocessed_user_messages as unprocessed_experience_messages,
)
from AI_Engine.api.conversation_jobs import (
    _sources_for_messages as job_sources_for_messages,
    _unprocessed_user_messages as unprocessed_job_messages,
)
from AI_Engine.api.jobs import _experience_dict, _load_rag_experiences
from AI_Engine.chat_context import estimate_tokens
from AI_Engine.conversation_analysis_workflow import ConversationAnalysisWorkflow
from AI_Engine.conversation_content_router import (
    AssistantConversationContext,
    ConversationContentRouterAI,
    ConversationRouteSource,
    RoutedConversationContent,
    conservative_fallback_route,
)
from AI_Engine.conversation_job_extraction import (
    ConversationJobCandidate,
    JobSourceText,
    job_content_fingerprint,
    job_contents_match,
)
from AI_Engine.conversation_job_workflow import (
    ConversationJobDiscoveryAI,
    JobWorkflowResolution,
)
from AI_Engine.database.connection import PROJECT_ROOT, SessionLocal
from AI_Engine.database.models import Conversation, JobAnalysisRecord
from AI_Engine.experience_ai import ExperienceAI
from AI_Engine.job_analysis_ai import (
    create_experience_retriever,
    create_job_analysis_ai,
)
from AI_Engine.llm_provider import get_ai_provider, get_chat_model_name
from AI_Engine.schemas import (
    EvidenceSource,
    EvidenceSourceType,
    ExperienceExtractionInputType,
    ExperienceExtractionRequest,
    JobAnalysisRequest,
)


DEFAULT_REPORT_ROOT = PROJECT_ROOT / "data" / "benchmarks" / "conversation-analysis"
DEFAULT_GOLD_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "conversation_analysis_gold_v1.json"
)


def _exact_text_tokens(values: list[str], model: str) -> tuple[int, str]:
    try:
        import tiktoken

        encoding = tiktoken.encoding_for_model(model)
        return sum(len(encoding.encode(value or "")) for value in values), "tiktoken"
    except Exception:
        return sum(estimate_tokens(value) for value in values), "heuristic-v1"


def _latest_conversation(database) -> Conversation:
    conversation = database.scalar(
        select(Conversation).order_by(Conversation.updated_at.desc())
    )
    if conversation is None:
        raise RuntimeError("No conversation is available for benchmarking.")
    return conversation


def _conversation(database, conversation_id: str | None) -> Conversation:
    if not conversation_id:
        return _latest_conversation(database)
    conversation = database.get(Conversation, conversation_id)
    if conversation is None:
        raise RuntimeError(f"Conversation not found: {conversation_id}")
    return conversation


def _build_retriever(database, user_id: str, root: str):
    experiences = _load_rag_experiences(user_id, database)
    searchable = [item for item in experiences if item.source_ids]
    if not searchable:
        return None
    return create_experience_retriever(
        [_experience_dict(item) for item in searchable],
        persist_directory=root,
        collection_name=f"benchmark_{hashlib.sha256(user_id.encode()).hexdigest()[:16]}",
    )


def _safe_experience_output(result: Any | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        "run": result.run.model_dump(mode="json"),
        "experience_drafts": [
            draft.model_dump(mode="json")
            for draft in result.experience_drafts
        ],
        "analyzed_source_ids": list(result.analyzed_source_ids),
    }


def _candidate_output(candidate: ConversationJobCandidate) -> dict[str, Any]:
    return {
        "message_id": candidate.message_id,
        "attachment_id": candidate.attachment_id,
        "posting_content": candidate.posting_content,
        "company_name": candidate.company_name,
        "role_name": candidate.role_name,
        "posting_title": candidate.posting_title,
        "source_url": candidate.source_url,
    }


def _run_once(
    *,
    conversation_id: str | None,
    label: str,
    run_number: int,
    discovery_ai: ConversationJobDiscoveryAI,
    experience_ai: ExperienceAI,
    routed: bool,
    content_router: ConversationContentRouterAI | None,
) -> dict[str, Any]:
    run_id = f"BENCH-{uuid4()}"
    collector = AnalysisMetricsCollector(
        run_id=run_id,
        provider=get_ai_provider(),
        model=get_chat_model_name(),
        architecture_version=(
            ANALYSIS_ARCHITECTURE_VERSION
            if routed
            else LEGACY_ANALYSIS_ARCHITECTURE_VERSION
        ),
    )
    job_outputs: dict[str, dict[str, Any]] = {}

    database = SessionLocal()
    try:
        with capture_analysis_metrics(collector):
            with measure_analysis_stage("load_sources"):
                conversation = _conversation(database, conversation_id)
                experience_messages = unprocessed_experience_messages(
                    conversation,
                    database,
                )
                job_messages = unprocessed_job_messages(conversation, database)
                if not experience_messages and not job_messages:
                    raise RuntimeError("No unprocessed conversation content is available.")
                all_user_messages = sorted(
                    {
                        message.id: message
                        for message in [*experience_messages, *job_messages]
                    }.values(),
                    key=lambda message: message.sequence,
                )
                source_messages = all_user_messages if routed else job_messages
                job_sources = job_sources_for_messages(
                    source_messages,
                    conversation.user_id,
                    database,
                )
                routing_sources = (
                    _routing_sources(
                        conversation,
                        all_user_messages,
                        job_sources,
                        database,
                    )
                    if routed
                    else []
                )
                unique_sources: dict[str, str] = {}
                for source in job_sources:
                    key = (
                        f"attachment:{source.attachment_id}"
                        if source.attachment_id
                        else f"message:{source.message_id}"
                    )
                    unique_sources.setdefault(key, source.text)
                unique_source_tokens, token_method = _exact_text_tokens(
                    list(unique_sources.values()),
                    collector.model,
                )
                collector.set_source_metrics(
                    message_count=len({
                        message.id
                        for message in [*experience_messages, *job_messages]
                    }),
                    unique_source_tokens=unique_source_tokens,
                    token_method=token_method,
                )
                existing_jobs = list(database.scalars(
                    select(JobAnalysisRecord).where(
                        JobAnalysisRecord.user_id == conversation.user_id
                    )
                ).all())

            with TemporaryDirectory(prefix="career-memory-benchmark-") as vector_root:
                with measure_analysis_stage("prepare_retriever"):
                    retriever = _build_retriever(
                        database,
                        conversation.user_id,
                        vector_root,
                    )
                job_ai = create_job_analysis_ai(experience_retriever=retriever)

                def resolve_job(
                    candidate: ConversationJobCandidate,
                ) -> JobWorkflowResolution:
                    stored = next(
                        (
                            item for item in existing_jobs
                            if job_contents_match(
                                candidate.posting_content,
                                item.posting_content,
                            )
                        ),
                        None,
                    )
                    if stored is not None:
                        return JobWorkflowResolution(
                            job_id=stored.id,
                            created=False,
                        )
                    fingerprint = job_content_fingerprint(
                        candidate.posting_content
                    )
                    result = job_ai.invoke(JobAnalysisRequest(
                        client_request_id=(
                            f"benchmark-job-{run_number}-{fingerprint[:24]}"
                        ),
                        posting_id=f"benchmark-posting-{fingerprint[:24]}",
                        company_name=candidate.company_name,
                        role_name=candidate.role_name,
                        posting_title=candidate.posting_title,
                        source_url=candidate.source_url,
                        posting_content=candidate.posting_content,
                    ))
                    job_outputs[result.analysis_id] = result.model_dump(mode="json")
                    return JobWorkflowResolution(
                        job_id=result.analysis_id,
                        created=True,
                    )

                def build_experience_sources(candidates):
                    return _build_experience_sources(
                        experience_messages,
                        candidates,
                        conversation.user_id,
                        database,
                    )

                assistant_contexts: list[AssistantConversationContext] = []

                def build_routed_experience_sources(
                    candidates: list[ConversationJobCandidate],
                    routed_content: RoutedConversationContent,
                ) -> list[EvidenceSource]:
                    nonlocal assistant_contexts
                    sources = _build_experience_sources(
                        experience_messages,
                        candidates,
                        conversation.user_id,
                        database,
                    )
                    included: list[EvidenceSource] = []
                    included_route_ids: set[str] = set()
                    for source in sources:
                        route_id = _route_id_for_evidence(
                            source,
                            experience_messages,
                        )
                        if route_id is None or (
                            route_id not in routed_content.categories
                            or route_id in routed_content.experience_source_ids
                        ):
                            included.append(source)
                            if route_id is not None:
                                included_route_ids.add(route_id)
                    assistant_contexts = [
                        context
                        for context in routed_content.assistant_contexts
                        if set(context.for_user_source_ids) & included_route_ids
                    ]
                    return included

                def analyze_experiences(sources):
                    message_ids = list(dict.fromkeys(
                        source.message_id
                        for source in sources
                        if source.message_id
                    ))
                    attachment_ids = list(dict.fromkeys(
                        source.attachment_id
                        for source in sources
                        if source.attachment_id
                    ))
                    organize_kwargs: dict[str, Any] = {"sources": sources}
                    if assistant_contexts:
                        organize_kwargs["assistant_contexts"] = assistant_contexts
                    return experience_ai.organize(
                        ExperienceExtractionRequest(
                            client_request_id=(
                                f"benchmark-experience-{run_number}-{uuid4()}"
                            ),
                            input_type=ExperienceExtractionInputType.CONVERSATION,
                            conversation_id=conversation.id,
                            from_sequence=experience_messages[0].sequence,
                            to_sequence=experience_messages[-1].sequence,
                            message_ids=message_ids,
                            attachment_ids=attachment_ids,
                        ),
                        **organize_kwargs,
                    )

                def route_content(
                    sources: list[ConversationRouteSource],
                ) -> RoutedConversationContent:
                    if content_router is None:
                        return conservative_fallback_route(sources)
                    try:
                        return content_router.route(sources)
                    except Exception as error:
                        return conservative_fallback_route(
                            sources,
                            reason=(
                                f"{error.__class__.__name__}: "
                                f"{str(error)[:240]}"
                            ),
                        )

                workflow = ConversationAnalysisWorkflow(
                    discover_jobs=discovery_ai.discover,
                    resolve_job=resolve_job,
                    build_experience_sources=build_experience_sources,
                    analyze_experiences=analyze_experiences,
                    route_content=route_content if routed else None,
                    build_routed_experience_sources=(
                        build_routed_experience_sources if routed else None
                    ),
                )
                state = workflow.invoke(
                    job_sources,
                    routing_sources=routing_sources,
                )

        database_writes_detected = bool(
            database.new or database.dirty or database.deleted
        )
        database.rollback()
        experience_result = state.get("experience_result")
        return {
            "label": label,
            "run_number": run_number,
            "conversation_id": conversation.id,
            "database_writes_detected": database_writes_detected,
            "metrics": collector.to_dict(),
            "workflow": {
                "steps": state.get("steps", []),
                "failures": state.get("failures", []),
                "job_discovery_succeeded": state.get(
                    "job_discovery_succeeded",
                    False,
                ),
                "experience_succeeded": state.get(
                    "experience_succeeded",
                    False,
                ),
                "content_router_fallback_used": bool(
                    state.get("content_route")
                    and state["content_route"].fallback_used
                ),
                "content_router_fallback_reason": (
                    state["content_route"].fallback_reason
                    if state.get("content_route")
                    else None
                ),
            },
            "result": {
                "experience_count": (
                    len(experience_result.experience_drafts)
                    if experience_result is not None
                    else 0
                ),
                "job_count": len(state.get("job_results", [])),
                "experience": _safe_experience_output(experience_result),
                "jobs": list(job_outputs.values()),
                "job_candidates": [
                    _candidate_output(candidate)
                    for candidate in state.get("unique_job_candidates", [])
                ],
            },
        }
    finally:
        database.rollback()
        database.close()


def _load_fixture(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("Benchmark fixture must contain messages.")
    required = {"id", "sequence", "role", "content"}
    if any(not isinstance(item, dict) or not required <= item.keys() for item in messages):
        raise ValueError("Every fixture message needs id, sequence, role, and content.")
    if any(item["role"] not in {"user", "assistant"} for item in messages):
        raise ValueError("Fixture message role must be user or assistant.")
    return payload


def _run_fixture_once(
    *,
    fixture: dict[str, Any],
    fixture_path: Path,
    label: str,
    run_number: int,
    discovery_ai: ConversationJobDiscoveryAI,
    experience_ai: ExperienceAI,
    routed: bool,
    content_router: ConversationContentRouterAI | None,
) -> dict[str, Any]:
    """Run the production workflow against synthetic in-memory sources."""

    user_messages = [
        message for message in fixture["messages"] if message["role"] == "user"
    ]
    job_sources = [
        JobSourceText(
            message_id=str(message["id"]),
            text=str(message["content"]),
            title=f"대화 메시지 {message['sequence']}",
        )
        for message in user_messages
    ]
    routing_sources = [
        ConversationRouteSource(
            source_id=f"message:{message['id']}",
            message_id=str(message["id"]),
            role="user",
            text=str(message["content"]),
            sequence=int(message["sequence"]),
            title=f"대화 메시지 {message['sequence']}",
        )
        for message in fixture["messages"]
        if message["role"] == "user"
    ] if routed else []
    if routed:
        user_by_sequence = {
            int(message["sequence"]): message
            for message in fixture["messages"]
            if message["role"] == "user"
        }
        for message in fixture["messages"]:
            if message["role"] != "assistant":
                continue
            next_user = user_by_sequence.get(int(message["sequence"]) + 1)
            if next_user is None or not _needs_assistant_context(
                str(next_user["content"])
            ):
                continue
            excerpt = _assistant_context_excerpt(str(message["content"]))
            if not excerpt:
                continue
            routing_sources.append(ConversationRouteSource(
                source_id=f"message:{message['id']}",
                message_id=str(message["id"]),
                role="assistant",
                text=excerpt,
                sequence=int(message["sequence"]),
                title=f"대화 메시지 {message['sequence']}",
            ))
        routing_sources.sort(key=lambda item: (item.sequence, item.source_id))
    run_id = f"BENCH-{uuid4()}"
    collector = AnalysisMetricsCollector(
        run_id=run_id,
        provider=get_ai_provider(),
        model=get_chat_model_name(),
        architecture_version=(
            ANALYSIS_ARCHITECTURE_VERSION
            if routed
            else LEGACY_ANALYSIS_ARCHITECTURE_VERSION
        ),
    )
    source_tokens, token_method = _exact_text_tokens(
        [source.text for source in job_sources],
        collector.model,
    )
    collector.set_source_metrics(
        message_count=len(user_messages),
        unique_source_tokens=source_tokens,
        token_method=token_method,
    )
    job_outputs: dict[str, dict[str, Any]] = {}

    with capture_analysis_metrics(collector):
        with TemporaryDirectory(prefix="career-memory-gold-benchmark-"):
            job_ai = create_job_analysis_ai(experience_retriever=None)

            def resolve_job(
                candidate: ConversationJobCandidate,
            ) -> JobWorkflowResolution:
                fingerprint = job_content_fingerprint(candidate.posting_content)
                result = job_ai.invoke(JobAnalysisRequest(
                    client_request_id=(
                        f"gold-job-{run_number}-{fingerprint[:24]}"
                    ),
                    posting_id=f"gold-posting-{fingerprint[:24]}",
                    company_name=candidate.company_name,
                    role_name=candidate.role_name,
                    posting_title=candidate.posting_title,
                    source_url=candidate.source_url,
                    posting_content=candidate.posting_content,
                ))
                job_outputs[result.analysis_id] = result.model_dump(mode="json")
                return JobWorkflowResolution(
                    job_id=result.analysis_id,
                    created=True,
                )

            def build_experience_sources(
                candidates: list[ConversationJobCandidate],
            ) -> list[EvidenceSource]:
                postings_by_message: dict[str, list[str]] = {}
                for candidate in candidates:
                    postings_by_message.setdefault(candidate.message_id, []).append(
                        candidate.posting_content
                    )
                sources: list[EvidenceSource] = []
                for message in user_messages:
                    text = str(message["content"])
                    for posting in sorted(
                        postings_by_message.get(str(message["id"]), []),
                        key=len,
                        reverse=True,
                    ):
                        text = text.replace(posting, "\n")
                    if text.strip():
                        sources.append(EvidenceSource(
                            id=f"source-{message['id']}",
                            type=EvidenceSourceType.MESSAGE_TEXT,
                            title=f"대화 메시지 {message['sequence']}",
                            message_id=str(message["id"]),
                            text=text.strip(),
                        ))
                return sources

            assistant_contexts: list[AssistantConversationContext] = []

            def build_routed_experience_sources(
                candidates: list[ConversationJobCandidate],
                routed_content: RoutedConversationContent,
            ) -> list[EvidenceSource]:
                nonlocal assistant_contexts
                sources = build_experience_sources(candidates)
                included = [
                    source
                    for source in sources
                    if (
                        f"message:{source.message_id}"
                        not in routed_content.categories
                        or f"message:{source.message_id}"
                        in routed_content.experience_source_ids
                    )
                ]
                included_route_ids = {
                    f"message:{source.message_id}"
                    for source in included
                    if source.message_id
                }
                assistant_contexts = [
                    context
                    for context in routed_content.assistant_contexts
                    if set(context.for_user_source_ids) & included_route_ids
                ]
                return included

            def analyze_experiences(sources: list[EvidenceSource]):
                organize_kwargs: dict[str, Any] = {"sources": sources}
                if assistant_contexts:
                    organize_kwargs["assistant_contexts"] = assistant_contexts
                return experience_ai.organize(
                    ExperienceExtractionRequest(
                        client_request_id=(
                            f"gold-experience-{run_number}-{uuid4()}"
                        ),
                        input_type=ExperienceExtractionInputType.CONVERSATION,
                        conversation_id=str(fixture["conversation_id"]),
                        from_sequence=min(
                            int(message["sequence"]) for message in user_messages
                        ),
                        to_sequence=max(
                            int(message["sequence"]) for message in user_messages
                        ),
                        message_ids=[
                            str(source.message_id)
                            for source in sources
                            if source.message_id
                        ],
                    ),
                    **organize_kwargs,
                )

            def route_content(
                sources: list[ConversationRouteSource],
            ) -> RoutedConversationContent:
                if content_router is None:
                    return conservative_fallback_route(sources)
                try:
                    return content_router.route(sources)
                except Exception as error:
                    return conservative_fallback_route(
                        sources,
                        reason=(
                            f"{error.__class__.__name__}: {str(error)[:240]}"
                        ),
                    )

            workflow = ConversationAnalysisWorkflow(
                discover_jobs=discovery_ai.discover,
                resolve_job=resolve_job,
                build_experience_sources=build_experience_sources,
                analyze_experiences=analyze_experiences,
                route_content=route_content if routed else None,
                build_routed_experience_sources=(
                    build_routed_experience_sources if routed else None
                ),
            )
            state = workflow.invoke(
                job_sources,
                routing_sources=routing_sources,
            )

    experience_result = state.get("experience_result")
    return {
        "label": label,
        "run_number": run_number,
        "fixture_id": fixture.get("fixture_id"),
        "fixture_path": str(fixture_path.resolve()),
        "database_writes_detected": False,
        "metrics": collector.to_dict(),
        "workflow": {
            "steps": state.get("steps", []),
            "failures": state.get("failures", []),
            "job_discovery_succeeded": state.get(
                "job_discovery_succeeded", False
            ),
            "experience_succeeded": state.get("experience_succeeded", False),
            "content_router_fallback_used": bool(
                state.get("content_route")
                and state["content_route"].fallback_used
            ),
            "content_router_fallback_reason": (
                state["content_route"].fallback_reason
                if state.get("content_route")
                else None
            ),
        },
        "result": {
            "experience_count": (
                len(experience_result.experience_drafts)
                if experience_result is not None
                else 0
            ),
            "job_count": len(state.get("job_results", [])),
            "experience": _safe_experience_output(experience_result),
            "jobs": list(job_outputs.values()),
            "job_candidates": [
                _candidate_output(candidate)
                for candidate in state.get("unique_job_candidates", [])
            ],
        },
    }


def _median(values: list[float | int | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return round(statistics.median(clean), 4) if clean else None


def _aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = [run["metrics"] for run in runs]
    warm = metrics[1:]
    stage_names = sorted({
        stage
        for item in metrics
        for stage in item.get("stages", {})
    })
    return {
        "run_count": len(runs),
        "cold_run": {
            "input_tokens": metrics[0]["input_tokens"],
            "cached_tokens": metrics[0]["cached_tokens"],
            "output_tokens": metrics[0]["output_tokens"],
            "llm_call_count": metrics[0]["llm_call_count"],
            "total_duration_ms": metrics[0]["total_duration_ms"],
            "estimated_cost_usd": metrics[0]["estimated_cost_usd"],
        },
        "all_runs_median": {
            "input_tokens": _median([item["input_tokens"] for item in metrics]),
            "cached_tokens": _median([item["cached_tokens"] for item in metrics]),
            "output_tokens": _median([item["output_tokens"] for item in metrics]),
            "llm_call_count": _median([item["llm_call_count"] for item in metrics]),
            "token_amplification": _median([
                item["token_amplification"] for item in metrics
            ]),
            "unique_source_ratio_pct": _median([
                item["unique_source_ratio_pct"] for item in metrics
            ]),
            "total_duration_ms": _median([
                item["total_duration_ms"] for item in metrics
            ]),
            "estimated_cost_usd": _median([
                item["estimated_cost_usd"] for item in metrics
            ]),
        },
        "warm_runs_median": {
            "input_tokens": _median([item["input_tokens"] for item in warm]),
            "cached_tokens": _median([item["cached_tokens"] for item in warm]),
            "output_tokens": _median([item["output_tokens"] for item in warm]),
            "total_duration_ms": _median([
                item["total_duration_ms"] for item in warm
            ]),
            "estimated_cost_usd": _median([
                item["estimated_cost_usd"] for item in warm
            ]),
        },
        "stage_duration_ms_median": {
            stage: _median([
                item.get("stages", {}).get(stage, {}).get("duration_ms")
                for item in metrics
            ])
            for stage in stage_names
        },
        "database_write_guard_passed": all(
            not run["database_writes_detected"] for run in runs
        ),
    }


def run_benchmark(
    *,
    conversation_id: str | None,
    fixture_path: Path | None = None,
    version: str,
    warm_runs: int,
    output: Path | None,
    routed: bool = False,
) -> tuple[Path, dict[str, Any]]:
    discovery_ai = ConversationJobDiscoveryAI()
    experience_ai = ExperienceAI()
    content_router = ConversationContentRouterAI() if routed else None
    runs = []
    total_runs = 1 + max(0, warm_runs)
    fixture = _load_fixture(fixture_path) if fixture_path else None
    for index in range(total_runs):
        common = {
            "label": "cold" if index == 0 else f"warm-{index}",
            "run_number": index + 1,
            "discovery_ai": discovery_ai,
            "experience_ai": experience_ai,
            "routed": routed,
            "content_router": content_router,
        }
        if fixture is not None and fixture_path is not None:
            runs.append(_run_fixture_once(
                fixture=fixture,
                fixture_path=fixture_path,
                **common,
            ))
        else:
            runs.append(_run_once(
                conversation_id=conversation_id,
                **common,
            ))
    report = {
        "schema_version": "conversation-analysis-benchmark-v1",
        "architecture_version": (
            ANALYSIS_ARCHITECTURE_VERSION
            if routed
            else LEGACY_ANALYSIS_ARCHITECTURE_VERSION
        ),
        "benchmark_version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider": get_ai_provider(),
        "model": get_chat_model_name(),
        "input": (
            {
                "type": "fixture",
                "fixture_id": fixture.get("fixture_id"),
                "fixture_path": str(fixture_path.resolve()),
            }
            if fixture is not None and fixture_path is not None
            else {"type": "database", "conversation_id": conversation_id}
        ),
        "aggregate": _aggregate(runs),
        "runs": runs,
    }
    if output is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = DEFAULT_REPORT_ROOT / f"{version}-{timestamp}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output, report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark the current conversation analysis without database writes."
        )
    )
    parser.add_argument("--conversation-id")
    parser.add_argument(
        "--fixture",
        type=Path,
        help=(
            "Run against an in-memory JSON fixture instead of the database. "
            f"Gold fixture: {DEFAULT_GOLD_FIXTURE}"
        ),
    )
    parser.add_argument("--version", default="baseline-v1")
    parser.add_argument("--warm-runs", type=int, default=3)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--routed",
        action="store_true",
        help="Use the conservative content router architecture.",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    output, report = run_benchmark(
        conversation_id=args.conversation_id,
        fixture_path=args.fixture,
        version=args.version,
        warm_runs=args.warm_runs,
        output=args.output,
        routed=args.routed,
    )
    print(json.dumps({
        "report_path": str(output.resolve()),
        "aggregate": report["aggregate"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
