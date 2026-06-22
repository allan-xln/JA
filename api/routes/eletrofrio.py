from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import hmac
import json
from pathlib import Path
import re
import time
import unicodedata
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
import requests

from api.ai.operational_qa import ASSISTANT_SUGGESTIONS, answer_operational_question
from api.analysis.metrics import build_metrics
from api.anomaly_operations import (
    add_anomaly_note,
    change_anomaly_status,
    ensure_operational_anomaly_public_code,
    get_operational_anomaly,
    get_operational_anomaly_by_code,
    list_anomaly_events,
    list_operational_anomalies,
    open_anomaly_ticket,
    reopen_anomaly,
    resolve_anomaly,
    send_anomaly_whatsapp,
    suggest_solution,
)
from api.auth import AuthUser, TenantScope, current_user, require_admin, scope_for_user
from api.communications import (
    communication_timeline,
    list_communications,
    list_rag_queries,
    list_whatsapp_messages,
    log_communication,
    log_rag_query,
)
from api.config import settings
from api.data_retention import prune_operational_data
from api.database import TEMPORARY_SUPABASE_MESSAGE, SupabaseError, is_temporary_supabase_error, supabase
from api.notifications.auto_notifier import (
    create_recipient,
    delete_recipient,
    list_events,
    list_recipients,
    notification_status,
    process_notifications,
    send_test_notification,
    update_recipient,
)
from api.repositories import list_alarms, list_devices, list_insights, list_telemetry, list_units, row_in_scope
from api.rules.rule_engine import evaluate_recent_operation
from api.rules.rule_repository import (
    RULE_SCHEMA_MESSAGE,
    apply_default_rules,
    create_rule,
    default_rules_preview,
    delete_rule,
    get_rule,
    list_rule_evaluations,
    list_rules,
    toggle_rule,
    update_rule,
)
from api.scheduler import CollectorBusyError, run_collector_managed


router = APIRouter(prefix="/api/eletrofrio", tags=["eletrofrio-real"])
_overview_cache: dict[str, tuple[float, dict]] = {}
_anomaly_list_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="anomaly-list")
_anomaly_fast_cache: dict[str, tuple[float, dict]] = {}
_ANOMALY_FAST_CACHE_FILE = Path("/app/data/anomaly_fast_cache.json")
_FAST_ACTIVE_ANOMALY_STATUSES = "open,acknowledged,investigating,solution_suggested,whatsapp_sent,ticket_opened,reopened"
_FAST_ANOMALY_SELECT = ",".join(
    [
        "id",
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
    ]
)


class WhatsAppTestPayload(BaseModel):
    phone: str
    message: str = "*Eletrofrio Refrigeração*\n✅ *Teste recebido*\n\nO canal operacional está pronto para enviar métricas e alertas inteligentes."


class AssistantQueryPayload(BaseModel):
    question: str
    origin: str = "panel"
    phone: str | None = None


