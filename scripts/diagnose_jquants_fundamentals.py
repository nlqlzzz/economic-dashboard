"""Run the Core20 J-Quants Financial Summary coverage diagnostic.

Set JQUANTS_API_KEY in the process environment (or execute inside Streamlit with
the same secret configured).  This command deliberately never prints the key.
"""

from __future__ import annotations

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
    codes = [str(stock["code"]) for stock in CORE_20]
    ticker_by_code = {str(stock["code"]): str(stock["ticker"]) for stock in CORE_20}
    company_by_code = {str(stock["code"]): str(stock["name"]) for stock in CORE_20}
    try:
        loaded = fetch_financial_summaries(codes)
    except JQuantsConfigurationError as exc:
        print(f"J-Quants diagnostic was not run: {exc}")
        return 2

    normalized = normalize_financial_summaries(
        loaded.records, ticker_by_code=ticker_by_code, company_by_code=company_by_code, fetched_at=loaded.fetched_at
    )
    coverage = assess_coverage(normalized, ticker_by_code.values())
    print("J-Quants Financial Summary diagnostic")
    print(f"records={len(normalized)}, failed_codes={len(loaded.failures)}, fetched_at={loaded.fetched_at}")
    if loaded.failures:
        print("failed J-Quants codes=" + ", ".join(loaded.failures))
    print(coverage.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
