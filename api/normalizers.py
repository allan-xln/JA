from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any


def ensure_list(payload: Any) -> list[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "dados", "items", "results", "result", "registros", "unidades", "alarmes", "telemetria"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return [payload]
    return []


def first_value(payload: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    lower_map = {str(k).lower(): v for k, v in payload.items()}
    for key in keys:
        value = lower_map.get(key.lower())
        if value not in (None, ""):
            return value
    return default


def to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def parse_datetime(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()

    text = str(value).strip()
    candidates = [
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y",
    ]
    clean = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(clean)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        pass

    for fmt in candidates:
        try:
            parsed = datetime.strptime(text, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def stable_hash(payload: dict[str, Any], preferred: list[Any]) -> str:
    parts = [str(item) for item in preferred if item not in (None, "")]
    if not parts:
        parts = [json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def normalize_unit(raw: dict[str, Any]) -> dict[str, Any]:
    loja_id = to_int(first_value(raw, ("loja_id", "lojaId", "idLoja", "id", "codigo", "codigoLoja")))
    loja_nome = first_value(raw, ("loja_nome", "lojaNome", "lojaNm", "nomeLoja", "nome", "fantasia", "descricao"))
    return {
        "loja_id": loja_id,
        "loja_nome": str(loja_nome).strip() if loja_nome is not None else None,
        "raw_payload": raw,
    }


def normalize_device(raw: dict[str, Any], fallback_loja_id: int | None = None, fallback_loja_nome: str | None = None) -> dict[str, Any] | None:
    source = raw.get("raw_payload") if isinstance(raw.get("raw_payload"), dict) else raw
    dispositivo_id = to_int(first_value(source, ("dispositivo_id", "dispositivoId", "idDispositivo", "device_id", "id")))
    if dispositivo_id is None:
        return None
    loja_id = to_int(first_value(source, ("loja_id", "lojaId", "idLoja"), fallback_loja_id))
    tag = first_value(source, ("tag", "dispositivoNm", "nomeDispositivo", "dispositivoNome", "equipamento", "descricao", "asset", "ponto"))
    return {
        "loja_id": loja_id,
        "dispositivo_id": dispositivo_id,
        "tag": str(tag).strip() if tag is not None else None,
        "raw_payload": {**source, "_fallback_loja_nome": fallback_loja_nome},
    }


def normalize_alarm(raw: dict[str, Any]) -> dict[str, Any]:
    loja_id = to_int(first_value(raw, ("loja_id", "lojaId", "idLoja")))
    loja_nome = first_value(raw, ("loja_nome", "lojaNome", "lojaNm", "nomeLoja", "loja"))
    dispositivo_id = to_int(first_value(raw, ("dispositivo_id", "dispositivoId", "idDispositivo", "device_id")))
    tag = first_value(raw, ("tag", "dispositivoNm", "nomeDispositivo", "dispositivoNome", "equipamento", "descricaoEquipamento"))
    alarm_type = first_value(raw, ("alarm_type", "tipoAlarme", "tipo", "alarmeTipo", "categoria", "criticidade", "grupoNm", "subgrupoNm"))
    alarm_message = first_value(raw, ("alarm_message", "alarmeDesc", "mensagem", "descricao", "alarme", "motivo", "texto", "eventoDesc"))
    started_at = parse_datetime(first_value(raw, ("started_at", "alarmeDhCad", "inicio", "dataInicio", "data_inicial", "data", "created_at")))
    ended_at = parse_datetime(first_value(raw, ("ended_at", "eventoDhCad", "fim", "dataFim", "data_final", "normalizadoEm")))
    alarme_id = first_value(raw, ("alarmeId", "alarm_id", "idAlarme"))
    external_hash = stable_hash(raw, [alarme_id, loja_id, dispositivo_id, tag, alarm_type, alarm_message, started_at, ended_at])
    return {
        "external_hash": external_hash,
        "loja_id": loja_id,
        "loja_nome": str(loja_nome).strip() if loja_nome is not None else None,
        "dispositivo_id": dispositivo_id,
        "tag": str(tag).strip() if tag is not None else None,
        "alarm_type": str(alarm_type).strip() if alarm_type is not None else None,
        "alarm_message": str(alarm_message).strip() if alarm_message is not None else None,
        "started_at": started_at,
        "ended_at": ended_at,
        "raw_payload": raw,
    }


def normalize_telemetry(raw: dict[str, Any], dispositivo_id: int | None = None) -> dict[str, Any]:
    device_id = to_int(first_value(raw, ("dispositivo_id", "dispositivoId", "idDispositivo", "device_id"), dispositivo_id))
    loja_id = to_int(first_value(raw, ("loja_id", "lojaId", "idLoja")))
    tag = first_value(raw, ("tag", "nomeDispositivo", "dispositivoNome", "equipamento"))
    measured_at = parse_datetime(first_value(raw, ("measured_at", "dataHora", "data", "timestamp", "ts", "created_at", "momento")))
    temperature = to_float(first_value(raw, ("temperature", "temperatura", "temperature_c", "valor", "valorTemperatura")))
    external_hash = stable_hash(raw, [loja_id, device_id, tag, measured_at, temperature])
    return {
        "external_hash": external_hash,
        "loja_id": loja_id,
        "dispositivo_id": device_id,
        "tag": str(tag).strip() if tag is not None else None,
        "measured_at": measured_at,
        "temperature": temperature,
        "raw_payload": raw,
    }


def label_to_datetime(label: Any, index: int, total: int) -> str:
    parsed = parse_datetime(label)
    if parsed:
        return parsed

    now = datetime.now(timezone.utc)
    text = str(label or "").strip()
    try:
        hour, minute = [int(part) for part in text.split(":", 1)]
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now + timedelta(minutes=5):
            candidate -= timedelta(days=1)
        return candidate.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        measured = now - timedelta(minutes=max(0, total - index - 1) * 5)
        return measured.astimezone(timezone.utc).isoformat()


def normalize_telemetry_payload(
    payload: Any,
    dispositivo_id: int,
    loja_id: int | None = None,
    tag: str | None = None,
) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [normalize_telemetry(item, dispositivo_id) for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    datasets = payload.get("datasets")
    labels = payload.get("labels") if isinstance(payload.get("labels"), list) else []
    if not isinstance(datasets, list):
        return [normalize_telemetry(payload, dispositivo_id)]

    rows: list[dict[str, Any]] = []
    for dataset in datasets:
        if not isinstance(dataset, dict):
            continue
        label = str(dataset.get("label") or "").strip()
        values = dataset.get("values")
        if not isinstance(values, list):
            continue

        is_temperature = "temperatura" in label.lower() or "temperature" in label.lower()
        if not is_temperature:
            continue

        for index, value in enumerate(values):
            temperature = to_float(value)
            if temperature is None:
                continue
            measured_at = label_to_datetime(labels[index] if index < len(labels) else None, index, len(values))
            raw_row = {
                "dispositivo_id": dispositivo_id,
                "loja_id": loja_id,
                "tag": tag,
                "measured_at": measured_at,
                "temperature": temperature,
                "dataset_label": label,
                "label": labels[index] if index < len(labels) else None,
                "value": value,
            }
            rows.append(
                {
                    "external_hash": stable_hash(raw_row, [dispositivo_id, label, measured_at, temperature]),
                    "loja_id": loja_id,
                    "dispositivo_id": dispositivo_id,
                    "tag": tag,
                    "measured_at": measured_at,
                    "temperature": temperature,
                    "raw_payload": raw_row,
                }
            )

    return rows