class OperationalRulePayload(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True
    scope_type: str = "global"
    scope_value: str | None = None
    priority: int = 100
    severity_when_triggered: str = "warning"
    equipment_type: str | None = None
    measurement_type: str | None = None
    condition_type: str
    threshold_min: float | None = None
    threshold_max: float | None = None
    duration_minutes: int | None = None
    recurrence_count: int | None = None
    recurrence_window_minutes: int | None = None
    alarm_text_pattern: str | None = None
    explanation_template: str | None = None
    recommended_action_template: str | None = None


class NotificationRecipientPayload(BaseModel):
    customer_id: str | None = None
    role: str = "client"
    name: str | None = None
    phone: str
    channel: str = "whatsapp"
    enabled: bool = True
    receive_critical: bool = True
    receive_warning_recurrent: bool = True
    cooldown_minutes: int = 60


class NotificationRecipientPatchPayload(BaseModel):
    customer_id: str | None = None
    role: str | None = None
    name: str | None = None
    phone: str | None = None
    channel: str | None = None
    enabled: bool | None = None
    receive_critical: bool | None = None
    receive_warning_recurrent: bool | None = None
    cooldown_minutes: int | None = None


class NotificationTestPayload(BaseModel):
    recipient_id: str | None = None
    phone: str | None = None
    message: str = "*Eletrofrio Refrigeração*\n✅ *Teste recebido*\n\nO canal operacional está pronto para enviar métricas e alertas inteligentes."
    dry_run: bool = True


class RetentionPrunePayload(BaseModel):
    dry_run: bool = True
    telemetry_days: int | None = None
    alarm_days: int | None = None
    insight_days: int | None = None
    communication_days: int | None = None
    collector_run_days: int | None = None
    resolved_anomaly_days: int | None = None
    batch_limit: int | None = None


class NotificationProcessPayload(BaseModel):
    dry_run: bool | None = None


class AnomalyStatusPayload(BaseModel):
    status: str
    note: str | None = None


class AnomalyActionPayload(BaseModel):
    note: str | None = None


class AnomalyNotePayload(BaseModel):
    note: str


class AnomalyWhatsappPayload(BaseModel):
    recipient_id: str | None = None
    phone: str | None = None
    confirm_duplicate: bool = False


class AnomalyTicketPayload(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    assigned_to: str | None = None


def handle_assistant_question(payload: AssistantQueryPayload, user: AuthUser):
    require_supabase()
    question = payload.question.strip()
    if len(question) < 4:
        raise HTTPException(status_code=400, detail="Pergunta muito curta.")
    if len(question) > 1000:
        raise HTTPException(status_code=400, detail="Pergunta muito longa.")
    started = time.perf_counter()
    answer = answer_operational_question(question, origin=payload.origin, scope=user.scope)
    response_time_ms = int((time.perf_counter() - started) * 1000)
    log_communication(
        {
            "type": "incoming_question",
            "direction": "incoming",
            "message_preview": question,
            "payload_json": {"origin": payload.origin},
            "customer_id": user.scope.customer_id if not user.scope.is_admin else None,
            "customer_name": user.scope.customer_name if not user.scope.is_admin else None,
            "status": "received",
            "source": "WhatsApp" if payload.origin == "whatsapp" else "usuário",
        }
    )
    log_rag_query(question=question, answer=answer, response_time_ms=response_time_ms, scope=user.scope)
    return answer


def require_internal_service_token(x_eletrofrio_service_token: str | None = Header(None)) -> None:
    expected = settings.internal_service_token
    if not expected or not x_eletrofrio_service_token or not hmac.compare_digest(x_eletrofrio_service_token, expected):
        raise HTTPException(status_code=401, detail="Token interno inválido.")


def phone_variants(value: str | None) -> set[str]:
    digits = "".join(char for char in str(value or "") if char.isdigit())
    if not digits:
        return set()
    variants = {digits}
    if digits.startswith("55") and len(digits) in {12, 13}:
        variants.add(digits[2:])
    if len(digits) in {10, 11}:
        variants.add(f"55{digits}")
    return variants


def phone_matches(left: str | None, right: str | None) -> bool:
    return bool(phone_variants(left) & phone_variants(right))


def whatsapp_recipient_for_phone(phone: str | None) -> dict | None:
    if not phone:
        return None
    try:
        rows = supabase.select(
            "eletrofrio_notification_recipients",
            {"select": "id,customer_id,role,name,phone,enabled", "limit": 1000},
        )
    except Exception:
        return None
    return next(
        (
            row
            for row in rows
            if row.get("enabled", True) and phone_matches(phone, row.get("phone"))
        ),
        None,
    )


def normalized_customer_text(value: str | None, compact: bool = False) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(char for char in normalized if not unicodedata.combining(char))
    if compact:
        return re.sub(r"[^a-z0-9]+", "", text)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def customer_from_question(question: str | None) -> dict | None:
    query = normalized_customer_text(question)
    compact_query = normalized_customer_text(question, compact=True)
    if not query and not compact_query:
        return None
    try:
        rows = supabase.select(
            "eletrofrio_customers",
            {"select": "id,slug,name,is_active", "limit": 10000},
        )
    except Exception:
        return None

    candidates: list[tuple[int, dict]] = []
    for row in rows:
        if row.get("is_active") is False:
            continue
        name = normalized_customer_text(row.get("name"))
        slug = normalized_customer_text(row.get("slug"), compact=True)
        if slug and slug in compact_query:
            candidates.append((len(slug) + 20, row))
            continue
        if name and f" {name} " in f" {query} ":
            candidates.append((len(name) + 10, row))
            continue
        tokens = [token for token in name.split() if len(token) >= 4]
        token_hits = [token for token in tokens if f" {token} " in f" {query} "]
        if token_hits:
            candidates.append((max(len(token) for token in token_hits), row))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def customer_scope_user(customer: dict, username: str = "whatsapp_cliente") -> AuthUser:
    user_row = {
        "id": f"whatsapp:{customer.get('id')}",
        "username": username,
        "role": "client",
        "customer_id": customer.get("id"),
    }
    scope = scope_for_user(user_row)
    return AuthUser(
        id=str(user_row["id"]),
        username=str(user_row["username"]),
        role="client",
        customer_id=scope.customer_id,
        customer_name=scope.customer_name,
        scope=scope,
    )


def whatsapp_user_for_phone(phone: str | None, question: str | None = None) -> AuthUser:
    recipient = whatsapp_recipient_for_phone(phone)
    if recipient and recipient.get("customer_id") and recipient.get("role") != "admin":
        return customer_scope_user({"id": recipient.get("customer_id")}, recipient.get("name") or "whatsapp_cliente")

    customer = customer_from_question(question)
    if customer:
        return customer_scope_user(customer, str(customer.get("slug") or customer.get("name") or "whatsapp_cliente"))

    scope = TenantScope(role="admin", customer_id=None, customer_name=None)
    return AuthUser(
        id="whatsapp-service",
        username="whatsapp",
        role="admin",
        customer_id=None,
        customer_name=None,
        scope=scope,
    )


def require_supabase() -> None:
    if not supabase.enabled():
        raise HTTPException(
            status_code=503,
            detail="Supabase não configurado. Preencha SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no .env.",
        )


def _read_unavailable_response(message: str = TEMPORARY_SUPABASE_MESSAGE) -> dict:
    return {"items": [], "data_unavailable": True, "message": message}


def _empty_overview(user: AuthUser, message: str = TEMPORARY_SUPABASE_MESSAGE) -> dict:
    return {
        "totals": {
            "units": 0,
            "devices": 0,
            "alarms": 0,
            "alarms_last_30_days": 0,
            "telemetry": 0,
            "insights_candidates": 0,
            "insights": 0,
        },
        "alarms_by_type": {},
        "device_metrics": [],
        "store_metrics": [],
        "most_problematic_devices": [],
        "most_critical_stores": [],
        "top_critical_devices": [],
        "top_critical_stores": [],
        "latest_insights": [],
        "scope": user.public_dict(),
        "data_unavailable": True,
        "message": message,
    }


def _temporary_read_failure(exc: Exception) -> bool:
    if isinstance(exc, SupabaseError):
        return is_temporary_supabase_error(exc)
    if isinstance(exc, HTTPException):
        return exc.status_code == 503
    return False


def _read_failure_message(exc: Exception) -> str:
    if isinstance(exc, HTTPException) and isinstance(exc.detail, str):
        return exc.detail
    if is_temporary_supabase_error(exc):
        return TEMPORARY_SUPABASE_MESSAGE
    return str(exc) or TEMPORARY_SUPABASE_MESSAGE


def _read_fast_anomaly_file_cache(cache_key: str) -> dict | None:
    try:
        if not _ANOMALY_FAST_CACHE_FILE.exists():
            return None
        data = json.loads(_ANOMALY_FAST_CACHE_FILE.read_text(encoding="utf-8"))
        entry = data.get(cache_key)
        if not isinstance(entry, dict):
            return None
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            return None
        cached_at = float(entry.get("cached_at") or 0)
        return {
            **payload,
            "cached": True,
            "cache_source": "file",
            "cache_age_seconds": round(time.time() - cached_at, 1) if cached_at else None,
        }
    except Exception:
        return None


def _write_fast_anomaly_file_cache(cache_key: str, payload: dict) -> None:
    try:
        _ANOMALY_FAST_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if _ANOMALY_FAST_CACHE_FILE.exists():
            existing = json.loads(_ANOMALY_FAST_CACHE_FILE.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                data = existing
        data[cache_key] = {"cached_at": time.time(), "payload": payload}
        # Keep only a small set of recent list variants; this cache is for UI resilience, not storage.
        if len(data) > 12:
            ordered = sorted(
                data.items(),
                key=lambda item: float(item[1].get("cached_at") or 0) if isinstance(item[1], dict) else 0,
                reverse=True,
            )
            data = dict(ordered[:12])
        _ANOMALY_FAST_CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        return


def _find_cached_fast_anomaly(*, anomaly_id: str | None = None, public_code: str | None = None) -> dict | None:
    try:
        if not _ANOMALY_FAST_CACHE_FILE.exists():
            return None
        data = json.loads(_ANOMALY_FAST_CACHE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        normalized_code = str(public_code or "").strip().upper()
        for entry in data.values():
            if not isinstance(entry, dict):
                continue
            payload = entry.get("payload")
            if not isinstance(payload, dict):
                continue
            for item in payload.get("items") or []:
                if not isinstance(item, dict):
                    continue
                if anomaly_id and str(item.get("id")) == str(anomaly_id):
                    return item
                if normalized_code and str(item.get("public_code") or "").strip().upper() == normalized_code:
                    return item
    except Exception:
        return None
    return None


def _cached_anomaly_detail(item: dict) -> dict:
    public_code = item.get("public_code") or "Código pendente"
    title = item.get("title") or item.get("summary") or item.get("message") or "Anomalia operacional"
    detected_at = item.get("detected_at") or item.get("created_at")
    last_seen_at = item.get("last_seen_at") or item.get("updated_at") or detected_at
    solution_json = {
        "diagnosis": f"{title} em {item.get('loja_nome') or 'unidade operacional'}, exigindo validação em campo.",
        "probable_cause": item.get("technical_reason") or "Condição operacional fora do padrão esperado pelo monitoramento.",
        "alternative_causes": [
            "Porta aberta ou excesso de carga térmica",
            "Ventilação obstruída",
            "Sensor com leitura inconsistente",
            "Degelo, compressor ou ventiladores exigindo verificação",
        ],
        "immediate_action": item.get("recommended_action") or "Verificar porta, ventilação, carga térmica e leitura do sensor.",
        "technical_action": "Validar sensor, compressor, degelo, ventiladores, evaporador e condição de operação do equipamento.",
        "urgency": "Alta" if str(item.get("severity") or "").lower() == "critical" else "Média",
        "risk": "Se a condição persistir, pode haver perda de eficiência térmica, perda de produto ou falha operacional.",
        "field_technician_required": "Sim, se a verificação operacional imediata não normalizar a condição.",
        "whatsapp_message": (
            f"Ocorrência {public_code}: {title}. "
            f"Loja: {item.get('loja_nome') or '-'}. Equipamento: {item.get('tag') or item.get('dispositivo_id') or '-'}."
        ),
        "root_cause_note": "A causa raiz precisa ser validada em campo antes de qualquer conclusão definitiva.",
    }
    return {
        **item,
        "title": title,
        "status": item.get("status") or "open",
        "detected_at": detected_at,
        "last_seen_at": last_seen_at,
        "value_label": item.get("value_label") or (str(item.get("value")) if item.get("value") is not None else "-"),
        "expected_range_label": item.get("expected_range_label") or "Validar faixa esperada no equipamento",
        "deviation_label": item.get("deviation_label") or "-",
        "open_hours": item.get("open_hours") or 0,
        "recurrence_count": item.get("recurrence_count") or 0,
        "priority_score": item.get("priority_score") or 0,
        "metadata": item.get("metadata") or {"source": "cache_local_apresentacao"},
        "evidence_json": item.get("evidence_json") or {
            "origem": "cache local de contingência",
            "motivo": "Supabase REST temporariamente em recuperação/schema cache",
        },
        "notes": [],
        "tickets": [],
        "events": [
            {
                "id": f"{item.get('id')}:cached-created",
                "anomaly_id": item.get("id"),
                "customer_id": item.get("customer_id"),
                "user_id": None,
                "event_type": "created",
                "old_status": None,
                "new_status": item.get("status") or "open",
                "title": f"{public_code} - Ocorrência disponível para acompanhamento",
                "description": "Registro carregado pelo cache local de contingência enquanto o Supabase estabiliza.",
                "metadata": {},
                "public_code": item.get("public_code"),
                "created_at": detected_at,
            },
            {
                "id": f"{item.get('id')}:cached-solution",
                "anomaly_id": item.get("id"),
                "customer_id": item.get("customer_id"),
                "user_id": None,
                "event_type": "ai_solution_generated",
                "old_status": None,
                "new_status": "solution_suggested",
                "title": f"{public_code} - Sugestão operacional pronta",
                "description": "Sugestão local exibida sem consumir tokens de IA durante indisponibilidade do banco.",
                "metadata": {},
                "public_code": item.get("public_code"),
                "created_at": last_seen_at,
            },
        ],
        "latest_solution": {
            "id": f"{item.get('id')}:cached-solution",
            "anomaly_id": item.get("id"),
            "customer_id": item.get("customer_id"),
            "user_id": None,
            "solution_hash": f"cached:{item.get('id')}",
            "model": "fallback-local",
            "used_ai": False,
            "cached": True,
            "prompt_context": {},
            "solution_json": solution_json,
            "solution_text": None,
            "error_message": None,
            "created_at": last_seen_at,
        },
        "cache_source": "file",
    }


def _fast_anomaly_list(
    user: AuthUser,
    *,
    limit: int,
    offset: int,
    status: str | None,
    severity: str | None,
    search: str | None,
) -> dict:
    normalized_status = str(status or "active").strip().lower()
    params: dict[str, str | int] = {
        "select": _FAST_ANOMALY_SELECT,
        "order": "updated_at.desc",
        "limit": min(max(limit + offset, 1), 240),
    }
    if normalized_status in {"active", "open", ""}:
        params["status"] = f"in.({_FAST_ACTIVE_ANOMALY_STATUSES})"
    elif normalized_status == "all":
        pass
    elif normalized_status == "history":
        params["status"] = "in.(resolved,ignored)"
    else:
        params["status"] = f"eq.{normalized_status}"
    if severity and severity != "all":
        params["severity"] = f"eq.{severity}"

    cache_key = f"{user.role}:{user.customer_id}:{limit}:{offset}:{normalized_status}:{severity or ''}:{search or ''}"
    try:
        rows = supabase.select("eletrofrio_anomalies", params, timeout=5, attempts=3)
    except Exception:
        cached = _anomaly_fast_cache.get(cache_key)
        if cached:
            cached_at, cached_payload = cached
            return {**cached_payload, "cached": True, "cache_age_seconds": round(time.time() - cached_at, 1)}
        file_cached = _read_fast_anomaly_file_cache(cache_key)
        if file_cached:
            return file_cached
        raise
    rows = [row for row in rows if row_in_scope(row, user.scope)]

    if search:
        needle = search.strip().casefold()
        rows = [
            row
            for row in rows
            if needle
            in " ".join(
                str(part or "")
                for part in [
                    row.get("public_code"),
                    row.get("title"),
                    row.get("message"),
                    row.get("loja_nome"),
                    row.get("tag"),
                    row.get("sensor_id"),
                    row.get("customer_id"),
                ]
            ).casefold()
        ]

    page_rows = rows[offset : offset + limit]
    items = []
    for row in page_rows:
        detected_at = row.get("detected_at") or row.get("created_at")
        last_seen_at = row.get("last_seen_at") or row.get("updated_at") or detected_at
        items.append(
            {
                **row,
                "title": row.get("title") or row.get("summary") or row.get("message") or "Anomalia operacional",
                "status": row.get("status") or "open",
                "dispositivo_id": row.get("dispositivo_id") or row.get("equipment_id"),
                "equipment_id": row.get("equipment_id") or row.get("dispositivo_id"),
                "detected_at": detected_at,
                "last_seen_at": last_seen_at,
                "value_label": str(row.get("value")) if row.get("value") is not None else "-",
                "expected_range_label": "faixa esperada no detalhe",
                "deviation_label": "-",
                "open_hours": 0,
                "recurrence_count": int(row.get("recurrence_count") or 0),
                "priority_score": float(row.get("priority_score") or 0),
                "metadata": {},
                "evidence_json": {},
            }
        )

    payload = {
        "items": items,
        "count": len(rows),
        "limit": limit,
        "offset": offset,
        "fast_mode": True,
    }
    _anomaly_fast_cache[cache_key] = (time.time(), payload)
    _write_fast_anomaly_file_cache(cache_key, payload)
    return payload


@router.get("/health")
def eletrofrio_health():
    return {
        "status": "ok",
        "supabase_configured": supabase.enabled(),
        "openai_configured": settings.openai_enabled,
        "collector_interval_minutes": settings.collector_interval_minutes,
        "internal_scheduler_enabled": settings.start_internal_scheduler,
        "whatsapp_enabled": settings.whatsapp_enabled,
        "auto_open_tickets": settings.auto_open_tickets,
    }


@router.post("/retention/prune")
def eletrofrio_retention_prune(payload: RetentionPrunePayload | None = None, user: AuthUser = Depends(require_admin)):
    require_supabase()
    data = payload or RetentionPrunePayload()
    return prune_operational_data(
        dry_run=data.dry_run,
        telemetry_days=data.telemetry_days,
        alarm_days=data.alarm_days,
        insight_days=data.insight_days,
        communication_days=data.communication_days,
        collector_run_days=data.collector_run_days,
        resolved_anomaly_days=data.resolved_anomaly_days,
        batch_limit=data.batch_limit,
    )


@router.get("/overview")
def eletrofrio_overview(user: AuthUser = Depends(current_user)):
    require_supabase()
    cache_key = f"{user.role}:{user.customer_id or 'admin'}"
    now = time.monotonic()
    cached = _overview_cache.get(cache_key)
    if cached and now - cached[0] <= max(0, settings.overview_cache_seconds):
        return cached[1]

    try:
        units = list_units(user.scope)
        devices = list_devices(user.scope)
        alarms = list_alarms(160, user.scope)
        telemetry_limit = 180 if user.scope.is_admin else 240
        telemetry = list_telemetry(telemetry_limit, user.scope)
        insights = list_insights(10, user.scope)
    except SupabaseError as exc:
        if cached:
            return {
                **cached[1],
                "data_unavailable": True,
                "stale": True,
                "message": _read_failure_message(exc),
            }
        return _empty_overview(user, _read_failure_message(exc))
    metrics = build_metrics(units, devices, alarms, telemetry)
    metrics["totals"]["insights"] = len(insights)
    metrics["latest_insights"] = insights[:5]
    metrics["scope"] = user.public_dict()
    _overview_cache[cache_key] = (now, metrics)
    return metrics


@router.get("/units")
def eletrofrio_units(user: AuthUser = Depends(current_user)):
    require_supabase()
    try:
        return {"items": list_units(user.scope)}
    except SupabaseError as exc:
        if is_temporary_supabase_error(exc):
            return _read_unavailable_response(_read_failure_message(exc))
        raise HTTPException(status_code=503, detail=_read_failure_message(exc)) from exc


@router.get("/devices")
def eletrofrio_devices(user: AuthUser = Depends(current_user)):
    require_supabase()
    try:
        return {"items": list_devices(user.scope)}
    except SupabaseError as exc:
        if is_temporary_supabase_error(exc):
            return _read_unavailable_response(_read_failure_message(exc))
        raise HTTPException(status_code=503, detail=_read_failure_message(exc)) from exc


@router.get("/alarms")
def eletrofrio_alarms(limit: int = 50, offset: int = 0, user: AuthUser = Depends(current_user)):
    require_supabase()
    try:
        return {"items": list_alarms(min(max(limit, 1), 200), user.scope, max(offset, 0))}
    except SupabaseError as exc:
        if is_temporary_supabase_error(exc):
            return _read_unavailable_response(_read_failure_message(exc))
        raise HTTPException(status_code=503, detail=_read_failure_message(exc)) from exc


@router.get("/telemetry")
def eletrofrio_telemetry(limit: int = 100, offset: int = 0, dispositivo_id: int | None = None, loja_id: int | None = None, user: AuthUser = Depends(current_user)):
    require_supabase()
    try:
        return {
            "items": list_telemetry(
                min(max(limit, 1), 200),
                user.scope,
                max(offset, 0),
                dispositivo_id=dispositivo_id,
                loja_id=loja_id,
            )
        }
    except SupabaseError as exc:
        if is_temporary_supabase_error(exc):
            return _read_unavailable_response(_read_failure_message(exc))
        raise HTTPException(status_code=503, detail=_read_failure_message(exc)) from exc


@router.get("/insights")
def eletrofrio_insights(limit: int = 50, offset: int = 0, user: AuthUser = Depends(current_user)):
    require_supabase()
    try:
        return {"items": list_insights(min(max(limit, 1), 200), user.scope, max(offset, 0))}
    except SupabaseError as exc:
        if is_temporary_supabase_error(exc):
            return _read_unavailable_response(_read_failure_message(exc))
        raise HTTPException(status_code=503, detail=_read_failure_message(exc)) from exc


@router.get("/anomalies")
def eletrofrio_anomalies(
    limit: int = 100,
    offset: int = 0,
    status: str | None = "active",
    severity: str | None = None,
    search: str | None = None,
    user: AuthUser = Depends(current_user),
):
    require_supabase()
    page_limit = min(max(limit, 1), 200)
    page_offset = max(offset, 0)
    try:
        return _fast_anomaly_list(
            user,
            limit=page_limit,
            offset=page_offset,
            status=status,
            severity=severity,
            search=search,
        )
    except Exception as exc:
        if not _temporary_read_failure(exc):
            raise
    try:
        future = _anomaly_list_executor.submit(
            list_operational_anomalies,
            user,
            page_limit,
            page_offset,
            status,
            severity,
            search,
        )
        return future.result(timeout=8)
    except FutureTimeoutError:
        return {
            **_read_unavailable_response(
                "Consulta de ocorrências demorou demais porque o banco está sobrecarregado. Tente atualizar em instantes."
            ),
            "count": 0,
            "limit": page_limit,
            "offset": page_offset,
        }
    except Exception as exc:
        if _temporary_read_failure(exc):
            return {**_read_unavailable_response(_read_failure_message(exc)), "count": 0, "limit": page_limit, "offset": page_offset}
        raise


@router.get("/anomalies/search")
def eletrofrio_anomaly_search(code: str, user: AuthUser = Depends(current_user)):
    require_supabase()
    try:
        return get_operational_anomaly_by_code(code, user)
    except Exception as exc:
        if _temporary_read_failure(exc):
            cached = _find_cached_fast_anomaly(public_code=code)
            if cached and row_in_scope(cached, user.scope):
                return _cached_anomaly_detail(cached)
        raise


@router.get("/anomalies/by-code/{public_code}")
def eletrofrio_anomaly_by_code(public_code: str, user: AuthUser = Depends(current_user)):
    require_supabase()
    try:
        return get_operational_anomaly_by_code(public_code, user)
    except Exception as exc:
        if _temporary_read_failure(exc):
            cached = _find_cached_fast_anomaly(public_code=public_code)
            if cached and row_in_scope(cached, user.scope):
                return _cached_anomaly_detail(cached)
        raise


@router.get("/anomalies/{anomaly_id}")
def eletrofrio_anomaly_detail(anomaly_id: str, user: AuthUser = Depends(current_user)):
    require_supabase()
    try:
        return get_operational_anomaly(anomaly_id, user)
    except Exception as exc:
        if _temporary_read_failure(exc):
            cached = _find_cached_fast_anomaly(anomaly_id=anomaly_id)
            if cached and row_in_scope(cached, user.scope):
                return _cached_anomaly_detail(cached)
        raise


@router.post("/anomalies/{anomaly_id}/ensure-public-code")
def eletrofrio_anomaly_ensure_public_code(anomaly_id: str, user: AuthUser = Depends(current_user)):
    require_supabase()
    return ensure_operational_anomaly_public_code(anomaly_id, user)


@router.get("/anomalies/{anomaly_id}/events")
def eletrofrio_anomaly_events(anomaly_id: str, user: AuthUser = Depends(current_user)):
    require_supabase()
    return list_anomaly_events(anomaly_id, user)


@router.post("/anomalies/{anomaly_id}/suggest-solution")
def eletrofrio_anomaly_suggest_solution(anomaly_id: str, user: AuthUser = Depends(current_user)):
    require_supabase()
    try:
        return suggest_solution(anomaly_id, user)
    except Exception as exc:
        if _temporary_read_failure(exc):
            cached = _find_cached_fast_anomaly(anomaly_id=anomaly_id)
            if cached and row_in_scope(cached, user.scope):
                detail = _cached_anomaly_detail(cached)
                return detail["latest_solution"]
        raise


@router.post("/anomalies/{anomaly_id}/send-whatsapp")
def eletrofrio_anomaly_send_whatsapp(
    anomaly_id: str,
    payload: AnomalyWhatsappPayload | None = None,
    user: AuthUser = Depends(current_user),
):
    require_supabase()
    return send_anomaly_whatsapp(anomaly_id, user, payload.dict() if payload else {})


@router.post("/anomalies/{anomaly_id}/resolve")
def eletrofrio_anomaly_resolve(
    anomaly_id: str,
    payload: AnomalyActionPayload | None = None,
    user: AuthUser = Depends(current_user),
):
    require_supabase()
    return resolve_anomaly(anomaly_id, user, payload.note if payload else None)


@router.post("/anomalies/{anomaly_id}/reopen")
def eletrofrio_anomaly_reopen(
    anomaly_id: str,
    payload: AnomalyActionPayload | None = None,
    user: AuthUser = Depends(current_user),
):
    require_supabase()
    return reopen_anomaly(anomaly_id, user, payload.note if payload else None)


@router.post("/anomalies/{anomaly_id}/notes")
def eletrofrio_anomaly_add_note(anomaly_id: str, payload: AnomalyNotePayload, user: AuthUser = Depends(current_user)):
    require_supabase()
    return add_anomaly_note(anomaly_id, user, payload.note)


@router.post("/anomalies/{anomaly_id}/ticket")
def eletrofrio_anomaly_open_ticket(
    anomaly_id: str,
    payload: AnomalyTicketPayload | None = None,
    user: AuthUser = Depends(current_user),
):
    require_supabase()
    return open_anomaly_ticket(anomaly_id, user, payload.dict() if payload else {})


@router.patch("/anomalies/{anomaly_id}/status")
def eletrofrio_anomaly_update_status(anomaly_id: str, payload: AnomalyStatusPayload, user: AuthUser = Depends(current_user)):
    require_supabase()
    return change_anomaly_status(anomaly_id, user, payload.status, payload.note)


@router.get("/rules/defaults/preview")
def eletrofrio_rules_defaults_preview():
    return {"items": default_rules_preview()}


@router.post("/rules/defaults/apply")
def eletrofrio_rules_defaults_apply(user: AuthUser = Depends(require_admin)):
    require_supabase()
    return apply_default_rules()


@router.get("/rules")
def eletrofrio_rules(user: AuthUser = Depends(current_user)):
    require_supabase()
    result = list_rules()
    if user.scope.is_admin:
        return result
    items = [
        rule for rule in result.get("items", [])
        if rule.get("scope_type") == "global"
        or (
            rule.get("scope_type") in {"loja", "store", "unit"}
            and str(rule.get("scope_value")) in {str(item) for item in user.scope.allowed_loja_ids}
        )
        or (
            rule.get("scope_type") in {"device", "dispositivo"}
            and str(rule.get("scope_value")) in {str(item) for item in user.scope.allowed_dispositivo_ids}
        )
    ]
    return {**result, "items": items}


@router.post("/rules")
def eletrofrio_rules_create(payload: OperationalRulePayload, user: AuthUser = Depends(require_admin)):
    require_supabase()
    try:
        return create_rule(payload.dict())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc) or RULE_SCHEMA_MESSAGE) from exc


@router.post("/rules/evaluate")
def eletrofrio_rules_evaluate(user: AuthUser = Depends(require_admin)):
    require_supabase()
    units = list_units()
    devices = list_devices()
    alarms = list_alarms(200)
    telemetry = list_telemetry(300)
    return evaluate_recent_operation(units, devices, alarms, telemetry)


@router.get("/rule-evaluations")
def eletrofrio_rule_evaluations(limit: int = 100, user: AuthUser = Depends(current_user)):
    require_supabase()
    result = list_rule_evaluations(limit)
    if user.scope.is_admin:
        return result
    from api.repositories import filter_rows_by_scope
    return {**result, "items": filter_rows_by_scope(result.get("items", []), user.scope)}


@router.get("/rules/{rule_id}")
def eletrofrio_rules_get(rule_id: str, user: AuthUser = Depends(current_user)):
    require_supabase()
    try:
        rule = get_rule(rule_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc) or RULE_SCHEMA_MESSAGE) from exc
    if not rule:
        raise HTTPException(status_code=404, detail="Regra operacional não encontrada.")
    return rule


@router.put("/rules/{rule_id}")
def eletrofrio_rules_update(rule_id: str, payload: OperationalRulePayload, user: AuthUser = Depends(require_admin)):
    require_supabase()
    try:
        return update_rule(rule_id, payload.dict())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Regra operacional não encontrada.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc) or RULE_SCHEMA_MESSAGE) from exc


