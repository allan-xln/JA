from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from api.analysis.rules import classify_alarm_severity, severity_rank
from api.config import settings
from api.logger import logger
from api.repositories import find_open_anomaly, insert_anomaly, patch_anomaly, utc_now_iso
from api.rules.rule_engine import enrich_evidence_with_rules


TEMPERATURE_MIN = -30.0
TEMPERATURE_WARNING_HIGH = 5.0
TEMPERATURE_CRITICAL_HIGH = 8.0


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _stable_key(parts: list[Any]) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts if part not in (None, "")).encode("utf-8")).hexdigest()


def _severity_rank(value: str) -> int:
    return {"low": 1, "info": 1, "medium": 2, "warning": 2, "high": 3, "critical": 4}.get(value, 0)


def _recipient_list() -> list[str]:
    return [item.strip() for item in settings.whatsapp_alert_to.split(",") if item.strip()]


def _format_value(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.1f} C"
    except (TypeError, ValueError):
        return str(value)


def _format_dt(value: str | None) -> str:
    parsed = _parse_dt(value) or datetime.now(timezone.utc)
    return parsed.astimezone().strftime("%d/%m/%Y %H:%M")


def _format_message(anomaly: dict[str, Any]) -> str:
    equipment = anomaly.get("tag") or (f"dispositivo {anomaly.get('equipment_id')}" if anomaly.get("equipment_id") else "equipamento monitorado")
    store = anomaly.get("loja_nome") or (f"loja {anomaly.get('loja_id')}" if anomaly.get("loja_id") else "loja monitorada")
    expected = anomaly.get("expected_range") or {}
    if isinstance(expected, dict) and expected:
        expected_label = f"{_format_value(expected.get('min'))} a {_format_value(expected.get('max'))}"
    else:
        expected_label = "faixa operacional esperada"

    return "\n".join(
        [
            "Ocorrência operacional Eletrofrio",
            "",
            f"Prioridade: {anomaly.get('severity')}",
            f"Loja: {store}",
            f"Equipamento: {equipment}",
            f"Tipo: {anomaly.get('type')}",
            f"Valor atual: {_format_value(anomaly.get('value'))}",
            f"Faixa esperada: {expected_label}",
            f"Horario: {_format_dt(anomaly.get('detected_at'))}",
            "",
            f"Ação recomendada: {anomaly.get('message') or 'Verifique o equipamento no painel operacional.'}",
            f"Painel: {settings.app_public_url}",
        ]
    )


def _send_whatsapp_alert(anomaly: dict[str, Any]) -> tuple[str, str | None, int]:
    if not settings.whatsapp_alert_enabled:
        return "disabled", None, 0

    recipients = _recipient_list()
    if not recipients:
        return "skipped_no_recipient", "WHATSAPP_ALERT_TO vazio.", 0

    message = _format_message(anomaly)
    sent_count = 0
    for recipient in recipients:
        try:
            response = requests.post(
                f"{settings.whatsapp_service_url}/send-test",
                json={"phone": recipient, "message": message},
                timeout=settings.http_timeout_seconds,
            )
            body = response.json() if response.text else {}
            if response.status_code >= 400:
                raise RuntimeError(json.dumps(body, ensure_ascii=False))
            if body.get("sent"):
                sent_count += 1
            elif body.get("dryRun"):
                logger.info("WhatsApp em dry-run; alerta seria enviado para %s", recipient)
        except Exception as exc:  # noqa: BLE001 - alerta nao deve quebrar coleta.
            logger.warning("Falha ao enviar WhatsApp para anomalia %s: %s", anomaly.get("id"), exc)
            return "error", str(exc), sent_count

    return ("sent" if sent_count else "dry_run"), None, sent_count


def _cooldown_active(existing: dict[str, Any], cooldown_minutes: int, incoming_severity: str) -> bool:
    last_sent = _parse_dt(existing.get("whatsapp_sent_at"))
    if not last_sent:
        return False
    current_rank = _severity_rank(str(existing.get("severity") or "low"))
    incoming_rank = _severity_rank(incoming_severity)
    if incoming_rank > current_rank:
        return False
    return datetime.now(timezone.utc) - last_sent < timedelta(minutes=max(5, cooldown_minutes))


