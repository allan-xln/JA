from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


IMPORTANT_TYPES = {
    "temperature_high",
    "temperature_low",
    "compressor_failure",
    "liquid_return",
    "pressure_low",
    "offline",
    "alarm",
}

IMPORTANT_TERMS = (
    "alta temperatura",
    "baixa temperatura",
    "compressor",
    "retorno de líquido",
    "retorno de liquido",
    "baixa pressão",
    "baixa pressao",
    "offline",
    "comunicação",
    "comunicacao",
    "temperatura fora",
    "falha",
)


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def severity_rank(value: Any) -> int:
    return {
        "info": 1,
        "low": 1,
        "medium": 2,
        "warning": 2,
        "high": 3,
        "critical": 4,
        "critico": 4,
        "crítico": 4,
    }.get(str(value or "").casefold(), 0)


def is_recent(row: dict[str, Any], max_age_hours: int = 48) -> bool:
    detected = (
        parse_dt(row.get("detected_at"))
        or parse_dt(row.get("created_at"))
        or parse_dt(row.get("started_at"))
    )
    if not detected:
        return False
    return datetime.now(timezone.utc) - detected <= timedelta(hours=max(1, max_age_hours))


def evidence_is_sufficient(row: dict[str, Any]) -> bool:
    evidence = row.get("evidence_json") if isinstance(row.get("evidence_json"), dict) else {}
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    if evidence.get("sufficient_evidence") is False:
        return False
    if not (row.get("loja_id") or row.get("loja_nome")):
        return False
    if not (row.get("dispositivo_id") or row.get("equipment_id") or row.get("tag")):
        row_type = str(row.get("type") or row.get("insight_type") or "").casefold()
        if row_type not in {"store_risk", "alarm"}:
            return False
    if metadata.get("telemetry") and not (row.get("message") or row.get("summary") or row.get("title")):
        return False
    return True


def local_relevance(row: dict[str, Any]) -> tuple[bool, str]:
    severity = str(row.get("severity") or "").casefold()
    if severity in {"info", "low"}:
        return False, "severity_info"
    if not is_recent(row):
        return False, "old_event"
    if not evidence_is_sufficient(row):
        return False, "insufficient_evidence"

    row_type = str(row.get("type") or row.get("insight_type") or "").casefold()
    if severity_rank(severity) >= 4:
        return True, "critical"
    if row_type in IMPORTANT_TYPES and severity_rank(severity) >= 3:
        return True, f"important_type:{row_type}"

    text = " ".join(
        str(row.get(key) or "")
        for key in ("title", "summary", "message", "technical_reason", "recommended_action", "type", "insight_type")
    ).casefold()
    if any(term in text for term in IMPORTANT_TERMS) and severity_rank(severity) >= 3:
        return True, "important_term"

    evidence = row.get("evidence_json") if isinstance(row.get("evidence_json"), dict) else {}
    rule_eval = evidence.get("rule_evaluation") if isinstance(evidence.get("rule_evaluation"), dict) else {}
    rule_severity = str(rule_eval.get("severity") or evidence.get("severity") or "").casefold()
    if severity_rank(rule_severity) >= 4:
        return True, "critical_rule"

    recurrence = 0
    for key in ("recurrence_count", "alarm_count"):
        try:
            recurrence = max(recurrence, int(row.get(key) or evidence.get(key) or 0))
        except (TypeError, ValueError):
            continue
    if severity in {"warning", "medium"} and recurrence >= 3:
        return True, "warning_recurrent"

    return False, "not_relevant"
