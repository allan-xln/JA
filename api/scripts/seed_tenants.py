from __future__ import annotations

import json
import re
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from api.auth import DATA_DIR, DEMO_USERS_FILE, hash_password
from api.database import SupabaseError, supabase
from api.repositories import list_devices, list_units


DEMO_TEXT_FILE = DATA_DIR / "demo_users_generated.txt"


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def slugify(value: Any, fallback: str) -> str:
    base = strip_accents(str(value or fallback).casefold())
    slug = re.sub(r"[^a-z0-9]+", "", base)
    return slug or fallback


def unit_customer_name(unit: dict[str, Any]) -> str:
    raw = unit.get("raw_payload") if isinstance(unit.get("raw_payload"), dict) else {}
    for key in ("contaNm", "conta_nome", "conta", "cliente", "cliente_nome", "empresa"):
        if raw.get(key):
            return str(raw[key]).strip()
    return str(unit.get("loja_nome") or f"Loja {unit.get('loja_id')}").strip()


def stable_id(kind: str, slug: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"eletrofrio:{kind}:{slug}"))


def safe_upsert(table: str, payload: dict[str, Any], on_conflict: str) -> dict[str, Any] | None:
    try:
        rows = supabase.upsert(table, payload, on_conflict)
        return rows[0] if rows else None
    except SupabaseError as exc:
        text = str(exc).lower()
        if "schema cache" in text or "pgrst205" in text or table in text:
            return None
        raise


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    units = list_units()
    devices = list_devices()

    customers_by_slug: dict[str, dict[str, Any]] = {}
    customer_units: list[dict[str, Any]] = []
    customer_devices: list[dict[str, Any]] = []

    for unit in units:
        loja_id = unit.get("loja_id")
        if loja_id is None:
            continue
        name = unit_customer_name(unit)
        slug = slugify(name, f"loja{loja_id}")
        customer = customers_by_slug.setdefault(
            slug,
            {
                "id": stable_id("customer", slug),
                "slug": slug,
                "name": name,
                "description": "Cliente gerado a partir dos dados operacionais da Eletrofrio.",
                "is_active": True,
            },
        )
        customer_units.append(
            {
                "id": stable_id("customer-unit", f"{slug}:{loja_id}"),
                "customer_id": customer["id"],
                "loja_id": int(loja_id),
                "loja_nome": unit.get("loja_nome"),
            }
        )

    for device in devices:
        loja_id = device.get("loja_id")
        dispositivo_id = device.get("dispositivo_id")
        if loja_id is None or dispositivo_id is None:
            continue
        owner = next((row for row in customer_units if row["loja_id"] == int(loja_id)), None)
        if not owner:
            continue
        customer_devices.append(
            {
                "id": stable_id("customer-device", f"{owner['customer_id']}:{dispositivo_id}"),
                "customer_id": owner["customer_id"],
                "dispositivo_id": int(dispositivo_id),
                "tag": device.get("tag"),
                "loja_id": int(loja_id),
            }
        )

    users: list[dict[str, Any]] = [
        {
            "id": stable_id("user", "admin"),
            "username": "admin",
            "password_hash": hash_password("admin"),
            "role": "admin",
            "customer_id": None,
            "is_active": True,
        }
    ]
    for customer in customers_by_slug.values():
        username = customer["slug"]
        users.append(
            {
                "id": stable_id("user", username),
                "username": username,
                "password_hash": hash_password(username),
                "role": "client",
                "customer_id": customer["id"],
                "customer_name": customer["name"],
                "is_active": True,
            }
        )

    db_seeded = True
    for customer in customers_by_slug.values():
        db_row = safe_upsert(
            "eletrofrio_customers",
            {key: customer[key] for key in ("slug", "name", "description", "is_active")},
            "slug",
        )
        if db_row and db_row.get("id"):
            old_id = customer["id"]
            customer["id"] = db_row["id"]
            for row in customer_units:
                if row["customer_id"] == old_id:
                    row["customer_id"] = customer["id"]
            for row in customer_devices:
                if row["customer_id"] == old_id:
                    row["customer_id"] = customer["id"]
            for user in users:
                if user.get("customer_id") == old_id:
                    user["customer_id"] = customer["id"]
        else:
            db_seeded = False

    for user in users:
        payload = {key: user.get(key) for key in ("username", "password_hash", "role", "customer_id", "is_active")}
        if safe_upsert("eletrofrio_users", payload, "username") is None:
            db_seeded = False
    for row in customer_units:
        if safe_upsert(
            "eletrofrio_customer_units",
            {key: row.get(key) for key in ("customer_id", "loja_id", "loja_nome")},
            "customer_id,loja_id",
        ) is None:
            db_seeded = False
    for row in customer_devices:
        if safe_upsert(
            "eletrofrio_customer_devices",
            {key: row.get(key) for key in ("customer_id", "dispositivo_id", "tag", "loja_id")},
            "customer_id,dispositivo_id",
        ) is None:
            db_seeded = False

    demo_store = {
        "users": users,
        "customers": list(customers_by_slug.values()),
        "customer_units": customer_units,
        "customer_devices": customer_devices,
        "db_seeded": db_seeded,
    }
    DEMO_USERS_FILE.write_text(json.dumps(demo_store, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["USUÁRIOS DE DEMO CRIADOS:", "admin / admin"]
    for customer in sorted(customers_by_slug.values(), key=lambda item: item["slug"]):
        lines.append(f"{customer['slug']} / {customer['slug']}")
    lines.append("")
    lines.append("Senha inicial de demonstração. Em produção, exigir troca de senha.")
    if not db_seeded:
        lines.append("Aviso: migration SQL ainda não aplicada; seed local salvo em data/demo_users_generated.json.")
    DEMO_TEXT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
