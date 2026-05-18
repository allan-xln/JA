from __future__ import annotations

from typing import Any

from api.database import SupabaseError, supabase
from api.logger import logger
from api.repositories import utc_now_iso


COMMUNICATION_SCHEMA_MESSAGE = (
    "Schema de comunicação operacional ainda não aplicado. "
    "Execute sql/004_operational_communications.sql no Supabase."
)


def preview_text(value: Any, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3].rstrip()}..."


def _schema_missing(exc: Exception) -> bool:
    text = str(exc).lower()
    return "eletrofrio_communication_logs" in text or "eletrofrio_rag_queries" in text or "eletrofrio_whatsapp_messages" in text or "pgrst205" in text or "schema cache" in text


def _safe_insert(table: str, payload: dict[str, Any]) -> None:
    try:
        supabase.insert(table, payload)
    except SupabaseError as exc:
        if _schema_missing(exc):
            logger.warning("%s: %s", COMMUNICATION_SCHEMA_MESSAGE, exc)
            return
        logger.warning("Falha ao registrar comunicação em %s: %s", table, exc)


def log_communication(payload: dict[str, Any]) -> None:
    payload = {
        "type": payload.get("type") or "system_event",
        "direction": payload.get("direction") or "system",
        "phone": payload.get("phone"),
        "loja_id": payload.get("loja_id"),
        "loja_nome": payload.get("loja_nome"),
        "dispositivo_id": payload.get("dispositivo_id"),
        "tag": payload.get("tag"),
        "message_preview": preview_text(payload.get("message_preview") or payload.get("message_full") or payload.get("message")),
        "payload_json": payload.get("payload_json") or {},
        "status": payload.get("status") or "received",
        "source": payload.get("source") or "sistema",
        "created_at": payload.get("created_at") or utc_now_iso(),
    }
    _safe_insert("eletrofrio_communication_logs", payload)


def log_rag_query(
    *,
    question: str,
    answer: dict[str, Any],
    response_time_ms: int,
) -> None:
    payload = {
        "question": question,
        "answer_preview": preview_text(answer.get("summary") or answer.get("answer")),
        "answer_full": answer.get("answer") or answer.get("summary") or "",
        "confidence": answer.get("confidence"),
        "confidence_label": answer.get("confidence_label"),
        "used_ai": bool(answer.get("used_ai")),
        "sources_json": answer.get("sources") or [],
        "warnings_json": answer.get("warnings") or [],
        "response_time_ms": response_time_ms,
        "created_at": utc_now_iso(),
    }
    _safe_insert("eletrofrio_rag_queries", payload)
    log_communication(
        {
            "type": "rag_response",
            "direction": "outgoing",
            "message_preview": payload["answer_preview"],
            "payload_json": {
                "question": question,
                "confidence": answer.get("confidence"),
                "confidence_label": answer.get("confidence_label"),
                "used_ai": answer.get("used_ai"),
                "response_time_ms": response_time_ms,
            },
            "status": "sent",
            "source": "IA operacional",
        }
    )


def list_communications(
    *,
    limit: int = 80,
    type_: str | None = None,
    status: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"select": "*", "order": "created_at.desc", "limit": min(max(limit, 1), 200)}
    if type_:
        params["type"] = f"eq.{type_}"
    if status:
        params["status"] = f"eq.{status}"
    try:
        rows = supabase.select("eletrofrio_communication_logs", params)
    except SupabaseError as exc:
        if _schema_missing(exc):
            return {"schema_applied": False, "message": COMMUNICATION_SCHEMA_MESSAGE, "items": []}
        raise
    if search:
        term = search.lower()
        rows = [
            row for row in rows
            if term in " ".join(str(row.get(key) or "") for key in ("phone", "loja_nome", "tag", "message_preview", "type", "status")).lower()
        ]
    return {"schema_applied": True, "items": rows}


def list_rag_queries(*, limit: int = 50, search: str | None = None) -> dict[str, Any]:
    try:
        rows = supabase.select(
            "eletrofrio_rag_queries",
            {"select": "*", "order": "created_at.desc", "limit": min(max(limit, 1), 200)},
        )
    except SupabaseError as exc:
        if _schema_missing(exc):
            return {"schema_applied": False, "message": COMMUNICATION_SCHEMA_MESSAGE, "items": []}
        raise
    if search:
        term = search.lower()
        rows = [row for row in rows if term in f"{row.get('question', '')} {row.get('answer_preview', '')}".lower()]
    return {"schema_applied": True, "items": rows}


def list_whatsapp_messages(*, limit: int = 80, status: str | None = None, type_: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"select": "*", "order": "created_at.desc", "limit": min(max(limit, 1), 200)}
    if status:
        params["delivery_status"] = f"eq.{status}"
    if type_:
        params["type"] = f"eq.{type_}"
    try:
        rows = supabase.select("eletrofrio_whatsapp_messages", params)
    except SupabaseError as exc:
        if _schema_missing(exc):
            return {"schema_applied": False, "message": COMMUNICATION_SCHEMA_MESSAGE, "items": []}
        raise
    return {"schema_applied": True, "items": rows}


def communication_timeline(limit: int = 80) -> dict[str, Any]:
    communications_result = list_communications(limit=limit)
    rag_result = list_rag_queries(limit=max(20, limit // 2))
    messages_result = list_whatsapp_messages(limit=max(20, limit // 2))
    if not communications_result.get("schema_applied", True) or not rag_result.get("schema_applied", True) or not messages_result.get("schema_applied", True):
        return {"schema_applied": False, "message": COMMUNICATION_SCHEMA_MESSAGE, "items": []}
    communications = communications_result.get("items", [])
    rag = rag_result.get("items", [])
    messages = messages_result.get("items", [])
    items: list[dict[str, Any]] = []
    for row in communications:
        items.append({**row, "timeline_source": "communication"})
    for row in rag:
        items.append({
            "id": row.get("id"),
            "type": "rag_query",
            "direction": "outgoing",
            "message_preview": row.get("question"),
            "status": "answered",
            "source": "IA operacional",
            "payload_json": row,
            "created_at": row.get("created_at"),
            "timeline_source": "rag",
        })
    for row in messages:
        items.append({
            "id": row.get("id"),
            "type": row.get("type"),
            "direction": row.get("direction"),
            "phone": row.get("phone"),
            "message_preview": row.get("message_preview"),
            "status": row.get("delivery_status"),
            "source": "WhatsApp",
            "payload_json": row,
            "created_at": row.get("created_at"),
            "timeline_source": "whatsapp",
        })
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return {"schema_applied": True, "items": items[: min(max(limit, 1), 200)]}
