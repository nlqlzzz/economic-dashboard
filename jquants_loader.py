"""J-Quants V2 financial-summary access and safe normalization helpers.

This module intentionally has no Streamlit UI dependency.  A caller supplies an
API key through ``JQUANTS_API_KEY`` or Streamlit Secrets; the key is never
returned, logged, or stored in result objects.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import tomllib

import pandas as pd


SOURCE_NAME = "J-Quants API V2 Financial Summary"
SOURCE_URL = "https://jpx-jquants.com/"
REQUIRED_COLUMNS = (
    "ticker", "code", "jquants_code", "company_name", "disclosure_date",
    "reference_period", "fiscal_year", "fiscal_quarter", "document_type",
    "accounting_standard", "consolidated_flag", "metric", "value", "unit",
    "currency", "is_cumulative", "is_derived", "source_name", "source_url", "fetched_at",
)


class JQuantsConfigurationError(RuntimeError):
    """Raised when a safe J-Quants configuration is unavailable."""


@dataclass(frozen=True)
class JQuantsLoadResult:
    records: pd.DataFrame
    failures: tuple[str, ...]
    fetched_at: str


def get_jquants_api_key() -> str | None:
    """Read the key without exposing it in exceptions, logs, or returned payloads."""
    value = os.getenv("JQUANTS_API_KEY", "").strip()
    if value:
        return value
    secret = _read_streamlit_runtime_secret()
    if secret:
        return secret
    return _read_local_streamlit_secret()


def _read_streamlit_runtime_secret() -> str | None:
    try:
        import streamlit as st

        value = st.secrets.get("JQUANTS_API_KEY", "")
        return str(value).strip() or None
    except Exception:
        # A standalone diagnostic can run outside Streamlit's project directory.
        return None


def _read_local_streamlit_secret() -> str | None:
    """Read only this repository's ignored Streamlit secret for standalone tools."""
    path = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
    try:
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
        value = parsed.get("JQUANTS_API_KEY", "")
        return str(value).strip() or None
    except (OSError, tomllib.TOMLDecodeError):
        return None


def to_jquants_code(code_or_ticker: str) -> str:
    """Convert a JPX four-digit code or Yahoo ticker to J-Quants' five-digit code."""
    value = str(code_or_ticker).strip().upper().replace(".T", "")
    if len(value) == 5 and value.isdigit():
        return value
    if len(value) == 4 and value.isdigit():
        return value + "0"
    raise ValueError("J-Quants code must be a four-digit JPX code or five-digit J-Quants code")


