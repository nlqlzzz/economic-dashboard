from __future__ import annotations

import pandas as pd


def calc_yoy(series: pd.Series, periods: int = 12) -> pd.Series:
    """月次系列の前年比をパーセントで返す。"""
    result = series.pct_change(periods=periods, fill_method=None) * 100
    result.name = f"{series.name}（前年比）"
    return result.dropna()


def normalize(series: pd.Series) -> pd.Series:
    """表示期間の最初の値を100とする指数へ変換する。"""
    clean = series.dropna()
    if clean.empty:
        return clean
    result = clean / clean.iloc[0] * 100
    result.name = series.name
    return result


def latest_value(series: pd.Series) -> tuple[pd.Timestamp, float]:
    """最新の観測日と値を返す。空の系列はエラーにする。"""
    clean = series.dropna()
    if clean.empty:
        raise ValueError("表示できるデータがありません。")
    return clean.index[-1], float(clean.iloc[-1])


def change_from_previous(series: pd.Series) -> tuple[float, float] | None:
    """直前の観測値からの変化幅と騰落率を返す。"""
    clean = series.dropna()
    if len(clean) < 2:
        return None

    previous = float(clean.iloc[-2])
    latest = float(clean.iloc[-1])
    if previous == 0:
        return None
    return latest - previous, (latest / previous - 1) * 100


def percent_change_since(series: pd.Series, reference_date: pd.Timestamp) -> float | None:
    """指定日以前で最も新しい観測値を基準に、最新値までの騰落率を返す。"""
    clean = series.dropna()
    if clean.empty:
        return None

    historical = clean.loc[:pd.Timestamp(reference_date)]
    if historical.empty or historical.index[-1] >= clean.index[-1]:
        return None

    reference_value = float(historical.iloc[-1])
    latest = float(clean.iloc[-1])
    if reference_value == 0:
        return None
    return (latest / reference_value - 1) * 100
