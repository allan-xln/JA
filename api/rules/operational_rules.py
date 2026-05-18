from __future__ import annotations

import re
from typing import Any


def _text(*values: Any) -> str:
    return " ".join(str(value or "") for value in values).lower()


def infer_equipment_type(*, tag: Any = None, alarm_text: Any = None, group: Any = None, subgroup: Any = None) -> dict[str, Any]:
    text = _text(tag, alarm_text, group, subgroup)

    if re.search(r"\b(glicol|bomba)\b", text):
        return {"equipment_type": "glycol_system", "confidence": 0.82, "reason": "Termos associados a circuito de glicol ou bomba."}
    if re.search(r"\b(rack|compressor|unidade condensadora|uc\b|condensadora)\b", text):
        return {"equipment_type": "refrigeration_system", "confidence": 0.82, "reason": "Termos associados ao sistema de refrigeração."}
    if re.search(r"\b(c\.?f\.?|câmara|camara)\b", text) and re.search(r"\b(congel|freezer|bta|btc)\b", text):
        return {"equipment_type": "cold_room_frozen", "confidence": 0.86, "reason": "Tag/texto indica câmara ou equipamento de congelados."}
    if re.search(r"\b(c\.?f\.?|câmara|camara)\b", text):
        return {"equipment_type": "cold_room_chilled", "confidence": 0.68, "reason": "Tag/texto indica câmara fria sem confirmação de congelados."}
    if re.search(r"\b(congel|freezer|bta|btc)\b", text):
        return {"equipment_type": "frozen", "confidence": 0.78, "reason": "Termos associados a congelados."}
    if re.search(r"\b(resfriad|latic[ií]nio|açougue|acougue|aves|rotisseria|preparo climatizado|expositor|mta)\b", text):
        return {"equipment_type": "chilled", "confidence": 0.72, "reason": "Termos associados a resfriados ou exposição refrigerada."}
    if re.search(r"\b(doca|preparo|ambiente)\b", text):
        return {"equipment_type": "preparation_area", "confidence": 0.58, "reason": "Termos associados a ambiente ou área de preparo."}
    return {"equipment_type": "unknown", "confidence": 0.2, "reason": "Não houve termos suficientes para classificar o ativo."}


def infer_measurement_type(text: str) -> str:
    normalized = text.lower()
    if re.search(r"temperatura|temp\.?|ambiente|evapora", normalized):
        return "temperature"
    if re.search(r"offline|comunica|sinal", normalized):
        return "communication"
    if re.search(r"compressor", normalized):
        return "compressor"
    if re.search(r"press[aã]o|succ?ao|glicol", normalized):
        return "pressure"
    if re.search(r"degelo", normalized):
        return "defrost"
    return "unknown"


def format_rule_limit(rule: dict[str, Any]) -> str:
    condition = rule.get("condition_type")
    min_value = rule.get("threshold_min")
    max_value = rule.get("threshold_max")
    if condition == "above" and max_value is not None:
        return f"> {max_value}"
    if condition == "below" and min_value is not None:
        return f"< {min_value}"
    if condition in {"between", "outside_range"} and (min_value is not None or max_value is not None):
        return f"{min_value if min_value is not None else '-'} a {max_value if max_value is not None else '-'}"
    if rule.get("alarm_text_pattern"):
        return str(rule["alarm_text_pattern"])
    if condition == "repeated_event":
        return f"{rule.get('recurrence_count') or 3} eventos / {rule.get('recurrence_window_minutes') or 120} min"
    return "-"


def normalize_rule(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id") or row.get("name"),
        "name": row.get("name") or "Regra operacional",
        "description": row.get("description"),
        "enabled": row.get("enabled", True),
        "scope_type": row.get("scope_type") or "global",
        "scope_value": row.get("scope_value"),
        "priority": int(row.get("priority") or 100),
        "severity_when_triggered": row.get("severity_when_triggered") or row.get("severity") or "warning",
        "equipment_type": row.get("equipment_type"),
        "measurement_type": row.get("measurement_type"),
        "condition_type": row.get("condition_type") or "contains_text",
        "threshold_min": row.get("threshold_min"),
        "threshold_max": row.get("threshold_max"),
        "duration_minutes": row.get("duration_minutes"),
        "recurrence_count": row.get("recurrence_count"),
        "recurrence_window_minutes": row.get("recurrence_window_minutes"),
        "alarm_text_pattern": row.get("alarm_text_pattern"),
        "explanation_template": row.get("explanation_template") or row.get("description") or "",
        "recommended_action_template": row.get("recommended_action_template") or "Validar evidências no painel operacional antes de acionar manutenção.",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }
