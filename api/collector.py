from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import time
from typing import Any

from api.config import settings
from api.database import supabase
from api.decision.alert_engine import generate_insights
from api.eletrofrio_client import EletrofrioApiError, eletrofrio_client
from api.logger import logger
from api.normalizers import ensure_list, normalize_alarm, normalize_device, normalize_telemetry_payload, normalize_unit
from api.notifications.auto_notifier import process_notifications
from api.repositories import (
    create_collector_run,
    finish_collector_run,
    insert_insights,
    latest_telemetry_timestamps,
    list_alarms,
    list_devices,
    list_telemetry,
    list_units,
    upsert_alarms,
    upsert_devices,
    upsert_telemetry,
    upsert_units,
)
from api.tickets import open_ticket_for_insight


def _elapsed(started_at: float) -> float:
    return round(time.perf_counter() - started_at, 3)


def _warning_text(items: list[str]) -> str | None:
    return " | ".join(items) if items else None


def _load_cached_units(reason: Exception) -> list[dict[str, Any]]:
    cached = list_units()
    if not cached:
        raise RuntimeError(f"{reason}. Não há unidades em cache para continuidade operacional.") from reason
    logger.warning("Endpoint de unidades indisponível; usando %s unidades cacheadas. Erro: %s", len(cached), reason)
    return cached


def _load_cached_alarms(reason: Exception) -> list[dict[str, Any]]:
    cached = list_alarms(300)
    if not cached:
        raise RuntimeError(f"{reason}. Não há alarmes em cache para continuidade operacional.") from reason
    logger.warning("Endpoint de alarmes indisponível; usando %s alarmes cacheados. Erro: %s", len(cached), reason)
    return cached


def discover_devices(units: list[dict[str, Any]], alarms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    devices: dict[int, dict[str, Any]] = {}
    for alarm in alarms:
        alarm_source = alarm.get("raw_payload") if isinstance(alarm.get("raw_payload"), dict) else alarm
        device = normalize_device(alarm_source, fallback_loja_id=alarm.get("loja_id"), fallback_loja_nome=alarm.get("loja_nome"))
        if device and device.get("dispositivo_id") is not None:
            devices[device["dispositivo_id"]] = device

    for unit in units:
        raw = unit.get("raw_payload") or {}
        nested = []
        for key in ("dispositivos", "devices", "equipamentos", "pontos"):
            value = raw.get(key) if isinstance(raw, dict) else None
            if isinstance(value, list):
                nested.extend(value)
        for item in nested:
            if isinstance(item, dict):
                device = normalize_device(item, fallback_loja_id=unit.get("loja_id"), fallback_loja_nome=unit.get("loja_nome"))
                if device and device.get("dispositivo_id") is not None:
                    devices[device["dispositivo_id"]] = device

    return list(devices.values())


def _device_id(device: dict[str, Any]) -> int | None:
    try:
        value = device.get("dispositivo_id")
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def select_telemetry_devices(devices: list[dict[str, Any]], alarms: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    mode = settings.telemetry_fetch_mode if settings.telemetry_fetch_mode in {"all", "priority", "none"} else "priority"
    if mode == "none":
        return [], len(devices)
    if mode == "all":
        return devices, 0

    max_devices = max(1, settings.telemetry_max_devices_per_run)
    cache_cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(0, settings.telemetry_cache_minutes))
    recent_by_device = latest_telemetry_timestamps()
    alarm_device_ids: set[int] = set()
    alarm_store_ids: set[int] = set()
    for alarm in alarms[:300]:
        try:
            if alarm.get("dispositivo_id") is not None:
                alarm_device_ids.add(int(alarm["dispositivo_id"]))
            if alarm.get("loja_id") is not None:
                alarm_store_ids.add(int(alarm["loja_id"]))
        except (TypeError, ValueError):
            continue

    scored: list[tuple[int, int, dict[str, Any]]] = []
    skipped_cache = 0
    for index, device in enumerate(devices):
        device_id = _device_id(device)
        if device_id is None:
            continue
        latest = recent_by_device.get(device_id)
        has_recent_cache = bool(latest and latest >= cache_cutoff)
        has_alarm = device_id in alarm_device_ids
        try:
            store_alarm = int(device.get("loja_id")) in alarm_store_ids if device.get("loja_id") is not None else False
        except (TypeError, ValueError):
            store_alarm = False
        if has_recent_cache and not has_alarm and not store_alarm:
            skipped_cache += 1
            continue
        score = 0
        if has_alarm:
            score += 100
        if store_alarm:
            score += 35
        if not latest:
            score += 20
        if has_recent_cache:
            score -= 20
        scored.append((score, -index, device))

    selected = [item[2] for item in sorted(scored, key=lambda row: (row[0], row[1]), reverse=True)[:max_devices]]
    return selected, skipped_cache


def fetch_telemetry_for_devices(devices: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    if not devices:
        return [], 0

    timeout = max(3, settings.telemetry_request_timeout_seconds)
    max_workers = min(max(1, settings.telemetry_concurrency), len(devices))
    rows: list[dict[str, Any]] = []
    failed = 0

    def fetch_one(device: dict[str, Any]) -> list[dict[str, Any]]:
        dispositivo_id = _device_id(device)
        if dispositivo_id is None:
            return []
        telemetry_payload = eletrofrio_client.fetch_telemetry(dispositivo_id, timeout=timeout)
        telemetry_items = normalize_telemetry_payload(
            telemetry_payload,
            dispositivo_id=dispositivo_id,
            loja_id=device.get("loja_id"),
            tag=device.get("tag"),
        )
        if not telemetry_items:
            logger.warning("Telemetria sem leitura útil para dispositivo %s.", dispositivo_id)
        return telemetry_items

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_one, device): device for device in devices}
        for future in as_completed(futures):
            device = futures[future]
            try:
                rows.extend(future.result())
            except Exception as exc:
                failed += 1
                logger.warning("Falha ao buscar telemetria do dispositivo %s: %s", device.get("dispositivo_id"), exc)
    return rows, failed


