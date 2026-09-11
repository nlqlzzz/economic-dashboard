"""Source-neutral Stock Detail fundamentals summaries."""
from __future__ import annotations

import pandas as pd

from jquants_loader import add_fiscal_yoy, derive_standalone_quarters

OPERATING_NOT_APPLICABLE = {"銀行", "保険"}
TREND_MINIMUM = 4


def build_fundamentals_summary(records: pd.DataFrame, sector: str) -> dict[str, object]:
    if records.empty:
        return {"status": "Unavailable", "reason": "J-Quants Financial Summaryを取得できません。", "history": pd.DataFrame(), "forecast": pd.DataFrame(), "momentum": "Unavailable"}
    actual = records[records["document_type"].fillna("").str.contains("FinancialStatements", case=False)].copy()
    actual = actual[actual["metric"].isin(("revenue", "operating_profit", "net_income", "eps"))]
    annual_history = actual[actual["fiscal_quarter"].eq("FY")].copy()
    standalone = add_fiscal_yoy(derive_standalone_quarters(actual))
    latest = (standalone.sort_values("disclosure_date").drop_duplicates("metric", keep="last"))
    history_count = standalone.groupby("metric").size().to_dict()
    for metric in ("revenue", "net_income", "eps", "operating_profit"):
        if metric not in history_count:
            history_count[metric] = 0
    if sector in OPERATING_NOT_APPLICABLE:
        latest = latest[latest.metric.ne("operating_profit")]
    forecast = records[records["metric"].str.startswith("forecast_")].copy()
    forecast = forecast.sort_values("disclosure_date").drop_duplicates("metric", keep="last")
    usable = latest[latest.metric.isin(("revenue", "net_income", "eps"))]
    yoy = pd.to_numeric(usable.get("yoy"), errors="coerce").dropna()
    positive = int((yoy > 0).sum()); negative = int((yoy < 0).sum())
    operating_yoy = _metric_yoy(latest, "operating_profit")
    if len(yoy) < 2: momentum = "Unavailable"
    elif positive >= 2 and negative == 0 and (operating_yoy is None or operating_yoy >= 0): momentum = "Strong"
    elif positive >= 2: momentum = "Improving"
    elif negative >= 2: momentum = "Weakening"
    else: momentum = "Mixed"
    return {"status": "Available", "latest": latest, "history": standalone,
            "annual_history": annual_history, "forecast": forecast,
            "momentum": momentum, "history_count": history_count,
            "history_status": "Full history" if min(history_count[x] for x in ("revenue", "net_income", "eps")) >= 8 else "History Limited",
            "operating_status": "Not Applicable" if sector in OPERATING_NOT_APPLICABLE else ("Available" if history_count["operating_profit"] else "Unavailable"),
            "source": "J-Quants API V2 Financial Summary",
            "momentum_reason": _momentum_reason(latest, momentum, sector)}


def format_jpy(value: object) -> str:
    """Format J-Quants yen amounts for compact Japanese mobile UI."""
    if value is None or pd.isna(value):
        return "—"
    amount = float(value)
    if abs(amount) >= 1_000_000_000_000:
        return _trim(amount / 1_000_000_000_000, decimals=2) + "兆円"
    if abs(amount) >= 100_000_000:
        return _trim(amount / 100_000_000) + "億円"
    return _trim(amount) + "円"


def format_eps(value: object) -> str:
    return "—" if value is None or pd.isna(value) else _trim(float(value)) + "円"


def format_yoy(value: object) -> str:
    return "前年比 —" if value is None or pd.isna(value) else f"前年比 {float(value):+.1f}%"


def build_fundamentals_cards(summary: dict[str, object]) -> list[dict[str, object]]:
    latest = summary.get("latest", pd.DataFrame())
    if not isinstance(latest, pd.DataFrame) or latest.empty:
        return []
    labels = {"revenue": "売上高等", "net_income": "純利益", "eps": "EPS", "operating_profit": "営業利益"}
    cards = []
    for metric in ("revenue", "net_income", "eps", "operating_profit"):
        rows = latest[latest["metric"].eq(metric)]
        if rows.empty:
            continue
        row = rows.iloc[0]
        cards.append({"metric": metric, "label": labels[metric], "value": format_eps(row["value"]) if metric == "eps" else format_jpy(row["value"]), "yoy": format_yoy(row.get("yoy"))})
    return cards


def build_annual_forecast_series(summary: dict[str, object], metric: str) -> pd.DataFrame:
    """Return only fiscal-year comparable actual and forecast observations.

    Quarterly standalone results are intentionally absent: a full-year company
    forecast must never be drawn as if it were the next quarterly result.
    """
    actual = summary.get("annual_history", pd.DataFrame())
    forecast = summary.get("forecast", pd.DataFrame())
    if not isinstance(actual, pd.DataFrame):
        actual = pd.DataFrame()
    if not isinstance(forecast, pd.DataFrame):
        forecast = pd.DataFrame()
    actual = actual[actual.get("metric", pd.Series(dtype=str)).eq(metric)].copy()
    forecast = forecast[forecast.get("metric", pd.Series(dtype=str)).eq(f"forecast_{metric}")].copy()
    rows = []
    for _, row in actual.drop_duplicates("fiscal_year", keep="last").iterrows():
        rows.append({"期": str(row.get("fiscal_year")), "実績": row.get("value"), "会社予想": None})
    for _, row in forecast.drop_duplicates("fiscal_year", keep="last").iterrows():
        year = str(row.get("fiscal_year"))
        found = next((item for item in rows if item["期"] == year), None)
        if found is None:
            rows.append({"期": year, "実績": None, "会社予想": row.get("value")})
        else:
            found["会社予想"] = row.get("value")
    return pd.DataFrame(rows).sort_values("期").reset_index(drop=True) if rows else pd.DataFrame(columns=["期", "実績", "会社予想"])


def chart_axis_ticks(values: pd.Series, metric: str) -> dict[str, list[object]]:
    """Compact Japanese tick labels shared by Plotly figures and hover text."""
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return {"tickvals": [], "ticktext": []}
    low, high = float(numeric.min()), float(numeric.max())
    if low == high:
        ticks = [low]
    else:
        ticks = [low + (high - low) * index / 4 for index in range(5)]
    formatter = format_eps if metric == "eps" else format_jpy
    return {"tickvals": ticks, "ticktext": [formatter(value) for value in ticks]}


def _metric_yoy(latest: pd.DataFrame, metric: str) -> float | None:
    rows = latest[latest.metric.eq(metric)]
    if rows.empty or pd.isna(rows.iloc[0].get("yoy")):
        return None
    return float(rows.iloc[0]["yoy"])


def _momentum_reason(latest: pd.DataFrame, momentum: str, sector: str) -> str:
    positives = []; negatives = []
    labels = {"revenue": "売上高等", "net_income": "純利益", "eps": "EPS", "operating_profit": "営業利益"}
    for metric, label in labels.items():
        value = _metric_yoy(latest, metric)
        if value is None:
            continue
        (positives if value > 0 else negatives).append(label)
    if momentum == "Unavailable":
        return "前年同期比を比較できる主要指標が十分ではありません。"
    text = ("改善: " + "・".join(positives) if positives else "改善指標なし")
    if negatives:
        text += "｜弱含み: " + "・".join(negatives)
    if sector in OPERATING_NOT_APPLICABLE:
        text += "｜営業利益は業種上の比較対象外です。"
    return text


def _trim(value: float, decimals: int = 1) -> str:
    return f"{value:,.{decimals}f}".rstrip("0").rstrip(".")
