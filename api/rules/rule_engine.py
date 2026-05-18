from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from api.analysis.rules import classify_alarm_severity, severity_rank
from api.rules.operational_rules import infer_equipment_type, infer_measurement_type, normalize_rule
from api.rules.rule_repository import get_enabled_rules, insert_rule_evaluations


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(*values: Any) -> str:
    return " ".join(str(value or "") for value in values)


def _matches_pattern(pattern: str | None, text: str) -> bool:
    if not pattern:
        return False
    try:
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
    except re.error:
        return pattern.lower() in text.lower()


def _condition_matches(rule: dict[str, Any], *, value: float | None, text: str, recurrence_count: int = 0, telemetry_count: int | None = None) -> bool:
    condition = rule.get("condition_type")
    min_value = _float(rule.get("threshold_min"))
    max_value = _float(rule.get("threshold_max"))

    if condition == "contains_text":
        return _matches_pattern(rule.get("alarm_text_pattern"), text)
    if condition == "above":
        if value is not None and max_value is not None and value > max_value:
            return True
        return _matches_pattern(rule.get("alarm_text_pattern"), text)
    if condition == "below":
        if value is not None and min_value is not None and value < min_value:
            return True
        return _matches_pattern(rule.get("alarm_text_pattern"), text)
    if condition == "outside_range":
        if value is not None:
            if min_value is not None and value < min_value:
                return True
            if max_value is not None and value > max_value:
                return True
        return _matches_pattern(rule.get("alarm_text_pattern"), text)
    if condition == "between":
        return value is not None and (min_value is None or value >= min_value) and (max_value is None or value <= max_value)
    if condition == "equals":
        return str(value) == str(rule.get("threshold_max"))
    if condition == "repeated_event":
        return recurrence_count >= int(rule.get("recurrence_count") or 3)
    if condition == "missing_telemetry":
        return telemetry_count == 0
    if condition in {"stale_data", "trend_rising", "trend_falling"}:
        return False
    return False


def _scope_matches(rule: dict[str, Any], context: dict[str, Any]) -> bool:
    scope = rule.get("scope_type") or "global"
    value = str(rule.get("scope_value") or "").lower()
    if scope == "global":
        return True
    if scope == "store":
        return value in {str(context.get("loja_id") or "").lower(), str(context.get("loja_nome") or "").lower()}
    if scope == "device":
        return value in {str(context.get("dispositivo_id") or "").lower(), str(context.get("tag") or "").lower()}
    if scope == "equipment_type":
        return value == str(context.get("equipment_type") or "").lower()
    if scope == "measurement_type":
        return value == str(context.get("measurement_type") or "").lower()
    if scope == "alarm_group":
        return True
    return True


def _rule_specificity_matches(rule: dict[str, Any], context: dict[str, Any]) -> bool:
    equipment_type = rule.get("equipment_type")
    measurement_type = rule.get("measurement_type")
    if equipment_type and context.get("equipment_type") not in {equipment_type, "unknown"}:
        return False
    if measurement_type and context.get("measurement_type") not in {measurement_type, "unknown"}:
        return False
    return True


def _score(rule: dict[str, Any], context: dict[str, Any], matched_by_alarm: bool) -> float:
    score = 45.0
    if matched_by_alarm:
        score += 18
    if context.get("telemetry_value") is not None:
        score += 12
    if context.get("recurrence_count", 0) >= int(rule.get("recurrence_count") or 3):
        score += 15
    if context.get("equipment_confidence", 0) >= 0.7:
        score += 8
    if severity_rank(str(context.get("alarm_severity") or "")) >= 3:
        score += 12
    return min(score, 100.0)


def _evidence_level(score: float) -> str:
    if score >= 78:
        return "strong"
    if score >= 58:
        return "medium"
    return "weak"


def _unit_for(rule: dict[str, Any], context: dict[str, Any]) -> str:
    if (rule.get("measurement_type") or context.get("measurement_type")) == "temperature":
        return "C"
    if (rule.get("measurement_type") or context.get("measurement_type")) == "pressure":
        return "bar"
    return ""


def _value_label(value: float | None, unit: str = "") -> str:
    if value is None:
        return "Sem leitura numérica vinculada"
    suffix = f" {unit}" if unit else ""
    return f"{value:g}{suffix}"