def run_collector_once(trigger_source: str = "manual") -> dict[str, Any]:
    if not supabase.enabled():
        raise RuntimeError("Supabase não configurado. Preencha .env antes de rodar o coletor real.")

    run_id = create_collector_run(trigger_source)
    collector_started = time.perf_counter()
    counts = {"units": 0, "alarms": 0, "telemetry": 0}
    anomaly_result: dict[str, Any] = {"created": 0, "updated": 0, "whatsapp_sent": 0}
    notification_result: dict[str, Any] = {"checked": 0, "sent": 0, "skipped": 0, "failed": 0, "dry_run": 0}
    metrics: dict[str, Any] = {
        "devices_requested": 0,
        "devices_skipped_cache": 0,
        "devices_failed": 0,
        "telemetry_rows_saved": 0,
    }
    warnings: list[str] = []
    try:
        logger.info("Coletor Eletrofrio iniciado")

        phase_started = time.perf_counter()
        try:
            units_payload = eletrofrio_client.fetch_units()
            units = [normalize_unit(item) for item in ensure_list(units_payload) if isinstance(item, dict)]
            saved_units = upsert_units(units)
            counts["units"] = len(saved_units) or len(units)
        except EletrofrioApiError as exc:
            units = _load_cached_units(exc)
            counts["units"] = len(units)
            warnings.append("Endpoint de unidades temporariamente indisponível; usados dados cacheados do Supabase.")
        metrics["units_duration"] = _elapsed(phase_started)

        unit_names = {unit.get("loja_id"): unit.get("loja_nome") for unit in units if unit.get("loja_id") is not None}

        phase_started = time.perf_counter()
        try:
            alarms_payload = eletrofrio_client.fetch_alarms()
            alarms = [normalize_alarm(item) for item in ensure_list(alarms_payload) if isinstance(item, dict)]
            for alarm in alarms:
                if not alarm.get("loja_nome") and alarm.get("loja_id") in unit_names:
                    alarm["loja_nome"] = unit_names[alarm.get("loja_id")]
            saved_alarms = upsert_alarms(alarms)
            counts["alarms"] = len(saved_alarms) or len(alarms)
        except EletrofrioApiError as exc:
            alarms = _load_cached_alarms(exc)
            counts["alarms"] = len(alarms)
            warnings.append("Endpoint de alarmes temporariamente indisponível; usados dados cacheados do Supabase.")
        metrics["alarms_duration"] = _elapsed(phase_started)

        devices = discover_devices(units, alarms)
        saved_devices = upsert_devices(devices)
        known_devices = saved_devices or devices or list_devices()

        phase_started = time.perf_counter()
        telemetry_devices, skipped_cache = select_telemetry_devices(known_devices, alarms)
        metrics["devices_requested"] = len(telemetry_devices)
        metrics["devices_skipped_cache"] = skipped_cache
        telemetry_rows, failed_devices = fetch_telemetry_for_devices(telemetry_devices)
        metrics["devices_failed"] = failed_devices

        saved_telemetry = upsert_telemetry(telemetry_rows)
        counts["telemetry"] = len(saved_telemetry) or len(telemetry_rows)
        metrics["telemetry_rows_saved"] = counts["telemetry"]
        metrics["telemetry_duration"] = _elapsed(phase_started)

        phase_started = time.perf_counter()
        recent_units = list_units()
        recent_devices = list_devices()
        recent_alarms = list_alarms(300)
        recent_telemetry_limit = min(600, max(200, settings.telemetry_max_devices_per_run * 4))
        recent_telemetry = list_telemetry(recent_telemetry_limit)
        insights = generate_insights(recent_units, recent_devices, recent_alarms, recent_telemetry)
        saved_insights = insert_insights(insights[:50]) if insights else []

        for insight in saved_insights:
            try:
                open_ticket_for_insight(insight)
            except Exception as exc:
                logger.warning("Falha ao abrir chamado para insight %s: %s", insight.get("id"), exc)

        try:
            from api.anomalies import detect_and_notify_anomalies

            anomaly_result = detect_and_notify_anomalies(recent_units, recent_devices, recent_alarms, recent_telemetry)
            logger.info(
                "Anomalias processadas: criadas=%s atualizadas=%s whatsapp=%s",
                anomaly_result.get("created", 0),
                anomaly_result.get("updated", 0),
                anomaly_result.get("whatsapp_sent", 0),
            )
        except Exception as exc:
            logger.warning("Falha ao processar anomalias após coleta: %s", exc)
        metrics["analysis_duration"] = _elapsed(phase_started)

        phase_started = time.perf_counter()
        try:
            notification_result = process_notifications()
            logger.info(
                "Notificações processadas: checked=%s sent=%s dry_run=%s skipped=%s failed=%s",
                notification_result.get("checked", 0),
                notification_result.get("sent", 0),
                notification_result.get("dry_run", 0),
                notification_result.get("skipped", 0),
                notification_result.get("failed", 0),
            )
        except Exception as exc:
            warnings.append("Falha ao processar notificações automáticas; coleta preservada.")
            notification_result = {"checked": 0, "sent": 0, "skipped": 0, "failed": 1, "dry_run": 0, "error": str(exc)}
            logger.warning("Falha ao processar notificações após coleta: %s", exc)
        metrics["notification_duration"] = _elapsed(phase_started)

        final_status = "partial_success" if warnings else "success"
        metrics["duration_seconds"] = _elapsed(collector_started)
        metrics["notifications_checked"] = int(notification_result.get("checked", 0) or 0)
        metrics["notifications_sent"] = int(notification_result.get("sent", 0) or 0) + int(notification_result.get("dry_run", 0) or 0)
        metrics["notifications_skipped"] = int(notification_result.get("skipped", 0) or 0)
        metrics["notifications_failed"] = int(notification_result.get("failed", 0) or 0)
        finish_collector_run(
            run_id,
            final_status,
            counts,
            error_message=_warning_text(warnings),
            anomalies_count=int(anomaly_result.get("created", 0) or 0),
            whatsapp_alerts_count=int(notification_result.get("sent", 0) or 0) + int(notification_result.get("dry_run", 0) or 0),
            extra_metrics=metrics,
        )
        logger.info("Coletor finalizado: status=%s counts=%s warnings=%s", final_status, counts, warnings)
        return {
            "status": final_status,
            **counts,
            "insights_count": len(saved_insights),
            "anomalies_count": anomaly_result.get("created", 0),
            "whatsapp_alerts_count": int(notification_result.get("sent", 0) or 0) + int(notification_result.get("dry_run", 0) or 0),
            "notifications": notification_result,
            "performance": metrics,
            "warnings": warnings,
        }
    except Exception as exc:
        logger.exception("Coletor falhou")
        finish_collector_run(run_id, "error", counts, str(exc))
        raise


def run_collector_loop() -> None:
    interval_seconds = max(1, settings.collector_interval_minutes) * 60
    logger.info("Loop do coletor iniciado. Intervalo=%ss", interval_seconds)
    while True:
        try:
            run_collector_once()
        except Exception as exc:
            logger.error("Execução do coletor falhou: %s", exc)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    run_collector_once("manual_cli")
