from __future__ import annotations

from typing import Any

from api.config import settings
from api.eletrofrio_client import eletrofrio_client
from api.logger import logger
from api.repositories import recent_ticket_for_device


def should_open_ticket(insight: dict[str, Any]) -> bool:
    if not settings.auto_open_tickets:
        return False
    if insight.get("severity") != "critical":
        return False
    evidence = insight.get("evidence_json") or {}
    if evidence.get("sufficient_evidence") is False:
        return False
    dispositivo_id = insight.get("dispositivo_id")
    if not dispositivo_id:
        return False
    if recent_ticket_for_device(int(dispositivo_id)):
        return False
    return True


def open_ticket_for_insight(insight: dict[str, Any]) -> Any | None:
    if not should_open_ticket(insight):
        return None

    payload = {
        "equipe": settings.eletrofrio_team_name or "Equipe IA Eletrofrio",
        "lojaId": insight.get("loja_id"),
        "lojaNome": insight.get("loja_nome") or "",
        "dispositivoId": insight.get("dispositivo_id"),
        "tag": insight.get("tag") or "",
        "motivoIA": insight.get("summary") or insight.get("title") or "Insight crítico gerado por IA",
        "requerTecnico": True,
    }
    logger.info("Abrindo chamado Eletrofrio para dispositivo=%s", payload["dispositivoId"])
    return eletrofrio_client.open_ticket(payload)
