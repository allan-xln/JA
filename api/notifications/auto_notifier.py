from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from api.auth import DATA_DIR, TenantScope
from api.communications import log_communication
from api.config import settings
from api.database import SupabaseError, supabase
from api.logger import logger
from api.notifications.message_builder import build_group_message, build_single_message, ensure_customer_context, portal_footer, preview
from api.notifications.notification_rules import local_relevance, severity_rank
from api.repositories import filter_rows_by_scope, list_anomalies, list_insights, utc_now_iso


NOTIFICATION_SCHEMA_MESSAGE = (
    "Schema de notificações ainda não aplicado. Execute sql/006_notifications_and_performance.sql no Supabase."
)
_logged_notification_schema_warnings: set[str] = set()

AI_NOTIFICATION_SYSTEM_PROMPT = (
    "Você escreve como operador de refrigeração da Eletrofrio, de forma clara e direta para WhatsApp. "
    "Não diga que é IA e não invente causa raiz, valores, lojas ou sensores. "
    "Se o campo cliente estiver presente nos dados, inclua o nome exatamente como recebido; se não estiver, omita cliente. "
    "Use poucos emojis, organize em linhas curtas, use negrito do WhatsApp com *texto* nos rótulos principais "
    "e mantenha tom profissional e amigável. "
    "Sempre finalize convidando a acessar o portal https://eletrofrio.147.15.56.49.nip.io/."
)


def _strip_portal_lines(message: str) -> str:
    lines = str(message or "").splitlines()
    cleaned: list[str] = []
    skip_next_url = False
    for line in lines:
        normalized = line.strip().casefold()
        has_url = bool(re.search(r"https?://\S+", line))
        mentions_portal = "portal" in normalized or "painel" in normalized
        if has_url and "eletrofrio.147.15.56.49.nip.io" not in line:
            continue
        if mentions_portal and "eletrofrio.147.15.56.49.nip.io" not in line:
            skip_next_url = True
            continue
        if skip_next_url and has_url:
            skip_next_url = False
            continue
        skip_next_url = False
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _with_portal_footer(message: str) -> str:
    text = _strip_portal_lines(str(message or "").strip())
    footer = portal_footer(settings.app_public_url)
    if "eletrofrio.147.15.56.49.nip.io" in text:
        return text
    return f"{text}\n\n{footer}".strip()


def _clamp_cooldown_minutes(value: Any) -> int:
    try:
        return min(60, max(1, int(value or 60)))
    except (TypeError, ValueError):
        return 60


def _normalize_recipient_phone(value: Any) -> str:
    digits = "".join(char for char in str(value or "") if char.isdigit())
    if digits.startswith("55") and len(digits) in {12, 13}:
        digits = digits[2:]
    if len(digits) not in {10, 11}:
        raise ValueError("Telefone deve estar no formato DDD + número. Exemplo: 41984476869.")
    return digits


def _schema_missing(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "eletrofrio_notification_recipients" in text
        or "eletrofrio_notification_events" in text
        or "notification_hash" in text
        or "pgrst205" in text
        or "schema cache" in text
    )


def _warn_schema_once(key: str, exc: Exception) -> None:
    if key in _logged_notification_schema_warnings:
        return
    logger.warning("%s: %s", NOTIFICATION_SCHEMA_MESSAGE, exc)
    _logged_notification_schema_warnings.add(key)