def _expected_range(rule: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    min_value = _float(rule.get("threshold_min"))
    max_value = _float(rule.get("threshold_max"))
    unit = _unit_for(rule, context)
    condition = rule.get("condition_type")

    if condition in {"outside_range", "between"} and (min_value is not None or max_value is not None):
        if min_value is not None and max_value is not None:
            label = f"{min_value:g} {unit} até {max_value:g} {unit}".strip()
        elif min_value is not None:
            label = f"acima de {min_value:g} {unit}".strip()
        else:
            label = f"até {max_value:g} {unit}".strip()
        return {"min": min_value, "max": max_value, "unit": unit, "label": label}

    if condition == "above" and max_value is not None:
        return {"min": None, "max": max_value, "unit": unit, "label": f"até {max_value:g} {unit}".strip()}

    if condition == "below" and min_value is not None:
        return {"min": min_value, "max": None, "unit": unit, "label": f"acima de {min_value:g} {unit}".strip()}

    return {"min": min_value, "max": max_value, "unit": unit, "label": "Definida por texto de alarme e regra operacional"}


def _deviation(value: float | None, expected: dict[str, Any]) -> dict[str, Any]:
    unit = expected.get("unit") or ""
    min_value = _float(expected.get("min"))
    max_value = _float(expected.get("max"))
    if value is None:
        return {
            "amount": None,
            "direction": "not_numeric",
            "label": "Sem leitura numérica; classificação baseada em alarme, recorrência ou regra textual.",
        }
    if min_value is not None and value < min_value:
        delta = round(min_value - value, 2)
        return {
            "amount": delta,
            "direction": "below",
            "label": f"{delta:g} {unit} abaixo do limite mínimo operacional.".strip(),
        }
    if max_value is not None and value > max_value:
        delta = round(value - max_value, 2)
        return {
            "amount": delta,
            "direction": "above",
            "label": f"{delta:g} {unit} acima do limite máximo operacional.".strip(),
        }
    return {"amount": 0, "direction": "inside", "label": "Leitura dentro da faixa; prioridade sustentada por alarme ou recorrência."}


def _confidence_label(score: float, context: dict[str, Any]) -> str:
    sources = int(bool(context.get("alarm_text"))) + int(context.get("telemetry_value") is not None)
    if score >= 78 and sources >= 1:
        return "Alta"
    if score >= 58:
        return "Média"
    return "Baixa"


def _sensor_label(rule: dict[str, Any], context: dict[str, Any]) -> str:
    device_id = context.get("dispositivo_id")
    measurement = rule.get("measurement_type") or context.get("measurement_type")
    alarm_text = str(context.get("alarm_text") or "").lower()
    if measurement == "temperature":
        prefix = "TEMP"
    elif measurement == "pressure":
        prefix = "PRESSAO"
    elif measurement == "communication":
        prefix = "COMUNICACAO"
    elif "compressor" in alarm_text or measurement == "compressor":
        prefix = "COMPRESSOR"
    elif measurement == "defrost":
        prefix = "DEGELO"
    else:
        prefix = "ALARME"
    return f"{prefix}_{device_id}" if device_id else prefix


def _evidence_origin(context: dict[str, Any]) -> list[str]:
    origin: list[str] = ["regras operacionais"]
    if context.get("telemetry_value") is not None or context.get("telemetry_id"):
        origin.insert(0, "telemetria")
    if context.get("alarm_text"):
        origin.insert(0, "alarmes")
    if int(context.get("recurrence_count") or 0) >= 2:
        origin.append("recorrência")
    return list(dict.fromkeys(origin))


def _risk_text(rule: dict[str, Any], context: dict[str, Any], deviation: dict[str, Any]) -> str:
    text = str(context.get("alarm_text") or "").lower()
    equipment = str(context.get("equipment_type") or "").lower()
    measurement = rule.get("measurement_type") or context.get("measurement_type")
    direction = deviation.get("direction")

    if "compressor" in text or measurement == "compressor":
        return "Possível atuação de proteção térmica, desgaste prematuro ou parada do conjunto de refrigeração."
    if "offline" in text or "comunic" in text or measurement == "communication":
        return "Perda de visibilidade do equipamento; a operação fica sem confirmação remota da condição real."
    if "press" in text or "glicol" in text or measurement == "pressure":
        return "Risco de instabilidade no circuito de refrigeração, circulação ou pressão de sucção."
    if measurement == "temperature" and direction == "below":
        return "Possível congelamento indevido, sensor descalibrado ou setpoint fora do padrão operacional."
    if measurement == "temperature" and ("frozen" in equipment or "congel" in text):
        return "Risco de perda de temperatura segura para produtos congelados se a condição persistir."
    if measurement == "temperature":
        return "Risco de conservação fora da faixa esperada e necessidade de validação local da leitura."
    return "Ocorrência com prioridade operacional definida por regra técnica e histórico recente."


def _technical_reason(rule: dict[str, Any], context: dict[str, Any], expected: dict[str, Any], deviation: dict[str, Any]) -> str:
    rule_name = rule.get("name") or "Regra operacional"
    if context.get("telemetry_value") is not None:
        return (
            f"{rule_name}: leitura {_value_label(context.get('telemetry_value'), expected.get('unit') or '')} "
            f"comparada com a faixa {expected.get('label')}. {deviation.get('label')}"
        )
    if context.get("alarm_text"):
        return f"{rule_name}: alarme operacional corresponde ao padrão técnico configurado para essa criticidade."
    return f"{rule_name}: critério operacional acionado pelo histórico recente do ativo."


def _operational_evidence(rule: dict[str, Any], context: dict[str, Any]) -> str:
    recurrence = int(context.get("recurrence_count") or 0)
    if recurrence >= 2:
        return f"Evento reincidente registrado {recurrence} vezes no recorte recente."
    if context.get("telemetry_value") is not None and context.get("alarm_text"):
        return "Alarme e telemetria recente sustentam a prioridade operacional."
    if context.get("telemetry_value") is not None:
        return "Telemetria recente sustenta a comparação com a faixa operacional."
    if context.get("alarm_text"):
        return "Alarme recente corresponde ao padrao configurado na regra operacional."
    return f"Critério {rule.get('condition_type') or 'operacional'} aplicado sobre o recorte atual."


def _operational_analysis(rule: dict[str, Any], context: dict[str, Any], score: float) -> dict[str, Any]:
    expected = _expected_range(rule, context)
    deviation = _deviation(context.get("telemetry_value"), expected)
    origin = _evidence_origin(context)
    return {
        "problem_type": rule.get("name") or "Ocorrencia operacional",
        "sensor": _sensor_label(rule, context),
        "current_value": context.get("telemetry_value"),
        "current_value_label": _value_label(context.get("telemetry_value"), expected.get("unit") or ""),
        "expected_range": expected,
        "expected_range_label": expected.get("label"),
        "deviation": deviation,
        "deviation_label": deviation.get("label"),
        "technical_reason": _technical_reason(rule, context, expected, deviation),
        "operational_evidence": _operational_evidence(rule, context),
        "risk": _risk_text(rule, context, deviation),
        "confidence_label": _confidence_label(score, context),
        "confidence_score": round(score / 100, 2),
        "origin": origin,
        "origin_label": " + ".join(origin),
    }


def build_context_from_evidence(evidence: dict[str, Any], severity: str | None = None) -> dict[str, Any]:
    alarm = evidence.get("alarm") or {}
    device_metrics = evidence.get("device_metrics") or evidence.get("device_alarm_summary") or {}
    store_metrics = evidence.get("store_metrics") or {}
    telemetry = evidence.get("telemetry") or {}
    text = _text(
        alarm.get("alarm_message"),
        alarm.get("alarm_type"),
        alarm.get("tag"),
        device_metrics.get("tag"),
        evidence.get("title"),
        evidence.get("insight_type"),
    )
    inferred = infer_equipment_type(
        tag=alarm.get("tag") or device_metrics.get("tag"),
        alarm_text=text,
        group=alarm.get("group") or alarm.get("grupo"),
        subgroup=alarm.get("subgroup") or alarm.get("subgrupo"),
    )
    alarm_severity = severity
    if alarm and not alarm_severity:
        alarm_severity = classify_alarm_severity(alarm)
    telemetry_value = _float(telemetry.get("temperature") or device_metrics.get("temperature_current") or evidence.get("value"))
    return {
        "loja_id": alarm.get("loja_id") or device_metrics.get("loja_id") or store_metrics.get("loja_id"),
        "loja_nome": alarm.get("loja_nome") or device_metrics.get("loja_nome") or store_metrics.get("loja_nome"),
        "dispositivo_id": alarm.get("dispositivo_id") or device_metrics.get("dispositivo_id"),
        "tag": alarm.get("tag") or device_metrics.get("tag"),
        "alarm_id": alarm.get("id"),
        "telemetry_id": telemetry.get("id"),
        "alarm_text": text,
        "alarm_severity": alarm_severity,
        "measurement_type": infer_measurement_type(text),
        "equipment_type": inferred["equipment_type"],
        "equipment_confidence": inferred["confidence"],
        "equipment_reason": inferred["reason"],
        "telemetry_value": telemetry_value,
        "telemetry_count": int(device_metrics.get("telemetry_count") or evidence.get("telemetry_count") or 0),
        "recurrence_count": int(device_metrics.get("alarm_count") or store_metrics.get("alarm_count") or evidence.get("recurrence_count") or 0),
    }


def evaluate_context(evidence: dict[str, Any], severity: str | None = None, rules: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    context = build_context_from_evidence(evidence, severity)
    matched: list[dict[str, Any]] = []
    for raw_rule in rules or get_enabled_rules():
        rule = normalize_rule(raw_rule)
        if not rule.get("enabled", True):
            continue
        if not _scope_matches(rule, context) or not _rule_specificity_matches(rule, context):
            continue
        condition_matched = _condition_matches(
            rule,
            value=context.get("telemetry_value"),
            text=context.get("alarm_text") or "",
            recurrence_count=int(context.get("recurrence_count") or 0),
            telemetry_count=int(context.get("telemetry_count") or 0),
        )
        if not condition_matched:
            continue
        score = _score(rule, context, matched_by_alarm=bool(context.get("alarm_text")))
        matched.append(
            {
                "rule": rule,
                "score": score,
                "evidence_level": _evidence_level(score),
                "context": context,
            }
        )
    if not matched:
        return None
    matched.sort(key=lambda item: (item["rule"].get("priority", 100), -item["score"]))
    best = matched[0]
    rule = best["rule"]
    context = best["context"]
    operational_analysis = _operational_analysis(rule, context, best["score"])
    return {
        "rule_id": rule.get("id"),
        "rule_name": rule.get("name"),
        "rule_explanation": rule.get("explanation_template"),
        "rule_based_reason": rule.get("explanation_template"),
        "recommended_action": rule.get("recommended_action_template"),
        "severity": rule.get("severity_when_triggered") or severity or "warning",
        "operational_score": round(best["score"], 1),
        "evidence_level": best["evidence_level"],
        "matched_rules": [
            {
                "id": item["rule"].get("id"),
                "name": item["rule"].get("name"),
                "severity": item["rule"].get("severity_when_triggered"),
                "score": round(item["score"], 1),
            }
            for item in matched[:5]
        ],
        "inferred_equipment_type": context.get("equipment_type"),
        "equipment_type_confidence": context.get("equipment_confidence"),
        "equipment_type_reason": context.get("equipment_reason"),
        "operational_analysis": operational_analysis,
        "context": context,
    }


def enrich_evidence_with_rules(evidence: dict[str, Any], severity: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    evaluation = evaluate_context(evidence, severity)
    if not evaluation:
        return evidence, None
    enriched = {
        **evidence,
        "rule_id": evaluation.get("rule_id"),
        "rule_name": evaluation.get("rule_name"),
        "rule_explanation": evaluation.get("rule_explanation"),
        "rule_based_reason": evaluation.get("rule_based_reason"),
        "operational_score": evaluation.get("operational_score"),
        "evidence_level": evaluation.get("evidence_level"),
        "matched_rules": evaluation.get("matched_rules"),
        "inferred_equipment_type": evaluation.get("inferred_equipment_type"),
        "equipment_type_confidence": evaluation.get("equipment_type_confidence"),
        "equipment_type_reason": evaluation.get("equipment_type_reason"),
        "operational_analysis": evaluation.get("operational_analysis"),
    }
    return enriched, evaluation


def evaluate_recent_operation(units: list[dict[str, Any]], devices: list[dict[str, Any]], alarms: list[dict[str, Any]], telemetry: list[dict[str, Any]]) -> dict[str, Any]:
    units_by_id = {row.get("loja_id"): row for row in units}
    devices_by_id = {row.get("dispositivo_id"): row for row in devices}
    evaluations: list[dict[str, Any]] = []
    rules = get_enabled_rules()

    for alarm in alarms[:120]:
        device = devices_by_id.get(alarm.get("dispositivo_id"), {})
        evidence = {"alarm": {**alarm, "tag": alarm.get("tag") or device.get("tag")}}
        result = evaluate_context(evidence, classify_alarm_severity(alarm), rules)
        if not result:
            continue
        context = result["context"]
        evaluations.append(
            {
                "rule_id": result.get("rule_id") if _looks_uuid(result.get("rule_id")) else None,
                "alarm_id": alarm.get("id") if _looks_uuid(alarm.get("id")) else None,
                "loja_id": context.get("loja_id"),
                "loja_nome": context.get("loja_nome") or units_by_id.get(context.get("loja_id"), {}).get("loja_nome"),
                "dispositivo_id": context.get("dispositivo_id"),
                "tag": context.get("tag"),
                "matched": True,
                "severity": result.get("severity"),
                "score": result.get("operational_score"),
                "evidence_json": {key: value for key, value in result.items() if key != "context"},
                "explanation": result.get("rule_explanation"),
                "recommended_action": result.get("recommended_action"),
                "evaluated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    saved = insert_rule_evaluations(evaluations[:200])
    return {
        "evaluated": len(alarms[:120]),
        "matched": len(evaluations),
        "inserted": saved.get("inserted", 0),
        "schema_applied": saved.get("schema_applied", True),
        "message": saved.get("message"),
        "items": evaluations[:20],
    }


def _looks_uuid(value: Any) -> bool:
    return bool(value and re.match(r"^[0-9a-fA-F-]{32,36}$", str(value)))
