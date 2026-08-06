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
