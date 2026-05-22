from __future__ import annotations

import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import requests

from api.ai.operational_qa import ASSISTANT_SUGGESTIONS, answer_operational_question
from api.analysis.metrics import build_metrics
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


def handle_assistant_question(payload: AssistantQueryPayload):
    require_supabase()
    question = payload.question.strip()
    if len(question) < 4:
        raise HTTPException(status_code=400, detail="Pergunta muito curta.")
    if len(question) > 1000:
        raise HTTPException(status_code=400, detail="Pergunta muito longa.")
    started = time.perf_counter()
    answer = answer_operational_question(question, origin=payload.origin)
    response_time_ms = int((time.perf_counter() - started) * 1000)
    log_communication(
        {
            "type": "incoming_question",
            "direction": "incoming",
            "message_preview": question,
            "payload_json": {"origin": payload.origin},
            "status": "received",
            "source": "WhatsApp" if payload.origin == "whatsapp" else "usuário",
        }
    )
    log_rag_query(question=question, answer=answer, response_time_ms=response_time_ms)
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
def eletrofrio_overview():
    require_supabase()
    units = list_units()
    devices = list_devices()
    alarms = list_alarms(300)
    telemetry = list_telemetry(800)
    insights = list_insights(50)
    metrics = build_metrics(units, devices, alarms, telemetry)
    metrics["totals"]["insights"] = len(insights)
    metrics["latest_insights"] = insights[:10]
    return metrics


@router.get("/units")
def eletrofrio_units():
    require_supabase()
    return {"items": list_units()}


@router.get("/devices")
def eletrofrio_devices():
    require_supabase()
    return {"items": list_devices()}


@router.get("/alarms")
def eletrofrio_alarms(limit: int = 200):
    require_supabase()
    return {"items": list_alarms(limit)}


@router.get("/telemetry")
def eletrofrio_telemetry(limit: int = 500):
    require_supabase()
    return {"items": list_telemetry(limit)}


@router.get("/insights")
def eletrofrio_insights(limit: int = 100):
    require_supabase()
    return {"items": list_insights(limit)}


@router.get("/rules/defaults/preview")
def eletrofrio_rules_defaults_preview():
    return {"items": default_rules_preview()}


@router.post("/rules/defaults/apply")
def eletrofrio_rules_defaults_apply():
    require_supabase()
    return apply_default_rules()


@router.get("/rules")
def eletrofrio_rules():
    require_supabase()
    return list_rules()


@router.post("/rules")
def eletrofrio_rules_create(payload: OperationalRulePayload):
    require_supabase()
    try:
        return create_rule(payload.dict())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc) or RULE_SCHEMA_MESSAGE) from exc


@router.post("/rules/evaluate")
def eletrofrio_rules_evaluate():
    require_supabase()
    units = list_units()
    devices = list_devices()
    alarms = list_alarms(300)
    telemetry = list_telemetry(800)
    return evaluate_recent_operation(units, devices, alarms, telemetry)


@router.get("/rule-evaluations")
def eletrofrio_rule_evaluations(limit: int = 100):
    require_supabase()
    return list_rule_evaluations(limit)


@router.get("/rules/{rule_id}")
def eletrofrio_rules_get(rule_id: str):
    require_supabase()
    try:
        rule = get_rule(rule_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc) or RULE_SCHEMA_MESSAGE) from exc
    if not rule:
        raise HTTPException(status_code=404, detail="Regra operacional não encontrada.")
    return rule


@router.put("/rules/{rule_id}")
def eletrofrio_rules_update(rule_id: str, payload: OperationalRulePayload):
    require_supabase()
    try:
        return update_rule(rule_id, payload.dict())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Regra operacional não encontrada.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc) or RULE_SCHEMA_MESSAGE) from exc


@router.patch("/rules/{rule_id}/toggle")
def eletrofrio_rules_toggle(rule_id: str):
    require_supabase()
    try:
        return toggle_rule(rule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Regra operacional não encontrada.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc) or RULE_SCHEMA_MESSAGE) from exc


@router.delete("/rules/{rule_id}")
def eletrofrio_rules_delete(rule_id: str):
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
def eletrofrio_communications(limit: int = 80, type: str | None = None, status: str | None = None, search: str | None = None):
    require_supabase()
    return list_communications(limit=limit, type_=type, status=status, search=search)


@router.get("/communications/timeline")
def eletrofrio_communications_timeline(limit: int = 80):
    require_supabase()
    return communication_timeline(limit)


@router.get("/rag/history")
def eletrofrio_rag_history(limit: int = 50, search: str | None = None):
    require_supabase()
    return list_rag_queries(limit=limit, search=search)


@router.get("/whatsapp/messages")
def eletrofrio_whatsapp_messages(limit: int = 80, status: str | None = None, type: str | None = None):
    require_supabase()
    return list_whatsapp_messages(limit=limit, status=status, type_=type)


@router.post("/assistant/ask")
def eletrofrio_assistant_ask(payload: AssistantQueryPayload):
    return handle_assistant_question(payload)


@router.post("/assistant/query")
def eletrofrio_assistant_query(payload: AssistantQueryPayload):
    return handle_assistant_question(payload)


@router.post("/run-collector")
def eletrofrio_run_collector():
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
def eletrofrio_whatsapp_start():
    return whatsapp_request("POST", "/start")


@router.get("/whatsapp/status")
def eletrofrio_whatsapp_status():
    return whatsapp_request("GET", "/status")


@router.get("/whatsapp/qr")
def eletrofrio_whatsapp_qr():
    return whatsapp_request("GET", "/qr")


@router.post("/whatsapp/logout")
def eletrofrio_whatsapp_logout():
    return whatsapp_request("POST", "/logout")


@router.post("/whatsapp/send-test")
def eletrofrio_whatsapp_send_test(payload: WhatsAppTestPayload):
    return whatsapp_request("POST", "/send-test", payload.dict())


@router.post("/whatsapp/process-insights")
def eletrofrio_whatsapp_process_insights():
    return whatsapp_request("POST", "/process-insights")


@router.post("/whatsapp/send-operational-summary")
def eletrofrio_whatsapp_send_operational_summary():
    return whatsapp_request("POST", "/send-operational-summary")