def _hash(parts: list[Any]) -> str:
    return hashlib.sha256("|".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()


def _status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {"sent": 0, "dry_run": 0, "failed": 0, "skipped": 0}
    for row in rows:
        status = str(row.get("status") or "skipped")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _load_demo_store() -> dict[str, Any]:
    path = DATA_DIR / "demo_users_generated.json"
    if not path.exists():
        return {"customers": [], "customer_units": [], "customer_devices": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Falha ao carregar fallback de tenants para notificações: %s", exc)
        return {"customers": [], "customer_units": [], "customer_devices": []}


def _load_customer_links() -> tuple[dict[int, str], dict[int, str]]:
    units: dict[int, str] = {}
    devices: dict[int, str] = {}
    try:
        for row in supabase.select("eletrofrio_customer_units", {"select": "customer_id,loja_id", "limit": 10000}):
            if row.get("loja_id") is not None and row.get("customer_id"):
                units[int(row["loja_id"])] = str(row["customer_id"])
        for row in supabase.select("eletrofrio_customer_devices", {"select": "customer_id,dispositivo_id", "limit": 10000}):
            if row.get("dispositivo_id") is not None and row.get("customer_id"):
                devices[int(row["dispositivo_id"])] = str(row["customer_id"])
    except Exception as exc:
        logger.warning("Usando fallback local de tenants para notificações: %s", exc)

    if units or devices:
        return units, devices

    store = _load_demo_store()
    for row in store.get("customer_units", []):
        try:
            units[int(row["loja_id"])] = str(row["customer_id"])
        except (KeyError, TypeError, ValueError):
            continue
    for row in store.get("customer_devices", []):
        try:
            devices[int(row["dispositivo_id"])] = str(row["customer_id"])
        except (KeyError, TypeError, ValueError):
            continue
    return units, devices


def _load_customer_names() -> dict[str, str]:
    names: dict[str, str] = {}
    try:
        for row in supabase.select("eletrofrio_customers", {"select": "id,name", "limit": 10000}):
            customer_id = str(row.get("id") or "").strip()
            name = " ".join(str(row.get("name") or "").split())
            if customer_id and name:
                names[customer_id] = name
    except Exception as exc:
        logger.warning("Usando fallback local para nomes de clientes nas notificações: %s", exc)

    if names:
        return names

    store = _load_demo_store()
    for row in store.get("customers", []):
        customer_id = str(row.get("id") or "").strip()
        name = " ".join(str(row.get("name") or "").split())
        if customer_id and name:
            names[customer_id] = name
    return names


def _customer_name_for_id(customer_id: str | None, customer_names: dict[str, str] | None = None) -> str | None:
    if not customer_id:
        return None
    customer_names = customer_names or _load_customer_names()
    return customer_names.get(str(customer_id))


def _row_customer_id(row: dict[str, Any], unit_links: dict[int, str], device_links: dict[int, str]) -> str | None:
    if row.get("customer_id"):
        return str(row["customer_id"])
    for key in ("dispositivo_id", "equipment_id"):
        try:
            device_id = int(row[key]) if row.get(key) is not None else None
        except (TypeError, ValueError):
            device_id = None
        if device_id is not None and device_id in device_links:
            return device_links[device_id]
    try:
        loja_id = int(row["loja_id"]) if row.get("loja_id") is not None else None
    except (TypeError, ValueError):
        loja_id = None
    if loja_id is not None:
        return unit_links.get(loja_id)
    return None


def _normalize_anomaly(row: dict[str, Any], customer_id: str | None, customer_name: str | None = None) -> dict[str, Any]:
    return {
        **row,
        "source_kind": "anomaly",
        "source_id": row.get("id"),
        "customer_id": customer_id,
        "customer_name": customer_name,
        "title": row.get("title") or row.get("summary") or "Ocorrência operacional relevante",
        "dispositivo_id": row.get("dispositivo_id") or row.get("equipment_id"),
    }


def _normalize_insight(row: dict[str, Any], customer_id: str | None, customer_name: str | None = None) -> dict[str, Any]:
    evidence = row.get("evidence_json") if isinstance(row.get("evidence_json"), dict) else {}
    return {
        **row,
        "source_kind": "insight",
        "source_id": row.get("id"),
        "customer_id": customer_id,
        "customer_name": customer_name,
        "type": row.get("insight_type"),
        "message": row.get("summary") or row.get("technical_reason") or row.get("title"),
        "expected_range": evidence.get("expected_range") or {},
    }


def _notification_hash(item: dict[str, Any], recipient: dict[str, Any]) -> str:
    return _hash([item.get("source_kind"), item.get("source_id"), recipient.get("id"), recipient.get("phone"), recipient.get("channel") or "whatsapp"])


def _event_exists(notification_hash: str, include_dry_run: bool = False) -> bool:
    try:
        status_filter = "in.(sent,dry_run)" if include_dry_run else "eq.sent"
        rows = supabase.select(
            "eletrofrio_notification_events",
            {
                "select": "id,status",
                "notification_hash": f"eq.{notification_hash}",
                "status": status_filter,
                "limit": 1,
            },
        )
        return bool(rows)
    except SupabaseError as exc:
        if _schema_missing(exc):
            return False
        raise


def _recipient_in_cooldown(recipient: dict[str, Any], include_dry_run: bool = True) -> bool:
    cooldown = _clamp_cooldown_minutes(recipient.get("cooldown_minutes"))
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=cooldown)).isoformat()
    params: dict[str, Any] = {
        "select": "id,created_at",
        "status": "in.(sent,dry_run)" if include_dry_run else "eq.sent",
        "created_at": f"gte.{cutoff}",
        "limit": 1,
    }
    if recipient.get("id") and recipient.get("source") != "env":
        params["recipient_id"] = f"eq.{recipient['id']}"
    elif recipient.get("phone"):
        params["phone"] = f"eq.{recipient['phone']}"
    else:
        return False
    try:
        return bool(supabase.select("eletrofrio_notification_events", params))
    except SupabaseError as exc:
        if _schema_missing(exc):
            return False
        raise


