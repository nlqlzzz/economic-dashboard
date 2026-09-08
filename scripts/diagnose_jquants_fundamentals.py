"""Run the Core20 J-Quants Financial Summary coverage diagnostic.

Set JQUANTS_API_KEY in the process environment (or execute inside Streamlit with
the same secret configured).  This command deliberately never prints the key.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from japan_equity import CORE_20
from jquants_loader import (
    JQuantsConfigurationError,
    assess_coverage,
    fetch_financial_summaries,
    normalize_financial_summaries,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose J-Quants Financial Summary coverage for Core20.")
    parser.add_argument("--codes", help="Comma-separated JPX codes; defaults to all Core20 codes.")
    parser.add_argument("--output", type=Path, help="Optional local JSON cache for rate-limited batch runs.")
    parser.add_argument("--requests-per-minute", type=float, default=5.0)
    args = parser.parse_args()
    codes = args.codes.split(",") if args.codes else [str(stock["code"]) for stock in CORE_20]
    codes = [code.strip() for code in codes if code.strip()]
    ticker_by_code = {str(stock["code"]): str(stock["ticker"]) for stock in CORE_20}
    company_by_code = {str(stock["code"]): str(stock["name"]) for stock in CORE_20}
    try:
        loaded = fetch_financial_summaries(codes, requests_per_minute=args.requests_per_minute)
    except JQuantsConfigurationError as exc:
        print(f"J-Quants diagnostic was not run: {exc}")
        return 2

    raw_records = _append_local_cache(args.output, loaded.records)
    normalized = normalize_financial_summaries(
        raw_records, ticker_by_code=ticker_by_code, company_by_code=company_by_code, fetched_at=loaded.fetched_at
    )
    coverage = assess_coverage(normalized, ticker_by_code.values())
    print("J-Quants Financial Summary diagnostic")
    print(f"records={len(normalized)}, failed_codes={len(loaded.failures)}, fetched_at={loaded.fetched_at}")
    if loaded.failures:
        print("failed J-Quants codes=" + ", ".join(loaded.failures))
    print(coverage.to_string(index=False))
    return 0


def _append_local_cache(path: Path | None, records):
    if path is None:
        return records
    import pandas as pd

    existing = pd.DataFrame()
    try:
        if path.exists():
            existing = pd.read_json(path)
    except (OSError, ValueError):
        existing = pd.DataFrame()
    combined = pd.concat([existing, records], ignore_index=True)
    identity = [column for column in ("Code", "DiscDate", "DiscNo", "DocType", "CurPerType") if column in combined]
    if identity:
        combined = combined.drop_duplicates(identity, keep="last")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(combined.to_json(orient="records", force_ascii=False), encoding="utf-8")
    return combined


if __name__ == "__main__":
    raise SystemExit(main())
