from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_loader import diagnose_taiwan_semiconductor_orders_archive
from global_semiconductor_demand import SEMICONDUCTOR_DATA_COLUMNS
from taiwan_export_orders_archive import (
    TAIWAN_ARCHIVE_MANIFEST_PATH,
    TAIWAN_ARCHIVE_SNAPSHOT_PATH,
    load_taiwan_archive_manifest,
    load_taiwan_archive_snapshot,
    taiwan_archive_missing_months,
    validate_taiwan_archive_snapshot,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="台湾外銷訂單archive snapshotを手動更新")
    parser.add_argument("--start", default="2022-08")
    parser.add_argument("--end", required=True)
    parser.add_argument("--period", action="append", default=[])
    parser.add_argument("--refresh", action="store_true", help="既存月も再取得して差分検知")
    parser.add_argument("--accept-changes", action="store_true", help="既存月の変更を明示承認")
    parser.add_argument("--snapshot", type=Path, default=TAIWAN_ARCHIVE_SNAPSHOT_PATH)
    parser.add_argument("--manifest", type=Path, default=TAIWAN_ARCHIVE_MANIFEST_PATH)
    parser.add_argument("--diagnose-early-2021", action="store_true")
    return parser.parse_args()


def _months(start: str, end: str) -> list[str]:
    return [str(period) for period in pd.period_range(start=start, end=end, freq="M")]


def _changes(old: pd.DataFrame, new: pd.DataFrame) -> list[dict[str, object]]:
    keys = ["reference_period", "series_id"]
    compare = ["release_date", "value", "yoy", "source_url"]
    joined = old.merge(new, on=keys, how="inner", suffixes=("_old", "_new"))
    reports: list[dict[str, object]] = []
    for _, row in joined.iterrows():
        changed = {
            field: {"old": str(row[f"{field}_old"]), "new": str(row[f"{field}_new"])}
            for field in compare
            if str(row[f"{field}_old"]) != str(row[f"{field}_new"])
        }
        if changed:
            reports.append(
                {
                    "reference_period": pd.Timestamp(row["reference_period"]).strftime("%Y-%m"),
                    "series_id": row["series_id"],
                    "changed": changed,
                }
            )
    return reports


def main() -> int:
    args = _arguments()
    requested = (
        [f"2021-{month:02d}" for month in range(1, 9)]
        if args.diagnose_early_2021
        else (args.period or _months(args.start, args.end))
    )
    existing = (
        load_taiwan_archive_snapshot(args.snapshot)
        if args.snapshot.exists()
        else pd.DataFrame(columns=SEMICONDUCTOR_DATA_COLUMNS)
    )
    existing_months = set(pd.to_datetime(existing["reference_period"]).dt.strftime("%Y-%m")) if not existing.empty else set()
    fetch_months = requested if args.refresh or args.diagnose_early_2021 else [month for month in requested if month not in existing_months]
    if not fetch_months:
        print(json.dumps({"status": "unchanged", "requested_months": requested}, ensure_ascii=False, indent=2))
        return 0

    fetched = diagnose_taiwan_semiconductor_orders_archive(tuple(fetch_months))
    loaded_months = set(pd.to_datetime(fetched["reference_period"]).dt.strftime("%Y-%m")) if not fetched.empty else set()
    missing = sorted(set(fetch_months) - loaded_months)
    report = {
        "requested_months": fetch_months,
        "loaded_months": sorted(loaded_months),
        "missing_months": missing,
        "failures": fetched.attrs.get("failed_months", []),
        "attachment_hashes": fetched.attrs.get("attachment_hashes", {}),
    }
    if args.diagnose_early_2021:
        print(json.dumps({"status": "diagnostic", **report}, ensure_ascii=False, indent=2, default=str))
        return 0 if not missing else 2
    if missing:
        print(json.dumps({"status": "incomplete", **report}, ensure_ascii=False, indent=2, default=str))
        return 2

    differences = _changes(existing, fetched) if not existing.empty else []
    old_manifest = load_taiwan_archive_manifest(args.manifest) if args.manifest.exists() else {}
    old_hashes = dict(old_manifest.get("attachment_hashes", {}))
    hash_changes = {
        month: {"old": old_hashes[month], "new": digest}
        for month, digest in fetched.attrs.get("attachment_hashes", {}).items()
        if month in old_hashes and old_hashes[month] != digest
    }
    if (differences or hash_changes) and not args.accept_changes:
        print(json.dumps({"status": "changes_require_confirmation", "row_changes": differences, "hash_changes": hash_changes}, ensure_ascii=False, indent=2, default=str))
        return 3

    replace = set(loaded_months)
    retained = existing[~pd.to_datetime(existing["reference_period"]).dt.strftime("%Y-%m").isin(replace)] if not existing.empty else existing
    result = pd.concat([retained, fetched], ignore_index=True)[list(SEMICONDUCTOR_DATA_COLUMNS)]
    validate_taiwan_archive_snapshot(result)
    result = result.sort_values(["reference_period", "series_id"])
    args.snapshot.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.snapshot, index=False, date_format="%Y-%m-%dT%H:%M:%S%z")
    hashes = {**old_hashes, **fetched.attrs.get("attachment_hashes", {})}
    periods = pd.to_datetime(result["reference_period"])
    snapshot_missing_months = taiwan_archive_missing_months(result)
    manifest = {
        "generated_at": pd.Timestamp.now(tz="Asia/Tokyo").isoformat(),
        "safe_start_month": periods.min().strftime("%Y-%m"),
        "latest_month": periods.max().strftime("%Y-%m"),
        "month_count": int(periods.dt.to_period("M").nunique()),
        "row_count": len(result),
        "missing_months": snapshot_missing_months,
        "source_archive_url": fetched.attrs.get("source_url"),
        "attachment_hashes": dict(sorted(hashes.items())),
    }
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "updated", **manifest, "row_changes": differences, "hash_changes": hash_changes}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
