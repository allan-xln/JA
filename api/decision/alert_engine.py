from __future__ import annotations

import hashlib
import json
from typing import Any

from api.ai.openai_analyzer import fallback_explanation
from api.analysis.metrics import build_metrics
from api.analysis.rules import classify_alarm_severity, classify_temperature, severity_rank
from api.config import settings
from api.rules.rule_engine import enrich_evidence_with_rules


def build_insight(
    insight_type: str,
    severity: str,
    evidence: dict[str, Any],
    loja_id: int | None = None,
    loja_nome: str | None = None,
    dispositivo_id: int | None = None,
    tag: str | None = None,
) -> dict[str, Any]:
    evidence, rule_evaluation = enrich_evidence_with_rules(
        {**evidence, "insight_type": insight_type},
        severity,
    )
    if rule_evaluation:
        severity = rule_evaluation.get("severity") or severity
        explanation = {
            "title": rule_evaluation.get("rule_name") or evidence.get("title") or "Ocorrência operacional priorizada",
            "summary": rule_evaluation.get("rule_explanation") or "Regra operacional aplicada com base nas evidências.",
            "technical_reason": (
                f"Regra aplicada: {rule_evaluation.get('rule_name')}. "
                f"{rule_evaluation.get('rule_based_reason') or rule_evaluation.get('rule_explanation')}"
            ),
            "recommended_action": rule_evaluation.get("recommended_action") or "Validar evidências no painel operacional antes de acionar manutenção.",
        }
    else:
        explanation = fallback_explanation({**evidence, "severity": severity, "insight_type": insight_type})
    hash_payload = {
        "insight_type": insight_type,
        "severity": severity,
        "loja_id": loja_id,
        "dispositivo_id": dispositivo_id,
        "tag": tag,
        "evidence": evidence,
    }
    insight_hash = hashlib.sha256(json.dumps(hash_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return {
        "insight_hash": insight_hash,
        "insight_type": insight_type,
        "severity": severity,
        "loja_id": loja_id,
        "loja_nome": loja_nome,
        "dispositivo_id": dispositivo_id,
        "tag": tag,
        "title": explanation["title"],
        "summary": explanation["summary"],
        "technical_reason": explanation["technical_reason"],
        "recommended_action": explanation["recommended_action"],
        "evidence_json": evidence,
        "gpt_model": settings.openai_model,
    }


def generate_insights(units: list[dict[str, Any]], devices: list[dict[str, Any]], alarms: list[dict[str, Any]], telemetry: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metrics = build_metrics(units, devices, alarms, telemetry)
    units_by_id = {row.get("loja_id"): row for row in units}
    devices_by_id = {row.get("dispositivo_id"): row for row in devices}
    insights: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    def add_insight(insight: dict[str, Any]) -> None:
        insight_hash = insight.get("insight_hash")
        if insight_hash in seen_hashes:
            return
        seen_hashes.add(insight_hash)
        insights.append(insight)

    for alarm in alarms[:80]:
        severity = classify_alarm_severity(alarm)
        if severity_rank(severity) < 2:
            continue
        add_insight(
            build_insight(
                "alarm",
                severity,
                {
                    "title": "Alarme relevante detectado",
                    "alarm": alarm,
                    "evidence_source": "eletrofrio_alarms",
                    "sufficient_evidence": True,
                },
                loja_id=alarm.get("loja_id"),
                loja_nome=alarm.get("loja_nome") or units_by_id.get(alarm.get("loja_id"), {}).get("loja_nome"),
                dispositivo_id=alarm.get("dispositivo_id"),
                tag=alarm.get("tag") or devices_by_id.get(alarm.get("dispositivo_id"), {}).get("tag"),
            )
        )

    for device in metrics["most_problematic_devices"]:
        if (device.get("alarm_count") or 0) < 1:
            continue
        severity = "critical" if (device.get("alarm_count") or 0) >= 3 else "warning"
        add_insight(
            build_insight(
                "device_alarm_repetition",
                severity,
                {
                    "title": "Equipamento com alarme recente",
                    "device_alarm_summary": device,
                    "evidence_source": "eletrofrio_alarms",
                    "sufficient_evidence": True,
                },
                loja_id=device.get("loja_id"),
                loja_nome=device.get("loja_nome"),
                dispositivo_id=device.get("dispositivo_id"),
                tag=device.get("tag"),
            )
        )

    for device_metric in metrics["device_metrics"][:30]:
        severity = classify_temperature(device_metric)
        repeated_alarms = (device_metric.get("alarm_count") or 0) >= 3
        if severity_rank(severity) < 2 and not repeated_alarms:
            continue
        final_severity = "critical" if repeated_alarms and severity == "warning" else severity
        loja_id = device_metric.get("loja_id")
        add_insight(
            build_insight(
                "device_behavior",
                final_severity,
                {
                    "title": "Comportamento anormal por dispositivo",
                    "device_metrics": device_metric,
                    "evidence_source": "eletrofrio_telemetry/eletrofrio_alarms",
                    "sufficient_evidence": device_metric.get("telemetry_count", 0) >= 3 or repeated_alarms,
                },
                loja_id=loja_id,
                loja_nome=units_by_id.get(loja_id, {}).get("loja_nome"),
                dispositivo_id=device_metric.get("dispositivo_id"),
                tag=device_metric.get("tag"),
            )
        )

    for store_metric in metrics["store_metrics"][:10]:
        if (store_metric.get("alarm_count") or 0) < 5:
            continue
        loja_id = store_metric.get("loja_id")
        severity = "critical" if store_metric.get("alarm_count", 0) >= 10 or loja_id == 315 else "warning"
        add_insight(
            build_insight(
                "store_risk",
                severity,
                {
                    "title": "Loja com concentração de alarmes",
                    "store_metrics": store_metric,
                    "special_rule": "loja_315" if loja_id == 315 else None,
                    "evidence_source": "eletrofrio_alarms",
                    "sufficient_evidence": True,
                },
                loja_id=loja_id,
                loja_nome=store_metric.get("loja_nome"),
            )
        )

    return insights
