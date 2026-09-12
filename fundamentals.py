"""Source-neutral Stock Detail fundamentals summaries with explicit comparability."""
from __future__ import annotations

import pandas as pd

from jquants_loader import add_fiscal_yoy, derive_standalone_quarters

OPERATING_NOT_APPLICABLE = {"銀行", "保険"}
ACTUAL_METRICS = ("revenue", "operating_profit", "net_income", "eps")


def build_fundamentals_summary(records: pd.DataFrame, sector: str) -> dict[str, object]:
    if records.empty:
        return _unavailable("J-Quants Financial Summaryを取得できません。")
    actual = records[records["document_type"].fillna("").str.contains("FinancialStatements", case=False)].copy()
    actual = actual[actual["metric"].isin(ACTUAL_METRICS)]
    history = add_fiscal_yoy(derive_standalone_quarters(actual))
    if history.empty:
        return _unavailable("比較可能な実績決算を取得できません。")
    latest, latest_period = _latest_period_cohort(history, sector)
    counts = history.groupby("metric").size().to_dict()
    history_count = {metric: int(counts.get(metric, 0)) for metric in ACTUAL_METRICS}
    annual_history = add_fiscal_yoy(actual[actual["fiscal_quarter"].eq("FY")].copy())
    forecast, forecast_status = _current_forecast_cohort(records, latest_period)
    momentum, reason = _assess_momentum(latest, sector)
    return {
        "status": "Available", "latest": latest, "latest_period": latest_period,
        "history": history, "annual_history": annual_history, "forecast": forecast,
        "forecast_status": forecast_status, "momentum": momentum,
        "history_count": history_count,
        "history_status": "Full history" if min(history_count[x] for x in ("revenue", "net_income")) >= 8 else "History Limited",
        "operating_status": "Not Applicable" if sector in OPERATING_NOT_APPLICABLE else ("Available" if history_count["operating_profit"] else "Unavailable"),
        "source": "J-Quants API V2 Financial Summary", "momentum_reason": reason,
    }


def _unavailable(reason: str) -> dict[str, object]:
    return {"status": "Unavailable", "reason": reason, "history": pd.DataFrame(), "forecast": pd.DataFrame(), "momentum": "Unavailable"}


def _latest_period_cohort(history: pd.DataFrame, sector: str) -> tuple[pd.DataFrame, dict[str, object]]:
    """Select one disclosed period; never fill a missing current metric from an older one."""
    selectable = history.copy()
    if sector in OPERATING_NOT_APPLICABLE:
        selectable = selectable[selectable.metric.ne("operating_profit")]
    identity = ["fiscal_year", "fiscal_quarter", "fiscal_year_start", "fiscal_year_end", "accounting_standard", "consolidated_flag", "currency", "unit", "reference_period"]
    for column in identity:
        if column not in selectable:
            selectable[column] = pd.NA
    periods = (selectable.groupby(identity, dropna=False).agg(disclosure_date=("disclosure_date", "max"), metrics=("metric", "nunique")).reset_index())
    periods["_reference"] = pd.to_datetime(periods["reference_period"], errors="coerce")
    periods["_disclosure"] = pd.to_datetime(periods["disclosure_date"], errors="coerce")
    chosen = periods.sort_values(["_reference", "_disclosure", "metrics"], ascending=[False, False, False], na_position="last").iloc[0]
    mask = pd.Series(True, index=selectable.index)
    for column in identity:
        value = chosen[column]
        mask &= selectable[column].isna() if pd.isna(value) else selectable[column].eq(value)
    latest = selectable[mask].sort_values("metric").drop_duplicates("metric", keep="last").copy()
    period = {column: (None if pd.isna(chosen[column]) else chosen[column]) for column in identity}
    period["disclosure_date"] = None if pd.isna(chosen["disclosure_date"]) else chosen["disclosure_date"]
    return latest, period


