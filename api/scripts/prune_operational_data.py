from __future__ import annotations

import argparse
import json

from api.data_retention import prune_operational_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Prune old Eletrofrio operational rows using sql/009 retention policy.")
    parser.add_argument("--apply", action="store_true", help="Delete matching rows. Without this flag the command runs a dry-run.")
    parser.add_argument("--telemetry-days", type=int)
    parser.add_argument("--alarm-days", type=int)
    parser.add_argument("--insight-days", type=int)
    parser.add_argument("--communication-days", type=int)
    parser.add_argument("--collector-run-days", type=int)
    parser.add_argument("--resolved-anomaly-days", type=int)
    parser.add_argument("--batch-limit", type=int)
    args = parser.parse_args()

    result = prune_operational_data(
        dry_run=not args.apply,
        telemetry_days=args.telemetry_days,
        alarm_days=args.alarm_days,
        insight_days=args.insight_days,
        communication_days=args.communication_days,
        collector_run_days=args.collector_run_days,
        resolved_anomaly_days=args.resolved_anomaly_days,
        batch_limit=args.batch_limit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
