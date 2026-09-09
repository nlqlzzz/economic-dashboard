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
    if len(yoy) < 2: momentum = "Unavailable"
    elif positive >= 2 and negative == 0: momentum = "Strong"
    elif positive >= 2: momentum = "Improving"
    elif negative >= 2: momentum = "Weakening"
    else: momentum = "Mixed"
    return {"status": "Available", "latest": latest, "history": standalone, "forecast": forecast,
            "momentum": momentum, "history_count": history_count,
            "history_status": "Full history" if min(history_count[x] for x in ("revenue", "net_income", "eps")) >= 8 else "History Limited",
            "operating_status": "Not Applicable" if sector in OPERATING_NOT_APPLICABLE else ("Available" if history_count["operating_profit"] else "Unavailable"),
            "source": "J-Quants API V2 Financial Summary"}