def _should_enrich_with_ai(rows: list[dict[str, Any]], ai_calls_used: int) -> bool:
    if not settings.ai_enrich_notifications:
        return False
    if not settings.openai_enabled:
        return False
    if ai_calls_used >= max(0, settings.ai_notification_max_per_run):
        return False
    if not rows:
        return False
    if not any(severity_rank(row.get("severity")) >= 4 for row in rows):
        return False
    return any(
        row.get("summary")
        or row.get("technical_reason")
        or row.get("recommended_action")
        or row.get("evidence_json")
        for row in rows
    )


def _compact_item_for_ai(row: dict[str, Any]) -> dict[str, Any]:
    evidence = row.get("evidence_json") if isinstance(row.get("evidence_json"), dict) else {}
    return {
        "source": row.get("source_kind"),
        "cliente": row.get("customer_name"),
        "severity": row.get("severity"),
        "loja_nome": row.get("loja_nome"),
        "loja_id": row.get("loja_id"),
        "equipamento": row.get("tag") or row.get("dispositivo_id") or row.get("equipment_id"),
        "title": row.get("title"),
        "summary": row.get("summary") or row.get("message"),
        "technical_reason": row.get("technical_reason"),
        "recommended_action": row.get("recommended_action"),
        "value": row.get("value") or evidence.get("value"),
        "expected_range": row.get("expected_range") or evidence.get("expected_range"),
        "detected_at": row.get("detected_at") or row.get("created_at") or row.get("started_at"),
    }


def _enrich_message_with_ai(rows: list[dict[str, Any]], local_message: str) -> tuple[str, bool, str | None]:
    payload = {
        "model": settings.openai_model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": AI_NOTIFICATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "Gerar uma mensagem curta de WhatsApp para alerta operacional.",
                        "rules": [
                            "Nao confirmar causa raiz automaticamente.",
                            "Nao inventar cliente, leitura, faixa, loja, sensor ou equipamento.",
                            "Se o item trouxer cliente, citar o cliente exatamente como veio no JSON.",
                            "Se houver várias ocorrências, agrupar em resumo com até 5 itens.",
                            "Manter no máximo 1200 caracteres.",
                            "Incluir ação inicial objetiva.",
                            "Nao falar que a mensagem foi feita por IA.",
                            "Incluir o link do portal quando couber: https://eletrofrio.147.15.56.49.nip.io/",
                        ],
                        "local_message": local_message,
                        "items": [_compact_item_for_ai(row) for row in rows[:5]],
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
            timeout=min(settings.http_timeout_seconds, 8),
        )
        response.raise_for_status()
        parsed = json.loads(response.json()["choices"][0]["message"]["content"])
        message = str(parsed.get("message") or parsed.get("answer") or "").strip()
        if not message:
            return local_message, False, "empty_ai_message"
        return _with_portal_footer(message[:1400]), True, None
    except Exception as exc:
        logger.warning("Falha ao enriquecer notificação com IA; usando template local: %s", exc)
        return local_message, False, str(exc)[:240]


