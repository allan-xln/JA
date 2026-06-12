from __future__ import annotations

import json
import re
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

import requests

from api.ai.knowledge_context import rules_for_terms
from api.analysis.metrics import build_metrics
from api.analysis.rules import classify_alarm_severity
from api.auth import TenantScope
from api.config import settings
from api.logger import logger
from api.repositories import (
    list_alarms,
    list_anomalies,
    list_collector_runs,
    list_devices,
    list_insights,
    list_telemetry,
    list_units,
)
from api.rules.rule_repository import get_enabled_rules


ASSISTANT_SUGGESTIONS = [
    "Me dá um resumo da operação agora",
    "Quais lojas estão mais críticas?",
    "Qual equipamento exige atenção imediata?",
    "Como está a loja Sítio Cercado?",
    "Teve alguma anomalia hoje?",
    "Quais equipamentos estão offline?",
    "Existe risco de perda por temperatura?",
    "Quais alarmes críticos estão abertos?",
]

INTENTS = {
    "operation_summary",
    "status_store",
    "status_device",
    "temperature_query",
    "recent_anomalies",
    "critical_alerts",
    "offline_devices",
    "top_critical_stores",
    "top_critical_devices",
    "temperature_risk",
    "trend_analysis",
    "unknown_question",
}

FAST_LOCAL_INTENTS = {
    "operation_summary",
    "status_store",
    "status_device",
    "temperature_query",
    "recent_anomalies",
    "critical_alerts",
    "offline_devices",
    "top_critical_stores",
    "top_critical_devices",
    "temperature_risk",
}

INTENT_LABELS = {
    "operation_summary": "Resumo operacional",
    "status_store": "Status da loja",
    "status_device": "Status do equipamento",
    "temperature_query": "Consulta de temperatura",
    "recent_anomalies": "Ocorrências recentes",
    "critical_alerts": "Alertas críticos",
    "offline_devices": "Equipamentos offline",
    "top_critical_stores": "Lojas críticas",
    "top_critical_devices": "Equipamentos críticos",
    "temperature_risk": "Risco por temperatura",
    "trend_analysis": "Tendência operacional",
    "unknown_question": "Pergunta não classificada",
}

SOURCE_PRIORITY = {
    "overview": 0,
    "anomaly": 1,
    "insight": 2,
    "alarm": 3,
    "telemetry": 4,
    "unit": 5,
    "device": 5,
    "run": 6,
    "store_metric": 7,
    "device_metric": 7,
}

SYSTEM_PROMPT = (
    "Voce e o assistente operacional da Eletrofrio. Responda em portugues do Brasil, "
    "com tom corporativo, curto e claro. Use somente o contexto JSON informado. "
    "Nao invente lojas, sensores, temperaturas, alarmes, causas ou status. "
    "Telemetria vazia nao confirma falha. Diferencie evidencia, hipotese e recomendacao. "
    "Se nao houver evidencia, diga isso explicitamente. Se o termo for ambiguo, peça confirmacao. "
    "A resposta deve cobrir situacao atual, evidencias, risco/prioridade, recomendacao e observacao de seguranca. "
    "Retorne apenas JSON com answer e bullet_points."
)

STOPWORDS = {
    "agora",
    "alguma",
    "algum",
    "como",
    "com",
    "das",
    "dos",
    "esta",
    "estao",
    "está",
    "estão",
    "eletrofrio",
    "equipamento",
    "equipamentos",
    "loja",
    "lojas",
    "mais",
    "menos",
    "operacao",
    "operação",
    "para",
    "qual",
    "quais",
    "que",
    "sensor",
    "sensores",
    "sobre",
    "status",
    "teve",
}

TECHNICAL_TERMS = {
    "compressor",
    "camara",
    "câmara",
    "rack",
    "alta temperatura",
    "baixa temperatura",
    "offline",
    "degelo",
    "pressao",
    "pressão",
    "glicol",
    "porta",
    "ventilacao",
    "ventilação",
    "congelado",
    "resfriado",
}


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _norm(value: Any) -> str:
    return _strip_accents(str(value or "").casefold())


def _tokens(question: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[\w-]{3,}", _norm(question))
        if word not in STOPWORDS
    }


def _meaningful_query(question: str) -> str:
    return " ".join(sorted(_tokens(question)))


def _numbers(question: str) -> set[int]:
    values: set[int] = set()
    for item in re.findall(r"\d+", question):
        try:
            values.add(int(item))
        except ValueError:
            continue
    return values


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _age_warning(value: Any, label: str) -> str | None:
    parsed = _parse_dt(value)
    if not parsed:
        return None
    hours = (datetime.now(timezone.utc) - parsed).total_seconds() / 3600
    if hours > 24:
        return f"{label} tem mais de 24 horas; validar com nova coleta."
    if hours > 6:
        return f"{label} nao e recente; interpretar com cautela."
    return None


def _row_text(row: dict[str, Any]) -> str:
    return _norm(json.dumps(row, ensure_ascii=False, default=str))


def _source(source_type: str, row: dict[str, Any], label: str, relevance_reason: str | None = None) -> dict[str, Any]:
    timestamp = (
        row.get("measured_at")
        or row.get("detected_at")
        or row.get("started_at")
        or row.get("finished_at")
        or row.get("created_at")
        or row.get("updated_at")
    )
    source_id = row.get("id") or row.get("anomaly_hash") or row.get("insight_hash") or row.get("external_hash")
    source_id = source_id or row.get("dispositivo_id") or row.get("loja_id") or source_type
    return {
        "type": source_type,
        "id": str(source_id),
        "label": label,
        "loja_id": row.get("loja_id"),
        "dispositivo_id": row.get("dispositivo_id") or row.get("equipment_id"),
        "loja_nome": row.get("loja_nome"),
        "tag": row.get("tag"),
        "timestamp": timestamp,
        "relevance_reason": relevance_reason or _default_relevance(source_type, row),
    }


def _dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, Any]] = set()
    deduped: list[dict[str, Any]] = []
    sorted_sources = sorted(sources, key=lambda item: SOURCE_PRIORITY.get(str(item.get("type")), 99))
    for item in sorted_sources:
        key = (item.get("type"), item.get("id"))
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:6]


def _default_relevance(source_type: str, row: dict[str, Any]) -> str:
    if source_type == "overview":
        return "Consolida totais, rankings e o estado geral do recorte operacional."
    if source_type == "anomaly":
        return "Ocorrência aberta usada para priorizar risco e ação."
    if source_type == "insight":
        return "Análise operacional gerada a partir de alarmes, telemetria ou regras."
    if source_type == "alarm":
        severity = row.get("severity") or row.get("criticidade") or row.get("alarm_type")
        if severity:
            return f"Alarme recente com prioridade {_priority_label(severity)}."
        return "Alarme recente relacionado ao diagnóstico."
    if source_type == "telemetry":
        return "Leitura de telemetria usada para verificar evidência operacional."
    if source_type == "run":
        return "Execução do coletor usada para avaliar atualidade dos dados."
    if source_type in {"unit", "store_metric"}:
        return "Registro de loja usado para confirmar identificação e recorrência."
    if source_type in {"device", "device_metric"}:
        return "Registro de equipamento usado para confirmar identificação e prioridade."
    return "Fonte relacionada à pergunta operacional."


def _item_label(row: dict[str, Any]) -> str:
    return str(
        row.get("tag")
        or row.get("title")
        or row.get("summary")
        or row.get("alarm_message")
        or row.get("dispositivo_id")
        or row.get("loja_nome")
        or row.get("loja_id")
        or "item sem identificação"
    )


def _alarm_description(row: dict[str, Any]) -> str:
    raw = row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {}
    return str(
        row.get("alarm_message")
        or row.get("summary")
        or row.get("title")
        or row.get("alarm_type")
        or raw.get("alarmeDesc")
        or raw.get("grupoNm")
        or "alarme operacional"
    )


def _priority_label(value: Any) -> str:
    normalized = _norm(value).strip()
    if normalized in {"critical", "critico", "c"}:
        return "crítica"
    if normalized in {"high", "alta", "a"}:
        return "alta prioridade"
    if normalized in {"warning", "medium", "media", "m"}:
        return "atenção operacional"
    if normalized in {"low", "baixa", "b"}:
        return "monitoramento"
    return "informativa"


def _confidence_details(confidence: float, sources: list[dict[str, Any]], warnings: list[str], matched: bool) -> tuple[str, str]:
    if not matched:
        return "Baixa", "A pergunta não teve correspondência operacional segura no recorte carregado."
    if confidence >= 0.82:
        label = "Alta"
    elif confidence >= 0.58:
        label = "Média"
    else:
        label = "Baixa"

    source_types = {source.get("type") for source in sources}
    evidence_parts = []
    if "overview" in source_types:
        evidence_parts.append("resumo operacional")
    if "anomaly" in source_types:
        evidence_parts.append("anomalias abertas")
    if "alarm" in source_types:
        evidence_parts.append("alarmes recentes")
    if "telemetry" in source_types:
        evidence_parts.append("telemetria")
    if "run" in source_types:
        evidence_parts.append("histórico de coleta")

    if evidence_parts and not warnings:
        reason = f"Baseada em {', '.join(evidence_parts)} sem aviso relevante no recorte."
    elif evidence_parts:
        reason = f"Baseada em {', '.join(evidence_parts)}, com ressalvas de evidência."
    else:
        reason = "Baseada em poucos dados diretos; exige validação adicional."
    return label, reason


def _score(row: dict[str, Any], question: str) -> int:
    text = _row_text(row)
    tokens = _tokens(question)
    numbers = _numbers(question)
    score = sum(2 for token in tokens if token in text)
    for field in ("loja_id", "dispositivo_id", "equipment_id"):
        value = row.get(field)
        if value is None:
            continue
        try:
            if int(value) in numbers:
                score += 12
        except (TypeError, ValueError):
            continue
    return score


def _rank(rows: list[dict[str, Any]], question: str, limit: int) -> list[dict[str, Any]]:
    scored = [(_score(row, question), row) for row in rows]
    selected = [row for score, row in sorted(scored, key=lambda item: item[0], reverse=True) if score > 0]
    return selected[:limit]


