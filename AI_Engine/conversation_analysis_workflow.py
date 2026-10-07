"""Integrated LangGraph workflow for conversation experience and job analysis."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, TypedDict

from fastapi import HTTPException
from langgraph.graph import END, START, StateGraph

from AI_Engine.analysis_metrics import measured_analysis_stage
from AI_Engine.conversation_job_extraction import (
    ConversationJobCandidate,
    JobSourceText,
    extract_job_posting_candidates,
    job_contents_match,
)
from AI_Engine.conversation_job_workflow import JobWorkflowResolution


class IntegratedJobResult(TypedDict):
    candidate: ConversationJobCandidate
    job_id: str
    created: bool


class IntegratedAnalysisFailure(TypedDict, total=False):
    stage: str
    message: str
    source_message_id: str


class ConversationAnalysisState(TypedDict, total=False):
    job_sources: list[JobSourceText]
    routing_sources: list[Any]
    content_route: Any
    job_candidates: list[ConversationJobCandidate]
    unique_job_candidates: list[ConversationJobCandidate]
    job_results: list[IntegratedJobResult]
    experience_sources: list[Any]
    experience_result: Any
    job_discovery_succeeded: bool
    experience_partition_succeeded: bool
    experience_succeeded: bool
    failures: list[IntegratedAnalysisFailure]
    steps: list[str]


def _error_message(error: Exception) -> str:
    if isinstance(error, HTTPException):
        return str(error.detail)
    return str(error) or error.__class__.__name__


class ConversationAnalysisWorkflow:
    """Coordinate job discovery/analysis and experience extraction as one graph."""

    def __init__(
        self,
        *,
        discover_jobs: Callable[
            [list[JobSourceText]],
            list[ConversationJobCandidate],
        ],
        resolve_job: Callable[
            [ConversationJobCandidate],
            JobWorkflowResolution,
        ],
        build_experience_sources: Callable[
            [list[ConversationJobCandidate]],
            list[Any],
        ],
        analyze_experiences: Callable[[list[Any]], Any],
        route_content: Callable[[list[Any]], Any] | None = None,
        build_routed_experience_sources: Callable[
            [list[ConversationJobCandidate], Any],
            list[Any],
        ] | None = None,
    ) -> None:
        self.discover_jobs = discover_jobs
        self.resolve_job = resolve_job
        self.build_experience_sources = build_experience_sources
        self.analyze_experiences = analyze_experiences
        self.route_content = route_content
        self.build_routed_experience_sources = build_routed_experience_sources

        builder = StateGraph(ConversationAnalysisState)
        builder.add_node("discover_jobs", self._discover_jobs)
        builder.add_node("deduplicate_jobs", self._deduplicate_jobs)
        builder.add_node("partition_sources", self._partition_sources)
        builder.add_node("analyze_jobs", self._analyze_jobs)
        builder.add_node("analyze_experiences", self._analyze_experiences)
        builder.add_node("complete", self._complete)
        builder.add_edge(START, "discover_jobs")
        builder.add_edge("discover_jobs", "deduplicate_jobs")
        builder.add_edge("deduplicate_jobs", "partition_sources")
        builder.add_conditional_edges(
            "partition_sources",
            self._route_after_partition,
            {
                "jobs": "analyze_jobs",
                "experiences": "analyze_experiences",
                "complete": "complete",
            },
        )
        builder.add_conditional_edges(
            "analyze_jobs",
            self._route_after_jobs,
            {
                "experiences": "analyze_experiences",
                "complete": "complete",
            },
        )
        builder.add_edge("analyze_experiences", "complete")
        builder.add_edge("complete", END)
        self.graph = builder.compile()

    def invoke(
        self,
        job_sources: list[JobSourceText],
        *,
        routing_sources: list[Any] | None = None,
    ) -> ConversationAnalysisState:
        return self.graph.invoke({
            "job_sources": job_sources,
            "routing_sources": routing_sources or [],
            "failures": [],
            "steps": [],
        })

    @measured_analysis_stage("discover_jobs")
    def _discover_jobs(
        self,
        state: ConversationAnalysisState,
    ) -> ConversationAnalysisState:
        failures = list(state.get("failures", []))
        succeeded = True
        try:
            content_route = None
            if self.route_content is not None:
                content_route = self.route_content(
                    state.get("routing_sources", [])
                )
                candidates = list(content_route.job_candidates)
            else:
                candidates = self.discover_jobs(state.get("job_sources", []))
        except Exception as error:
            # A deterministic fallback keeps the experience branch usable and
            # lets a later request retry AI discovery because it is not marked
            # as successfully scanned.
            succeeded = False
            candidates = extract_job_posting_candidates(
                state.get("job_sources", [])
            )
            failures.append({
                "stage": (
                    "route_content"
                    if self.route_content is not None
                    else "discover_jobs"
                ),
                "message": _error_message(error),
            })
            content_route = None
        result: ConversationAnalysisState = {
            "job_candidates": candidates,
            "job_discovery_succeeded": succeeded,
            "failures": failures,
            "steps": [
                *state.get("steps", []),
                "route_content" if self.route_content is not None else "discover_jobs",
            ],
        }
        if content_route is not None:
            result["content_route"] = content_route
        return result

    @staticmethod
    @measured_analysis_stage("deduplicate_jobs")
    def _deduplicate_jobs(
        state: ConversationAnalysisState,
    ) -> ConversationAnalysisState:
        unique: list[ConversationJobCandidate] = []
        for candidate in state.get("job_candidates", []):
            if any(
                job_contents_match(
                    candidate.posting_content,
                    stored.posting_content,
                )
                for stored in unique
            ):
                continue
            unique.append(candidate)
        return {
            "unique_job_candidates": unique,
            "steps": [*state.get("steps", []), "deduplicate_jobs"],
        }

    @measured_analysis_stage("partition_sources")
    def _partition_sources(
        self,
        state: ConversationAnalysisState,
    ) -> ConversationAnalysisState:
        failures = list(state.get("failures", []))
        succeeded = True
        try:
            content_route = state.get("content_route")
            if (
                content_route is not None
                and self.build_routed_experience_sources is not None
            ):
                sources = self.build_routed_experience_sources(
                    state.get("unique_job_candidates", []),
                    content_route,
                )
            else:
                sources = self.build_experience_sources(
                    state.get("unique_job_candidates", [])
                )
        except Exception as error:
            succeeded = False
            sources = []
            failures.append({
                "stage": "partition_sources",
                "message": _error_message(error),
            })
        return {
            "experience_sources": sources,
            "experience_partition_succeeded": succeeded,
            "experience_succeeded": succeeded and not sources,
            "failures": failures,
            "steps": [*state.get("steps", []), "partition_sources"],
        }

    @staticmethod
    def _route_after_partition(
        state: ConversationAnalysisState,
    ) -> Literal["jobs", "experiences", "complete"]:
        if state.get("unique_job_candidates"):
            return "jobs"
        if state.get("experience_sources"):
            return "experiences"
        return "complete"

    @measured_analysis_stage("analyze_jobs")
    def _analyze_jobs(
        self,
        state: ConversationAnalysisState,
    ) -> ConversationAnalysisState:
        failures = list(state.get("failures", []))
        results: list[IntegratedJobResult] = []
        for candidate in state.get("unique_job_candidates", []):
            try:
                resolved = self.resolve_job(candidate)
            except Exception as error:
                failures.append({
                    "stage": "analyze_jobs",
                    "message": _error_message(error),
                    "source_message_id": candidate.message_id,
                })
                # Provider/quota failures usually affect every remaining item;
                # stop here so one request does not multiply failed AI calls.
                break
            results.append({
                "candidate": candidate,
                "job_id": resolved.job_id,
                "created": resolved.created,
            })
        return {
            "job_results": results,
            "failures": failures,
            "steps": [*state.get("steps", []), "analyze_jobs"],
        }

    @staticmethod
    def _route_after_jobs(
        state: ConversationAnalysisState,
    ) -> Literal["experiences", "complete"]:
        return "experiences" if state.get("experience_sources") else "complete"

    @measured_analysis_stage("analyze_experiences")
    def _analyze_experiences(
        self,
        state: ConversationAnalysisState,
    ) -> ConversationAnalysisState:
        failures = list(state.get("failures", []))
        succeeded = True
        result = None
        try:
            result = self.analyze_experiences(
                state.get("experience_sources", [])
            )
        except Exception as error:
            succeeded = False
            failures.append({
                "stage": "analyze_experiences",
                "message": _error_message(error),
            })
        return {
            "experience_result": result,
            "experience_succeeded": succeeded,
            "failures": failures,
            "steps": [*state.get("steps", []), "analyze_experiences"],
        }

    @staticmethod
    @measured_analysis_stage("complete")
    def _complete(
        state: ConversationAnalysisState,
    ) -> ConversationAnalysisState:
        return {"steps": [*state.get("steps", []), "complete"]}


__all__ = [
    "ConversationAnalysisState",
    "ConversationAnalysisWorkflow",
    "IntegratedAnalysisFailure",
    "IntegratedJobResult",
]