def list_recipients(scope: TenantScope | None = None) -> dict[str, Any]:
    try:
        rows = supabase.select(
            "eletrofrio_notification_recipients",
            {"select": "*", "order": "created_at.desc", "limit": 500},
        )
    except SupabaseError as exc:
        if _schema_missing(exc):
            return {"schema_applied": False, "message": NOTIFICATION_SCHEMA_MESSAGE, "items": _env_recipients(scope)}
        raise
    if scope and not scope.is_admin:
        rows = [row for row in rows if str(row.get("customer_id") or "") == str(scope.customer_id)]
    return {"schema_applied": True, "items": rows}


def _env_recipients(scope: TenantScope | None = None) -> list[dict[str, Any]]:
    phones = [item.strip() for item in settings.whatsapp_alert_to.split(",") if item.strip()]
    if scope and not scope.is_admin:
        return []
    return [
        {
            "id": f"env-admin-{index}",
            "customer_id": None,
            "role": "admin",
            "name": "Admin via WHATSAPP_ALERT_TO",
            "phone": _normalize_recipient_phone(phone),
            "channel": "whatsapp",
            "enabled": True,
            "receive_critical": True,
            "receive_warning_recurrent": True,
            "cooldown_minutes": _clamp_cooldown_minutes(settings.whatsapp_alert_cooldown_minutes),
            "source": "env",
        }
        for index, phone in enumerate(phones, 1)
    ]


def create_recipient(payload: dict[str, Any]) -> dict[str, Any]:
    rows = supabase.insert(
        "eletrofrio_notification_recipients",
        {
            "customer_id": payload.get("customer_id"),
            "role": payload.get("role") or ("client" if payload.get("customer_id") else "admin"),
            "name": payload.get("name"),
            "phone": _normalize_recipient_phone(payload.get("phone")),
            "channel": payload.get("channel") or "whatsapp",
            "enabled": payload.get("enabled", True),
            "receive_critical": payload.get("receive_critical", True),
            "receive_warning_recurrent": payload.get("receive_warning_recurrent", True),
            "cooldown_minutes": _clamp_cooldown_minutes(payload.get("cooldown_minutes")),
        },
    )
    return rows[0] if rows else {}


def update_recipient(recipient_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "customer_id",
        "role",
        "name",
        "phone",
        "channel",
        "enabled",
        "receive_critical",
        "receive_warning_recurrent",
        "cooldown_minutes",
    }
    data = {key: value for key, value in payload.items() if key in allowed}
    if "phone" in data and data["phone"] is not None:
        data["phone"] = _normalize_recipient_phone(data["phone"])
    if "cooldown_minutes" in data:
        data["cooldown_minutes"] = _clamp_cooldown_minutes(data["cooldown_minutes"])
    rows = supabase.patch("eletrofrio_notification_recipients", {"id": recipient_id}, data)
    return rows[0] if rows else {}


def delete_recipient(recipient_id: str) -> dict[str, Any]:
    rows = supabase.delete("eletrofrio_notification_recipients", {"id": recipient_id})
    return rows[0] if rows else {"id": recipient_id, "deleted": True}


