from __future__ import annotations

from typing import Any

DEFAULT_PORTAL_URL = "https://eletrofrio.147.15.56.49.nip.io/"


def _clean(value: Any, fallback: str = "-") -> str:
    text = " ".join(str(value or "").split())
    return text or fallback


def _format_value(value: Any) -> str:
    if value in (None, ""):
        return "-"
    try:
        return f"{float(value):.1f}°C"
    except (TypeError, ValueError):
        return _clean(value)


def _expected_range_label(value: Any) -> str:
    if isinstance(value, dict):
        min_value = value.get("min")
        max_value = value.get("max")
        if min_value is not None and max_value is not None:
            return f"{_format_value(min_value)} a {_format_value(max_value)}"
        if min_value is not None:
            return f"acima de {_format_value(min_value)}"
        if max_value is not None:
            return f"até {_format_value(max_value)}"
    return "faixa operacional esperada"


def priority_label(severity: Any) -> str:
    value = str(severity or "").casefold()
    if value in {"critical", "critico", "crítico", "high"}:
        return "Crítica"
    if value in {"warning", "medium"}:
        return "Atenção"
    return "Informativa"


def priority_heading(severity: Any) -> str:
    value = str(severity or "").casefold()
    if value in {"critical", "critico", "crítico", "high"}:
        return "🚨 *Ocorrência crítica*"
    if value in {"warning", "medium"}:
        return "⚠️ *Ocorrência em atenção*"
    return "ℹ️ *Ocorrência informativa*"


def priority_emoji(severity: Any) -> str:
    value = str(severity or "").casefold()
    if value in {"critical", "critico", "crítico", "high"}:
        return "🚨"
    if value in {"warning", "medium"}:
        return "⚠️"
    return "ℹ️"


def portal_footer(panel_url: str = "") -> str:
    url = (panel_url or DEFAULT_PORTAL_URL).strip() or DEFAULT_PORTAL_URL
    if "eletrofrio.147.15.56.49.nip.io" not in url:
        url = DEFAULT_PORTAL_URL
    url = f"{url.rstrip('/')}/"
    return f"🔎 *Acesse o portal para acompanhar:*\n{url}"


def problem_label(item: dict[str, Any]) -> str:
    text = _clean(item.get("message") or item.get("summary") or item.get("title"), "")
    lowered = text.casefold()
    item_type = str(item.get("type") or item.get("insight_type") or "").casefold()
    if "compressor" in lowered:
        return "Falha térmica ou alarme de compressor."
    if "offline" in lowered or "comunica" in lowered:
        return "Comunicação ou equipamento offline recorrente."
    if "baixa" in lowered and "temperatura" in lowered:
        return "Baixa temperatura fora da faixa operacional."
    if "alta" in lowered and "temperatura" in lowered:
        return "Alta temperatura fora da faixa operacional."
    if item_type == "temperature_high":
        return "Temperatura acima da faixa operacional."
    if item_type == "temperature_low":
        return "Temperatura abaixo da faixa operacional."
    return text or "Ocorrência operacional relevante."


def customer_label(item: dict[str, Any]) -> str:
    return _clean(item.get("customer_name"), "")


def customer_names(items: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in items:
        name = customer_label(item)
        key = name.casefold()
        if name and key not in seen:
            names.append(name)
            seen.add(key)
    return names


def customer_context_line(items: list[dict[str, Any]]) -> str:
    names = customer_names(items)
    if not names:
        return ""
    if len(names) == 1:
        return f"👤 *Cliente:* {names[0]}"
    return f"👤 *Clientes:* {', '.join(names[:5])}"


def ensure_customer_context(message: str, items: list[dict[str, Any]]) -> str:
    names = customer_names(items)
    if not names:
        return message
    lowered = str(message or "").casefold()
    if all(name.casefold() in lowered for name in names):
        return message
    return f"{customer_context_line(items)}\n\n{message}".strip()


def item_title(item: dict[str, Any]) -> str:
    store = item.get("loja_nome") or (f"Loja {item.get('loja_id')}" if item.get("loja_id") else "Loja não identificada")
    tag = item.get("tag") or (f"Dispositivo {item.get('dispositivo_id') or item.get('equipment_id')}" if item.get("dispositivo_id") or item.get("equipment_id") else "equipamento monitorado")
    parts = [customer_label(item), store, tag]
    return " — ".join(part for part in parts if part)


def store_label(item: dict[str, Any]) -> str:
    return _clean(item.get("loja_nome") or (f"Loja {item.get('loja_id')}" if item.get("loja_id") else None))


def equipment_label(item: dict[str, Any]) -> str:
    device_id = item.get("dispositivo_id") or item.get("equipment_id")
    return _clean(item.get("tag") or (f"Dispositivo {device_id}" if device_id else None))


def build_single_message(item: dict[str, Any], panel_url: str = "") -> str:
    public_code = _clean(item.get("public_code"), "")
    if not public_code:
        raise ValueError("Ocorrência sem código público não pode ser enviada por WhatsApp.")
    action = item.get("recommended_action") or "Validar sensor, porta, carga térmica e condição do sistema de refrigeração."
    technical_reason = _clean(item.get("technical_reason"), "")
    identity_lines = []
    customer = customer_label(item)
    if customer:
        identity_lines.append(f"👤 *Cliente:* {customer}")
    identity_lines.extend(
        [
            f"🏬 *Loja:* {store_label(item)}",
            f"🧊 *Equipamento:* {equipment_label(item)}",
        ]
    )
    lines = [
        "*Eletrofrio Refrigeração*",
        priority_heading(item.get("severity")),
        "",
        *identity_lines,
        f"🆔 *Código:* {public_code}",
        "",
        "📌 *Erro detectado*",
        problem_label(item),
        "" if technical_reason else None,
        "🔍 *Evidência técnica*" if technical_reason else None,
        technical_reason or None,
        "",
        "🌡️ *Leitura*",
        f"Atual: {_format_value(item.get('value'))}",
        f"Esperado: {_expected_range_label(item.get('expected_range'))}",
        "",
        "✅ *Solução recomendada*",
        _clean(action),
        "",
        "_Diagnóstico inicial. Confirme a condição no local antes de acionar manutenção._",
        f"_Use o código {public_code} no painel para ver detalhes e possível solução._",
        "",
        portal_footer(panel_url),
    ]
    return "\n".join(line for line in lines if line is not None)


def build_group_message(items: list[dict[str, Any]], panel_url: str = "") -> str:
    selected = items[:5]
    lines = [
        "*Eletrofrio Refrigeração*",
        "📋 *Resumo operacional*",
        "",
        f"Foram encontradas *{len(items)} ocorrência(s) relevante(s)* que passaram pelos filtros de prioridade.",
        "",
        "✨ *Principais pontos*",
        "",
    ]
    for index, item in enumerate(selected, 1):
        lines.extend(
            [
                f"{index}. {priority_emoji(item.get('severity'))} *{item_title(item)}*",
                f"   • {problem_label(item)}",
                f"   • Prioridade: *{priority_label(item.get('severity'))}*",
                "",
            ]
        )
    lines.extend(
        [
            "✅ *Próximo passo:* confira o painel antes de acionar manutenção ou visita técnica.",
            "",
            portal_footer(panel_url),
        ]
    )
    return "\n".join(lines).strip()


def preview(message: str, limit: int = 220) -> str:
    text = " ".join(message.split())
    return text if len(text) <= limit else f"{text[: limit - 3].rstrip()}..."
