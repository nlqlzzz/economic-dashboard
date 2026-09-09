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
    operating_yoy = _metric_yoy(latest, "operating_profit")
    if len(yoy) < 2: momentum = "Unavailable"
    elif positive >= 2 and negative == 0 and (operating_yoy is None or operating_yoy >= 0): momentum = "Strong"
    elif positive >= 2: momentum = "Improving"
    elif negative >= 2: momentum = "Weakening"
    else: momentum = "Mixed"
    return {"status": "Available", "latest": latest, "history": standalone, "forecast": forecast,
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
        return _trim(amount / 1_000_000_000_000) + "兆円"
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


def _trim(value: float) -> str:
    return f"{value:,.1f}".rstrip("0").rstrip(".")