def _attach_customer_names(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    customer_names = _load_customer_names()
    enriched: list[dict[str, Any]] = []
    for row in rows:
        customer_id = str(row.get("customer_id") or "").strip()
        customer_name = row.get("customer_name") or customer_names.get(customer_id)
        enriched.append({**row, "customer_name": customer_name})
    return enriched


def list_events(limit: int = 80, status: str | None = None, scope: TenantScope | None = None, offset: int = 0) -> dict[str, Any]:
    page_limit = min(max(limit, 1), 200)
    page_offset = max(offset, 0)
    fetch_limit = min(max(page_limit + page_offset, page_limit), 500) if scope and not scope.is_admin else page_limit
    params: dict[str, Any] = {"select": "*", "order": "created_at.desc", "limit": fetch_limit}
    if not scope or scope.is_admin:
        params["offset"] = page_offset
    if status:
        params["status"] = f"eq.{status}"
    try:
        rows = supabase.select("eletrofrio_notification_events", params)
    except SupabaseError as exc:
        if _schema_missing(exc):
            return {"schema_applied": False, "message": NOTIFICATION_SCHEMA_MESSAGE, "items": []}
        raise
    if scope and not scope.is_admin:
        rows = [row for row in rows if str(row.get("customer_id") or "") == str(scope.customer_id)]
        rows = rows[page_offset : page_offset + page_limit]
    return {"schema_applied": True, "items": _attach_customer_names(rows[:page_limit])}


def _recipient_event_id(recipient: dict[str, Any]) -> str | None:
    if recipient.get("source") in {"env", "manual"}:
        return None
    value = recipient.get("id")
    if not value:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError):
        return None


def _insert_event(item: dict[str, Any], recipient: dict[str, Any] | None, status: str, message: str, skip_reason: str | None = None, error_message: str | None = None, provider_message_id: str | None = None) -> None:
    recipient = recipient or {}
    base_hash = _notification_hash(item, recipient) if recipient else _hash([item.get("source_kind"), item.get("source_id")])
    notification_hash = (
        base_hash
        if status == "sent"
        else _hash([base_hash, status, skip_reason, error_message, datetime.now(timezone.utc).isoformat(timespec="seconds")])
    )
    payload = {
        "notification_hash": notification_hash,
        "customer_id": item.get("customer_id"),
        "anomaly_id": item.get("source_id") if item.get("source_kind") == "anomaly" else None,
        "insight_id": item.get("source_id") if item.get("source_kind") == "insight" else None,
        "recipient_id": _recipient_event_id(recipient),
        "phone": recipient.get("phone"),
        "channel": recipient.get("channel") or "whatsapp",
        "severity": item.get("severity"),
        "title": item.get("title") or item.get("summary") or "Ocorrência operacional",
        "message_preview": preview(message),
        "message_full": message,
        "status": status,
        "skip_reason": skip_reason,
        "provider_message_id": provider_message_id,
        "error_message": error_message,
        "sent_at": utc_now_iso() if status in {"sent", "dry_run"} else None,
    }
    try:
        supabase.insert("eletrofrio_notification_events", payload)
    except SupabaseError as exc:
        if "duplicate" in str(exc).lower() or "23505" in str(exc):
            return
        if _schema_missing(exc):
            _warn_schema_once("notification_events_insert", exc)
            return
        logger.warning("Falha ao registrar evento de notificação: %s", exc)
        return

    if status in {"sent", "dry_run", "failed"}:
        log_communication(
            {
                "type": "operational_alert",
                "direction": "outgoing",
                "phone": recipient.get("phone"),
                "loja_id": item.get("loja_id"),
                "loja_nome": item.get("loja_nome"),
                "dispositivo_id": item.get("dispositivo_id") or item.get("equipment_id"),
                "tag": item.get("tag"),
                "customer_id": item.get("customer_id"),
                "customer_name": item.get("customer_name"),
                "message_preview": message,
                "payload_json": {
                    "notification_status": status,
                    "source_kind": item.get("source_kind"),
                    "source_id": item.get("source_id"),
                    "skip_reason": skip_reason,
                    "provider_message_id": provider_message_id,
                },
                "status": status,
                "source": "notificador automático",
            }
        )