def _register_anomaly(candidate: dict[str, Any], cooldown_minutes: int) -> tuple[dict[str, Any] | None, bool, int]:
    now = utc_now_iso()
    existing = find_open_anomaly(candidate["anomaly_key"])
    if existing:
        update = {
            "last_seen_at": now,
            "severity": candidate["severity"] if _severity_rank(candidate["severity"]) > _severity_rank(str(existing.get("severity") or "")) else existing.get("severity"),
            "value": candidate.get("value"),
            "message": candidate.get("message"),
            "metadata": candidate.get("metadata", {}),
        }
        updated = patch_anomaly(existing["id"], update) or existing
        if _cooldown_active(existing, cooldown_minutes, candidate["severity"]):
            logger.info("Anomalia existente em cooldown: %s", candidate["anomaly_key"])
            return updated, False, 0
        logger.info("Anomalia existente atualizada: %s", candidate["anomaly_key"])
        return updated, False, 0

    anomaly = insert_anomaly({**candidate, "detected_at": now, "last_seen_at": now})
    if not anomaly:
        return None, False, 0

    status, error, sent_count = _send_whatsapp_alert(anomaly)
    patch: dict[str, Any] = {"whatsapp_status": status, "whatsapp_error": error}
    if status == "sent":
        patch["whatsapp_sent_at"] = utc_now_iso()
    anomaly = patch_anomaly(anomaly["id"], patch) or anomaly
    logger.info("Anomalia detectada: %s status_whatsapp=%s", candidate["anomaly_key"], status)
    return anomaly, True, sent_count


