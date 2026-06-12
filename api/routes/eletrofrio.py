from __future__ import annotations

import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import requests

from api.ai.operational_qa import ASSISTANT_SUGGESTIONS, answer_operational_question
from api.analysis.metrics import build_metrics
from api.auth import AuthUser, current_user, require_admin
from api.communications import (
    communication_timeline,
    list_communications,
    list_rag_queries,
    list_whatsapp_messages,
    log_communication,
    log_rag_query,
)
from api.config import settings
from api.database import supabase
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
from api.repositories import list_alarms, list_devices, list_insights, list_telemetry, list_units
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


class WhatsAppTestPayload(BaseModel):
    phone: str
    message: str = "Teste de WhatsApp da Eletrofrio IA."


class AssistantQueryPayload(BaseModel):
    question: str
    origin: str = "panel"


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
    message: str = "Teste de notificação operacional Eletrofrio."
    dry_run: bool = True


class NotificationProcessPayload(BaseModel):
    dry_run: bool | None = None


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


def require_supabase() -> None:
    if not supabase.enabled():
        raise HTTPException(
            status_code=503,
            detail="Supabase não configurado. Preencha SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no .env.",
        )


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


@router.get("/overview")
def eletrofrio_overview(user: AuthUser = Depends(current_user)):
    require_supabase()
    cache_key = f"{user.role}:{user.customer_id or 'admin'}"
    now = time.monotonic()
    cached = _overview_cache.get(cache_key)
    if cached and now - cached[0] <= max(0, settings.overview_cache_seconds):
        return cached[1]

    units = list_units(user.scope)
    devices = list_devices(user.scope)
    alarms = list_alarms(160, user.scope)
    telemetry_limit = 180 if user.scope.is_admin else 240
    telemetry = list_telemetry(telemetry_limit, user.scope)
    insights = list_insights(10, user.scope)
    metrics = build_metrics(units, devices, alarms, telemetry)
    metrics["totals"]["insights"] = len(insights)
    metrics["latest_insights"] = insights[:5]
    metrics["scope"] = user.public_dict()
    _overview_cache[cache_key] = (now, metrics)
    return metrics


@router.get("/units")
def eletrofrio_units(user: AuthUser = Depends(current_user)):
    require_supabase()
    return {"items": list_units(user.scope)}


@router.get("/devices")
def eletrofrio_devices(user: AuthUser = Depends(current_user)):
    require_supabase()
    return {"items": list_devices(user.scope)}


@router.get("/alarms")
def eletrofrio_alarms(limit: int = 50, offset: int = 0, user: AuthUser = Depends(current_user)):
    require_supabase()
    return {"items": list_alarms(min(max(limit, 1), 200), user.scope, max(offset, 0))}


@router.get("/telemetry")
def eletrofrio_telemetry(limit: int = 100, offset: int = 0, dispositivo_id: int | None = None, loja_id: int | None = None, user: AuthUser = Depends(current_user)):
    require_supabase()
    return {
        "items": list_telemetry(
            min(max(limit, 1), 200),
            user.scope,
            max(offset, 0),
            dispositivo_id=dispositivo_id,
            loja_id=loja_id,
        )
    }


@router.get("/insights")
def eletrofrio_insights(limit: int = 50, offset: int = 0, user: AuthUser = Depends(current_user)):
    require_supabase()
    return {"items": list_insights(min(max(limit, 1), 200), user.scope, max(offset, 0))}


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
