from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from api.auth import TenantScope
from api.database import SupabaseError, supabase
from api.logger import logger
from api.repositories import parse_utc_datetime, row_in_scope, utc_now_iso


PUBLIC_CODE_PREFIX = "OC"
PUBLIC_CODE_PATTERN = re.compile(r"^OC-(\d{8})-(\d{4,})$")
PUBLIC_CODE_INPUT_PATTERN = re.compile(r"^OC[-\s_]*(\d{8})[-\s_]*(\d{1,})$", re.IGNORECASE)


def normalize_public_code(value: Any) -> str | None:
    text = " ".join(str(value or "").strip().upper().split())
    match = PUBLIC_CODE_INPUT_PATTERN.fullmatch(text)
    if not match:
        return None
    date_part, sequence_part = match.groups()
    try:
        datetime.strptime(date_part, "%Y%m%d")
    except ValueError:
        return None
    return f"{PUBLIC_CODE_PREFIX}-{date_part}-{int(sequence_part):04d}"


def extract_public_code(value: Any) -> str | None:
    text = str(value or "").upper()
    match = re.search(r"\bOC[-\s_]*\d{8}[-\s_]*\d{1,}\b", text)
    return normalize_public_code(match.group(0)) if match else None


def _code_date(row: dict[str, Any]) -> str:
    parsed = (
        parse_utc_datetime(row.get("detected_at"))
        or parse_utc_datetime(row.get("created_at"))
        or datetime.now(timezone.utc)
    )
    return parsed.astimezone().strftime("%Y%m%d")


def _rpc_code(result: Any) -> str | None:
    if isinstance(result, str):
        return normalize_public_code(result)
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, str):
            return normalize_public_code(first)
        if isinstance(first, dict):
            for value in first.values():
                code = normalize_public_code(value)
                if code:
                    return code
    if isinstance(result, dict):
        for value in result.values():
            code = normalize_public_code(value)
            if code:
                return code
    return None


def _fallback_public_code(anomaly_id: str, row: dict[str, Any]) -> str:
    date_part = _code_date(row)
    prefix = f"{PUBLIC_CODE_PREFIX}-{date_part}-"
    for _attempt in range(30):
        existing = supabase.select(
            "eletrofrio_anomalies",
            {
                "select": "public_code",
                "public_code": f"like.{prefix}%",
                "order": "public_code.desc",
                "limit": 1,
            },
        )
        sequence = 1
        if existing:
            current = normalize_public_code(existing[0].get("public_code"))
            if current:
                sequence = int(current.rsplit("-", 1)[1]) + 1
        candidate = f"{prefix}{sequence:04d}"
        try:
            updated = supabase.patch(
                "eletrofrio_anomalies",
                {"id": anomaly_id},
                {"public_code": candidate, "public_code_created_at": utc_now_iso()},
            )
            if updated:
                return candidate
        except SupabaseError as exc:
            if "duplicate" in str(exc).casefold() or "23505" in str(exc):
                continue
            raise
    raise RuntimeError("Não foi possível gerar código público único para a ocorrência.")


def ensure_anomaly_public_code(anomaly_id: str, row: dict[str, Any] | None = None) -> str:
    current_row = row
    if current_row is None or str(current_row.get("id") or "") != str(anomaly_id):
        rows = supabase.select(
            "eletrofrio_anomalies",
            {"select": "*", "id": f"eq.{anomaly_id}", "limit": 1},
        )
        current_row = rows[0] if rows else None
    if not current_row:
        raise KeyError("Anomalia não encontrada.")

    current_code = normalize_public_code(current_row.get("public_code"))
    if current_code:
        return current_code

    try:
        result = supabase.rpc("ensure_eletrofrio_anomaly_public_code", {"p_anomaly_id": anomaly_id})
        generated = _rpc_code(result)
        if generated:
            return generated
    except SupabaseError as exc:
        logger.warning("RPC de código público indisponível; tentando fallback seguro: %s", exc)

    return _fallback_public_code(anomaly_id, current_row)


def ensure_public_code_on_row(row: dict[str, Any]) -> dict[str, Any]:
    code = normalize_public_code(row.get("public_code"))
    if code:
        return {**row, "public_code": code}
    anomaly_id = str(row.get("id") or "").strip()
    if not anomaly_id:
        raise ValueError("Anomalia sem ID não pode receber código público.")
    return {
        **row,
        "public_code": ensure_anomaly_public_code(anomaly_id, row),
        "public_code_created_at": row.get("public_code_created_at") or utc_now_iso(),
    }


def find_anomaly_by_public_code(public_code: str, scope: TenantScope | None = None) -> dict[str, Any] | None:
    normalized = normalize_public_code(public_code)
    if not normalized:
        return None
    rows = supabase.select(
        "eletrofrio_anomalies",
        {"select": "*", "public_code": f"eq.{normalized}", "limit": 1},
    )
    if not rows:
        return None
    row = rows[0]
    if scope is not None and not row_in_scope(row, scope):
        return None
    return {**row, "public_code": normalized}
