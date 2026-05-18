from __future__ import annotations

import time
from typing import Any

from api.database import SupabaseError, supabase
from api.logger import logger
from api.repositories import utc_now_iso
from api.rules.operational_rules import normalize_rule
from api.rules.rule_defaults import DEFAULT_OPERATIONAL_RULES


RULE_SCHEMA_MESSAGE = "Schema de regras operacionais ainda não aplicado. Execute sql/003_operational_rules.sql no Supabase."
_warned = False
_enabled_rules_cache: tuple[float, list[dict[str, Any]]] | None = None


def _schema_unavailable(exc: Exception) -> dict[str, Any]:
    global _warned
    if not _warned:
        logger.warning("%s Erro original: %s", RULE_SCHEMA_MESSAGE, exc)
        _warned = True
    return {"schema_applied": False, "message": RULE_SCHEMA_MESSAGE}


def default_rules_preview() -> list[dict[str, Any]]:
    return [normalize_rule({**rule, "id": rule["name"]}) for rule in DEFAULT_OPERATIONAL_RULES]


def list_rules(include_disabled: bool = True) -> dict[str, Any]:
    params: dict[str, Any] = {"select": "*", "order": "priority.asc,name.asc"}
    if not include_disabled:
        params["enabled"] = "eq.true"
    try:
        rows = supabase.select("eletrofrio_operational_rules", params)
    except SupabaseError as exc:
        return {**_schema_unavailable(exc), "items": default_rules_preview(), "using_defaults": True}
    return {"schema_applied": True, "items": [normalize_rule(row) for row in rows], "using_defaults": False}


def get_enabled_rules() -> list[dict[str, Any]]:
    global _enabled_rules_cache
    if _enabled_rules_cache and time.time() - _enabled_rules_cache[0] < 60:
        return _enabled_rules_cache[1]
    result = list_rules(include_disabled=False)
    items = result.get("items") or []
    if not result.get("schema_applied") or not items:
        items = default_rules_preview()
    _enabled_rules_cache = (time.time(), items)
    return items


def get_rule(rule_id: str) -> dict[str, Any] | None:
    try:
        rows = supabase.select("eletrofrio_operational_rules", {"select": "*", "id": f"eq.{rule_id}", "limit": 1})
    except SupabaseError as exc:
        raise RuntimeError(RULE_SCHEMA_MESSAGE) from exc
    return normalize_rule(rows[0]) if rows else None


def create_rule(payload: dict[str, Any]) -> dict[str, Any]:
    global _enabled_rules_cache
    clean = normalize_rule(payload)
    clean.pop("id", None)
    clean = {key: value for key, value in clean.items() if value is not None}
    clean["updated_at"] = utc_now_iso()
    try:
        rows = supabase.insert("eletrofrio_operational_rules", clean)
    except SupabaseError as exc:
        raise RuntimeError(RULE_SCHEMA_MESSAGE) from exc
    _enabled_rules_cache = None
    return normalize_rule(rows[0]) if rows else clean


def update_rule(rule_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    global _enabled_rules_cache
    clean = {key: value for key, value in payload.items() if value is not None}
    clean["updated_at"] = utc_now_iso()
    try:
        rows = supabase.patch("eletrofrio_operational_rules", {"id": rule_id}, clean)
    except SupabaseError as exc:
        raise RuntimeError(RULE_SCHEMA_MESSAGE) from exc
    if not rows:
        raise KeyError(rule_id)
    _enabled_rules_cache = None
    return normalize_rule(rows[0])


def toggle_rule(rule_id: str) -> dict[str, Any]:
    rule = get_rule(rule_id)
    if not rule:
        raise KeyError(rule_id)
    return update_rule(rule_id, {"enabled": not bool(rule.get("enabled"))})


def apply_default_rules() -> dict[str, Any]:
    global _enabled_rules_cache
    applied = 0
    skipped = 0
    try:
        existing = supabase.select("eletrofrio_operational_rules", {"select": "name"})
        existing_names = {row.get("name") for row in existing}
        for rule in DEFAULT_OPERATIONAL_RULES:
            if rule["name"] in existing_names:
                skipped += 1
                continue
            supabase.insert("eletrofrio_operational_rules", {**rule, "enabled": True, "updated_at": utc_now_iso()})
            applied += 1
    except SupabaseError as exc:
        return {**_schema_unavailable(exc), "applied": applied, "skipped": skipped}
    _enabled_rules_cache = None
    return {"schema_applied": True, "applied": applied, "skipped": skipped, "total": applied + skipped}


def insert_rule_evaluations(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"schema_applied": True, "inserted": 0}
    try:
        supabase.insert("eletrofrio_rule_evaluations", rows)
    except SupabaseError as exc:
        return {**_schema_unavailable(exc), "inserted": 0}
    return {"schema_applied": True, "inserted": len(rows)}


def list_rule_evaluations(limit: int = 100) -> dict[str, Any]:
    try:
        rows = supabase.select("eletrofrio_rule_evaluations", {"select": "*", "order": "evaluated_at.desc", "limit": limit})
    except SupabaseError as exc:
        return {**_schema_unavailable(exc), "items": []}
    return {"schema_applied": True, "items": rows}
