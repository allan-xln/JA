from __future__ import annotations

from typing import Any


CRITICAL_WORDS = (
    "critico",
    "crítico",
    "alta",
    "excesso",
    "falha",
    "emergencia",
    "emergência",
    "parado",
    "degelo",
    "compressor",
    "camara",
    "câmara",
    "rack",
    "glicol",
    "comunicacao",
    "comunicação",
)
WARNING_WORDS = ("alarme", "atenção", "atencao", "porta", "temperatura", "pressao", "pressão", "baixa", "medio", "médio", "ventilacao", "ventilação")


def classify_alarm_severity(alarm: dict[str, Any]) -> str:
    text = " ".join(str(alarm.get(key) or "") for key in ("alarm_type", "alarm_message", "tag")).lower()
    raw = alarm.get("raw_payload") if isinstance(alarm.get("raw_payload"), dict) else {}
    criticidade = str(raw.get("criticidade") or alarm.get("alarm_type") or "").strip().upper()
    if criticidade in {"C", "CRITICO", "CRÍTICO"}:
        return "critical"
    if criticidade == "A":
        return "critical"
    if criticidade == "M":
        return "warning"
    if any(word in text for word in CRITICAL_WORDS):
        return "critical"
    if any(word in text for word in WARNING_WORDS):
        return "warning"
    return "info"


def classify_temperature(metric: dict[str, Any]) -> str:
    current = metric.get("temperature_current")
    max_temp = metric.get("temperature_max")
    trend = metric.get("temperature_trend")
    if current is None and max_temp is None:
        return "info"
    if current is not None and current >= 8:
        return "critical"
    if max_temp is not None and max_temp >= 8:
        return "critical"
    if current is not None and current >= 5:
        return "warning"
    if trend == "rising":
        return "warning"
    return "info"


def severity_rank(severity: str) -> int:
    return {"info": 1, "warning": 2, "critical": 3}.get(severity, 0)