@router.patch("/rules/{rule_id}/toggle")
def eletrofrio_rules_toggle(rule_id: str, user: AuthUser = Depends(require_admin)):
    require_supabase()
    try:
        return toggle_rule(rule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Regra operacional não encontrada.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc) or RULE_SCHEMA_MESSAGE) from exc


@router.delete("/rules/{rule_id}")
def eletrofrio_rules_delete(rule_id: str, user: AuthUser = Depends(require_admin)):
    require_supabase()
    try:
        return delete_rule(rule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Regra operacional não encontrada.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc) or RULE_SCHEMA_MESSAGE) from exc


@router.get("/assistant/suggestions")
def eletrofrio_assistant_suggestions():
    return {"items": ASSISTANT_SUGGESTIONS}


@router.get("/communications")
def eletrofrio_communications(limit: int = 50, offset: int = 0, type: str | None = None, status: str | None = None, search: str | None = None, user: AuthUser = Depends(current_user)):
    require_supabase()
    return list_communications(limit=min(max(limit, 1), 200), offset=max(offset, 0), type_=type, status=status, search=search, scope=user.scope)


@router.get("/communications/timeline")
def eletrofrio_communications_timeline(limit: int = 50, user: AuthUser = Depends(current_user)):
    require_supabase()
    return communication_timeline(min(max(limit, 1), 200), user.scope)


