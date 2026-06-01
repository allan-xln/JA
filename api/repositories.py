from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from api.database import SupabaseError, supabase
from api.config import settings
from api.logger import logger
from api.auth import TenantScope


_schema_warning_keys: set[str] = set()


def _warn_schema_once(key: str, message: str, exc: Exception) -> None:
    if key in _schema_warning_keys:
        return
    logger.warning("%s: %s", message, exc)
    _schema_warning_keys.add(key)


def dedupe_by_key(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    deduped: dict[Any, dict[str, Any]] = {}
    ignored_without_key = 0
    duplicate_count = 0

    for row in rows:
        value = row.get(key)
        if value is None or value == "":
            ignored_without_key += 1
            continue

        if value in deduped:
            duplicate_count += 1

        deduped[value] = row

    if ignored_without_key:
        logger.warning(
            "Ignorando %s registros sem chave '%s' antes do upsert.",
            ignored_without_key,
            key,
        )

    if duplicate_count:
        logger.warning(
            "Deduplicados %s registros repetidos pela chave '%s' antes do upsert.",
            duplicate_count,
            key,
        )

    return list(deduped.values())


def upsert_units(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean = dedupe_by_key(rows, "loja_id")
    return supabase.upsert("eletrofrio_units", clean, "loja_id")


def upsert_devices(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean = dedupe_by_key(rows, "dispositivo_id")
    return supabase.upsert("eletrofrio_devices", clean, "dispositivo_id")


def upsert_alarms(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean = dedupe_by_key(rows, "external_hash")
    return supabase.upsert("eletrofrio_alarms", clean, "external_hash")


def upsert_telemetry(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean = dedupe_by_key(rows, "external_hash")
    if not clean:
        return []

    batch_size = max(50, settings.supabase_upsert_batch_size)
    for start in range(0, len(clean), batch_size):
        batch = clean[start : start + batch_size]
        supabase.upsert(
            "eletrofrio_telemetry",
            batch,
            "external_hash",
            return_representation=False,
        )
        logger.info(
            "Telemetria persistida em lote: %s-%s de %s",
            start + 1,
            min(start + len(batch), len(clean)),
            len(clean),
        )

    return []


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_utc_datetime(value: Any) -> datetime | None:
    if not value:
        return None


def _to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def row_in_scope(row: dict[str, Any], scope: TenantScope | None) -> bool:
    if scope is None or scope.is_admin:
        return True
    loja_id = _to_int(row.get("loja_id"))
    dispositivo_id = _to_int(row.get("dispositivo_id") or row.get("equipment_id"))
    if loja_id is not None and loja_id in scope.allowed_loja_ids:
        return True
    if dispositivo_id is not None and dispositivo_id in scope.allowed_dispositivo_ids:
        return True
    return False


def filter_rows_by_scope(rows: list[dict[str, Any]], scope: TenantScope | None) -> list[dict[str, Any]]:
    if scope is None or scope.is_admin:
        return rows
    return [row for row in rows if row_in_scope(row, scope)]


def scoped_fetch_limit(limit: int, scope: TenantScope | None, multiplier: int = 6) -> int:
    if scope is None or scope.is_admin:
        return limit
    return min(max(limit * multiplier, limit, 500), 5000)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def create_collector_run(trigger_source: str = "manual") -> str | None:
    try:
        rows = supabase.insert("eletrofrio_collector_runs", {"status": "running", "trigger_source": trigger_source})
    except SupabaseError as exc:
        if "trigger_source" not in str(exc):
            raise
        _warn_schema_once(
            "collector_runs_trigger_source",
            "Tabela eletrofrio_collector_runs sem trigger_source; usando schema legado",
            exc,
        )
        rows = supabase.insert("eletrofrio_collector_runs", {"status": "running"})
    return rows[0]["id"] if rows else None


def finish_collector_run(
    run_id: str | None,
    status: str,
    counts: dict[str, int],
    error_message: str | None = None,
    anomalies_count: int = 0,
    whatsapp_alerts_count: int = 0,
) -> None:
    if not run_id:
        return
    payload = {
        "finished_at": utc_now_iso(),
        "status": status,
        "units_count": counts.get("units", 0),
        "alarms_count": counts.get("alarms", 0),
        "telemetry_count": counts.get("telemetry", 0),
        "error_message": error_message,
        "anomalies_count": anomalies_count,
        "whatsapp_alerts_count": whatsapp_alerts_count,
    }
    try:
        supabase.patch("eletrofrio_collector_runs", {"id": run_id}, payload)
    except SupabaseError as exc:
        if "anomalies_count" not in str(exc) and "whatsapp_alerts_count" not in str(exc):
            raise
        _warn_schema_once(
            "collector_runs_automation_columns",
            "Tabela eletrofrio_collector_runs sem colunas de automacao; usando schema legado",
            exc,
        )
        legacy_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"anomalies_count", "whatsapp_alerts_count"}
        }
        supabase.patch("eletrofrio_collector_runs", {"id": run_id}, legacy_payload)


def insert_insights(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean = dedupe_by_key(rows, "insight_hash")
    return supabase.upsert("eletrofrio_ai_insights", clean, "insight_hash")


def list_units(scope: TenantScope | None = None) -> list[dict[str, Any]]:
    rows = supabase.select("eletrofrio_units", {"select": "*", "order": "loja_nome.asc", "limit": 5000})
    return filter_rows_by_scope(rows, scope)


def list_devices(scope: TenantScope | None = None) -> list[dict[str, Any]]:
    rows = supabase.select("eletrofrio_devices", {"select": "*", "order": "tag.asc", "limit": 5000})
    return filter_rows_by_scope(rows, scope)


def list_alarms(limit: int = 200, scope: TenantScope | None = None) -> list[dict[str, Any]]:
    rows = supabase.select(
        "eletrofrio_alarms",
        {"select": "*", "order": "created_at.desc", "limit": scoped_fetch_limit(limit, scope)},
    )
    return filter_rows_by_scope(rows, scope)[:limit]


def list_telemetry(limit: int = 500, scope: TenantScope | None = None) -> list[dict[str, Any]]:
    rows = supabase.select(
        "eletrofrio_telemetry",
        {"select": "*", "order": "measured_at.desc", "limit": scoped_fetch_limit(limit, scope)},
    )
    return filter_rows_by_scope(rows, scope)[:limit]


def list_insights(limit: int = 100, scope: TenantScope | None = None) -> list[dict[str, Any]]:
    rows = supabase.select(
        "eletrofrio_ai_insights",
        {"select": "*", "order": "created_at.desc", "limit": scoped_fetch_limit(limit, scope)},
    )
    return filter_rows_by_scope(rows, scope)[:limit]


def get_collector_settings() -> dict[str, Any] | None:
    try:
        rows = supabase.select("eletrofrio_collector_settings", {"select": "*", "id": "eq.default", "limit": 1})
    except SupabaseError as exc:
        _warn_schema_once(
            "collector_settings_unavailable",
            "Configuração do coletor indisponível; usando fallback local",
            exc,
        )
        return None
    return rows[0] if rows else None


def ensure_collector_settings(interval_minutes: int = 5) -> dict[str, Any]:
    existing = get_collector_settings()
    if existing:
        return existing
    fallback = {
        "id": "default",
        "is_enabled": False,
        "enabled": False,
        "interval_minutes": max(5, interval_minutes),
        "alert_cooldown_minutes": 60,
        "running": False,
        "last_status": "never_run",
    }
    try:
        rows = supabase.insert("eletrofrio_collector_settings", fallback)
    except SupabaseError as exc:
        if "is_enabled" in str(exc):
            _warn_schema_once(
                "collector_settings_is_enabled",
                "Tabela eletrofrio_collector_settings sem is_enabled; usando coluna enabled legada",
                exc,
            )
            legacy_fallback = {key: value for key, value in fallback.items() if key != "is_enabled"}
            try:
                rows = supabase.insert("eletrofrio_collector_settings", legacy_fallback)
                return rows[0] if rows else legacy_fallback
            except SupabaseError as legacy_exc:
                exc = legacy_exc
        _warn_schema_once(
            "collector_settings_create_unavailable",
            "Não foi possível criar configuração do coletor; usando fallback local",
            exc,
        )
        return fallback
    return rows[0] if rows else {}


def update_collector_settings(data: dict[str, Any]) -> dict[str, Any]:
    payload = {**data, "updated_at": utc_now_iso()}
    try:
        rows = supabase.patch("eletrofrio_collector_settings", {"id": "default"}, payload)
        if rows:
            return rows[0]
        base = ensure_collector_settings()
        return {**base, **payload}
    except SupabaseError as exc:
        if "is_enabled" in str(exc):
            _warn_schema_once(
                "collector_settings_update_is_enabled",
                "Tabela eletrofrio_collector_settings sem is_enabled; persistindo formato legado",
                exc,
            )
            legacy_payload = {key: value for key, value in payload.items() if key != "is_enabled"}
            try:
                rows = supabase.patch("eletrofrio_collector_settings", {"id": "default"}, legacy_payload)
                if rows:
                    return rows[0]
                base = ensure_collector_settings()
                return {**base, **legacy_payload}
            except SupabaseError as legacy_exc:
                exc = legacy_exc
        _warn_schema_once(
            "collector_settings_update_unavailable",
            "Não foi possível persistir configuração do coletor; usando resposta transitória",
            exc,
        )
        base = ensure_collector_settings()
        return {**base, **payload, "persistence_warning": "Configuração não persistida no Supabase."}


def list_collector_runs(limit: int = 30) -> list[dict[str, Any]]:
    return supabase.select("eletrofrio_collector_runs", {"select": "*", "order": "started_at.desc", "limit": limit})


def patch_collector_run(run_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    rows = supabase.patch("eletrofrio_collector_runs", {"id": run_id}, data)
    return rows[0] if rows else None


def reconcile_stale_collector_runs(max_age_minutes: int = 60, limit: int = 20) -> list[dict[str, Any]]:
    rows = list_collector_runs(limit)
    threshold = datetime.now(timezone.utc) - timedelta(minutes=max(15, max_age_minutes))
    reconciled: list[dict[str, Any]] = []

    for row in rows:
        if row.get("status") != "running" or row.get("finished_at"):
            continue
        started_at = parse_utc_datetime(row.get("started_at"))
        if not started_at or started_at > threshold:
            continue

        error_message = (
            "Execução anterior ficou em aberto e foi marcada como interrompida automaticamente. "
            "Execute uma nova coleta para atualizar os dados operacionais."
        )
        try:
            updated = patch_collector_run(
                str(row["id"]),
                {
                    "status": "error",
                    "finished_at": utc_now_iso(),
                    "error_message": row.get("error_message") or error_message,
                },
            )
            if updated:
                reconciled.append(updated)
        except SupabaseError as exc:
            _warn_schema_once(
                "collector_runs_reconcile_unavailable",
                "Não foi possível reconciliar execuções antigas do coletor",
                exc,
            )
            break

    if reconciled:
        logger.warning("Execuções antigas do coletor reconciliadas: %s", len(reconciled))
    return reconciled


def find_open_anomaly(anomaly_key: str) -> dict[str, Any] | None:
    rows = supabase.select(
        "eletrofrio_anomalies",
        {"select": "*", "anomaly_key": f"eq.{anomaly_key}", "status": "eq.open", "limit": 1},
    )
    return rows[0] if rows else None


def insert_anomaly(row: dict[str, Any]) -> dict[str, Any] | None:
    rows = supabase.insert("eletrofrio_anomalies", row)
    return rows[0] if rows else None


def patch_anomaly(anomaly_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    rows = supabase.patch("eletrofrio_anomalies", {"id": anomaly_id}, {**data, "updated_at": utc_now_iso()})
    return rows[0] if rows else None


def list_anomalies(limit: int = 100, status: str | None = None, scope: TenantScope | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"select": "*", "order": "detected_at.desc", "limit": scoped_fetch_limit(limit, scope)}
    if status:
        params["status"] = f"eq.{status}"
    try:
        return filter_rows_by_scope(supabase.select("eletrofrio_anomalies", params), scope)[:limit]
    except SupabaseError as exc:
        _warn_schema_once(
            "anomalies_unavailable",
            "Tabela de anomalias indisponível; retornando lista vazia",
            exc,
        )
        return []


def recent_ticket_for_device(dispositivo_id: int) -> bool:
    rows = supabase.select(
        "eletrofrio_ai_insights",
        {
            "select": "id",
            "dispositivo_id": f"eq.{dispositivo_id}",
            "ticket_opened_at": "not.is.null",
            "order": "ticket_opened_at.desc",
            "limit": 1,
        },
    )
    return bool(rows)
