from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from fastapi import HTTPException

from api.anomaly_public_code import (
    ensure_anomaly_public_code,
    ensure_public_code_on_row,
    find_anomaly_by_public_code,
    normalize_public_code,
)
from api.auth import AuthUser, TenantScope
from api.config import settings
from api.database import SupabaseError, supabase
from api.logger import logger
from api.notifications.auto_notifier import (
    _customer_name_for_id,
    _load_customer_links,
    _load_customer_names,
    _normalize_recipient_phone,
    _row_customer_id,
    _send_message,
    _whatsapp_status,
    list_recipients,
)
from api.repositories import parse_utc_datetime, patch_anomaly, row_in_scope, scoped_fetch_limit, utc_now_iso


ANOMALY_OPERATIONS_SCHEMA_MESSAGE = "Execute sql/007_anomaly_operations.sql no Supabase antes de usar operações de anomalia."
OPERATIONAL_STATUSES = {
    "open",
    "acknowledged",
    "investigating",
    "solution_suggested",
    "whatsapp_sent",
    "ticket_opened",
    "resolved",
    "reopened",
    "ignored",
}
ACTIVE_STATUSES = {
    "open",
    "acknowledged",
    "investigating",
    "solution_suggested",
    "whatsapp_sent",
    "ticket_opened",
    "reopened",
}

ANOMALY_LIST_SELECT = ",".join(
    [
        "id",
        "anomaly_hash",
        "anomaly_key",
        "status",
        "severity",
        "loja_id",
        "loja_nome",
        "dispositivo_id",
        "equipment_id",
        "sensor_id",
        "tag",
        "type",
        "title",
        "summary",
        "message",
        "technical_reason",
        "recommended_action",
        "value",
        "expected_range",
        "source",
        "detected_at",
        "last_seen_at",
        "resolved_at",
        "whatsapp_sent_at",
        "whatsapp_status",
        "whatsapp_error",
        "ticket_opened_at",
        "created_at",
        "updated_at",
        "customer_id",
        "acknowledged_at",
        "reopened_at",
        "ignored_until",
        "recurrence_count",
        "priority_score",
        "public_code",
        "public_code_created_at",
        "related_public_code",
    ]
)

AI_SOLUTION_SYSTEM_PROMPT = (
    "Voce e um especialista operacional em refrigeracao comercial da Eletrofrio. "
    "Use somente o JSON da anomalia fornecido. Nao invente loja, equipamento, sensor, valor, faixa ou causa raiz. "
    "Aponte hipoteses praticas, deixando claro que a causa raiz precisa ser validada em campo. "
    "Responda apenas JSON valido com as chaves: diagnosis, probable_cause, alternative_causes, immediate_action, "
    "technical_action, urgency, risk, field_technician_required, whatsapp_message, root_cause_note."
)


def _schema_missing(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "eletrofrio_anomaly_events" in text
        or "eletrofrio_anomaly_tickets" in text
        or "eletrofrio_anomaly_notes" in text
        or "eletrofrio_anomaly_ai_solutions" in text
        or "last_solution_json" in text
        or "priority_score" in text
        or "reopened_at" in text
        or "pgrst205" in text
        or "schema cache" in text
    )


def _raise_schema(exc: Exception) -> None:
    if _schema_missing(exc):
        raise HTTPException(status_code=503, detail=ANOMALY_OPERATIONS_SCHEMA_MESSAGE) from exc
    raise exc


def _severity_rank(value: Any) -> int:
    normalized = str(value or "").strip().casefold()
    return {
        "critical": 4,
        "critico": 4,
        "crítico": 4,
        "high": 3,
        "alta": 3,
        "warning": 2,
        "medium": 2,
        "media": 2,
        "média": 2,
        "low": 1,
        "info": 1,
    }.get(normalized, 0)


def _parse_number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _format_value(value: Any) -> str:
    numeric = _parse_number(value)
    if numeric is None:
        return "-" if value in (None, "") else str(value)
    return f"{numeric:.1f} C"


def _expected_range_label(expected_range: Any) -> str:
    expected = _json_dict(expected_range)
    minimum = expected.get("min")
    maximum = expected.get("max")
    if minimum is None and maximum is None:
        return "faixa esperada nao informada"
    if minimum is None:
        return f"ate {_format_value(maximum)}"
    if maximum is None:
        return f"a partir de {_format_value(minimum)}"
    return f"{_format_value(minimum)} a {_format_value(maximum)}"


def _deviation(row: dict[str, Any]) -> float | None:
    value = _parse_number(row.get("value"))
    expected = _json_dict(row.get("expected_range"))
    if value is None or not expected:
        return None
    minimum = _parse_number(expected.get("min"))
    maximum = _parse_number(expected.get("max"))
    if minimum is not None and value < minimum:
        return minimum - value
    if maximum is not None and value > maximum:
        return value - maximum
    return 0.0


def _dt(value: Any) -> datetime | None:
    return parse_utc_datetime(value)


def _age_hours(row: dict[str, Any]) -> float:
    started = _dt(row.get("detected_at")) or _dt(row.get("created_at"))
    if not started:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - started).total_seconds() / 3600)


def _customer_context(row: dict[str, Any], customer_names: dict[str, str] | None = None) -> tuple[str | None, str | None]:
    customer_id = str(row.get("customer_id") or "").strip() or None
    if not customer_id:
        unit_links, device_links = _load_customer_links()
        customer_id = _row_customer_id(row, unit_links, device_links)
    return customer_id, _customer_name_for_id(customer_id, customer_names) if customer_id else None


