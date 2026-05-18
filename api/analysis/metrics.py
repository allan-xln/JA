from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any


def _temperatures(rows: list[dict[str, Any]]) -> list[float]:
    return [float(row["temperature"]) for row in rows if row.get("temperature") is not None]


def _trend(values: list[float]) -> str:
    if len(values) < 4:
        return "insufficient_data"
    midpoint = len(values) // 2
    before = mean(values[:midpoint])
    after = mean(values[midpoint:])
    delta = after - before
    if delta >= 1.0:
        return "rising"
    if delta <= -1.0:
        return "falling"
    return "stable"


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _alarm_type(row: dict[str, Any]) -> str:
    if row.get("alarm_type"):
        return str(row["alarm_type"])
    raw = row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {}
    for key in ("criticidade", "grupoNm", "subgrupoNm", "alarmeDesc"):
        value = raw.get(key)
        if value not in (None, ""):
            return str(value)
    return "sem_tipo"


def build_metrics(units: list[dict[str, Any]], devices: list[dict[str, Any]], alarms: list[dict[str, Any]], telemetry: list[dict[str, Any]]) -> dict[str, Any]:
    cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)
    alarms_last_30_days = [
        row for row in alarms
        if (_parse_dt(row.get("started_at")) or _parse_dt(row.get("created_at")) or datetime.now(timezone.utc)) >= cutoff_30d
    ]
    alarms_by_loja = Counter(row.get("loja_id") for row in alarms if row.get("loja_id") is not None)
    alarms_by_device = Counter(row.get("dispositivo_id") for row in alarms if row.get("dispositivo_id") is not None)
    alarms_by_type = Counter(_alarm_type(row) for row in alarms)
    units_by_id = {row.get("loja_id"): row for row in units}
    devices_by_id = {row.get("dispositivo_id"): row for row in devices}

    telemetry_by_device: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(telemetry, key=lambda item: item.get("measured_at") or ""):
        telemetry_by_device[row.get("dispositivo_id")].append(row)

    device_metrics = []
    for device_id, rows in telemetry_by_device.items():
        temps = _temperatures(rows)
        latest = rows[-1] if rows else {}
        device_metrics.append(
            {
                "dispositivo_id": device_id,
                "tag": latest.get("tag") or devices_by_id.get(device_id, {}).get("tag"),
                "loja_id": latest.get("loja_id"),
                "loja_nome": units_by_id.get(latest.get("loja_id"), {}).get("loja_nome"),
                "temperature_current": temps[-1] if temps else None,
                "temperature_avg": round(mean(temps), 2) if temps else None,
                "temperature_min": min(temps) if temps else None,
                "temperature_max": max(temps) if temps else None,
                "temperature_trend": _trend(temps),
                "telemetry_count": len(rows),
                "alarm_count": alarms_by_device.get(device_id, 0),
            }
        )

    store_metrics = []
    for loja_id, count in alarms_by_loja.items():
        store_metrics.append(
            {
                "loja_id": loja_id,
                "loja_nome": units_by_id.get(loja_id, {}).get("loja_nome"),
                "alarm_count": count,
                "device_count": len([device for device in devices if device.get("loja_id") == loja_id]),
            }
        )

    top_stores = []
    for loja_id, count in alarms_by_loja.most_common(10):
        unit = units_by_id.get(loja_id, {})
        top_stores.append(
            {
                "loja_id": loja_id,
                "loja_nome": unit.get("loja_nome"),
                "alarm_count": count,
            }
        )

    top_devices = []
    for device_id, count in alarms_by_device.most_common(10):
        device = devices_by_id.get(device_id, {})
        loja_id = device.get("loja_id")
        top_devices.append(
            {
                "dispositivo_id": device_id,
                "tag": device.get("tag"),
                "loja_id": loja_id,
                "loja_nome": units_by_id.get(loja_id, {}).get("loja_nome"),
                "alarm_count": count,
            }
        )

    return {
        "totals": {
            "units": len(units),
            "devices": len(devices),
            "alarms": len(alarms),
            "alarms_last_30_days": len(alarms_last_30_days),
            "telemetry": len(telemetry),
            "insights_candidates": 0,
        },
        "alarms_by_type": dict(alarms_by_type),
        "device_metrics": sorted(device_metrics, key=lambda row: (row.get("alarm_count") or 0, row.get("temperature_max") or -999), reverse=True),
        "store_metrics": sorted(store_metrics, key=lambda row: row.get("alarm_count") or 0, reverse=True),
        "most_problematic_devices": top_devices,
        "most_critical_stores": top_stores,
        "top_critical_devices": top_devices,
        "top_critical_stores": top_stores,
    }
