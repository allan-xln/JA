from __future__ import annotations

import json
from typing import Any

from api.anomaly_public_code import ensure_anomaly_public_code, normalize_public_code
from api.database import supabase


PAGE_SIZE = 1000


def load_anomalies() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = supabase.select(
            "eletrofrio_anomalies",
            {
                "select": "id,public_code,public_code_created_at,related_anomaly_id,related_public_code,detected_at,created_at",
                "order": "detected_at.asc",
                "limit": PAGE_SIZE,
                "offset": offset,
            },
        )
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def run_backfill() -> dict[str, Any]:
    rows = load_anomalies()
    summary: dict[str, Any] = {
        "analyzed": len(rows),
        "updated": 0,
        "already_had_code": 0,
        "relations_updated": 0,
        "errors": [],
    }
    code_by_id: dict[str, str] = {}

    for row in rows:
        anomaly_id = str(row.get("id") or "")
        existing = normalize_public_code(row.get("public_code"))
        if existing:
            summary["already_had_code"] += 1
            code_by_id[anomaly_id] = existing
            continue
        try:
            generated = ensure_anomaly_public_code(anomaly_id, row)
            code_by_id[anomaly_id] = generated
            summary["updated"] += 1
        except Exception as exc:
            summary["errors"].append({"id": anomaly_id, "error": str(exc)[:300]})

    for row in rows:
        anomaly_id = str(row.get("id") or "")
        related_id = str(row.get("related_anomaly_id") or "")
        related_code = code_by_id.get(related_id)
        if not related_code or normalize_public_code(row.get("related_public_code")) == related_code:
            continue
        try:
            supabase.patch(
                "eletrofrio_anomalies",
                {"id": anomaly_id},
                {"related_public_code": related_code},
            )
            summary["relations_updated"] += 1
        except Exception as exc:
            summary["errors"].append({"id": anomaly_id, "relation_error": str(exc)[:300]})

    summary["error_count"] = len(summary["errors"])
    return summary


if __name__ == "__main__":
    print(json.dumps(run_backfill(), ensure_ascii=False, indent=2))