def _similarity(left: str, right: str) -> float:
    left_norm = _norm(left)
    right_norm = _norm(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm in right_norm or right_norm in left_norm:
        return 0.95
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def detect_intent(question: str) -> str:
    q = _norm(question)
    if "loja" in q and any(term in q for term in ("critica", "criticas", "critico", "criticos", "maior risco", "mais risco")):
        return "top_critical_stores"
    if any(term in q for term in ("equipamento exige atencao", "exige atencao imediata", "maior risco", "mais critico agora")):
        return "top_critical_devices"
    if any(term in q for term in ("risco de perda", "perda por temperatura", "risco por temperatura", "risco de temperatura")):
        return "temperature_risk"
    if any(term in q for term in ("offline", "sem comunicacao", "sem comunicação")):
        return "offline_devices"
    if any(term in q for term in ("resumo", "operacao", "operação", "geral")):
        return "operation_summary"
    if any(term in q for term in ("anomalia", "anomalias", "problema hoje", "ocorrencia hoje", "ocorrência hoje")):
        return "recent_anomalies"
    if any(term in q for term in ("lojas criticas", "lojas críticas", "loja mais critica", "loja mais crítica")):
        return "top_critical_stores"
    if any(term in q for term in ("equipamentos criticos", "equipamentos críticos", "dispositivos criticos", "dispositivos críticos")):
        return "top_critical_devices"
    if any(term in q for term in ("critico", "crítico", "alertas", "prioridade", "problema")):
        return "critical_alerts"
    if any(term in q for term in ("variacao", "variação", "historico", "histórico", "ultimas horas", "últimas horas")):
        return "trend_analysis"
    if "loja" in q:
        return "status_store"
    if "temperatura" in q:
        return "temperature_query"
    if any(term in q for term in ("sensor", "camara", "câmara")):
        return "status_device"
    if any(term in q for term in ("equipamento", "compressor", "dispositivo")):
        return "status_device"
    return "unknown_question"


def _extract_entities(question: str) -> dict[str, Any]:
    q = _norm(question)
    period = "now"
    if any(term in q for term in ("hoje", "dia")):
        period = "today"
    elif any(term in q for term in ("ultimas horas", "últimas horas", "hora")):
        period = "last_hours"
    elif any(term in q for term in ("semana", "7 dias")):
        period = "last_week"

    severity = None
    if any(term in q for term in ("critico", "crítico", "alta prioridade")):
        severity = "critical"
    elif any(term in q for term in ("warning", "medio", "médio", "alerta")):
        severity = "warning"

    measurement_type = None
    if "temperatura" in q:
        measurement_type = "temperature"
    elif any(term in q for term in ("pressao", "pressão")):
        measurement_type = "pressure"

    return {
        "period": period,
        "severity": severity,
        "measurement_type": measurement_type,
        "technical_terms": [term for term in sorted(TECHNICAL_TERMS) if _norm(term) in q],
        "numbers": sorted(_numbers(question)),
        "tokens": sorted(_tokens(question)),
    }


def _find_store(question: str, units: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    numbers = _numbers(question)
    for unit in units:
        try:
            if int(unit.get("loja_id")) in numbers:
                return unit, []
        except (TypeError, ValueError):
            pass

    query_terms = _tokens(question)
    query_text = _meaningful_query(question)
    candidates = []
    for unit in units:
        store_name = str(unit.get("loja_nome") or "")
        store_norm = _norm(store_name)
        store_terms = set(re.findall(r"[\w-]{3,}", store_norm))
        overlap = len(query_terms & store_terms)
        score = max(_similarity(question, store_name), _similarity(query_text, store_name))
        if overlap:
            score += min(0.35, overlap * 0.12)
        if score >= 0.45 or overlap >= 2:
            candidates.append((score, unit))
    candidates.sort(key=lambda item: item[0], reverse=True)
    if candidates and candidates[0][0] >= 0.70:
        return candidates[0][1], [item[1] for item in candidates[1:4]]
    return None, [item[1] for item in candidates[:4]]


def _find_device(question: str, devices: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    numbers = _numbers(question)
    for device in devices:
        try:
            if int(device.get("dispositivo_id")) in numbers:
                return device, []
        except (TypeError, ValueError):
            pass

    query_terms = _tokens(question)
    query_text = _meaningful_query(question)
    candidates = []
    for device in devices:
        label = " ".join(str(device.get(field) or "") for field in ("tag", "dispositivo_id", "loja_nome", "loja_id"))
        label_norm = _norm(label)
        overlap = len(query_terms & set(re.findall(r"[\w-]{3,}", label_norm)))
        score = max(_similarity(question, label), _similarity(query_text, label))
        if overlap:
            score += min(0.30, overlap * 0.10)
        if score >= 0.35 or overlap:
            candidates.append((score, device))
    candidates.sort(key=lambda item: item[0], reverse=True)
    if candidates and candidates[0][0] >= 0.62:
        return candidates[0][1], [item[1] for item in candidates[1:4]]
    return None, [item[1] for item in candidates[:4]]


def _for_store(rows: list[dict[str, Any]], store: dict[str, Any]) -> list[dict[str, Any]]:
    loja_id = store.get("loja_id")
    loja_nome = _norm(store.get("loja_nome"))
    return [
        row
        for row in rows
        if row.get("loja_id") == loja_id or (loja_nome and loja_nome in _norm(row.get("loja_nome")))
    ]


def _for_device(rows: list[dict[str, Any]], device: dict[str, Any]) -> list[dict[str, Any]]:
    dispositivo_id = device.get("dispositivo_id")
    tag = _norm(device.get("tag"))
    return [
        row
        for row in rows
        if row.get("dispositivo_id") == dispositivo_id or (tag and tag in _norm(row.get("tag")))
    ]


def _format_store(store: dict[str, Any]) -> str:
    name = store.get("loja_nome") or "loja sem nome"
    loja_id = store.get("loja_id")
    return f"{name} ({loja_id})" if loja_id is not None else str(name)


def _format_device(device: dict[str, Any]) -> str:
    tag = device.get("tag") or "equipamento sem tag"
    device_id = device.get("dispositivo_id")
    return f"{tag} ({device_id})" if device_id is not None else str(tag)


def _latest_telemetry(telemetry: list[dict[str, Any]]) -> dict[str, Any] | None:
    return max(telemetry, key=lambda row: _parse_dt(row.get("measured_at")) or datetime.min.replace(tzinfo=timezone.utc), default=None)


def _confidence(sources: list[dict[str, Any]], warnings: list[str], matched: bool = True) -> float:
    if not matched:
        return 0.25
    base = 0.4
    if any(source.get("type") in {"unit", "device", "store_metric", "device_metric"} for source in sources):
        base += 0.14
    if any(source.get("type") == "alarm" for source in sources):
        base += 0.16
    if any(source.get("type") == "telemetry" for source in sources):
        base += 0.14
    if any(source.get("type") in {"insight", "anomaly"} for source in sources):
        base += 0.14
    base += min(0.12, len(sources) * 0.015)
    if any(source.get("timestamp") and not _age_warning(source.get("timestamp"), "Dado") for source in sources):
        base += 0.08
    if warnings:
        base -= min(0.25, len(warnings) * 0.06)
    return round(max(0.2, min(0.96, base)), 2)


def _safe_fetch(label: str, fetcher: Any, default: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    try:
        return fetcher()
    except Exception as exc:
        logger.warning("Falha ao carregar %s para o RAG operacional: %s", label, exc)
        return default or []


def retrieve_operational_context(question: str, intent: str, scope: TenantScope | None = None) -> dict[str, Any]:
    retrieval_warnings: list[str] = []

    def capture(label: str, fetcher: Any) -> list[dict[str, Any]]:
        try:
            return fetcher()
        except Exception as exc:
            logger.warning("Falha ao carregar %s para o RAG operacional: %s", label, exc)
            retrieval_warnings.append(f"Não foi possível carregar {label}; resposta baseada nas demais fontes disponíveis.")
            return []

    units = capture("lojas", lambda: list_units(scope))
    devices = capture("dispositivos", lambda: list_devices(scope))
    alarms = capture("alarmes", lambda: list_alarms(180, scope))
    telemetry = capture("telemetria", lambda: list_telemetry(240, scope))
    insights = capture("insights", lambda: list_insights(80, scope))
    anomalies = capture("anomalias", lambda: list_anomalies(80, scope=scope))
    runs = capture("histórico de coletas", lambda: list_collector_runs(8))
    metrics = build_metrics(units, devices, alarms, telemetry)
    store, store_alternatives = _find_store(question, units)
    device, device_alternatives = _find_device(question, devices)
    operational_rules = [
        {
            "id": rule.get("id"),
            "name": rule.get("name"),
            "severity": rule.get("severity_when_triggered"),
            "equipment_type": rule.get("equipment_type"),
            "condition_type": rule.get("condition_type"),
            "explanation": rule.get("explanation_template"),
            "recommended_action": rule.get("recommended_action_template"),
        }
        for rule in _safe_fetch("regras operacionais", get_enabled_rules)[:12]
    ]

    return {
        "question": question,
        "intent": intent,
        "units": units,
        "devices": devices,
        "alarms": alarms,
        "telemetry": telemetry,
        "insights": insights,
        "anomalies": anomalies,
        "collector_runs": runs,
        "overview": metrics,
        "entities": _extract_entities(question),
        "matched_store": store,
        "store_alternatives": store_alternatives,
        "matched_device": device,
        "device_alternatives": device_alternatives,
        "ranked_devices": _rank(devices, question, 8),
        "ranked_alarms": _rank(alarms, question, 12),
        "ranked_telemetry": _rank(telemetry, question, 12),
        "ranked_insights": _rank(insights, question, 12),
        "ranked_anomalies": _rank(anomalies, question, 12),
        "knowledge_rules": rules_for_terms(question),
        "operational_rules": operational_rules,
        "retrieval_warnings": retrieval_warnings,
        "scope": {
            "label": scope.label if scope else "Visão administrativa",
            "role": scope.role if scope else "admin",
            "customer_id": scope.customer_id if scope and not scope.is_admin else None,
            "customer_name": scope.customer_name if scope and not scope.is_admin else None,
            "allowed_loja_ids": sorted(scope.allowed_loja_ids) if scope and not scope.is_admin else [],
            "allowed_dispositivo_ids": sorted(scope.allowed_dispositivo_ids) if scope and not scope.is_admin else [],
        },
    }


def _operation_summary(context: dict[str, Any]) -> dict[str, Any]:
    overview = context["overview"]
    insights = context["insights"]
    alarms = context["alarms"]
    anomalies = context["anomalies"]
    runs = context["collector_runs"]
    top_stores = overview.get("top_critical_stores") or overview.get("most_critical_stores") or []
    top_devices = overview.get("top_critical_devices") or overview.get("most_problematic_devices") or []
    alarm_types = Counter(_alarm_description(row) for row in alarms[:120])
    latest_run = runs[0] if runs else None
    sources = [
        {
            "type": "overview",
            "id": "overview",
            "label": "Resumo operacional",
            "loja_nome": None,
            "tag": None,
            "timestamp": latest_run.get("finished_at") or latest_run.get("started_at") if latest_run else None,
            "relevance_reason": "Consolida lojas, dispositivos, alarmes, telemetria, rankings e anomalias abertas.",
        },
        *[_source("anomaly", row, "Anomalia aberta", "Ocorrência aberta usada para montar a prioridade do resumo.") for row in anomalies[:3]],
        *[_source("insight", row, "Insight operacional", "Insight recente com evidência estruturada do recorte.") for row in insights[:2]],
        *[_source("alarm", row, "Alarme crítico", "Alarme recente usado para identificar tipo de ocorrência e prioridade.") for row in alarms[:3]],
        *[_source("run", row, "Execução do coletor", "Execução usada para confirmar atualidade da leitura operacional.") for row in runs[:2]],
    ]
    warnings = []
    if latest_run and latest_run.get("status") != "success":
        warnings.append(f"Ultima coleta registrada com status {latest_run.get('status')}.")
    if latest_run:
        warning = _age_warning(latest_run.get("finished_at") or latest_run.get("started_at"), "Ultima coleta")
        if warning:
            warnings.append(warning)

    totals = overview.get("totals", {})
    top_store = top_stores[0] if top_stores else None
    top_device_labels = [_item_label(item) for item in (anomalies[:3] or top_devices[:3])]
    occurrence_types = [name for name, _ in alarm_types.most_common(3)]
    key_findings = [
        f"{totals.get('units', 0)} lojas, {totals.get('devices', 0)} dispositivos e {totals.get('telemetry', 0)} leituras de telemetria no recorte carregado.",
        f"{totals.get('alarms', 0)} alarmes recentes, {len(anomalies)} anomalias abertas e {len(insights)} insights operacionais disponíveis.",
    ]
    if top_store:
        key_findings.append(
            f"{top_store.get('loja_nome') or top_store.get('loja_id')} aparece como principal loja por recorrência, com {top_store.get('alarm_count', 0)} alarmes."
        )
    if top_device_labels:
        key_findings.append(f"Equipamentos em destaque: {', '.join(top_device_labels[:3])}.")
    if occurrence_types:
        key_findings.append(f"Tipos de ocorrência mais visíveis: {', '.join(occurrence_types)}.")

    recommended_actions = [
        "Priorizar a validação dos equipamentos críticos da fila operacional.",
        "Confirmar leitura local, porta, carga térmica e condição do controlador antes de concluir causa raiz.",
        "Manter a coleta atualizada antes de tomar decisão de manutenção em campo.",
    ]

    answer = (
        f"Resumo operacional: a operação possui {totals.get('units', 0)} lojas monitoradas, "
        f"{totals.get('devices', 0)} dispositivos identificados, {totals.get('alarms', 0)} alarmes recentes, "
        f"{totals.get('telemetry', 0)} leituras de telemetria e {len(anomalies)} anomalias abertas. "
    )
    if top_store:
        answer += (
            f"O principal ponto de atenção é {top_store.get('loja_nome') or top_store.get('loja_id')}, "
            f"com {top_store.get('alarm_count', 0)} alarmes no recorte. "
        )
    if top_device_labels:
        answer += f"Equipamentos que justificam atenção imediata: {', '.join(top_device_labels[:3])}. "
    if occurrence_types:
        answer += f"As ocorrências mais visíveis envolvem {', '.join(occurrence_types[:3])}. "
    answer += (
        "A recomendação é tratar primeiro os itens críticos, validar evidência local e não assumir defeito sem confirmação de campo."
    )

    return {
        "answer": answer,
        "summary": answer,
        "key_findings": key_findings,
        "recommended_actions": recommended_actions,
        "sources": sources,
        "warnings": warnings,
        "matched": True,
    }


def _enrich_local_response(local: dict[str, Any]) -> dict[str, Any]:
    answer = str(local.get("answer") or "")
    if not local.get("summary"):
        local["summary"] = answer
    if not local.get("key_findings"):
        local["key_findings"] = [answer] if answer else []
    if not local.get("recommended_actions"):
        local["recommended_actions"] = [
            "Validar as evidências no painel antes de acionar manutenção.",
            "Confirmar condição local quando houver alarme sem telemetria suficiente.",
        ]
    return local


def _status_store(context: dict[str, Any]) -> dict[str, Any]:
    store = context["matched_store"]
    if not store:
        alternatives = ", ".join(_format_store(item) for item in context["store_alternatives"][:3])
        if context.get("scope", {}).get("role") == "client":
            warning = "Não encontrei essa loja no seu ambiente."
        else:
            warning = "Loja nao identificada com seguranca."
        if alternatives:
            warning += f" Possiveis correspondencias: {alternatives}."
        return {"answer": warning, "sources": [], "warnings": [warning], "matched": False}

    devices = _for_store(context["devices"], store)
    alarms = _for_store(context["alarms"], store)
    insights = _for_store(context["insights"], store)
    anomalies = _for_store(context["anomalies"], store)
    telemetry = _for_store(context["telemetry"], store)
    critical = [item for item in insights + anomalies if str(item.get("severity") or "").casefold() in {"critical", "critico", "crítico"}]
    latest = _latest_telemetry(telemetry)
    warnings = []
    if latest:
        warning = _age_warning(latest.get("measured_at"), "Ultima telemetria da loja")
        if warning:
            warnings.append(warning)
    else:
        warnings.append("Nao ha telemetria recente no recorte carregado para confirmar status termico da loja.")

    answer = f"Situação atual da loja {_format_store(store)}: {len(devices)} dispositivos monitorados, {len(alarms)} alarmes recentes, {len(anomalies)} anomalias abertas e {len(insights)} insights no recorte. "
    if critical:
        evidence = critical[0]
        answer += (
            f"Prioridade alta: há {len(critical)} evidência(s) crítica(s), com destaque para "
            f"{evidence.get('tag') or evidence.get('title') or evidence.get('dispositivo_id')}. "
            "Recomendação: validar operação local, porta, carga térmica, sensor e condição do equipamento antes de acionar manutenção."
        )
    elif alarms or insights:
        answer += "Há evidências para acompanhamento, mas sem criticidade alta confirmada no recorte. Recomendo acompanhar recorrência e validar nova coleta."
    else:
        answer += "Não encontrei dados suficientes para confirmar falha nessa loja. Isso não confirma normalidade se os dados estiverem desatualizados."

    sources = [
        _source("unit", store, "Loja identificada"),
        *[_source("device", row, "Dispositivo da loja") for row in devices[:3]],
        *[_source("alarm", row, "Alarme recente da loja") for row in alarms[:4]],
        *[_source("anomaly", row, "Anomalia aberta da loja") for row in anomalies[:4]],
        *[_source("insight", row, "Insight da loja") for row in insights[:4]],
    ]
    if latest:
        sources.append(_source("telemetry", latest, "Ultima telemetria da loja"))
    return {"answer": answer, "sources": sources, "warnings": warnings, "matched": True}


def _status_device(context: dict[str, Any]) -> dict[str, Any]:
    device = context["matched_device"]
    if not device:
        alternatives = ", ".join(_format_device(item) for item in context["device_alternatives"][:3])
        warning = "Sensor/equipamento nao identificado com seguranca."
        if alternatives:
            warning += f" Possiveis correspondencias: {alternatives}."
        return {"answer": warning, "sources": [], "warnings": [warning], "matched": False}

    alarms = _for_device(context["alarms"], device)
    insights = _for_device(context["insights"], device)
    anomalies = _for_device(context["anomalies"], device)
    telemetry = _for_device(context["telemetry"], device)
    latest = _latest_telemetry(telemetry)
    warnings = []
    if latest:
        warning = _age_warning(latest.get("measured_at"), "Ultima telemetria do equipamento")
        if warning:
            warnings.append(warning)
    else:
        warnings.append("Nao ha leitura de telemetria suficiente para confirmar temperatura ou normalidade.")

    answer = f"Situação atual do equipamento {_format_device(device)}: "
    if latest and latest.get("temperature") not in (None, ""):
        answer += f"última temperatura registrada {latest.get('temperature')} C em {latest.get('measured_at')}. "
    else:
        answer += "não encontrei temperatura recente no recorte carregado. "

    if anomalies:
        answer += (
            f"Há {len(anomalies)} anomalia(s) aberta(s) relacionada(s), maior severidade {anomalies[0].get('severity')}. "
            "Recomendação: validar evidência local antes de concluir defeito no equipamento."
        )
    elif insights:
        answer += f"Há {len(insights)} insight(s) relacionado(s), maior severidade {insights[0].get('severity')}. Recomendo priorizar se houver recorrência."
    elif alarms:
        answer += f"Há {len(alarms)} alarme(s) recente(s) relacionado(s). A evidência indica atenção operacional, não causa raiz confirmada."
    else:
        answer += "Não há alarmes, anomalias ou insights relacionados no recorte. Isso não confirma normalidade sem telemetria recente."

    sources = [
        _source("device", device, "Equipamento identificado"),
        *[_source("telemetry", row, "Telemetria do equipamento") for row in telemetry[:4]],
        *[_source("alarm", row, "Alarme do equipamento") for row in alarms[:4]],
        *[_source("anomaly", row, "Anomalia do equipamento") for row in anomalies[:4]],
        *[_source("insight", row, "Insight do equipamento") for row in insights[:4]],
    ]
    return {"answer": answer, "sources": sources, "warnings": warnings, "matched": True}


def _recent_anomalies(context: dict[str, Any]) -> dict[str, Any]:
    anomalies = context["anomalies"][:20]
    insights = context["insights"][:20]
    alarms = context["alarms"][:30]
    severity_counter = Counter(str(item.get("severity") or "info") for item in anomalies + insights)
    stores = Counter(str(item.get("loja_nome") or item.get("loja_id") or "sem loja") for item in anomalies + insights + alarms)
    sources = [
        *[_source("anomaly", row, "Anomalia recente") for row in anomalies[:6]],
        *[_source("insight", row, "Insight/anomalia recente") for row in insights[:6]],
        *[_source("alarm", row, "Alarme recente") for row in alarms[:6]],
    ]
    if not anomalies and not insights and not alarms:
        warning = "Não encontrei dados suficientes para confirmar anomalias recentes no recorte carregado."
        return {"answer": warning, "sources": [], "warnings": [warning], "matched": True}
    answer = (
        f"Situação atual: encontrei {len(anomalies)} anomalias abertas, {len(insights)} insights e {len(alarms)} alarmes recentes. "
        f"Evidência por severidade: {dict(severity_counter)}. "
    )
    if stores:
        answer += f"Prioridade: maiores concentrações em {', '.join(name for name, _ in stores.most_common(3))}. Recomendo validar os itens críticos antes de acionar manutenção."
    return {"answer": answer, "sources": sources, "warnings": [], "matched": True}


def _offline_devices(context: dict[str, Any]) -> dict[str, Any]:
    rows = context["alarms"] + context["insights"] + context["anomalies"]
    offline = [row for row in rows if "offline" in _row_text(row) or "comunicacao" in _row_text(row)]
    sources = []
    for row in offline[:10]:
        source_type = "alarm" if row in context["alarms"] else "anomaly" if row in context["anomalies"] else "insight"
        sources.append(_source(source_type, row, "Evidencia de offline/comunicacao"))
    if not offline:
        warning = "Não encontrei evidência confiável de equipamentos offline em alarmes, anomalias ou insights. Telemetria ausente sozinha não confirma offline."
        return {"answer": warning, "sources": [], "warnings": [warning], "matched": True}
    labels = []
    for row in offline[:5]:
        labels.append(str(row.get("tag") or row.get("dispositivo_id") or row.get("alarm_message") or row.get("title")))
    answer = f"Situação atual: encontrei {len(offline)} evidência(s) de offline/comunicação. Prioridade: {', '.join(labels)}. Recomendação: verificar comunicação, sinal, alimentação e conexão antes de tratar como falha do equipamento."
    return {"answer": answer, "sources": sources, "warnings": [], "matched": True}


def _critical_alerts(context: dict[str, Any]) -> dict[str, Any]:
    insights = [
        row
        for row in context["insights"]
        if str(row.get("severity") or "").casefold() in {"critical", "critico", "crítico", "warning"}
    ]
    anomalies = [
        row
        for row in context["anomalies"]
        if str(row.get("severity") or "").casefold() in {"critical", "critico", "crítico", "warning"}
    ]
    alarms = [row for row in context["alarms"] if classify_alarm_severity(row) in {"critical", "warning"}][:20]
    device_counter = Counter(
        str(row.get("tag") or row.get("dispositivo_id") or "equipamento sem identificacao")
        for row in anomalies + insights + alarms
    )
    sources = [
        *[_source("anomaly", row, "Anomalia prioritaria") for row in anomalies[:6]],
        *[_source("insight", row, "Insight prioritario") for row in insights[:6]],
        *[_source("alarm", row, "Alarme recente") for row in alarms[:4]],
    ]
    if not sources:
        warning = "Nao ha alerta critico ou equipamento problematico identificado no recorte carregado."
        return {"answer": warning, "sources": [], "warnings": [warning], "matched": True}
    top_devices = ", ".join(name for name, _ in device_counter.most_common(5))
    answer = f"Prioridade operacional: os equipamentos que exigem atenção no recorte atual são {top_devices}. A evidência vem de alarmes, anomalias ou insights; confirme leitura local e condição do equipamento antes de acionar manutenção."
    return {"answer": answer, "sources": sources, "warnings": [], "matched": True}


def _historical_trend(context: dict[str, Any]) -> dict[str, Any]:
    telemetry = context["ranked_telemetry"] or context["telemetry"][:80]
    if not telemetry:
        warning = "Não há telemetria suficiente no recorte carregado para avaliar variação histórica."
        return {"answer": warning, "sources": [], "warnings": [warning], "matched": True}

    grouped: dict[str, list[float]] = {}
    latest_rows: dict[str, dict[str, Any]] = {}
    for row in telemetry:
        value = row.get("temperature")
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        key = str(row.get("tag") or row.get("dispositivo_id") or "sem identificacao")
        grouped.setdefault(key, []).append(numeric)
        latest_rows[key] = row

    variations = sorted(
        ((max(values) - min(values), key, values) for key, values in grouped.items() if len(values) >= 2),
        reverse=True,
    )
    if not variations:
        warning = "Há telemetria, mas não há pontos suficientes por sensor para calcular variação confiável."
        return {"answer": warning, "sources": [_source("telemetry", row, "Telemetria recente") for row in telemetry[:5]], "warnings": [warning], "matched": True}

    top = variations[:5]
    labels = [f"{key}: variacao {delta:.1f} C" for delta, key, _ in top]
    sources = [_source("telemetry", latest_rows[key], "Telemetria usada na variacao") for _, key, _ in top]
    return {"answer": f"Variação recente: maiores oscilações no recorte carregado: {', '.join(labels)}. Recomendo validar sensores com variação alta antes de concluir falha.", "sources": sources, "warnings": [], "matched": True}


def _top_critical_stores(context: dict[str, Any]) -> dict[str, Any]:
    overview = context["overview"]
    stores = overview.get("top_critical_stores") or overview.get("most_critical_stores") or []
    if not stores:
        warning = "Não há ranking de lojas críticas no recorte atual."
        return {"answer": warning, "sources": [], "warnings": [warning], "matched": True}
    labels = [f"{item.get('loja_nome') or item.get('loja_id')} ({item.get('alarm_count', 0)} alarmes)" for item in stores[:5]]
    sources = [_source("store_metric", row, "Ranking de loja critica") for row in stores[:5]]
    return {"answer": f"Lojas mais críticas no recorte: {', '.join(labels)}. Recomendo priorizar lojas com maior recorrência antes de tratar casos isolados.", "sources": sources, "warnings": [], "matched": True}


def _top_critical_devices(context: dict[str, Any]) -> dict[str, Any]:
    overview = context["overview"]
    devices = overview.get("top_critical_devices") or overview.get("most_problematic_devices") or []
    anomaly_devices = [
        row for row in context["anomalies"]
        if str(row.get("severity") or "").casefold() in {"critical", "critico", "crítico", "warning"}
    ]
    if not devices and not anomaly_devices:
        warning = "Não encontrei equipamento com prioridade clara no recorte atual."
        return {"answer": warning, "sources": [], "warnings": [warning], "matched": True}
    labels = []
    for item in anomaly_devices[:3]:
        labels.append(str(item.get("tag") or item.get("dispositivo_id") or item.get("title") or "equipamento sem tag"))
    for item in devices[:5]:
        label = f"{item.get('tag') or item.get('dispositivo_id')} ({item.get('alarm_count', 0)} alarmes)"
        if label not in labels:
            labels.append(label)
    sources = [
        *[_source("anomaly", row, "Anomalia de equipamento prioritaria") for row in anomaly_devices[:4]],
        *[_source("device_metric", row, "Ranking de equipamento critico") for row in devices[:5]],
    ]
    return {
        "answer": (
            f"Equipamento com maior atenção no momento: {labels[0]}. Outros itens relevantes: {', '.join(labels[1:5]) or 'sem segundo item claro'}. "
            "A recomendação é validar alarme, condição local e histórico antes de acionar manutenção."
        ),
        "sources": sources,
        "warnings": [],
        "matched": True,
    }


def _temperature_risk(context: dict[str, Any]) -> dict[str, Any]:
    rows = context["anomalies"] + context["insights"] + context["alarms"]
    temperature_rows = [
        row
        for row in rows
        if any(term in _row_text(row) for term in ("temperatura", "temperature", "congel", "resfriad", "camara", "câmara"))
    ]
    critical_rows = [
        row
        for row in temperature_rows
        if str(row.get("severity") or classify_alarm_severity(row) or "").casefold() in {"critical", "critico", "crítico", "warning"}
    ]
    telemetry = [
        row
        for row in context["telemetry"][:120]
        if row.get("temperature") not in (None, "")
    ]
    sources = [
        *[_source("anomaly", row, "Ocorrência de temperatura") for row in critical_rows[:4] if row in context["anomalies"]],
        *[_source("insight", row, "Insight de temperatura") for row in critical_rows[:4] if row in context["insights"]],
        *[_source("alarm", row, "Alarme de temperatura") for row in critical_rows[:5] if row in context["alarms"]],
        *[_source("telemetry", row, "Telemetria de temperatura") for row in telemetry[:3]],
    ]
    if not critical_rows and not telemetry:
        warning = "Não encontrei leitura ou alarme de temperatura suficiente no recorte carregado para avaliar risco de perda."
        return {"answer": warning, "sources": [], "warnings": [warning], "matched": True}

    labels = list(dict.fromkeys(
        str(
            " - ".join(
                item for item in [
                    str(row.get("loja_nome") or row.get("loja_id") or "").strip(),
                    str(row.get("tag") or row.get("title") or row.get("alarm_message") or row.get("dispositivo_id") or "").strip(),
                ]
                if item
            )
            or row.get("title")
            or row.get("alarm_message")
            or row.get("dispositivo_id")
            or "item sem identificação"
        )
        for row in critical_rows[:8]
    ))
    answer = (
        f"Risco por temperatura: encontrei {len(critical_rows)} ocorrência(s) prioritária(s) ligada(s) a temperatura "
        f"e {len(telemetry)} leitura(s) recentes com valor térmico no recorte. "
    )
    if labels:
        answer += f"Os principais pontos para validar são {', '.join(labels[:4])}. "
    answer += (
        "Priorize equipamentos críticos de congelados/resfriados, confirme leitura local, porta, carga térmica, sensor e condição de refrigeração antes de concluir perda ou defeito."
    )
    return {
        "answer": answer,
        "sources": sources,
        "warnings": [],
        "matched": True,
        "key_findings": [
            f"{len(critical_rows)} ocorrência(s) prioritária(s) de temperatura no recorte.",
            f"{len(telemetry)} leitura(s) de telemetria térmica disponíveis para conferência.",
            f"Pontos de atenção: {', '.join(labels[:3]) if labels else 'sem ranking claro por loja/equipamento'}.",
        ],
        "recommended_actions": [
            "Validar leitura local dos equipamentos de maior criticidade.",
            "Conferir porta, carga térmica, vedação, sensor e controlador.",
            "Acionar manutenção apenas após confirmar condição persistente ou recorrente.",
        ],
    }


def _build_local_response(context: dict[str, Any]) -> dict[str, Any]:
    intent = context["intent"]
    if intent == "operation_summary":
        return _enrich_local_response(_operation_summary(context))
    if intent == "status_store":
        return _enrich_local_response(_status_store(context))
    if intent in {"status_sensor", "status_equipment", "status_device", "temperature_query"}:
        return _enrich_local_response(_status_device(context))
    if intent in {"historical_trend", "trend_analysis"}:
        return _enrich_local_response(_historical_trend(context))
    if intent == "recent_anomalies":
        return _enrich_local_response(_recent_anomalies(context))
    if intent == "offline_devices":
        return _enrich_local_response(_offline_devices(context))
    if intent == "critical_alerts":
        return _enrich_local_response(_critical_alerts(context))
    if intent == "top_critical_stores":
        return _enrich_local_response(_top_critical_stores(context))
    if intent == "top_critical_devices":
        return _enrich_local_response(_top_critical_devices(context))
    if intent == "temperature_risk":
        return _enrich_local_response(_temperature_risk(context))
    ranked = context["ranked_insights"] or context["ranked_alarms"] or context["ranked_devices"]
    if ranked:
        return _enrich_local_response({
            "answer": "Encontrei dados relacionados, mas a pergunta esta ambigua. Informe loja, dispositivo ou tag para uma resposta operacional mais precisa.",
            "sources": [_source("related", row, "Dado relacionado") for row in ranked[:5]],
            "warnings": ["Pergunta ambigua; confirme a loja, sensor ou equipamento."],
            "matched": False,
        })
    return _enrich_local_response({
        "answer": "Não encontrei dados suficientes para confirmar isso com segurança. Informe loja, equipamento, tag ou período para uma consulta mais precisa.",
        "sources": [],
        "warnings": ["Sem correspondencia operacional confiavel."],
        "matched": False,
    })


def _context_for_ai(context: dict[str, Any], local: dict[str, Any]) -> dict[str, Any]:
    return {
        "question": context["question"],
        "intent": context["intent"],
        "intent_label": INTENT_LABELS.get(context["intent"], "Pergunta operacional"),
        "entities": context["entities"],
        "local_answer": local["answer"],
        "summary": local.get("summary"),
        "key_findings": local.get("key_findings", []),
        "recommended_actions": local.get("recommended_actions", []),
        "warnings": local["warnings"],
        "sources": local["sources"],
        "matched_store": context["matched_store"],
        "matched_device": context["matched_device"],
        "overview_totals": context["overview"].get("totals"),
        "collector_runs": context["collector_runs"][:3],
        "relevant_anomalies": context["ranked_anomalies"][:8] or context["anomalies"][:8],
        "relevant_alarms": context["ranked_alarms"][:8],
        "relevant_telemetry": context["ranked_telemetry"][:8],
        "relevant_insights": context["ranked_insights"][:8],
        "knowledge_rules": context["knowledge_rules"],
        "operational_rules": context["operational_rules"][:8],
        "scope": context.get("scope"),
    }


def _synthesize_with_openai(context: dict[str, Any], local: dict[str, Any]) -> tuple[str, list[str], bool, str | None, str | None]:
    if context["intent"] in FAST_LOCAL_INTENTS:
        return local["answer"], [], False, None, None

    if not settings.openai_enabled:
        return (
            local["answer"],
            [],
            False,
            None,
            "Resposta gerada por regras locais porque o serviço de IA externa não está disponível.",
        )

    payload = {
        "model": settings.openai_model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(_context_for_ai(context, local), ensure_ascii=False, default=str),
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
        answer = str(parsed.get("answer") or local["answer"])
        bullets = parsed.get("bullet_points") if isinstance(parsed.get("bullet_points"), list) else []
        return answer, [str(item) for item in bullets[:6]], True, settings.openai_model, None
    except Exception as exc:
        logger.warning("Falha na IA consultiva; usando fallback local: %s", exc)
        return (
            local["answer"],
            [],
            False,
            None,
            "Resposta gerada por regras locais porque o serviço de IA externa não está disponível.",
        )


def answer_operational_question(question: str, origin: str = "panel", scope: TenantScope | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    intent = detect_intent(question)
    error: str | None = None
    used_ai = False
    confidence = 0.0
    source_count = 0
    try:
        context = retrieve_operational_context(question, intent, scope)
        local = _build_local_response(context)
        if context.get("retrieval_warnings"):
            local["warnings"] = list(dict.fromkeys([*local.get("warnings", []), *context["retrieval_warnings"]]))
        answer, bullet_points, used_ai, model, ai_warning = _synthesize_with_openai(context, local)
        sources = _dedupe_sources(local["sources"])
        warnings = list(dict.fromkeys([*local["warnings"], *([ai_warning] if ai_warning else [])]))
        confidence = _confidence(sources, warnings, bool(local["matched"]))
        confidence_label, confidence_reason = _confidence_details(confidence, sources, warnings, bool(local["matched"]))
        source_count = len(sources)
        response = {
            "answer": answer,
            "intent": intent if intent in INTENTS else "unknown_question",
            "intent_label": INTENT_LABELS.get(intent, "Pergunta operacional"),
            "confidence": confidence,
            "confidence_label": confidence_label,
            "confidence_reason": confidence_reason,
            "summary": local.get("summary") or answer,
            "key_findings": local.get("key_findings", []),
            "recommended_actions": local.get("recommended_actions", []),
            "sources": sources,
            "warnings": warnings,
            "used_ai": used_ai,
            "used_openai": used_ai,
            "model": model,
            "question": question,
            "bullet_points": bullet_points,
            "scope": context.get("scope"),
        }
        return response
    except Exception as exc:
        error = str(exc)
        logger.exception("assistant_query_failed")
        return {
            "answer": "Nao consegui consultar os dados operacionais agora. Tente novamente em alguns instantes.",
            "intent": intent,
            "intent_label": INTENT_LABELS.get(intent, "Pergunta operacional"),
            "confidence": 0.0,
            "confidence_label": "Baixa",
            "confidence_reason": "A consulta falhou antes de recuperar evidências operacionais.",
            "summary": "Nao consegui consultar os dados operacionais agora.",
            "key_findings": [],
            "recommended_actions": ["Verifique se o backend e o Supabase estão disponíveis e tente novamente."],
            "sources": [],
            "warnings": ["Falha ao consultar dados operacionais."],
            "used_ai": False,
            "used_openai": False,
            "model": None,
            "question": question,
            "bullet_points": [],
        }
    finally:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "assistant_usage %s",
            json.dumps(
                {
                    "question": question,
                    "origin": origin,
                    "intent": intent,
                    "confidence": confidence,
                    "used_ai": used_ai,
                    "elapsed_ms": elapsed_ms,
                    "sources_count": source_count,
                    "error": error,
                },
                ensure_ascii=False,
            ),
        )
