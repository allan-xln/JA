from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


def cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def delete_where(base_url: str, headers: dict[str, str], table: str, filters: dict[str, str], timeout: int) -> dict[str, Any]:
    started = time.perf_counter()
    response = requests.delete(
        f"{base_url}/{table}",
        headers=headers,
        params=filters,
        timeout=timeout,
    )
    elapsed = round(time.perf_counter() - started, 2)
    return {
        "table": table,
        "status": response.status_code,
        "elapsed_seconds": elapsed,
        "ok": response.status_code < 400,
        "body": response.text[:500],
        "filters": filters,
    }


def run_once(timeout: int) -> list[dict[str, Any]]:
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not service_key:
        raise RuntimeError("SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY ausentes.")

    base_url = f"{supabase_url}/rest/v1"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    operations = [
        ("eletrofrio_telemetry", {"measured_at": f"lt.{cutoff(30)}"}),
        ("eletrofrio_telemetry", {"created_at": f"lt.{cutoff(30)}", "measured_at": "is.null"}),
        ("eletrofrio_alarms", {"started_at": f"lt.{cutoff(120)}"}),
        ("eletrofrio_alarms", {"created_at": f"lt.{cutoff(120)}", "started_at": "is.null"}),
        ("eletrofrio_ai_insights", {"created_at": f"lt.{cutoff(180)}"}),
        ("eletrofrio_notification_events", {"created_at": f"lt.{cutoff(180)}"}),
        ("eletrofrio_communication_logs", {"created_at": f"lt.{cutoff(180)}"}),
        ("eletrofrio_rag_queries", {"created_at": f"lt.{cutoff(180)}"}),
        ("eletrofrio_whatsapp_messages", {"created_at": f"lt.{cutoff(180)}"}),
        ("eletrofrio_collector_runs", {"started_at": f"lt.{cutoff(90)}"}),
        ("eletrofrio_anomalies", {"status": "in.(resolved,ignored)", "updated_at": f"lt.{cutoff(365)}"}),
    ]
    return [delete_where(base_url, headers, table, filters, timeout) for table, filters in operations]


def main() -> None:
    parser = argparse.ArgumentParser(description="Conservative Supabase REST cleanup for Eletrofrio presentation.")
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--sleep", type=int, default=60)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    for attempt in range(1, max(args.retries, 1) + 1):
        print(json.dumps({"attempt": attempt, "event": "start"}, ensure_ascii=False), flush=True)
        try:
            results = run_once(args.timeout)
            print(json.dumps({"attempt": attempt, "results": results}, ensure_ascii=False), flush=True)
            if any(item["ok"] for item in results):
                print(json.dumps({"attempt": attempt, "event": "cleanup_attempted"}, ensure_ascii=False), flush=True)
                return
        except Exception as exc:
            print(json.dumps({"attempt": attempt, "error": str(exc)}, ensure_ascii=False), flush=True)
        if attempt < args.retries:
            time.sleep(max(args.sleep, 1))

    raise SystemExit(1)


if __name__ == "__main__":
    main()