def _current_forecast_cohort(records: pd.DataFrame, latest_period: dict[str, object]) -> tuple[pd.DataFrame, str]:
    forecast = records[records["metric"].astype(str).str.startswith("forecast_")].copy()
    fiscal_year = latest_period.get("fiscal_year")
    if forecast.empty or fiscal_year is None:
        return pd.DataFrame(columns=forecast.columns), "Unavailable"
    for column in ("accounting_standard", "consolidated_flag", "currency", "unit"):
        if column not in forecast:
            continue
        value = latest_period.get(column)
        if value is not None:
            forecast = forecast[forecast[column].eq(value)]
    years = pd.to_numeric(forecast["fiscal_year"], errors="coerce")
    current_year = pd.to_numeric(pd.Series([fiscal_year]), errors="coerce").iloc[0]
    if pd.isna(current_year):
        return pd.DataFrame(columns=forecast.columns), "Unavailable"
    # The newest actual FY can already be complete; then the next FY forecast is
    # the current company outlook.  Never fall back to an older target FY.
    target_year = years[years >= current_year].min()
    forecast = forecast[years.eq(target_year)] if pd.notna(target_year) else pd.DataFrame(columns=forecast.columns)
    if forecast.empty:
        return forecast, "Unavailable"
    latest_date = pd.to_datetime(forecast["disclosure_date"], errors="coerce").max()
    if pd.isna(latest_date):
        return pd.DataFrame(columns=forecast.columns), "Unavailable"
    cohort = forecast[pd.to_datetime(forecast["disclosure_date"], errors="coerce").eq(latest_date)].copy()
    return cohort.sort_values("metric").drop_duplicates("metric", keep="last"), "Available"


def format_jpy(value: object) -> str:
    if value is None or pd.isna(value): return "—"
    amount = float(value)
    if abs(amount) >= 1_000_000_000_000: return _trim(amount / 1_000_000_000_000, 2) + "兆円"
    if abs(amount) >= 100_000_000: return _trim(amount / 100_000_000) + "億円"
    return _trim(amount) + "円"


def format_eps(value: object) -> str:
    return "—" if value is None or pd.isna(value) else _trim(float(value)) + "円"


def format_financial_value(value: object, metric: str, unit: object = None) -> str:
    if metric == "eps": return format_eps(value)
    # Financial Summary currently has no row-level amount-unit field.  Do not
    # label unknown raw values as yen until source-unit confirmation is retained.
    if unit is not None and not pd.isna(unit) and str(unit) in {"JPY", "yen"}: return format_jpy(value)
    return "—" if value is None or pd.isna(value) else _trim(float(value)) + "（単位未確認）"


def comparison_label(comparison: object, yoy: object = None, value_change: object = None, metric: str = "") -> str:
    labels = {"increase": "増加", "decrease": "減少", "flat": "横ばい", "profit_turnaround": "黒字転換", "loss_turnaround": "赤字転落", "loss_narrowing": "赤字縮小", "loss_widening": "赤字拡大", "from_zero_increase": "前年ゼロから増加", "from_zero_decrease": "前年ゼロから減少", "unavailable": "比較不能"}
    label = labels.get(str(comparison), "比較不能")
    if str(comparison) in {"increase", "decrease"} and yoy is not None and not pd.isna(yoy):
        return f"前年比 {float(yoy):+.1f}%（{label}）"
    return label


def format_yoy(value: object) -> str:
    return "前年比 —" if value is None or pd.isna(value) else f"前年比 {float(value):+.1f}%"


def build_fundamentals_cards(summary: dict[str, object]) -> list[dict[str, object]]:
    latest = summary.get("latest", pd.DataFrame())
    if not isinstance(latest, pd.DataFrame) or latest.empty: return []
    labels = {"revenue": "売上高等", "net_income": "純利益", "eps": "EPS", "operating_profit": "営業利益"}
    cards = []
    for metric in ("revenue", "net_income", "eps", "operating_profit"):
        rows = latest[latest["metric"].eq(metric)]
        if rows.empty: continue
        row = rows.iloc[0]
        cards.append({"metric": metric, "label": labels[metric], "value": format_financial_value(row["value"], metric, row.get("unit")), "yoy": comparison_label(row.get("comparison"), row.get("yoy"), row.get("value_change"), metric), "comparison": row.get("comparison", "unavailable")})
    return cards