def _whatsapp_status() -> dict[str, Any]:
    if not settings.whatsapp_enabled:
        return {"enabled": False, "connected": False, "dryRun": settings.whatsapp_dry_run}
    try:
        response = requests.get(f"{settings.whatsapp_service_url}/status", timeout=min(settings.http_timeout_seconds, 8))
        if response.status_code >= 400:
            return {"enabled": True, "connected": False, "error": response.text[:200], "dryRun": settings.whatsapp_dry_run}
        body = response.json() if response.text else {}
        body.setdefault("enabled", True)
        body.setdefault("dryRun", settings.whatsapp_dry_run)
        return body
    except Exception as exc:
        return {"enabled": True, "connected": False, "error": str(exc), "dryRun": settings.whatsapp_dry_run}


def _send_message(recipient: dict[str, Any], message: str) -> tuple[str, str | None, str | None]:
    if settings.whatsapp_dry_run:
        return "dry_run", None, None
    response = requests.post(
        f"{settings.whatsapp_service_url}/send-test",
        json={"phone": recipient.get("phone"), "message": message},
        timeout=settings.http_timeout_seconds,
    )
    body = response.json() if response.text else {}
    if response.status_code >= 400:
        return "failed", json.dumps(body, ensure_ascii=False), None
    if body.get("dryRun"):
        return "dry_run", None, body.get("jid")
    if body.get("sent"):
        return "sent", None, body.get("jid")
    return "failed", json.dumps(body, ensure_ascii=False), body.get("jid")


def _candidate_items() -> list[dict[str, Any]]:
    unit_links, device_links = _load_customer_links()
    customer_names = _load_customer_names()
    items: list[dict[str, Any]] = []
    for row in list_anomalies(120, "open"):
        customer_id = _row_customer_id(row, unit_links, device_links)
        items.append(_normalize_anomaly(row, customer_id, _customer_name_for_id(customer_id, customer_names)))
    for row in list_insights(80):
        customer_id = _row_customer_id(row, unit_links, device_links)
        items.append(_normalize_insight(row, customer_id, _customer_name_for_id(customer_id, customer_names)))
    return items


def _annotate_recurrence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    store_counts: dict[tuple[str | None, Any], int] = defaultdict(int)
    device_counts: dict[tuple[str | None, Any], int] = defaultdict(int)
    recent_items = []
    for item in items:
        detected = (
            _parse_dt(item.get("detected_at"))
            or _parse_dt(item.get("created_at"))
            or _parse_dt(item.get("started_at"))
        )
        if detected and datetime.now(timezone.utc) - detected <= timedelta(hours=48):
            recent_items.append(item)
            if item.get("loja_id") is not None:
                store_counts[(item.get("customer_id"), item.get("loja_id"))] += 1
            device_id = item.get("dispositivo_id") or item.get("equipment_id")
            if device_id is not None:
                device_counts[(item.get("customer_id"), device_id)] += 1

    for item in recent_items:
        recurrence = 0
        if item.get("loja_id") is not None:
            recurrence = max(recurrence, store_counts[(item.get("customer_id"), item.get("loja_id"))])
        device_id = item.get("dispositivo_id") or item.get("equipment_id")
        if device_id is not None:
            recurrence = max(recurrence, device_counts[(item.get("customer_id"), device_id)])
        if recurrence > 1:
            item["recurrence_count"] = max(int(item.get("recurrence_count") or 0), recurrence)
    return items