def fetch_financial_summaries(
    codes: Iterable[str],
    *,
    client_factory: Callable[[str], Any] | None = None,
    requests_per_minute: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> JQuantsLoadResult:
    """Fetch one summary history per code with low-rate, partial-failure handling.

    ``get_fin_summary_range`` is not used here because its official client helper
    requests each calendar day.  Per-code summary history is safer for Core20
    diagnostics and avoids range scans on constrained plans.
    """
    api_key = get_jquants_api_key()
    if not api_key:
        raise JQuantsConfigurationError("JQUANTS_API_KEY が未設定です。環境変数またはStreamlit Secretsへ設定してください。")
    if client_factory is None:
        try:
            from jquantsapi import ClientV2
        except ImportError as exc:
            raise JQuantsConfigurationError("jquants-api-client がインストールされていません。") from exc
        client_factory = lambda key: ClientV2(api_key=key)

    client = client_factory(api_key)
    frames: list[pd.DataFrame] = []
    failures: list[str] = []
    code_list = [to_jquants_code(code) for code in codes]
    if requests_per_minute is None:
        try:
            requests_per_minute = float(os.getenv("JQUANTS_REQUESTS_PER_MINUTE", "5"))
        except ValueError:
            requests_per_minute = 5.0
    pause = 60.0 / requests_per_minute if requests_per_minute and requests_per_minute > 0 else 0.0
    for position, code in enumerate(code_list):
        try:
            raw = client.get_fin_summary(code=code)
            frame = _as_frame(raw)
            if not frame.empty:
                frame["_jquants_code"] = code
                frames.append(frame)
        except Exception as exc:
            # API responses can contain operational details; keep the UI-safe code only.
            failures.append(code)
        if pause and position < len(code_list) - 1:
            sleep(pause)
    raw_records = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return JQuantsLoadResult(raw_records, tuple(failures), _utc_now())


def normalize_financial_summaries(
    raw: pd.DataFrame | list[Mapping[str, object]],
    *,
    ticker_by_code: Mapping[str, str] | None = None,
    company_by_code: Mapping[str, str] | None = None,
    fetched_at: str | None = None,
) -> pd.DataFrame:
    """Normalize J-Quants summary records into a source-neutral long schema.

    Values are preserved as supplied.  The API unit is not guessed; presentation
    must verify source unit metadata before formatting a monetary amount.
    """
    frame = _as_frame(raw)
    if frame.empty:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    fetched_at = fetched_at or _utc_now()
    ticker_by_code = {str(key)[:4]: value for key, value in (ticker_by_code or {}).items()}
    company_by_code = {str(key)[:4]: value for key, value in (company_by_code or {}).items()}
    rows: list[dict[str, object]] = []
    for _, record in frame.iterrows():
        source_code = str(record.get("Code") or record.get("_jquants_code") or "").strip()
        code = source_code[:4]
        period_type = _fiscal_quarter(record.get("CurPerType"))
        cur_start = _date_or_none(record.get("CurPerSt"))
        fiscal_start = _date_or_none(record.get("CurFYSt"))
        reference_period = _date_or_none(record.get("CurPerEn"))
        fiscal_end = _date_or_none(record.get("CurFYEn"))
        document_type = _text_or_none(record.get("DocType"))
        base = {
            "ticker": ticker_by_code.get(code), "code": code or None, "jquants_code": source_code or None,
            "company_name": company_by_code.get(code), "disclosure_date": _date_or_none(record.get("DiscDate")),
            "reference_period": reference_period, "fiscal_year": fiscal_end[:4] if fiscal_end else None,
            "fiscal_quarter": period_type, "document_type": document_type,
            "accounting_standard": _accounting_standard(document_type),
            "consolidated_flag": _consolidated_flag(document_type), "unit": None, "currency": "JPY",
            "is_cumulative": _is_cumulative(period_type, cur_start, fiscal_start), "is_derived": False,
            "source_name": SOURCE_NAME, "source_url": SOURCE_URL, "fetched_at": fetched_at,
        }
        for field, metric in (("Sales", "revenue"), ("OP", "operating_profit"), ("NP", "net_income"), ("EPS", "eps"),
                              ("FSales", "forecast_revenue"), ("FOP", "forecast_operating_profit"),
                              ("FNP", "forecast_net_income"), ("FEPS", "forecast_eps")):
            value = _number_or_none(record.get(field))
            if value is not None:
                # Forecast fields are for the fiscal year ending at CurFYEn, not
                # for the currently reported quarter.  Keep that target period
                # explicit so a forecast is never plotted as a next-quarter fact.
                forecast_base = (
                    {**base, "fiscal_quarter": "FY", "reference_period": fiscal_end,
                     "is_cumulative": True}
                    if metric.startswith("forecast_") else base
                )
                rows.append({**forecast_base, "metric": metric, "value": value})
    result = pd.DataFrame(rows, columns=REQUIRED_COLUMNS)
    return result.sort_values(["ticker", "metric", "disclosure_date"], na_position="last").reset_index(drop=True) if not result.empty else result


def derive_standalone_quarters(records: pd.DataFrame) -> pd.DataFrame:
    """Derive Q2/Q3/Q4 only when cumulative-period evidence is explicit and comparable."""
    if records.empty:
        return records.copy()
    output: list[dict[str, object]] = []
    key_columns = ["ticker", "code", "metric", "fiscal_year", "accounting_standard", "consolidated_flag"]
    raw = records.copy()
    raw = raw[raw["metric"].isin(("revenue", "operating_profit", "net_income", "eps"))]
    raw = raw[raw["document_type"].fillna("").str.contains("FinancialStatements", case=False)]
    for _, group in raw.groupby(key_columns, dropna=False):
        latest = (group.sort_values("disclosure_date", na_position="first")
                       .drop_duplicates("fiscal_quarter", keep="last"))
        by_quarter = {row["fiscal_quarter"]: row for _, row in latest.iterrows()}
        q1, q2, q3, fy = (by_quarter.get(name) for name in ("Q1", "Q2", "Q3", "FY"))
        if q1 is not None and q1.get("is_cumulative") is False:
            output.append(q1.to_dict())
        for label, current, previous in (("Q2", q2, q1), ("Q3", q3, q2), ("Q4", fy, q3)):
            if current is None or previous is None or current.get("is_cumulative") is not True or previous.get("value") is None:
                continue
            if label in {"Q3", "Q4"} and previous.get("is_cumulative") is not True:
                continue
            if current.get("value") is None or current.get("unit") != previous.get("unit") or current.get("currency") != previous.get("currency"):
                continue
            derived = current.to_dict()
            derived["fiscal_quarter"] = label
            derived["value"] = float(current["value"]) - float(previous["value"])
            derived["is_cumulative"] = False
            derived["is_derived"] = True
            output.append(derived)
    return pd.DataFrame(output, columns=records.columns)


def add_fiscal_yoy(records: pd.DataFrame) -> pd.DataFrame:
    """Add YoY only between matching fiscal quarters and compatible definitions."""
    output = records.copy()
    output["yoy"] = pd.NA
    if output.empty:
        return output
    keys = ["ticker", "code", "metric", "fiscal_quarter", "accounting_standard", "consolidated_flag", "is_derived"]
    for _, group in output.groupby(keys, dropna=False):
        ordered = group.sort_values("fiscal_year")
        previous: pd.Series | None = None
        for index, row in ordered.iterrows():
            if previous is not None and row.get("fiscal_year") and previous.get("fiscal_year"):
                if int(str(row["fiscal_year"])) == int(str(previous["fiscal_year"])) + 1 and float(previous["value"]) != 0:
                    output.loc[index, "yoy"] = (float(row["value"]) / float(previous["value"]) - 1.0) * 100.0
            previous = row
    return output


def assess_coverage(records: pd.DataFrame, expected_tickers: Iterable[str]) -> pd.DataFrame:
    """Summarize actual normalized coverage without inventing unavailable observations."""
    expected = set(expected_tickers)
    rows: list[dict[str, object]] = []
    for metric in ("revenue", "operating_profit", "net_income", "eps", "forecast_revenue", "forecast_operating_profit", "forecast_net_income", "forecast_eps"):
        subset = records[records.get("metric", pd.Series(dtype=str)).eq(metric)] if not records.empty else pd.DataFrame()
        tickers = set(subset.get("ticker", pd.Series(dtype=str)).dropna()) if not subset.empty else set()
        actual = subset[subset.get("document_type", pd.Series(dtype=str)).fillna("").str.contains("FinancialStatements", case=False)] if not subset.empty else subset
        actual = actual.sort_values("disclosure_date", na_position="first").drop_duplicates(["ticker", "fiscal_year", "fiscal_quarter"], keep="last") if not actual.empty else actual
        quarter_counts = actual[actual.get("fiscal_quarter", pd.Series(dtype=str)).isin(("Q1", "Q2", "Q3", "Q4"))].groupby("ticker").size() if not actual.empty else pd.Series(dtype=int)
        rows.append({"metric": metric, "coverage": len(tickers), "coverage_total": len(expected),
                     "coverage_ratio": len(tickers) / len(expected) if expected else None,
                     "eight_quarter_coverage": int((quarter_counts >= 8).sum()),
                     "definition_quality": "Pending actual record review"})
    return pd.DataFrame(rows)


def _as_frame(raw: Any) -> pd.DataFrame:
    if isinstance(raw, pd.DataFrame):
        return raw.copy()
    if raw is None:
        return pd.DataFrame()
    return pd.DataFrame(raw)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _date_or_none(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float)) and abs(float(value)) >= 10_000_000_000:
        parsed = pd.to_datetime(value, unit="ms", errors="coerce")
    else:
        parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date().isoformat()


