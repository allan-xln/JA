from __future__ import annotations

import time
from typing import Any

from api.config import settings
from api.database import supabase
from api.decision.alert_engine import generate_insights
from api.eletrofrio_client import EletrofrioApiError, eletrofrio_client
from api.logger import logger
from api.normalizers import ensure_list, normalize_alarm, normalize_device, normalize_telemetry_payload, normalize_unit
from api.repositories import (
    create_collector_run,
    finish_collector_run,
    insert_insights,
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


def run_collector_once(trigger_source: str = "manual") -> dict[str, Any]:
    if not supabase.enabled():
        raise RuntimeError("Supabase não configurado. Preencha .env antes de rodar o coletor real.")

    run_id = create_collector_run(trigger_source)
    counts = {"units": 0, "alarms": 0, "telemetry": 0}
    anomaly_result: dict[str, Any] = {"created": 0, "updated": 0, "whatsapp_sent": 0}
    warnings: list[str] = []
    try:
        logger.info("Coletor Eletrofrio iniciado")

        try:
            units_payload = eletrofrio_client.fetch_units()
            units = [normalize_unit(item) for item in ensure_list(units_payload) if isinstance(item, dict)]
            saved_units = upsert_units(units)
            counts["units"] = len(saved_units) or len(units)
        except EletrofrioApiError as exc:
            units = _load_cached_units(exc)
            counts["units"] = len(units)
            warnings.append("Endpoint de unidades temporariamente indisponível; usados dados cacheados do Supabase.")

        unit_names = {unit.get("loja_id"): unit.get("loja_nome") for unit in units if unit.get("loja_id") is not None}

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

        devices = discover_devices(units, alarms)
        saved_devices = upsert_devices(devices)
        known_devices = saved_devices or devices or list_devices()

        telemetry_rows = []
        for device in known_devices:
            dispositivo_id = device.get("dispositivo_id")
            if not dispositivo_id:
                continue
            try:
                telemetry_payload = eletrofrio_client.fetch_telemetry(dispositivo_id)
                telemetry_items = normalize_telemetry_payload(
                    telemetry_payload,
                    dispositivo_id=int(dispositivo_id),
                    loja_id=device.get("loja_id"),
                    tag=device.get("tag"),
                )
                if not telemetry_items:
                    logger.warning("Telemetria sem leitura útil para dispositivo %s.", dispositivo_id)
                telemetry_rows.extend(telemetry_items)
            except Exception as exc:
                logger.warning("Falha ao buscar telemetria do dispositivo %s: %s", dispositivo_id, exc)

        saved_telemetry = upsert_telemetry(telemetry_rows)
        counts["telemetry"] = len(saved_telemetry) or len(telemetry_rows)

        recent_units = list_units()
        recent_devices = list_devices()
        recent_alarms = list_alarms(300)
        recent_telemetry = list_telemetry(800)
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

        final_status = "partial_success" if warnings else "success"
        finish_collector_run(
            run_id,
            final_status,
            counts,
            error_message=_warning_text(warnings),
            anomalies_count=int(anomaly_result.get("created", 0) or 0),
            whatsapp_alerts_count=int(anomaly_result.get("whatsapp_sent", 0) or 0),
        )
        logger.info("Coletor finalizado: status=%s counts=%s warnings=%s", final_status, counts, warnings)
        return {
            "status": final_status,
            **counts,
            "insights_count": len(saved_insights),
            "anomalies_count": anomaly_result.get("created", 0),
            "whatsapp_alerts_count": anomaly_result.get("whatsapp_sent", 0),
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
