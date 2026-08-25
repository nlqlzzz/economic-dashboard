from __future__ import annotations

import math
from collections.abc import Callable

import pandas as pd


STRESS_INPUT_INDICATORS = (
    "VIX指数",
    "S&P 500指数",
    "UST 10Y",
    "USD/JPY",
)


def calculate_market_stress(
    series_by_name: dict[str, pd.Series],
    lookback_years: int = 5,
    minimum_history: int = 252,
    minimum_components: int = 3,
) -> dict[str, object]:
    """既存市場系列の現在値を過去分布と比較し、0〜100のストレス度を返す。"""
    component_definitions: list[
        tuple[str, str, str, Callable[[pd.Series], pd.Series]]
    ] = [
        ("VIX水準", "VIX指数", "pt", _level),
        ("S&P 500 20日実現ボラ", "S&P 500指数", "%", _realized_volatility),
        ("S&P 500 60日高値からの下落", "S&P 500指数", "%", _drawdown),
        ("米10年金利 日次変化幅", "UST 10Y", "bp", _yield_shock),
        ("USD/JPY 20日実現ボラ", "USD/JPY", "%", _realized_volatility),
    ]
    rows: list[dict[str, object]] = []
    unavailable: list[str] = []
    for component_name, indicator_name, unit, transform in component_definitions:
        source = series_by_name.get(indicator_name)
        if source is None:
            unavailable.append(f"{component_name}: {indicator_name}を取得できませんでした")
            continue
        metric = _clean_metric(transform(source))
        if metric.empty:
            unavailable.append(
                f"{component_name}: 計算可能な過去観測が不足しています（0件）"
            )
            continue
        current_date = pd.Timestamp(metric.index[-1])
        history_start = current_date - pd.DateOffset(years=lookback_years)
        history = metric.loc[history_start:current_date].iloc[:-1]
        if len(history) < minimum_history:
            unavailable.append(
                f"{component_name}: 過去観測が不足しています（{len(history)}件）"
            )
            continue
        current_value = float(metric.iloc[-1])
        percentile = float((history <= current_value).mean() * 100)
        rows.append(
            {
                "項目": component_name,
                "実測値": current_value,
                "単位": unit,
                "過去5年percentile": percentile,
                "サンプル数": len(history),
                "基準日": current_date,
            }
        )

    if len(rows) < minimum_components:
        return {
            "score": None,
            "level": "算出不可",
            "coverage": len(rows),
            "total_components": len(component_definitions),
            "components": pd.DataFrame(rows),
            "unavailable": unavailable,
        }

    equal_weight = 1 / len(rows)
    for row in rows:
        row["ウェイト"] = equal_weight * 100
        row["スコア寄与"] = float(row["過去5年percentile"]) * equal_weight
    components = pd.DataFrame(rows)
    score = float(components["スコア寄与"].sum())
    return {
        "score": score,
        "level": stress_level(score),
        "coverage": len(rows),
        "total_components": len(component_definitions),
        "components": components,
        "unavailable": unavailable,
    }


def stress_level(score: float) -> str:
    if score >= 75:
        return "高ストレス"
    if score >= 50:
        return "ストレス上昇"
    if score >= 25:
        return "中立"
    return "低ストレス"


def _clean_metric(series: pd.Series) -> pd.Series:
    clean = series.replace([float("inf"), float("-inf")], pd.NA).dropna().copy()
    clean.index = pd.DatetimeIndex(clean.index).tz_localize(None).normalize()
    return clean[~clean.index.duplicated(keep="last")].sort_index()


def _level(series: pd.Series) -> pd.Series:
    return series.astype(float)


def _realized_volatility(series: pd.Series) -> pd.Series:
    returns = series.astype(float).sort_index().pct_change(fill_method=None)
    return returns.rolling(20).std() * math.sqrt(252) * 100


def _drawdown(series: pd.Series) -> pd.Series:
    clean = series.astype(float).sort_index()
    return ((1 - clean / clean.rolling(60).max()) * 100).clip(lower=0)


def _yield_shock(series: pd.Series) -> pd.Series:
    return series.astype(float).sort_index().diff().abs() * 100