@router.get("/rag/history")
def eletrofrio_rag_history(limit: int = 50, offset: int = 0, search: str | None = None, user: AuthUser = Depends(current_user)):
    require_supabase()
    return list_rag_queries(limit=min(max(limit, 1), 200), offset=max(offset, 0), search=search, scope=user.scope)


@router.get("/whatsapp/messages")
def eletrofrio_whatsapp_messages(limit: int = 50, offset: int = 0, status: str | None = None, type: str | None = None, user: AuthUser = Depends(current_user)):
    require_supabase()
    return list_whatsapp_messages(limit=min(max(limit, 1), 200), offset=max(offset, 0), status=status, type_=type, scope=user.scope)


@router.get("/notifications/status")
def eletrofrio_notifications_status(user: AuthUser = Depends(current_user)):
    require_supabase()
    return notification_status(user.scope)


@router.post("/notifications/process")
def eletrofrio_notifications_process(payload: NotificationProcessPayload | None = None, user: AuthUser = Depends(require_admin)):
    require_supabase()
    return process_notifications(user.scope, dry_run=payload.dry_run if payload else None)


@router.get("/notifications/events")
def eletrofrio_notifications_events(limit: int = 80, offset: int = 0, status: str | None = None, user: AuthUser = Depends(current_user)):
    require_supabase()
    return list_events(limit=min(max(limit, 1), 200), offset=max(offset, 0), status=status, scope=user.scope)