def send_test_notification(payload: dict[str, Any], scope: TenantScope | None = None) -> dict[str, Any]:
    recipients = list_recipients(scope).get("items", [])
    recipient: dict[str, Any] = {"source": "manual", "channel": "whatsapp", "role": "admin"}
    if payload.get("recipient_id"):
        recipient = next((item for item in recipients if str(item.get("id")) == str(payload["recipient_id"])), {})
        if not recipient:
            raise KeyError("Destinatário não encontrado.")

    phone = payload.get("phone") or recipient.get("phone")
    if not phone:
        raise ValueError("Informe phone ou recipient_id para envio de teste.")
    phone = _normalize_recipient_phone(phone)

    recipient = {**recipient, "phone": phone, "channel": recipient.get("channel") or "whatsapp"}
    message = _with_portal_footer(
        str(
            payload.get("message")
            or "*Eletrofrio Refrigeração*\n✅ *Teste de WhatsApp recebido*\n\nSeu número está pronto para receber métricas e alertas operacionais inteligentes."
        ).strip()
    )
    item = {
        "source_kind": "test",
        "source_id": _hash(["test", phone, datetime.now(timezone.utc).isoformat(timespec="seconds")]),
        "customer_id": recipient.get("customer_id") if recipient.get("role") != "admin" else None,
        "customer_name": _customer_name_for_id(recipient.get("customer_id")) if recipient.get("role") != "admin" else None,
        "severity": "info",
        "title": "Teste de notificação operacional",
    }
    effective_dry_run = settings.whatsapp_dry_run if payload.get("dry_run") is None else bool(payload.get("dry_run"))
    whatsapp = _whatsapp_status()
    if not effective_dry_run and (not whatsapp.get("enabled") or not whatsapp.get("connected")):
        _insert_event(item, recipient, "skipped", message, skip_reason="whatsapp_disconnected")
        return {"status": "skipped", "skip_reason": "whatsapp_disconnected", "phone": phone, "message_preview": preview(message)}

    status, error, provider_id = ("dry_run", None, None) if effective_dry_run else _send_message(recipient, message)
    _insert_event(item, recipient, status, message, error_message=error, provider_message_id=provider_id)
    return {
        "status": status,
        "phone": phone,
        "message_preview": preview(message),
        "provider_message_id": provider_id,
        "error_message": error,
    }