def _temperature_candidates(telemetry: list[dict[str, Any]], devices_by_id: dict[Any, dict[str, Any]], units_by_id: dict[Any, dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_device: dict[Any, dict[str, Any]] = {}
    for row in telemetry:
        device_id = row.get("dispositivo_id")
        if device_id is None:
            continue
        current = latest_by_device.get(device_id)
        if not current or str(row.get("measured_at") or "") > str(current.get("measured_at") or ""):
            latest_by_device[device_id] = row

    candidates: list[dict[str, Any]] = []
    for device_id, row in latest_by_device.items():
        value = row.get("temperature")
        if value is None:
            continue
        try:
            temp = float(value)
        except (TypeError, ValueError):
            continue
        if temp >= TEMPERATURE_CRITICAL_HIGH:
            severity = "critical"
            anomaly_type = "temperature_high"
            message = "Temperatura elevada. Verifique operação, porta, carga térmica, sensor e refrigeração."
        elif temp >= TEMPERATURE_WARNING_HIGH:
            severity = "medium"
            anomaly_type = "temperature_high"
            message = "Temperatura acima da faixa de atenção. Acompanhe a evolução operacional."
        elif temp <= TEMPERATURE_MIN:
            severity = "medium"
            anomaly_type = "temperature_low"
            message = "Temperatura muito baixa. Verifique configuração, sensor e controle."
        else:
            continue

        device = devices_by_id.get(device_id, {})
        loja_id = row.get("loja_id") or device.get("loja_id")
        unit = units_by_id.get(loja_id, {})
        evidence, rule_eval = enrich_evidence_with_rules(
            {
                "title": "Temperatura fora da faixa operacional",
                "telemetry": row,
                "device_metrics": {
                    "dispositivo_id": device_id,
                    "tag": row.get("tag") or device.get("tag"),
                    "loja_id": loja_id,
                    "telemetry_count": 1,
                    "temperature_current": temp,
                },
                "value": temp,
                "evidence_source": "eletrofrio_telemetry",
            },
            severity,
        )
        candidates.append(
            {
                "anomaly_key": _stable_key(["temperature", anomaly_type, device_id]),
                "sensor_id": f"temperature:{device_id}",
                "equipment_id": device_id,
                "loja_id": loja_id,
                "loja_nome": unit.get("loja_nome"),
                "tag": row.get("tag") or device.get("tag"),
                "type": anomaly_type,
                "severity": (rule_eval or {}).get("severity") or severity,
                "value": temp,
                "expected_range": {"min": TEMPERATURE_MIN, "max": TEMPERATURE_WARNING_HIGH},
                "message": (rule_eval or {}).get("rule_explanation") or message,
                "source": "automatic_collector",
                "technical_reason": (rule_eval or {}).get("rule_based_reason"),
                "recommended_action": (rule_eval or {}).get("recommended_action"),
                "evidence_json": evidence,
                "metadata": {"telemetry": row, "rule": "temperature_range", "rule_evaluation": rule_eval},
            }
        )
    return candidates


def _alarm_candidates(alarms: list[dict[str, Any]], devices_by_id: dict[Any, dict[str, Any]], units_by_id: dict[Any, dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for alarm in alarms[:120]:
        severity = classify_alarm_severity(alarm)
        if severity_rank(severity) < 2:
            continue
        device_id = alarm.get("dispositivo_id")
        loja_id = alarm.get("loja_id")
        device = devices_by_id.get(device_id, {})
        unit = units_by_id.get(loja_id, {})
        alarm_message = alarm.get("alarm_message") or "Alarme operacional relevante detectado."
        alarm_type = str(alarm.get("alarm_type") or "alarm").lower()
        evidence, rule_eval = enrich_evidence_with_rules(
            {
                "title": "Alarme operacional relevante detectado",
                "alarm": {**alarm, "tag": alarm.get("tag") or device.get("tag")},
                "evidence_source": "eletrofrio_alarms",
                "sufficient_evidence": True,
            },
            severity,
        )
        candidates.append(
            {
                "anomaly_key": _stable_key(["alarm", device_id or loja_id, alarm_type, alarm_message]),
                "sensor_id": f"alarm:{device_id or loja_id or 'store'}",
                "equipment_id": device_id,
                "loja_id": loja_id,
                "loja_nome": alarm.get("loja_nome") or unit.get("loja_nome"),
                "tag": alarm.get("tag") or device.get("tag"),
                "type": "offline" if "offline" in alarm_message.lower() else "alarm",
                "severity": (rule_eval or {}).get("severity") or ("critical" if severity == "critical" else "medium"),
                "value": None,
                "expected_range": {},
                "message": (rule_eval or {}).get("rule_explanation") or alarm_message,
                "source": "automatic_collector",
                "technical_reason": (rule_eval or {}).get("rule_based_reason"),
                "recommended_action": (rule_eval or {}).get("recommended_action"),
                "evidence_json": evidence,
                "metadata": {"alarm": alarm, "rule": "alarm_severity", "rule_evaluation": rule_eval},
            }
        )
    return candidates


def detect_and_notify_anomalies(
    units: list[dict[str, Any]],
    devices: list[dict[str, Any]],
    alarms: list[dict[str, Any]],
    telemetry: list[dict[str, Any]],
    cooldown_minutes: int | None = None,
) -> dict[str, Any]:
    cooldown = max(5, cooldown_minutes or settings.whatsapp_alert_cooldown_minutes)
    units_by_id = {row.get("loja_id"): row for row in units}
    devices_by_id = {row.get("dispositivo_id"): row for row in devices}

    candidates = [
        *_temperature_candidates(telemetry, devices_by_id, units_by_id),
        *_alarm_candidates(alarms, devices_by_id, units_by_id),
    ]

    created = 0
    updated = 0
    whatsapp_sent = 0
    anomalies: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for candidate in candidates:
        if candidate["anomaly_key"] in seen_keys:
            continue
        seen_keys.add(candidate["anomaly_key"])
        anomaly, is_new, sent_count = _register_anomaly(candidate, cooldown)
        if not anomaly:
            continue
        anomalies.append(anomaly)
        created += 1 if is_new else 0
        updated += 0 if is_new else 1
        whatsapp_sent += sent_count

    return {
        "candidates": len(candidates),
        "created": created,
        "updated": updated,
        "whatsapp_sent": whatsapp_sent,
        "items": anomalies,
    }