@router.get("/notifications/recipients")
def eletrofrio_notifications_recipients(user: AuthUser = Depends(current_user)):
    require_supabase()
    return list_recipients(user.scope)


@router.post("/notifications/recipients")
def eletrofrio_notifications_recipients_create(payload: NotificationRecipientPayload, user: AuthUser = Depends(require_admin)):
    require_supabase()
    try:
        return create_recipient(payload.dict())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/notifications/recipients/{recipient_id}")
def eletrofrio_notifications_recipients_update(recipient_id: str, payload: NotificationRecipientPatchPayload, user: AuthUser = Depends(require_admin)):
    require_supabase()
    data = payload.dict(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar.")
    try:
        return update_recipient(recipient_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/notifications/recipients/{recipient_id}")
def eletrofrio_notifications_recipients_delete(recipient_id: str, user: AuthUser = Depends(require_admin)):
    require_supabase()
    return delete_recipient(recipient_id)


@router.post("/notifications/test")
def eletrofrio_notifications_test(payload: NotificationTestPayload, user: AuthUser = Depends(require_admin)):
    require_supabase()
    try:
        return send_test_notification(payload.dict(), user.scope)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/assistant/ask")
def eletrofrio_assistant_ask(payload: AssistantQueryPayload, user: AuthUser = Depends(current_user)):
    return handle_assistant_question(payload, user)


@router.post("/assistant/query")
def eletrofrio_assistant_query(payload: AssistantQueryPayload, user: AuthUser = Depends(current_user)):
    return handle_assistant_question(payload, user)


@router.post("/assistant/whatsapp")
def eletrofrio_assistant_whatsapp(payload: AssistantQueryPayload, _: None = Depends(require_internal_service_token)):
    require_supabase()
    whatsapp_payload = AssistantQueryPayload(question=payload.question, origin="whatsapp", phone=payload.phone)
    return handle_assistant_question(whatsapp_payload, whatsapp_user_for_phone(payload.phone, payload.question))


@router.post("/run-collector")
def eletrofrio_run_collector(user: AuthUser = Depends(require_admin)):
    require_supabase()
    try:
        return run_collector_managed("manual")
    except CollectorBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def whatsapp_request(method: str, path: str, payload: dict | None = None):
    url = f"{settings.whatsapp_service_url}{path}"
    try:
        response = requests.request(method, url, json=payload, timeout=settings.http_timeout_seconds)
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Serviço WhatsApp indisponível. Inicie o serviço local com "
                "'npm run dev' dentro da pasta ELETROFRIO/JA/whatsapp."
            ),
        ) from exc

    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=body)
    return body