def process_notifications(scope: TenantScope | None = None, dry_run: bool | None = None) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    recipients_result = list_recipients(scope)
    recipients = [row for row in recipients_result.get("items", []) if row.get("enabled", True) and row.get("phone")]
    if scope and not scope.is_admin:
        recipients = [row for row in recipients if str(row.get("customer_id") or "") == str(scope.customer_id)]

    items = _annotate_recurrence(_candidate_items())
    if scope and not scope.is_admin:
        items = filter_rows_by_scope(items, scope)

    whatsapp = _whatsapp_status()
    effective_dry_run = settings.whatsapp_dry_run if dry_run is None else dry_run

    if not recipients_result.get("schema_applied", True):
        elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return {
            "schema_applied": False,
            "message": recipients_result.get("message") or NOTIFICATION_SCHEMA_MESSAGE,
            "checked": len(items),
            "sent": 0,
            "dry_run": 0,
            "skipped": len(items),
            "failed": 0,
            "recipients": len(recipients),
            "whatsapp": whatsapp,
            "ai_enrichment": settings.ai_enrich_notifications,
            "ai_calls_used": 0,
            "ai_enriched": 0,
            "elapsed_ms": elapsed_ms,
        }

    checked = 0
    skipped = 0
    sent = 0
    failed = 0
    dry_run_count = 0
    ai_calls_used = 0
    ai_enriched = 0
    selected_by_recipient: dict[str, list[dict[str, Any]]] = defaultdict(list)
    recipient_by_id: dict[str, dict[str, Any]] = {}

    for item in items:
        checked += 1
        relevant, reason = local_relevance(item)
        if not relevant:
            skipped += 1
            logger.debug("Notificação ignorada por regra local: source=%s reason=%s", item.get("source_id"), reason)
            continue
        if not item.get("customer_id"):
            skipped += 1
            _insert_event(item, None, "skipped", build_single_message(item, settings.app_public_url), skip_reason="missing_customer")
            continue

        matching = [
            recipient
            for recipient in recipients
            if recipient.get("role") == "admin"
            or not recipient.get("customer_id")
            or str(recipient.get("customer_id")) == str(item.get("customer_id"))
        ]
        if not matching:
            skipped += 1
            _insert_event(item, None, "skipped", build_single_message(item, settings.app_public_url), skip_reason="no_recipient")
            continue

        for recipient in matching:
            if _recipient_in_cooldown(recipient, include_dry_run=effective_dry_run):
                skipped += 1
                _insert_event(item, recipient, "skipped", build_single_message(item, settings.app_public_url), skip_reason="recipient_cooldown")
                continue
            if severity_rank(item.get("severity")) >= 4 and not recipient.get("receive_critical", True):
                skipped += 1
                _insert_event(item, recipient, "skipped", build_single_message(item, settings.app_public_url), skip_reason="recipient_critical_disabled")
                continue
            if severity_rank(item.get("severity")) < 4 and not recipient.get("receive_warning_recurrent", True):
                skipped += 1
                _insert_event(item, recipient, "skipped", build_single_message(item, settings.app_public_url), skip_reason="recipient_warning_disabled")
                continue
            notification_hash = _notification_hash(item, recipient)
            if _event_exists(notification_hash, include_dry_run=effective_dry_run):
                skipped += 1
                continue
            recipient_key = str(recipient.get("id") or recipient.get("phone"))
            selected_by_recipient[recipient_key].append(item)
            recipient_by_id[recipient_key] = recipient

    if not settings.whatsapp_enabled:
        whatsapp = {**whatsapp, "enabled": False}

    if not effective_dry_run and (not whatsapp.get("enabled") or not whatsapp.get("connected")):
        for recipient_key, rows in selected_by_recipient.items():
            recipient = recipient_by_id[recipient_key]
            for item in rows:
                skipped += 1
                _insert_event(item, recipient, "skipped", build_single_message(item, settings.app_public_url), skip_reason="whatsapp_disconnected")
        selected_by_recipient.clear()

    for recipient_key, rows in selected_by_recipient.items():
        recipient = recipient_by_id[recipient_key]
        rows = sorted(rows, key=lambda item: severity_rank(item.get("severity")), reverse=True)[:5]
        message = build_group_message(rows, settings.app_public_url) if len(rows) > 1 else build_single_message(rows[0], settings.app_public_url)
        if _should_enrich_with_ai(rows, ai_calls_used):
            ai_calls_used += 1
            message, used_ai, _ai_warning = _enrich_message_with_ai(rows, message)
            if used_ai:
                ai_enriched += len(rows)
        message = ensure_customer_context(message, rows)
        message = _with_portal_footer(message)
        status, error, provider_id = ("dry_run", None, None) if effective_dry_run else _send_message(recipient, message)
        if status == "sent":
            sent += len(rows)
        elif status == "dry_run":
            dry_run_count += len(rows)
        else:
            failed += len(rows)
        for item in rows:
            _insert_event(item, recipient, status, message, error_message=error, provider_message_id=provider_id)

    elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    return {
        "schema_applied": recipients_result.get("schema_applied", True),
        "message": recipients_result.get("message"),
        "checked": checked,
        "sent": sent,
        "dry_run": dry_run_count,
        "skipped": skipped,
        "failed": failed,
        "recipients": len(recipients),
        "whatsapp": whatsapp,
        "ai_enrichment": settings.ai_enrich_notifications,
        "ai_calls_used": ai_calls_used,
        "ai_enriched": ai_enriched,
        "elapsed_ms": elapsed_ms,
    }


def notification_status(scope: TenantScope | None = None) -> dict[str, Any]:
    events = list_events(200, scope=scope)
    rows = events.get("items", [])
    today = datetime.now(timezone.utc).date()
    today_rows = [
        row
        for row in rows
        if ((_parse_dt(row.get("created_at")).date() if _parse_dt(row.get("created_at")) else None) == today)
    ]
    return {
        "schema_applied": events.get("schema_applied", True),
        "message": events.get("message"),
        "whatsapp": _whatsapp_status(),
        "dry_run": settings.whatsapp_dry_run,
        "ai_enrichment": settings.ai_enrich_notifications,
        "events_today": _status_counts(today_rows),
        "recent": _status_counts(rows),
        "pending": 0,
        "recipients": len(list_recipients(scope).get("items", [])),
    }