def _normalize_anomaly(row: dict[str, Any], customer_names: dict[str, str] | None = None) -> dict[str, Any]:
    customer_id, customer_name = _customer_context(row, customer_names)
    evidence = _json_dict(row.get("evidence_json"))
    metadata = _json_dict(row.get("metadata"))
    value = row.get("value")
    deviation = _deviation(row)
    detected_at = row.get("detected_at") or row.get("created_at")
    last_seen_at = row.get("last_seen_at") or row.get("updated_at") or detected_at
    title = (
        row.get("title")
        or row.get("summary")
        or row.get("message")
        or "Anomalia operacional"
    )
    normalized = {
        **row,
        "title": title,
        "status": row.get("status") or "open",
        "customer_id": customer_id,
        "customer_name": customer_name,
        "dispositivo_id": row.get("dispositivo_id") or row.get("equipment_id"),
        "equipment_id": row.get("equipment_id") or row.get("dispositivo_id"),
        "value_label": _format_value(value),
        "expected_range_label": _expected_range_label(row.get("expected_range")),
        "deviation": deviation,
        "deviation_label": _format_value(deviation) if deviation is not None else "-",
        "detected_at": detected_at,
        "last_seen_at": last_seen_at,
        "open_hours": round(_age_hours(row), 2),
        "recurrence_count": int(row.get("recurrence_count") or 0),
        "evidence_json": evidence,
        "metadata": metadata,
    }
    return normalized


def _ensure_access(row: dict[str, Any], scope: TenantScope) -> dict[str, Any]:
    normalized = _normalize_anomaly(row)
    if not row_in_scope(normalized, scope):
        raise HTTPException(status_code=404, detail="Anomalia não encontrada para este ambiente.")
    return normalized


def _fetch_anomaly(anomaly_id: str, user: AuthUser) -> dict[str, Any]:
    rows = supabase.select("eletrofrio_anomalies", {"select": "*", "id": f"eq.{anomaly_id}", "limit": 1})
    if not rows:
        raise HTTPException(status_code=404, detail="Anomalia não encontrada.")
    try:
        row = ensure_public_code_on_row(rows[0])
    except Exception as exc:
        logger.warning("Não foi possível garantir código público para anomalia %s: %s", anomaly_id, exc)
        row = rows[0]
    return _ensure_access(row, user.scope)


def _status_base_score(status: str) -> int:
    return {
        "reopened": 700,
        "open": 650,
        "investigating": 600,
        "solution_suggested": 560,
        "ticket_opened": 540,
        "whatsapp_sent": 530,
        "acknowledged": 500,
        "ignored": 80,
        "resolved": 0,
    }.get(status, 350)


def _priority_score(row: dict[str, Any], store_counts: dict[Any, int], device_counts: dict[Any, int]) -> float:
    severity = _severity_rank(row.get("severity"))
    status = str(row.get("status") or "open")
    recurrence = int(row.get("recurrence_count") or 0)
    loja_id = row.get("loja_id")
    device_id = row.get("dispositivo_id") or row.get("equipment_id")
    deviation = _deviation(row) or 0
    age = min(_age_hours(row), 96)

    score = severity * 1000 + _status_base_score(status)
    if severity >= 4 and status == "reopened":
        score += 400
    if severity >= 4 and status == "open":
        score += 250
    if severity >= 2 and recurrence > 0:
        score += min(250, recurrence * 80)
    if store_counts.get(loja_id, 0) > 1:
        score += min(180, store_counts[loja_id] * 35)
    if device_counts.get(device_id, 0) > 1:
        score += min(180, device_counts[device_id] * 45)
    if row.get("whatsapp_sent_at") and status not in {"resolved", "ignored"}:
        score += 60
    if row.get("ticket_opened_at") and status not in {"resolved", "ignored"}:
        score += 40
    score += min(120, age * 2)
    score += min(160, abs(deviation) * 12)
    return round(score, 2)