@router.post("/whatsapp/start")
def eletrofrio_whatsapp_start(user: AuthUser = Depends(require_admin)):
    return whatsapp_request("POST", "/start")


@router.get("/whatsapp/status")
def eletrofrio_whatsapp_status(user: AuthUser = Depends(current_user)):
    return whatsapp_request("GET", "/status")


@router.get("/whatsapp/qr")
def eletrofrio_whatsapp_qr(user: AuthUser = Depends(require_admin)):
    return whatsapp_request("GET", "/qr")


@router.post("/whatsapp/logout")
def eletrofrio_whatsapp_logout(user: AuthUser = Depends(require_admin)):
    return whatsapp_request("POST", "/logout")


@router.post("/whatsapp/send-test")
def eletrofrio_whatsapp_send_test(payload: WhatsAppTestPayload, user: AuthUser = Depends(require_admin)):
    return whatsapp_request("POST", "/send-test", payload.dict())


@router.post("/whatsapp/process-insights")
def eletrofrio_whatsapp_process_insights(user: AuthUser = Depends(require_admin)):
    return whatsapp_request("POST", "/process-insights")


@router.post("/whatsapp/send-operational-summary")
def eletrofrio_whatsapp_send_operational_summary(user: AuthUser = Depends(require_admin)):
    return whatsapp_request("POST", "/send-operational-summary")