def _text_or_none(value: object) -> str | None:
    return None if value is None or pd.isna(value) or not str(value).strip() else str(value).strip()


def _number_or_none(value: object) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(parsed) else float(parsed)


def _fiscal_quarter(value: object) -> str | None:
    text = _text_or_none(value)
    if not text:
        return None
    upper = text.upper()
    for candidate, aliases in (("Q1", ("Q1", "1Q")), ("Q2", ("Q2", "2Q")), ("Q3", ("Q3", "3Q")), ("FY", ("FY",))):
        if any(alias in upper for alias in aliases):
            return candidate
    return None


def _accounting_standard(document_type: str | None) -> str | None:
    if not document_type:
        return None
    upper = document_type.upper()
    if "IFRS" in upper:
        return "IFRS"
    if "US" in upper and "GAAP" in upper:
        return "US GAAP"
    if "JP" in upper or "J-GAAP" in upper:
        return "Japan GAAP"
    return None


def _consolidated_flag(document_type: str | None) -> bool | None:
    if not document_type:
        return None
    upper = document_type.upper()
    if "NONCONSOLIDATED" in upper or "NON_CONSOLIDATED" in upper:
        return False
    if "CONSOLIDATED" in upper:
        return True
    return None


def _is_cumulative(period_type: str | None, period_start: str | None, fiscal_start: str | None) -> bool | None:
    if not period_type or not period_start or not fiscal_start:
        return None
    if period_type == "Q1":
        return False if period_start == fiscal_start else None
    if period_type in {"Q2", "Q3", "FY"}:
        return True if period_start == fiscal_start else None
    return None