def _sort_prioritized(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active_rows = [row for row in rows if str(row.get("status") or "open") not in {"resolved", "ignored"}]
    store_counts: dict[Any, int] = {}
    device_counts: dict[Any, int] = {}
    for row in active_rows:
        if row.get("loja_id") is not None:
            store_counts[row.get("loja_id")] = store_counts.get(row.get("loja_id"), 0) + 1
        device_id = row.get("dispositivo_id") or row.get("equipment_id")
        if device_id is not None:
            device_counts[device_id] = device_counts.get(device_id, 0) + 1

    enriched = []
    for row in rows:
        priority = _priority_score(row, store_counts, device_counts)
        enriched.append({**row, "priority_score": priority})

    return sorted(
        enriched,
        key=lambda item: (
            str(item.get("status") or "open") in {"resolved", "ignored"},
            -float(item.get("priority_score") or 0),
            -(parse_utc_datetime(item.get("last_seen_at") or item.get("detected_at") or item.get("updated_at")) or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
        ),
    )


def list_operational_anomalies(
    user: AuthUser,
    limit: int = 100,
    offset: int = 0,
    status: str | None = "active",
    severity: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    page_limit = min(max(limit, 1), 200)
    page_offset = max(offset, 0)
    fetch_limit = scoped_fetch_limit(page_limit + page_offset, user.scope, multiplier=8)
    params: dict[str, Any] = {"select": ANOMALY_LIST_SELECT, "order": "updated_at.desc", "limit": fetch_limit}
    normalized_status = str(status or "active").strip().lower()
    if normalized_status in {"active", "open", ""}:
        params["status"] = f"in.({','.join(sorted(ACTIVE_STATUSES))})"
    elif normalized_status in OPERATIONAL_STATUSES:
        params["status"] = f"eq.{normalized_status}"
    elif normalized_status == "history":
        params["status"] = "in.(resolved,ignored)"
    if severity and severity != "all":
        params["severity"] = f"eq.{severity}"
    if user.scope.is_admin:
        params["offset"] = page_offset if normalized_status in OPERATIONAL_STATUSES else 0

    try:
        raw_rows = supabase.select("eletrofrio_anomalies", params, timeout=6, attempts=1)
    except SupabaseError as exc:
        _raise_schema(exc)

    customer_names = _load_customer_names()
    rows = [_normalize_anomaly(row, customer_names) for row in raw_rows]
    rows = [row for row in rows if row_in_scope(row, user.scope)]

    if normalized_status in {"active", "open", ""}:
        rows = [row for row in rows if str(row.get("status") or "open") in ACTIVE_STATUSES]
    elif normalized_status == "history":
        rows = [row for row in rows if str(row.get("status") or "open") in {"resolved", "ignored"}]
    elif normalized_status == "all":
        pass

    if search:
        needle = search.strip().casefold()
        rows = [
            row
            for row in rows
            if needle
            in " ".join(
                str(part or "")
                for part in [
                    row.get("title"),
                    row.get("message"),
                    row.get("loja_nome"),
                    row.get("tag"),
                    row.get("sensor_id"),
                    row.get("type"),
                    row.get("customer_name"),
                    row.get("public_code"),
                ]
            ).casefold()
        ]

    prioritized = _sort_prioritized(rows)
    if not user.scope.is_admin or normalized_status not in OPERATIONAL_STATUSES:
        prioritized = prioritized[page_offset : page_offset + page_limit]
    else:
        prioritized = prioritized[:page_limit]

    return {"items": prioritized, "count": len(rows), "limit": page_limit, "offset": page_offset}


def _event_payload(
    anomaly: dict[str, Any],
    user: AuthUser,
    event_type: str,
    title: str,
    description: str | None = None,
    old_status: str | None = None,
    new_status: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "anomaly_id": anomaly.get("id"),
        "customer_id": anomaly.get("customer_id"),
        "public_code": anomaly.get("public_code"),
        "user_id": user.id,
        "event_type": event_type,
        "old_status": old_status,
        "new_status": new_status,
        "title": title,
        "description": description,
        "metadata": {"public_code": anomaly.get("public_code"), **(metadata or {})},
    }


def create_anomaly_event(
    anomaly: dict[str, Any],
    user: AuthUser,
    event_type: str,
    title: str,
    description: str | None = None,
    old_status: str | None = None,
    new_status: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    try:
        rows = supabase.insert(
            "eletrofrio_anomaly_events",
            _event_payload(anomaly, user, event_type, title, description, old_status, new_status, metadata),
        )
        return rows[0] if rows else None
    except SupabaseError as exc:
        _raise_schema(exc)
    return None


def _synthetic_created_event(anomaly: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"synthetic-created-{anomaly.get('id')}",
        "anomaly_id": anomaly.get("id"),
        "customer_id": anomaly.get("customer_id"),
        "user_id": None,
        "event_type": "created",
        "old_status": None,
        "new_status": anomaly.get("status") or "open",
        "title": "Anomalia detectada",
        "description": anomaly.get("message") or anomaly.get("title"),
        "metadata": {"source": anomaly.get("source"), "public_code": anomaly.get("public_code")},
        "created_at": anomaly.get("detected_at") or anomaly.get("created_at"),
        "synthetic": True,
    }


def list_anomaly_events(anomaly_id: str, user: AuthUser) -> dict[str, Any]:
    anomaly = _fetch_anomaly(anomaly_id, user)
    try:
        rows = supabase.select(
            "eletrofrio_anomaly_events",
            {"select": "*", "anomaly_id": f"eq.{anomaly_id}", "order": "created_at.asc", "limit": 500},
        )
    except SupabaseError as exc:
        _raise_schema(exc)
    events = [
        _synthetic_created_event(anomaly),
        *[{**row, "public_code": row.get("public_code") or anomaly.get("public_code")} for row in rows],
    ]
    return {"items": events}


def _list_notes(anomaly_id: str) -> list[dict[str, Any]]:
    try:
        return supabase.select(
            "eletrofrio_anomaly_notes",
            {"select": "*", "anomaly_id": f"eq.{anomaly_id}", "order": "created_at.asc", "limit": 200},
        )
    except SupabaseError as exc:
        _raise_schema(exc)
    return []


def _list_tickets(anomaly_id: str, public_code: str | None = None) -> list[dict[str, Any]]:
    try:
        rows = supabase.select(
            "eletrofrio_anomaly_tickets",
            {"select": "*", "anomaly_id": f"eq.{anomaly_id}", "order": "created_at.desc", "limit": 50},
        )
        return [{**row, "public_code": row.get("public_code") or public_code} for row in rows]
    except SupabaseError as exc:
        _raise_schema(exc)
    return []


def _latest_solution(anomaly_id: str) -> dict[str, Any] | None:
    try:
        rows = supabase.select(
            "eletrofrio_anomaly_ai_solutions",
            {"select": "*", "anomaly_id": f"eq.{anomaly_id}", "order": "created_at.desc", "limit": 1},
        )
        return rows[0] if rows else None
    except SupabaseError as exc:
        _raise_schema(exc)
    return None


def get_operational_anomaly(anomaly_id: str, user: AuthUser) -> dict[str, Any]:
    anomaly = _fetch_anomaly(anomaly_id, user)
    return {
        **anomaly,
        "events": list_anomaly_events(anomaly_id, user)["items"],
        "notes": _list_notes(anomaly_id),
        "tickets": _list_tickets(anomaly_id, anomaly.get("public_code")),
        "latest_solution": _latest_solution(anomaly_id),
    }


def get_operational_anomaly_by_code(public_code: str, user: AuthUser) -> dict[str, Any]:
    normalized = normalize_public_code(public_code)
    if not normalized:
        raise HTTPException(status_code=404, detail="Ocorrência não encontrada ou sem permissão para visualizar.")
    row = find_anomaly_by_public_code(normalized, user.scope)
    if not row:
        raise HTTPException(status_code=404, detail="Ocorrência não encontrada ou sem permissão para visualizar.")
    return get_operational_anomaly(str(row["id"]), user)


def ensure_operational_anomaly_public_code(anomaly_id: str, user: AuthUser) -> dict[str, Any]:
    anomaly = _fetch_anomaly(anomaly_id, user)
    try:
        code = ensure_anomaly_public_code(anomaly_id, anomaly)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Anomalia não encontrada.") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Não foi possível gerar o código da ocorrência agora.") from exc
    return {**anomaly, "public_code": code}


def _solution_context(anomaly: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": anomaly.get("id"),
        "public_code": anomaly.get("public_code"),
        "customer_name": anomaly.get("customer_name"),
        "customer_id": anomaly.get("customer_id"),
        "loja_nome": anomaly.get("loja_nome"),
        "loja_id": anomaly.get("loja_id"),
        "equipamento": anomaly.get("tag") or anomaly.get("dispositivo_id") or anomaly.get("equipment_id"),
        "sensor": anomaly.get("sensor_id"),
        "type": anomaly.get("type"),
        "title": anomaly.get("title"),
        "message": anomaly.get("message"),
        "technical_reason": anomaly.get("technical_reason"),
        "recommended_action": anomaly.get("recommended_action"),
        "severity": anomaly.get("severity"),
        "status": anomaly.get("status"),
        "value": anomaly.get("value"),
        "value_label": anomaly.get("value_label"),
        "expected_range": anomaly.get("expected_range"),
        "expected_range_label": anomaly.get("expected_range_label"),
        "deviation": anomaly.get("deviation"),
        "detected_at": anomaly.get("detected_at"),
        "last_seen_at": anomaly.get("last_seen_at"),
        "open_hours": anomaly.get("open_hours"),
        "recurrence_count": anomaly.get("recurrence_count"),
        "evidence": anomaly.get("evidence_json"),
    }


def _solution_hash(anomaly: dict[str, Any]) -> str:
    context = _solution_context(anomaly)
    relevant = {
        key: context.get(key)
        for key in [
            "type",
            "severity",
            "status",
            "value",
            "expected_range",
            "message",
            "technical_reason",
            "recommended_action",
            "last_seen_at",
            "recurrence_count",
        ]
    }
    return hashlib.sha256(json.dumps(relevant, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _solution_to_text(solution: dict[str, Any]) -> str:
    alternatives = _json_list(solution.get("alternative_causes"))
    alternatives_text = "\n".join(f"- {item}" for item in alternatives) if alternatives else "- Sem causas alternativas evidentes nos dados."
    return "\n".join(
        [
            "Diagnóstico provável:",
            str(solution.get("diagnosis") or "-"),
            "",
            "Causa mais provável:",
            str(solution.get("probable_cause") or "-"),
            "",
            "Causas alternativas:",
            alternatives_text,
            "",
            "Ação imediata:",
            str(solution.get("immediate_action") or "-"),
            "",
            "Ação técnica:",
            str(solution.get("technical_action") or "-"),
            "",
            "Urgência:",
            str(solution.get("urgency") or "-"),
            "",
            "Risco se não corrigir:",
            str(solution.get("risk") or "-"),
            "",
            "Precisa técnico em campo:",
            str(solution.get("field_technician_required") or "-"),
            "",
            "Mensagem WhatsApp:",
            str(solution.get("whatsapp_message") or "-"),
            "",
            str(solution.get("root_cause_note") or "A causa raiz precisa ser validada em campo."),
        ]
    ).strip()


def _fallback_solution(anomaly: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
    store = anomaly.get("loja_nome") or f"loja {anomaly.get('loja_id') or '-'}"
    equipment = anomaly.get("tag") or f"equipamento {anomaly.get('dispositivo_id') or anomaly.get('equipment_id') or '-'}"
    title = anomaly.get("title") or anomaly.get("message") or "anomalia operacional"
    severity = str(anomaly.get("severity") or "warning")
    urgency = "Alta" if _severity_rank(severity) >= 4 else "Média"
    value = anomaly.get("value_label") or _format_value(anomaly.get("value"))
    expected = anomaly.get("expected_range_label") or _expected_range_label(anomaly.get("expected_range"))
    return {
        "diagnosis": f"{title} em {equipment}, {store}. Leitura atual {value}, faixa esperada {expected}.",
        "probable_cause": "Condição operacional fora da faixa registrada nos dados. A causa raiz ainda não está confirmada.",
        "alternative_causes": [
            "Porta aberta ou carga térmica elevada.",
            "Obstrução de ventilação ou evaporador com restrição.",
            "Sensor com leitura inconsistente.",
            "Falha ou baixa eficiência no ciclo de refrigeração.",
        ],
        "immediate_action": "Validar porta, carga térmica, circulação de ar, leitura do sensor e condição visual do equipamento.",
        "technical_action": "Checar sensor, compressor, ventiladores, degelo, evaporador e parâmetros de controle.",
        "urgency": urgency,
        "risk": "Se a condição permanecer fora da faixa, pode haver perda de produto, perda de eficiência térmica ou falha operacional.",
        "field_technician_required": "Recomendado acionar técnico se a condição persistir apos verificações operacionais simples.",
        "whatsapp_message": (
            f"Ocorrência {severity} na {store}, {equipment}. {title}. "
            "Verificar porta, sensor, ventilação e sistema de refrigeração."
        ),
        "root_cause_note": "A causa raiz precisa ser validada em campo antes de qualquer conclusão definitiva.",
        "fallback_reason": reason,
    }


def _cached_solution(anomaly_id: str, solution_hash: str) -> dict[str, Any] | None:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max(1, settings.ai_solution_cache_minutes))).isoformat()
    try:
        rows = supabase.select(
            "eletrofrio_anomaly_ai_solutions",
            {
                "select": "*",
                "anomaly_id": f"eq.{anomaly_id}",
                "solution_hash": f"eq.{solution_hash}",
                "created_at": f"gte.{cutoff}",
                "order": "created_at.desc",
                "limit": 1,
            },
        )
        return rows[0] if rows else None
    except SupabaseError as exc:
        _raise_schema(exc)
    return None


def _daily_count(params: dict[str, str]) -> int:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    query = {"select": "id", "created_at": f"gte.{start}", "limit": 1000, **params}
    try:
        return len(supabase.select("eletrofrio_anomaly_ai_solutions", query))
    except SupabaseError as exc:
        _raise_schema(exc)
    return 0


def _ai_quota_available(user: AuthUser, customer_id: str | None) -> tuple[bool, str | None]:
    if settings.ai_solution_max_per_user_day > 0:
        user_count = _daily_count({"user_id": f"eq.{user.id}"})
        if user_count >= settings.ai_solution_max_per_user_day:
            return False, "limite diário de IA por usuário atingido"
    if customer_id and settings.ai_solution_max_per_customer_day > 0:
        customer_count = _daily_count({"customer_id": f"eq.{customer_id}"})
        if customer_count >= settings.ai_solution_max_per_customer_day:
            return False, "limite diário de IA por cliente atingido"
    return True, None


def _call_openai_solution(context: dict[str, Any]) -> tuple[dict[str, Any], bool, str | None]:
    if not settings.ai_solution_enabled:
        return {}, False, "IA de sugestão desativada."
    if not settings.openai_enabled:
        return {}, False, "OpenAI não configurada."

    payload = {
        "model": settings.ai_solution_model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": AI_SOLUTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "Gerar sugestao pratica de correcao para esta anomalia operacional.",
                        "required_output": [
                            "diagnosis",
                            "probable_cause",
                            "alternative_causes",
                            "immediate_action",
                            "technical_action",
                            "urgency",
                            "risk",
                            "field_technician_required",
                            "whatsapp_message",
                            "root_cause_note",
                        ],
                        "anomaly": context,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ],
    }
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=min(settings.http_timeout_seconds, 20),
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            return {}, False, "Resposta da IA veio em formato inesperado."
        return parsed, True, None
    except Exception as exc:
        logger.warning("Falha ao gerar sugestão IA de anomalia; usando fallback local: %s", exc)
        return {}, False, str(exc)[:300]


def _persist_solution(
    anomaly: dict[str, Any],
    user: AuthUser,
    solution_hash: str,
    context: dict[str, Any],
    solution: dict[str, Any],
    used_ai: bool,
    cached: bool,
    error: str | None,
) -> dict[str, Any]:
    solution_text = _solution_to_text(solution)
    try:
        rows = supabase.insert(
            "eletrofrio_anomaly_ai_solutions",
            {
                "anomaly_id": anomaly.get("id"),
                "customer_id": anomaly.get("customer_id"),
                "user_id": user.id,
                "solution_hash": solution_hash,
                "model": settings.ai_solution_model if used_ai else None,
                "used_ai": used_ai,
                "cached": cached,
                "prompt_context": context,
                "solution_json": solution,
                "solution_text": solution_text,
                "error_message": error,
            },
        )
    except SupabaseError as exc:
        _raise_schema(exc)
    saved = rows[0] if rows else {}
    return {**saved, "solution_json": solution, "solution_text": solution_text, "used_ai": used_ai, "cached": cached}


def suggest_solution(anomaly_id: str, user: AuthUser) -> dict[str, Any]:
    anomaly = _fetch_anomaly(anomaly_id, user)
    solution_hash = _solution_hash(anomaly)
    create_anomaly_event(
        anomaly,
        user,
        "ai_solution_requested",
        "Sugestão de correção solicitada",
        "Usuário solicitou análise operacional por IA.",
        metadata={"solution_hash": solution_hash},
    )

    cached = _cached_solution(str(anomaly["id"]), solution_hash)
    if cached:
        create_anomaly_event(
            anomaly,
            user,
            "ai_solution_generated",
            "Sugestão reutilizada do cache",
            "A anomalia não mudou dentro da janela de cache configurada.",
            old_status=anomaly.get("status"),
            new_status=anomaly.get("status"),
            metadata={"solution_hash": solution_hash, "cached": True, "solution_id": cached.get("id")},
        )
        return {"solution": cached, "cached": True, "anomaly": anomaly}

    quota_ok, quota_reason = _ai_quota_available(user, anomaly.get("customer_id"))
    context = _solution_context(anomaly)
    ai_solution: dict[str, Any] = {}
    used_ai = False
    error: str | None = quota_reason
    if quota_ok:
        ai_solution, used_ai, error = _call_openai_solution(context)

    solution = ai_solution if ai_solution else _fallback_solution(anomaly, error)
    saved = _persist_solution(anomaly, user, solution_hash, context, solution, used_ai, False, error)
    old_status = str(anomaly.get("status") or "open")
    new_status = "solution_suggested" if old_status not in {"resolved", "ignored"} else old_status
    patch_payload = {
        "last_solution_hash": solution_hash,
        "last_solution_at": utc_now_iso(),
        "last_solution_json": solution,
    }
    if new_status != old_status:
        patch_payload["status"] = new_status
    try:
        updated = patch_anomaly(str(anomaly["id"]), patch_payload) or anomaly
    except SupabaseError as exc:
        _raise_schema(exc)
    updated = _normalize_anomaly(updated)

    create_anomaly_event(
        updated,
        user,
        "ai_solution_generated",
        "IA gerou sugestão de correção" if used_ai else "Sugestão local gerada",
        None if used_ai else "Fallback local usado para manter a operação fluindo.",
        old_status=old_status,
        new_status=new_status,
        metadata={"solution_hash": solution_hash, "solution_id": saved.get("id"), "used_ai": used_ai, "error": error},
    )
    return {"solution": saved, "cached": False, "anomaly": updated}


def _latest_solution_payload(anomaly: dict[str, Any]) -> dict[str, Any]:
    latest = _latest_solution(str(anomaly["id"]))
    if latest:
        return latest
    if anomaly.get("last_solution_json"):
        solution_json = _json_dict(anomaly.get("last_solution_json"))
        return {
            "id": None,
            "anomaly_id": anomaly.get("id"),
            "customer_id": anomaly.get("customer_id"),
            "solution_json": solution_json,
            "solution_text": _solution_to_text(solution_json),
            "created_at": anomaly.get("last_solution_at"),
        }
    raise HTTPException(status_code=400, detail="Gere uma sugestão de correção antes de enviar por WhatsApp.")


def _recipient_for_payload(anomaly: dict[str, Any], user: AuthUser, payload: dict[str, Any]) -> dict[str, Any]:
    recipients = [row for row in list_recipients(None if user.scope.is_admin else user.scope).get("items", []) if row.get("enabled", True)]
    anomaly_customer_id = str(anomaly.get("customer_id") or "")

    if payload.get("recipient_id"):
        recipient = next((row for row in recipients if str(row.get("id")) == str(payload["recipient_id"])), None)
        if not recipient:
            raise HTTPException(status_code=404, detail="Destinatário não encontrado para este ambiente.")
        if not user.scope.is_admin and str(recipient.get("customer_id") or "") != anomaly_customer_id:
            raise HTTPException(status_code=403, detail="Destinatário não pertence a este cliente.")
        return recipient

    if payload.get("phone"):
        if not user.scope.is_admin:
            raise HTTPException(status_code=403, detail="Cliente só pode usar destinatários configurados do próprio ambiente.")
        try:
            phone = _normalize_recipient_phone(payload["phone"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "source": "manual",
            "role": "admin",
            "name": "Envio manual",
            "phone": phone,
            "channel": "whatsapp",
            "customer_id": anomaly.get("customer_id"),
        }

    matching = [
        row
        for row in recipients
        if row.get("phone")
        and (
            (anomaly_customer_id and str(row.get("customer_id") or "") == anomaly_customer_id)
            or (user.scope.is_admin and row.get("role") == "admin")
        )
    ]
    if matching:
        matching.sort(key=lambda item: (0 if str(item.get("customer_id") or "") == anomaly_customer_id else 1, str(item.get("name") or "")))
        return matching[0]

    raise HTTPException(status_code=400, detail="Nenhum destinatário WhatsApp configurado para o cliente desta anomalia.")


def _whatsapp_message(anomaly: dict[str, Any], solution: dict[str, Any]) -> str:
    data = _json_dict(solution.get("solution_json"))
    suggestion = str(data.get("whatsapp_message") or data.get("immediate_action") or anomaly.get("recommended_action") or anomaly.get("message") or "").strip()
    if len(suggestion) > 420:
        suggestion = suggestion[:417].rstrip() + "..."
    return "\n".join(
        [
            "Alerta Eletrofrio",
            "",
            f"Código: {anomaly.get('public_code')}",
            f"Loja: {anomaly.get('loja_nome') or anomaly.get('customer_name') or anomaly.get('loja_id') or '-'}",
            f"Equipamento: {anomaly.get('tag') or anomaly.get('dispositivo_id') or anomaly.get('equipment_id') or '-'}",
            f"Problema: {anomaly.get('title') or anomaly.get('message') or '-'}",
            f"Prioridade: {anomaly.get('severity') or '-'}",
            "",
            "Sugestão:",
            suggestion or "Verificar condição operacional no painel.",
            "",
            f"Use o código {anomaly.get('public_code')} no painel para consultar detalhes e possível solução.",
            settings.app_public_url,
        ]
    ).strip()


def _recent_whatsapp_event(anomaly_id: str, solution_hash: str | None) -> bool:
    try:
        rows = supabase.select(
            "eletrofrio_anomaly_events",
            {
                "select": "id,metadata",
                "anomaly_id": f"eq.{anomaly_id}",
                "event_type": "eq.whatsapp_sent",
                "order": "created_at.desc",
                "limit": 5,
            },
        )
    except SupabaseError as exc:
        _raise_schema(exc)
    if not rows:
        return False
    if not solution_hash:
        return True
    return any(_json_dict(row.get("metadata")).get("solution_hash") == solution_hash for row in rows)


def send_anomaly_whatsapp(anomaly_id: str, user: AuthUser, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    anomaly = _fetch_anomaly(anomaly_id, user)
    solution = _latest_solution_payload(anomaly)
    solution_hash = str(solution.get("solution_hash") or anomaly.get("last_solution_hash") or "")
    create_anomaly_event(
        anomaly,
        user,
        "whatsapp_send_requested",
        "Envio WhatsApp solicitado",
        metadata={"solution_id": solution.get("id"), "solution_hash": solution_hash},
    )

    if not payload.get("confirm_duplicate") and _recent_whatsapp_event(anomaly_id, solution_hash):
        raise HTTPException(status_code=409, detail="Esta sugestão já foi enviada por WhatsApp. Confirme para reenviar.")

    recipient = _recipient_for_payload(anomaly, user, payload)
    message = _whatsapp_message(anomaly, solution)
    dry_run = settings.whatsapp_dry_run
    whatsapp = _whatsapp_status()
    if not dry_run and (not whatsapp.get("enabled") or not whatsapp.get("connected")):
        create_anomaly_event(
            anomaly,
            user,
            "whatsapp_failed",
            "WhatsApp desconectado",
            "O serviço WhatsApp não está conectado no momento.",
            metadata={"whatsapp": whatsapp, "recipient": recipient.get("id") or recipient.get("phone")},
        )
        patch_anomaly(str(anomaly["id"]), {"whatsapp_status": "whatsapp_disconnected", "whatsapp_error": whatsapp.get("error")})
        return {"status": "whatsapp_disconnected", "whatsapp": whatsapp, "message": "WhatsApp desconectado.", "sent": False}

    status, error, provider_id = ("dry_run", None, None) if dry_run else _send_message(recipient, message)
    old_status = str(anomaly.get("status") or "open")
    new_status = "whatsapp_sent" if status in {"sent", "dry_run"} and old_status not in {"resolved", "ignored"} else old_status
    patch_payload = {
        "whatsapp_status": status,
        "whatsapp_error": error,
    }
    if status in {"sent", "dry_run"}:
        patch_payload["whatsapp_sent_at"] = utc_now_iso()
        if new_status != old_status:
            patch_payload["status"] = new_status
    try:
        updated = patch_anomaly(str(anomaly["id"]), patch_payload) or anomaly
    except SupabaseError as exc:
        _raise_schema(exc)
    updated = _normalize_anomaly(updated)
    event_type = "whatsapp_sent" if status in {"sent", "dry_run"} else "whatsapp_failed"
    create_anomaly_event(
        updated,
        user,
        event_type,
        "Sugestão enviada por WhatsApp" if status in {"sent", "dry_run"} else "Falha ao enviar WhatsApp",
        error,
        old_status=old_status,
        new_status=new_status,
        metadata={
            "status": status,
            "recipient_id": recipient.get("id"),
            "phone": recipient.get("phone"),
            "solution_id": solution.get("id"),
            "solution_hash": solution_hash,
            "provider_message_id": provider_id,
            "message_preview": message[:240],
        },
    )
    return {
        "status": status,
        "sent": status in {"sent", "dry_run"},
        "dry_run": status == "dry_run",
        "phone": recipient.get("phone"),
        "provider_message_id": provider_id,
        "error_message": error,
        "anomaly": updated,
    }


def change_anomaly_status(anomaly_id: str, user: AuthUser, status: str, note: str | None = None) -> dict[str, Any]:
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in OPERATIONAL_STATUSES:
        raise HTTPException(status_code=422, detail="Status operacional inválido.")

    anomaly = _fetch_anomaly(anomaly_id, user)
    old_status = str(anomaly.get("status") or "open")
    now = utc_now_iso()
    patch_payload: dict[str, Any] = {"status": normalized_status}
    if normalized_status == "resolved":
        patch_payload["resolved_at"] = now
    elif normalized_status == "reopened":
        patch_payload.update({"resolved_at": None, "reopened_at": now})
    elif normalized_status == "acknowledged":
        patch_payload["acknowledged_at"] = now
    elif normalized_status == "ignored":
        patch_payload["resolved_at"] = now
    else:
        if old_status in {"resolved", "ignored"}:
            patch_payload["resolved_at"] = None

    try:
        updated = patch_anomaly(str(anomaly["id"]), patch_payload) or anomaly
    except SupabaseError as exc:
        _raise_schema(exc)
    updated = _normalize_anomaly(updated)

    event_type = {
        "resolved": "resolved",
        "reopened": "reopened",
        "ignored": "ignored",
        "acknowledged": "acknowledged",
    }.get(normalized_status, "status_changed")
    create_anomaly_event(
        updated,
        user,
        event_type,
        f"Status alterado para {normalized_status}",
        note,
        old_status=old_status,
        new_status=normalized_status,
    )
    return updated


def resolve_anomaly(anomaly_id: str, user: AuthUser, note: str | None = None) -> dict[str, Any]:
    return change_anomaly_status(anomaly_id, user, "resolved", note)


def reopen_anomaly(anomaly_id: str, user: AuthUser, note: str | None = None) -> dict[str, Any]:
    return change_anomaly_status(anomaly_id, user, "reopened", note)


def add_anomaly_note(anomaly_id: str, user: AuthUser, note: str) -> dict[str, Any]:
    clean_note = str(note or "").strip()
    if len(clean_note) < 3:
        raise HTTPException(status_code=400, detail="Observação muito curta.")
    if len(clean_note) > 2000:
        raise HTTPException(status_code=400, detail="Observação muito longa.")
    anomaly = _fetch_anomaly(anomaly_id, user)
    try:
        rows = supabase.insert(
            "eletrofrio_anomaly_notes",
            {
                "anomaly_id": anomaly.get("id"),
                "customer_id": anomaly.get("customer_id"),
                "user_id": user.id,
                "author_name": user.username,
                "note": clean_note,
            },
        )
    except SupabaseError as exc:
        _raise_schema(exc)
    saved = rows[0] if rows else {}
    create_anomaly_event(
        anomaly,
        user,
        "note_added",
        "Observação adicionada",
        clean_note,
        metadata={"note_id": saved.get("id")},
    )
    return saved


def _ticket_description(anomaly: dict[str, Any], description: str | None = None) -> str:
    base = [
        f"Código da ocorrência: {anomaly.get('public_code') or '-'}",
        f"Loja: {anomaly.get('loja_nome') or anomaly.get('loja_id') or '-'}",
        f"Cliente: {anomaly.get('customer_name') or anomaly.get('customer_id') or '-'}",
        f"Equipamento: {anomaly.get('tag') or anomaly.get('dispositivo_id') or anomaly.get('equipment_id') or '-'}",
        f"Sensor: {anomaly.get('sensor_id') or '-'}",
        f"Severidade: {anomaly.get('severity') or '-'}",
        f"Status: {anomaly.get('status') or '-'}",
        f"Valor atual: {anomaly.get('value_label') or _format_value(anomaly.get('value'))}",
        f"Faixa esperada: {anomaly.get('expected_range_label') or _expected_range_label(anomaly.get('expected_range'))}",
        f"Detectada em: {anomaly.get('detected_at') or '-'}",
        "",
        "Descrição:",
        str(anomaly.get("message") or anomaly.get("title") or "-"),
        "",
        "Recomendação inicial:",
        str(anomaly.get("recommended_action") or "Validar condição operacional e causa raiz em campo."),
    ]
    if description:
        base.extend(["", "Observação do chamado:", description])
    return "\n".join(base).strip()


def open_anomaly_ticket(anomaly_id: str, user: AuthUser, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    anomaly = _fetch_anomaly(anomaly_id, user)
    title = str(
        payload.get("title")
        or f"[{anomaly.get('public_code')}] {anomaly.get('title') or 'Anomalia operacional'}"
    ).strip()
    description = _ticket_description(anomaly, payload.get("description"))
    priority = str(payload.get("priority") or anomaly.get("severity") or "medium").strip().lower()
    try:
        rows = supabase.insert(
            "eletrofrio_anomaly_tickets",
            {
                "anomaly_id": anomaly.get("id"),
                "customer_id": anomaly.get("customer_id"),
                "public_code": anomaly.get("public_code"),
                "title": title[:300],
                "description": description,
                "priority": priority,
                "status": "open",
                "assigned_to": payload.get("assigned_to"),
                "created_by": user.id,
            },
        )
    except SupabaseError as exc:
        _raise_schema(exc)
    ticket = rows[0] if rows else {}

    old_status = str(anomaly.get("status") or "open")
    new_status = "ticket_opened" if old_status not in {"resolved", "ignored"} else old_status
    patch_payload = {"ticket_opened_at": utc_now_iso()}
    if new_status != old_status:
        patch_payload["status"] = new_status
    try:
        updated = patch_anomaly(str(anomaly["id"]), patch_payload) or anomaly
    except SupabaseError as exc:
        _raise_schema(exc)
    updated = _normalize_anomaly(updated)
    create_anomaly_event(
        updated,
        user,
        "ticket_opened",
        "Chamado interno aberto",
        f"Chamado {ticket.get('id')} aberto para tratativa operacional.",
        old_status=old_status,
        new_status=new_status,
        metadata={"ticket_id": ticket.get("id"), "priority": priority},
    )
    return {"ticket": ticket, "anomaly": updated}
