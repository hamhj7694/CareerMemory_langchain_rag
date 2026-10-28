"""사용자가 저장 전 AI 분석 초안을 복구하고 분석 계보를 확인하는 API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from AI_Engine.auth.dependencies import get_current_user, require_csrf_user
from AI_Engine.database.connection import get_database_session
from AI_Engine.database.models import AnalysisRunRecord, AnalysisRunTarget, User, utc_now


router = APIRouter(prefix="/api/v2/analysis-runs", tags=["analysis-runs"])


def _owned_run(run_id: str, user_id: str, database: Session) -> AnalysisRunRecord:
    item = database.scalar(select(AnalysisRunRecord).where(
        AnalysisRunRecord.id == run_id,
        AnalysisRunRecord.user_id == user_id,
    ))
    if item is None:
        raise HTTPException(status_code=404, detail="AI 분석 기록을 찾을 수 없습니다.")
    return item


def _target_payloads(item: AnalysisRunRecord, database: Session) -> list[dict]:
    return [
        {
            "unit_id": target.unit_id,
            "target_type": target.target_type,
            "target_id": target.target_id,
            "created_at": target.created_at,
        }
        for target in database.scalars(select(AnalysisRunTarget).where(
            AnalysisRunTarget.analysis_run_id == item.id,
            AnalysisRunTarget.user_id == item.user_id,
        ))
    ]


def _run_payload(item: AnalysisRunRecord, *, include_payload: bool, database: Session) -> dict:
    result = {
        "id": item.id,
        "external_run_id": item.external_run_id,
        "client_request_id": item.client_request_id,
        "target_type": item.target_type,
        "target_id": item.target_id,
        "input_type": item.input_type,
        "source_ids": item.source_ids,
        "status": item.status,
        "versions": item.versions,
        "token_usage": item.token_usage,
        "coverage_report": item.coverage_report,
        "omitted_source_ids": item.omitted_source_ids,
        "error": item.error,
        "started_at": item.started_at,
        "completed_at": item.completed_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "targets": _target_payloads(item, database),
    }
    if include_payload:
        result["input_payload"] = item.input_payload
        result["output_payload"] = item.output_payload
    return result


@router.get("")
def list_analysis_runs(
    target_type: str | None = None,
    unclaimed_only: bool = False,
    include_payload: bool = True,
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
) -> dict:
    statement = select(AnalysisRunRecord).where(
        AnalysisRunRecord.user_id == current_user.id,
        AnalysisRunRecord.status != "discarded",
    )
    if target_type:
        statement = statement.where(AnalysisRunRecord.target_type == target_type)
    if unclaimed_only:
        statement = statement.where(
            AnalysisRunRecord.status.in_(("succeeded", "partial")),
        )
    items = list(database.scalars(statement.order_by(AnalysisRunRecord.created_at.desc())))
    if unclaimed_only:
        filtered = []
        for item in items:
            unit_ids = set((item.output_payload or {}).get("unit_ids") or [])
            claimed = {target["unit_id"] for target in _target_payloads(item, database)}
            if (unit_ids and unit_ids - claimed) or (not unit_ids and item.target_id is None):
                filtered.append(item)
        items = filtered
    items = items[:limit]
    return {
        "items": [
            _run_payload(item, include_payload=include_payload, database=database) for item in items
        ],
        "total_count": len(items),
    }


@router.get("/{run_id}")
def get_analysis_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_database_session),
) -> dict:
    return _run_payload(
        _owned_run(run_id, current_user.id, database), include_payload=True,
        database=database,
    )


@router.post("/{run_id}/discard")
def discard_analysis_run(
    run_id: str,
    current_user: User = Depends(require_csrf_user),
    database: Session = Depends(get_database_session),
) -> dict:
    item = _owned_run(run_id, current_user.id, database)
    if item.target_id or _target_payloads(item, database):
        raise HTTPException(status_code=409, detail="저장된 결과의 분석 기록은 숨길 수 없습니다.")
    item.status = "discarded"
    item.updated_at = utc_now()
    database.commit()
    return {"discarded_id": item.id}


__all__ = ["router"]
