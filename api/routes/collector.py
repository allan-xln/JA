from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import AuthUser, current_user, require_admin
from api.database import supabase
from api.repositories import list_anomalies, list_collector_runs, parse_utc_datetime, patch_anomaly, reconcile_stale_collector_runs, utc_now_iso
from api.scheduler import CollectorBusyError, collector_status, get_settings_status, run_collector_managed, save_settings


router = APIRouter(prefix="/api/collector", tags=["collector-automation"])


class CollectorSettingsPayload(BaseModel):
    enabled: bool
    intervalMinutes: int = Field(..., ge=5)
    alertCooldownMinutes: int | None = Field(default=None, ge=5)


def is_noisy_timeout_run(row: dict) -> bool:
    message = str(row.get("error_message") or "")
    started_at = parse_utc_datetime(row.get("started_at"))
    stale_running = (
        row.get("status") == "running"
        and started_at is not None
        and datetime.now(timezone.utc) - started_at > timedelta(minutes=5)
    )
    return (
        row.get("trigger_source") in {"loop", "schedule"}
        and row.get("units_count", 0) == 0
        and row.get("alarms_count", 0) == 0
        and (
            "Timeout na API Eletrofrio: unidades" in message
            or stale_running
        )
    )


def require_supabase() -> None:
    if not supabase.enabled():
        raise HTTPException(
            status_code=503,
            detail="Supabase não configurado. Configure SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY.",
        )


@router.get("/settings")
def get_collector_settings(user: AuthUser = Depends(require_admin)):
    require_supabase()
    try:
        return get_settings_status()
    except Exception as exc:
        return fallback_collector_status(str(exc))


@router.put("/settings")
def put_collector_settings(payload: CollectorSettingsPayload, user: AuthUser = Depends(require_admin)):
    require_supabase()
    try:
        return save_settings(payload.enabled, payload.intervalMinutes, payload.alertCooldownMinutes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/run-now")
def run_collector_now(user: AuthUser = Depends(require_admin)):
    require_supabase()
    try:
        return run_collector_managed("manual")
    except CollectorBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/status")
def get_collector_status(user: AuthUser = Depends(current_user)):
    require_supabase()
    try:
        return collector_status()
    except Exception as exc:
        return fallback_collector_status(str(exc))


@router.get("/runs")
def get_collector_runs(limit: int = Query(default=30, ge=1, le=100), user: AuthUser = Depends(require_admin)):
    require_supabase()
    try:
        fetch_limit = max(50, limit * 3)
        reconcile_stale_collector_runs(limit=fetch_limit)
        rows = list_collector_runs(fetch_limit)
        visible_rows = [row for row in rows if not is_noisy_timeout_run(row)]
        return {"items": visible_rows[:limit]}
    except Exception:
        return {"items": []}


@router.get("/anomalies")
def get_collector_anomalies(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    user: AuthUser = Depends(current_user),
):
    require_supabase()
    try:
        return {"items": list_anomalies(limit, status, user.scope, offset)}
    except Exception:
        return {"items": []}


def fallback_collector_status(error: str) -> dict:
    latest_run = None
    try:
        runs = list_collector_runs(1)
        latest_run = runs[0] if runs else None
    except Exception:
        latest_run = None

    return {
        "enabled": False,
        "intervalMinutes": 5,
        "alertCooldownMinutes": 60,
        "lastRunAt": latest_run.get("finished_at") or latest_run.get("started_at") if latest_run else None,
        "nextRunAt": None,
        "running": latest_run.get("status") == "running" if latest_run else False,
        "lastStatus": latest_run.get("status") if latest_run else "never_run",
        "lastError": error,
        "createdAt": None,
        "updatedAt": None,
        "latestRun": latest_run,
    }


@router.post("/anomalies/{anomaly_id}/resolve")
def resolve_anomaly(anomaly_id: str, user: AuthUser = Depends(require_admin)):
    require_supabase()
    row = patch_anomaly(anomaly_id, {"status": "resolved", "resolved_at": utc_now_iso()})
    if not row:
        raise HTTPException(status_code=404, detail="Anomalia não encontrada.")
    return row


@router.post("/anomalies/{anomaly_id}/ignore")
def ignore_anomaly(anomaly_id: str, user: AuthUser = Depends(require_admin)):
    require_supabase()
    row = patch_anomaly(anomaly_id, {"status": "ignored", "resolved_at": utc_now_iso()})
    if not row:
        raise HTTPException(status_code=404, detail="Anomalia não encontrada.")
    return row
