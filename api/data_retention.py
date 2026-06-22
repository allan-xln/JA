from __future__ import annotations

from typing import Any

from api.config import settings
from api.database import TEMPORARY_SUPABASE_MESSAGE, SupabaseError, is_temporary_supabase_error, supabase
from api.logger import logger


RETENTION_SCHEMA_MESSAGE = (
    "Schema de retenção ainda não aplicado. Execute sql/009_data_retention_and_cleanup.sql no Supabase."
)


def _retention_schema_missing(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "prune_eletrofrio_operational_data" in text
        or "eletrofrio_retention_runs" in text
        or "pgrst202" in text
        or "pgrst205" in text
        or "schema cache" in text
    )


def _database_temporarily_read_only(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        is_temporary_supabase_error(exc)
        or "read-only transaction" in text
        or "database system is in recovery mode" in text
        or "57p03" in text
        or "25006" in text
    )


def retention_payload(
    *,
    dry_run: bool = True,
    telemetry_days: int | None = None,
    alarm_days: int | None = None,
    insight_days: int | None = None,
    communication_days: int | None = None,
    collector_run_days: int | None = None,
    resolved_anomaly_days: int | None = None,
    batch_limit: int | None = None,
) -> dict[str, Any]:
    def days(value: int | None, fallback: int) -> int:
        return max(0, value if value is not None else fallback)

    return {
        "p_dry_run": dry_run,
        "p_telemetry_days": days(telemetry_days, settings.retention_telemetry_days),
        "p_alarm_days": days(alarm_days, settings.retention_alarm_days),
        "p_insight_days": days(insight_days, settings.retention_insight_days),
        "p_communication_days": days(communication_days, settings.retention_communication_days),
        "p_collector_run_days": days(collector_run_days, settings.retention_collector_run_days),
        "p_resolved_anomaly_days": days(resolved_anomaly_days, settings.retention_resolved_anomaly_days),
        "p_batch_limit": max(100, min(batch_limit or settings.retention_batch_limit, 50000)),
    }


def prune_operational_data(
    *,
    dry_run: bool = True,
    telemetry_days: int | None = None,
    alarm_days: int | None = None,
    insight_days: int | None = None,
    communication_days: int | None = None,
    collector_run_days: int | None = None,
    resolved_anomaly_days: int | None = None,
    batch_limit: int | None = None,
) -> dict[str, Any]:
    payload = retention_payload(
        dry_run=dry_run,
        telemetry_days=telemetry_days,
        alarm_days=alarm_days,
        insight_days=insight_days,
        communication_days=communication_days,
        collector_run_days=collector_run_days,
        resolved_anomaly_days=resolved_anomaly_days,
        batch_limit=batch_limit,
    )
    try:
        result = supabase.rpc("prune_eletrofrio_operational_data", payload)
    except SupabaseError as exc:
        if _database_temporarily_read_only(exc):
            logger.warning("Banco indisponível para retenção operacional: %s", exc)
            return {
                "dry_run": dry_run,
                "schema_applied": False,
                "data_unavailable": True,
                "message": TEMPORARY_SUPABASE_MESSAGE,
                "parameters": payload,
            }
        if _retention_schema_missing(exc):
            logger.warning("%s: %s", RETENTION_SCHEMA_MESSAGE, exc)
            return {
                "dry_run": dry_run,
                "schema_applied": False,
                "message": RETENTION_SCHEMA_MESSAGE,
                "parameters": payload,
            }
        raise
    if isinstance(result, dict):
        return {"schema_applied": True, **result}
    return {"schema_applied": True, "result": result, "parameters": payload}


def scheduled_retention_cleanup() -> dict[str, Any] | None:
    if not settings.retention_cleanup_enabled:
        return None
    result = prune_operational_data(dry_run=settings.retention_cleanup_dry_run)
    logger.info("Retenção operacional executada: %s", result)
    return result
