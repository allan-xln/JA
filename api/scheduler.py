from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from api.collector import run_collector_once
from api.config import settings
from api.data_retention import scheduled_retention_cleanup
from api.database import supabase
from api.logger import logger
from api.repositories import (
    ensure_collector_settings,
    get_collector_settings,
    list_collector_runs,
    parse_utc_datetime,
    reconcile_stale_collector_runs,
    update_collector_settings,
)


MIN_INTERVAL_MINUTES = 5
STALE_RUN_MINUTES = 15
_collector_lock = threading.Lock()
_scheduler_task: asyncio.Task[None] | None = None
_stop_event: asyncio.Event | None = None
_fallback_settings: dict[str, Any] | None = None
_last_retention_cleanup_at: datetime | None = None


class CollectorBusyError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_dt(value: Any) -> datetime | None:
    return parse_utc_datetime(value)


def _running_state_is_stale(data: dict[str, Any]) -> bool:
    if not data.get("running") or _collector_lock.locked():
        return False
    marker = _parse_dt(data.get("last_run_at")) or _parse_dt(data.get("updated_at")) or _parse_dt(data.get("next_run_at"))
    if not marker:
        return False
    return _now() - marker > timedelta(minutes=STALE_RUN_MINUTES)


def _is_noisy_timeout_run(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    message = str(row.get("error_message") or "")
    return (
        row.get("trigger_source") in {"loop", "schedule"}
        and row.get("units_count", 0) == 0
        and row.get("alarms_count", 0) == 0
        and (
            "Timeout na API Eletrofrio: unidades" in message
            or (row.get("status") == "running" and _run_is_stale(row, max_age_minutes=5))
        )
    )


def _maybe_run_retention_cleanup() -> None:
    global _last_retention_cleanup_at
    if not settings.retention_cleanup_enabled:
        return
    now = _now()
    interval = timedelta(hours=max(1, settings.retention_cleanup_interval_hours))
    if _last_retention_cleanup_at and now - _last_retention_cleanup_at < interval:
        return
    try:
        scheduled_retention_cleanup()
    except Exception as exc:
        logger.warning("Limpeza de retenção operacional não executada: %s", exc)
    finally:
        _last_retention_cleanup_at = now


def _run_is_stale(row: dict[str, Any], max_age_minutes: int = STALE_RUN_MINUTES) -> bool:
    if row.get("status") != "running" or row.get("finished_at"):
        return False
    started_at = _parse_dt(row.get("started_at"))
    return bool(started_at and _now() - started_at > timedelta(minutes=max_age_minutes))


def _normalize_settings(row: dict[str, Any] | None = None) -> dict[str, Any]:
    data = row or ensure_collector_settings(settings.collector_interval_minutes)
    if _running_state_is_stale(data):
        data = update_collector_settings(
            {
                "running": False,
                "last_status": "error",
                "last_error": "Execução anterior ficou em aberto e foi liberada automaticamente.",
            }
        )
    interval = max(MIN_INTERVAL_MINUTES, int(data.get("interval_minutes") or settings.collector_interval_minutes or MIN_INTERVAL_MINUTES))
    enabled = data.get("enabled")
    if enabled is None:
        enabled = data.get("is_enabled", False)
    if not bool(enabled) and data.get("running") and not _collector_lock.locked():
        data = update_collector_settings({"running": False})
    return {
        "enabled": bool(enabled),
        "intervalMinutes": interval,
        "alertCooldownMinutes": max(MIN_INTERVAL_MINUTES, int(data.get("alert_cooldown_minutes") or settings.whatsapp_alert_cooldown_minutes)),
        "lastRunAt": data.get("last_run_at"),
        "nextRunAt": data.get("next_run_at"),
        "running": bool(data.get("running", False)) or _collector_lock.locked(),
        "lastStatus": data.get("last_status") or "never_run",
        "lastError": data.get("last_error"),
        "createdAt": data.get("created_at"),
        "updatedAt": data.get("updated_at"),
    }


def get_settings_status() -> dict[str, Any]:
    global _fallback_settings
    if not supabase.enabled():
        return {
            "enabled": False,
            "intervalMinutes": max(MIN_INTERVAL_MINUTES, settings.collector_interval_minutes),
            "alertCooldownMinutes": max(MIN_INTERVAL_MINUTES, settings.whatsapp_alert_cooldown_minutes),
            "lastRunAt": None,
            "nextRunAt": None,
            "running": False,
            "lastStatus": "error",
            "lastError": "Supabase não configurado.",
            "createdAt": None,
            "updatedAt": None,
        }
    stored_settings = get_collector_settings()
    if supabase.enabled():
        try:
            reconcile_stale_collector_runs(max(STALE_RUN_MINUTES, settings.collector_interval_minutes * 3), 20)
        except Exception as exc:
            logger.warning("Não foi possível verificar execuções antigas do coletor: %s", exc)
    status = _normalize_settings(stored_settings or _fallback_settings)
    if stored_settings is None and _fallback_settings is not None:
        status["lastError"] = status.get("lastError") or "Configuração em memória; tabela de automação indisponível no Supabase."
    try:
        runs = list_collector_runs(30)
        clean_runs = [row for row in runs if not _is_noisy_timeout_run(row)]
        latest = next((row for row in clean_runs if row.get("status") != "running"), clean_runs[0] if clean_runs else None)
        last_good = next((row for row in runs if row.get("status") in {"success", "partial_success"}), None)
    except Exception as exc:
        logger.warning("Não foi possível carregar última execução do coletor: %s", exc)
        latest = None
        last_good = None

    if latest:
        status["lastRunAt"] = status.get("lastRunAt") or latest.get("finished_at") or latest.get("started_at")
        status["lastStatus"] = latest.get("status") or status.get("lastStatus")
        if not last_good:
            status["lastError"] = status.get("lastError") or latest.get("error_message")
        elif status.get("lastStatus") == "running" and _is_noisy_timeout_run(latest):
            status["lastStatus"] = last_good.get("status") or "success"
            status["lastError"] = None
        else:
            status["lastError"] = None
    elif last_good:
        status["lastRunAt"] = last_good.get("finished_at") or last_good.get("started_at")
        status["lastStatus"] = last_good.get("status") or "success"
        status["lastError"] = None
    if last_good and "Timeout na API Eletrofrio: unidades" in str(status.get("lastError") or ""):
        status["lastStatus"] = last_good.get("status") or "success"
        status["lastError"] = None
    status["lastGoodRun"] = last_good
    return status


def save_settings(enabled: bool, interval_minutes: int, alert_cooldown_minutes: int | None = None) -> dict[str, Any]:
    global _fallback_settings
    if interval_minutes < MIN_INTERVAL_MINUTES:
        raise ValueError(f"Intervalo mínimo de coleta é {MIN_INTERVAL_MINUTES} minutos.")
    cooldown = max(MIN_INTERVAL_MINUTES, alert_cooldown_minutes or settings.whatsapp_alert_cooldown_minutes)
    next_run_at = _now() + timedelta(minutes=interval_minutes) if enabled else None
    payload = {
        "enabled": enabled,
        "is_enabled": enabled,
        "interval_minutes": interval_minutes,
        "alert_cooldown_minutes": cooldown,
        "next_run_at": _iso(next_run_at),
        "last_error": None,
    }
    row = update_collector_settings(payload)
    if row.get("persistence_warning"):
        _fallback_settings = {**(_fallback_settings or {}), **row}
    else:
        _fallback_settings = None
    logger.info("Configuração do scheduler alterada: enabled=%s interval=%s cooldown=%s", enabled, interval_minutes, cooldown)
    return _normalize_settings(row)


def _mark_running() -> None:
    update_collector_settings({"running": True, "last_status": "running", "last_error": None})


def _mark_finished(status: str, interval_minutes: int, error: str | None = None) -> None:
    now = _now()
    next_run = now + timedelta(minutes=max(MIN_INTERVAL_MINUTES, interval_minutes))
    update_collector_settings(
        {
            "running": False,
            "last_status": status,
            "last_error": error,
            "last_run_at": _iso(now),
            "next_run_at": _iso(next_run),
        }
    )


def run_collector_managed(trigger_source: str = "manual") -> dict[str, Any]:
    reconcile_stale_collector_runs(max(STALE_RUN_MINUTES, settings.collector_interval_minutes * 3), 20)
    current = _normalize_settings(get_collector_settings())
    if current["running"] and not _collector_lock.locked():
        logger.warning("Coleta ignorada: banco indica execução em andamento.")
        raise CollectorBusyError("Já existe uma coleta registrada como em execução. Aguarde a finalização antes de iniciar outra.")

    if not _collector_lock.acquire(blocking=False):
        logger.warning("Coleta ignorada: execução anterior ainda em andamento.")
        raise CollectorBusyError("Já existe uma coleta em execução. Aguarde a finalização antes de iniciar outra.")

    interval = current["intervalMinutes"]
    try:
        logger.info("Coleta iniciada pelo scheduler: source=%s", trigger_source)
        _mark_running()
        result = run_collector_once(trigger_source=trigger_source)
        result_status = str(result.get("status") or "success")
        warnings = result.get("warnings")
        warning_text = " | ".join(warnings) if isinstance(warnings, list) and warnings else None
        _mark_finished(result_status, interval, warning_text)
        logger.info("Coleta concluída pelo scheduler: %s", result)
        return result
    except Exception as exc:
        _mark_finished("error", interval, str(exc))
        logger.exception("Coleta falhou no scheduler")
        raise
    finally:
        _collector_lock.release()


async def _scheduler_loop() -> None:
    logger.info("Scheduler interno Eletrofrio iniciado.")
    while _stop_event and not _stop_event.is_set():
        try:
            await asyncio.to_thread(_maybe_run_retention_cleanup)
            current = _normalize_settings(get_collector_settings())
            if current["enabled"]:
                next_run = _parse_dt(current.get("nextRunAt"))
                if next_run is None:
                    next_run = _now() + timedelta(minutes=current["intervalMinutes"])
                    update_collector_settings({"next_run_at": _iso(next_run)})
                elif next_run <= _now() and not _collector_lock.locked():
                    await asyncio.to_thread(run_collector_managed, "schedule")
            await asyncio.sleep(15)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Falha no loop do scheduler: %s", exc)
            try:
                update_collector_settings({"running": False, "last_status": "error", "last_error": str(exc)})
            except Exception:
                pass
            await asyncio.sleep(30)


async def start_scheduler() -> None:
    global _scheduler_task, _stop_event
    if _scheduler_task and not _scheduler_task.done():
        return
    if supabase.enabled():
        try:
            update_collector_settings({"running": False})
        except Exception as exc:
            logger.warning("Não foi possível limpar estado de execução anterior do scheduler: %s", exc)
    _stop_event = asyncio.Event()
    _scheduler_task = asyncio.create_task(_scheduler_loop())


async def stop_scheduler() -> None:
    global _scheduler_task, _stop_event
    if _stop_event:
        _stop_event.set()
    if _scheduler_task:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
    _scheduler_task = None
    _stop_event = None
    logger.info("Scheduler interno Eletrofrio encerrado.")


def run_collector_loop() -> None:
    interval_seconds = max(MIN_INTERVAL_MINUTES, settings.collector_interval_minutes) * 60
    logger.info("Scheduler externo do coletor iniciado. Intervalo base=%ss", interval_seconds)
    while True:
        try:
            _maybe_run_retention_cleanup()
            current = _normalize_settings(get_collector_settings())
            if not current["enabled"]:
                logger.info("Coleta automática desativada; scheduler externo em espera.")
                time.sleep(30)
                continue

            next_run = _parse_dt(current.get("nextRunAt"))
            if next_run is None:
                next_run = _now() + timedelta(minutes=current["intervalMinutes"])
                update_collector_settings({"next_run_at": _iso(next_run)})
                time.sleep(30)
                continue

            if next_run <= _now():
                run_collector_managed("schedule")
                continue
        except CollectorBusyError as exc:
            logger.warning("%s", exc)
        except Exception as exc:
            logger.error("Execução do coletor falhou: %s", exc)
        time.sleep(min(60, interval_seconds))


def collector_status() -> dict[str, Any]:
    status = get_settings_status()
    runs = list_collector_runs(30) if supabase.enabled() else []
    clean_runs = [row for row in runs if not _is_noisy_timeout_run(row)]
    status["latestRun"] = next((row for row in clean_runs if row.get("status") != "running"), clean_runs[0] if clean_runs else None)
    status["lastGoodRun"] = next((row for row in runs if row.get("status") in {"success", "partial_success"}), None)
    return status


if __name__ == "__main__":
    run_collector_loop()