def build_annual_forecast_series(summary: dict[str, object], metric: str) -> pd.DataFrame:
    actual, forecast = summary.get("annual_history", pd.DataFrame()), summary.get("forecast", pd.DataFrame())
    if not isinstance(actual, pd.DataFrame): actual = pd.DataFrame()
    if not isinstance(forecast, pd.DataFrame): forecast = pd.DataFrame()
    actual = actual[actual.get("metric", pd.Series(dtype=str)).eq(metric)].copy()
    forecast = forecast[forecast.get("metric", pd.Series(dtype=str)).eq(f"forecast_{metric}")].copy()
    rows = []
    for _, row in actual.sort_values("disclosure_date").drop_duplicates("fiscal_year", keep="last").iterrows(): rows.append({"期": str(row.get("fiscal_year")), "実績": row.get("value"), "会社予想": None})
    for _, row in forecast.iterrows():
        year = str(row.get("fiscal_year")); found = next((item for item in rows if item["期"] == year), None)
        if found is None: rows.append({"期": year, "実績": None, "会社予想": row.get("value")})
        else: found["会社予想"] = row.get("value")
    return pd.DataFrame(rows).sort_values("期").reset_index(drop=True) if rows else pd.DataFrame(columns=["期", "実績", "会社予想"])


def chart_axis_ticks(values: pd.Series, metric: str, unit: object = "JPY") -> dict[str, list[object]]:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty: return {"tickvals": [], "ticktext": []}
    low, high = float(numeric.min()), float(numeric.max())
    ticks = [low] if low == high else [low + (high - low) * index / 4 for index in range(5)]
    formatter = lambda value: format_financial_value(value, metric, unit)
    return {"tickvals": ticks, "ticktext": [formatter(value) for value in ticks]}


def _assess_momentum(latest: pd.DataFrame, sector: str) -> tuple[str, str]:
    statuses = {row.metric: str(row.get("comparison", "unavailable")) for _, row in latest.iterrows()}
    revenue, income, operating = statuses.get("revenue", "unavailable"), statuses.get("net_income", "unavailable"), statuses.get("operating_profit", "unavailable")
    positive, negative = {"increase", "profit_turnaround", "loss_narrowing", "from_zero_increase"}, {"decrease", "loss_turnaround", "loss_widening", "from_zero_decrease"}
    if all(state in {"unavailable", "flat"} for state in (revenue, income)): return "Unavailable", "売上高等と利益の前年同期比較が十分ではありません。"
    if revenue in positive and income in positive:
        return ("Strong" if sector not in OPERATING_NOT_APPLICABLE and operating in positive else "Improving"), _momentum_reason(statuses, sector)
    if revenue in negative and income in negative: return "Weakening", _momentum_reason(statuses, sector)
    return "Mixed", _momentum_reason(statuses, sector)


def _momentum_reason(statuses: dict[str, str], sector: str) -> str:
    labels = {"revenue": "売上高等", "net_income": "純利益", "eps": "EPS", "operating_profit": "営業利益"}
    pieces = [f"{labels[key]}: {comparison_label(value)}" for key, value in statuses.items() if value != "unavailable"]
    if sector in OPERATING_NOT_APPLICABLE: pieces.append("営業利益は業種上の比較対象外")
    return "｜".join(pieces) if pieces else "比較可能な前年同期データがありません。"


def _trim(value: float, decimals: int = 1) -> str:
    return f"{value:,.{decimals}f}".rstrip("0").rstrip(".")
