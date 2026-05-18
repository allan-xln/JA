from __future__ import annotations

import json
from typing import Any

import requests

from api.config import settings
from api.logger import logger


SYSTEM_PROMPT = (
    "Você é um assistente técnico de monitoramento de refrigeração. "
    "Responda somente com base nos dados fornecidos. Se faltar evidência, diga que não há dados suficientes. "
    "Não invente valores, nomes, sensores, lojas, alarmes ou diagnósticos. "
    "Diferencie possível causa de causa confirmada."
)


def fallback_explanation(evidence: dict[str, Any]) -> dict[str, str]:
    severity = evidence.get("severity", "info")
    title = evidence.get("title", "Insight operacional")
    alarm = evidence.get("alarm") if isinstance(evidence.get("alarm"), dict) else {}
    device_summary = evidence.get("device_alarm_summary") if isinstance(evidence.get("device_alarm_summary"), dict) else {}
    device_metrics = evidence.get("device_metrics") if isinstance(evidence.get("device_metrics"), dict) else {}
    store_metrics = evidence.get("store_metrics") if isinstance(evidence.get("store_metrics"), dict) else {}
    source = evidence.get("evidence_source") or "dados operacionais"

    loja = alarm.get("loja_nome") or device_summary.get("loja_nome") or store_metrics.get("loja_nome")
    tag = alarm.get("tag") or device_summary.get("tag") or device_metrics.get("tag")
    alarm_message = alarm.get("alarm_message") or alarm.get("alarm_type")

    if alarm_message:
        summary = f"Evidência operacional registrada: {alarm_message}."
    elif tag:
        summary = f"Equipamento {tag} apresenta recorrência ou comportamento que exige acompanhamento."
    elif loja:
        summary = f"Loja {loja} concentra ocorrências no recorte analisado."
    else:
        summary = "Ocorrência operacional identificada a partir dos dados monitorados."

    if loja and loja not in summary:
        summary += f" Loja: {loja}."
    if tag and tag not in summary:
        summary += f" Equipamento: {tag}."

    priority = "alta" if str(severity).casefold() == "critical" else "de atenção"
    return {
        "title": str(title),
        "summary": summary,
        "technical_reason": f"Evidência baseada em {source}, classificada com prioridade {priority}. Não há confirmação automática de causa raiz.",
        "recommended_action": "Validar operação local, porta, carga térmica, comunicação e condição do equipamento antes de acionar manutenção.",
    }


def explain_evidence(evidence: dict[str, Any]) -> dict[str, str]:
    if not settings.openai_enabled:
        return fallback_explanation(evidence)

    payload = {
        "model": settings.openai_model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Gere um JSON com title, summary, technical_reason e recommended_action. "
                    "Use apenas o evidence_json abaixo. Se os dados forem insuficientes, diga isso claramente.\n\n"
                    f"evidence_json={json.dumps(evidence, ensure_ascii=False, default=str)}"
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
            timeout=settings.http_timeout_seconds,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return {
            "title": str(parsed.get("title") or evidence.get("title") or "Insight operacional"),
            "summary": str(parsed.get("summary") or "Não há dados suficientes para uma explicação conclusiva."),
            "technical_reason": str(parsed.get("technical_reason") or "Sem razão técnica suficiente nos dados enviados."),
            "recommended_action": str(parsed.get("recommended_action") or "Validar dados e revisar ativo."),
        }
    except Exception as exc:
        logger.warning("Falha ao gerar explicação GPT; usando fallback controlado: %s", exc)
        return fallback_explanation(evidence)
