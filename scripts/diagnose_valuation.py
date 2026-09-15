"""Run the Core20 valuation readiness diagnostic without exposing API secrets."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
import time

import pandas as pd

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from data_loader import load_yfinance_batch
from japan_equity import CORE_20, core_tickers
from jquants_loader import (
    JQuantsConfigurationError,
    fetch_financial_summaries,
    get_jquants_api_key,
    normalize_financial_summaries,
    to_jquants_code,
)
from valuation import (
    assess_current_forward_per,
    assessment_dict,
    build_forecast_eps_revisions,
    historical_feasibility,
    normalized_pbr_readiness,
    sector_valuation_caution,
    split_basis_status_from_daily_bars,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose Core20 valuation data readiness.")
    parser.add_argument("--requests-per-minute", type=float, default=5.0)
    parser.add_argument("--price-start", default="2016-01-01")
    parser.add_argument("--output", type=Path, help="Optional JSON output path.")
    args = parser.parse_args()
    ticker_by_code = {str(stock["code"]): str(stock["ticker"]) for stock in CORE_20}
    company_by_code = {str(stock["code"]): str(stock["name"]) for stock in CORE_20}
    try:
        loaded = fetch_financial_summaries(
            ticker_by_code, requests_per_minute=args.requests_per_minute
        )
    except JQuantsConfigurationError:
        print("Valuation live diagnostic was not run: JQUANTS_API_KEY is unavailable.")
        return 2
    try:
        prices = load_yfinance_batch(core_tickers(), args.price_start)
    except Exception:
        prices = pd.DataFrame()
    normalized = normalize_financial_summaries(
        loaded.records,
        ticker_by_code=ticker_by_code,
        company_by_code=company_by_code,
        fetched_at=loaded.fetched_at,
    )
    adjustment_bars, adjustment_failures = _load_adjustment_bars(
        normalized, prices, args.requests_per_minute
    )
    report = build_live_report(
        normalized, prices, loaded.records, loaded.failures, loaded.fetched_at,
        adjustment_bars=adjustment_bars, adjustment_failures=adjustment_failures,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Valuation diagnostic written: {args.output}")
    else:
        print(rendered)
    return 0


def build_live_report(
    records: pd.DataFrame,
    prices: pd.DataFrame,
    raw_records: pd.DataFrame,
    failures: tuple[str, ...] = (),
    fetched_at: str | None = None,
    *,
    adjustment_bars: dict[str, pd.DataFrame] | None = None,
    adjustment_failures: tuple[str, ...] = (),
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    revision_ready = 0
    safe_current = 0
    safe_history = 0
    adjustment_bars = adjustment_bars or {}
    for stock in CORE_20:
        ticker = str(stock["ticker"])
        selected = records[records.get("ticker", pd.Series(dtype=str)).eq(ticker)].copy()
        series = prices[ticker] if ticker in prices else pd.Series(dtype=float)
        split_status = _split_status(selected, series, adjustment_bars.get(ticker, pd.DataFrame()))
        history_split_status = _split_status(
            selected, series, adjustment_bars.get(ticker, pd.DataFrame()), earliest=True
        )
        assessment = assess_current_forward_per(selected, series, split_basis_status=split_status)
        revisions = build_forecast_eps_revisions(selected)
        comparable = revisions[revisions["revision_direction"].ne("comparison_unavailable")]
        history = historical_feasibility(selected, history_split_status)
        revision_count = len(revisions.drop_duplicates(["fiscal_year", "disclosure_date"]))
        if not comparable.empty:
            revision_ready += 1
        if assessment.calculable:
            safe_current += 1
        if history["status"] == "GO":
            safe_history += 1
        rows.append({
            "ticker": ticker,
            "company_name": stock["name"],
            "sector": stock["sector"],
            **assessment_dict(assessment),
            "forecast_eps_revision_observations": revision_count,
            "comparable_revision_pairs": len(comparable),
            "historical_forward_per_feasibility": history,
            "sector_specific_caution": sector_valuation_caution(str(stock["sector"])),
            "verdict": _overall_verdict(assessment.calculable, not comparable.empty, history["status"]),
        })
    raw_fields = {
        field: int(pd.to_numeric(raw_records.get(field), errors="coerce").notna().sum())
        if field in raw_records else 0
        for field in ("BPS", "NCBPS", "Eq", "NCEq", "ShOutFY", "AvgSh")
    }
    return {
        "diagnostic_date": date.today().isoformat(),
        "fetched_at": fetched_at,
        # Keep diagnostics useful without persisting provider exception text.
        "failed_jquants_codes": [_failure_code(value) for value in failures],
        "failed_adjustment_factor_codes": list(adjustment_failures),
        "coverage": {
            "core20": len(CORE_20),
            "safe_current_forward_per": safe_current,
            "forecast_revision_comparable": revision_ready,
            "safe_historical_forward_per": safe_history,
            "split_basis_unknown": sum(row["split_basis_status"] != "aligned" for row in rows),
        },
        "pbr": normalized_pbr_readiness(records),
        "raw_summary_field_non_null_rows": raw_fields,
        "rows": rows,
    }


def _overall_verdict(current: bool, revisions: bool, history_status: str) -> str:
    if current and revisions and history_status == "GO":
        return "GO"
    if current or revisions or history_status == "CONDITIONAL":
        return "CONDITIONAL"
    return "NO-GO"


def _failure_code(value: object) -> str:
    """Retain only a code-like identifier, never an API exception or response."""
    candidate = str(value).split(":", 1)[0].strip()
    return candidate if candidate.isdigit() and 4 <= len(candidate) <= 5 else "unknown"


def _split_status(
    records: pd.DataFrame, prices: pd.Series, bars: pd.DataFrame, *, earliest: bool = False
) -> str:
    if prices.dropna().empty or records.empty:
        return "unknown"
    price_date = prices.dropna().sort_index().index[-1]
    forecasts = records[records.get("metric", pd.Series(dtype=str)).eq("forecast_eps")].copy()
    disclosed = pd.to_datetime(forecasts.get("disclosure_date"), errors="coerce")
    eligible = forecasts[disclosed <= pd.Timestamp(price_date)]
    if eligible.empty:
        return "unknown"
    ordered = eligible.assign(_disclosed=pd.to_datetime(eligible["disclosure_date"])).sort_values("_disclosed")
    chosen = ordered.iloc[0] if earliest else ordered.iloc[-1]
    return split_basis_status_from_daily_bars(
        bars, chosen["disclosure_date"], price_date
    )


def _load_adjustment_bars(
    records: pd.DataFrame, prices: pd.DataFrame, requests_per_minute: float
) -> tuple[dict[str, pd.DataFrame], tuple[str, ...]]:
    api_key = get_jquants_api_key()
    if not api_key:
        return {}, tuple(str(stock["code"]) for stock in CORE_20)
    from jquantsapi import ClientV2

    client = ClientV2(api_key=api_key)
    results: dict[str, pd.DataFrame] = {}
    failures: list[str] = []
    pause = 60.0 / requests_per_minute if requests_per_minute > 0 else 0.0
    candidates = [stock for stock in CORE_20 if stock["ticker"] in prices]
    for position, stock in enumerate(candidates):
        ticker, code = str(stock["ticker"]), str(stock["code"])
        selected = records[
            records.get("ticker", pd.Series(dtype=str)).eq(ticker)
            & records.get("metric", pd.Series(dtype=str)).eq("forecast_eps")
        ]
        disclosures = pd.to_datetime(selected.get("disclosure_date"), errors="coerce").dropna()
        series = prices[ticker].dropna().sort_index()
        if disclosures.empty or series.empty:
            failures.append(code)
            continue
        try:
            results[ticker] = client.get_eq_bars_daily(
                code=to_jquants_code(code),
                from_yyyymmdd=disclosures.min().strftime("%Y%m%d"),
                to_yyyymmdd=pd.Timestamp(series.index[-1]).strftime("%Y%m%d"),
            )
        except Exception:
            failures.append(code)
        if pause and position < len(candidates) - 1:
            time.sleep(pause)
    return results, tuple(failures)


if __name__ == "__main__":
    raise SystemExit(main())
