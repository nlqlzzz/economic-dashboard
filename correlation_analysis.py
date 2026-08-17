from __future__ import annotations

import pandas as pd


def weekly_return_correlation(
    left: pd.Series, right: pd.Series, rolling_weeks: int = 13
) -> tuple[pd.Series, float | None, float | None, int]:
    """2系列を週次騰落率にそろえ、相関係数とその推移を返す。"""
    weekly = pd.concat(
        {
            "left": left.resample("W-FRI").last(),
            "right": right.resample("W-FRI").last(),
        },
        axis=1,
    ).dropna()
    returns = weekly.pct_change(fill_method=None).dropna()

    if len(returns) < 2:
        return pd.Series(dtype=float), None, None, len(returns)

    correlation_3m = _correlation_for_last(returns, 13)
    correlation_1y = _correlation_for_last(returns, 52)
    rolling = returns["left"].rolling(rolling_weeks).corr(returns["right"]).dropna()
    return rolling, correlation_3m, correlation_1y, len(returns)


def build_weekly_return_frame(series_by_name: dict[str, pd.Series]) -> pd.DataFrame:
    """各価格系列を金曜終値ベースの週次騰落率にそろえる。"""
    weekly = pd.concat(
        {
            name: series.resample("W-FRI").last()
            for name, series in series_by_name.items()
        },
        axis=1,
    ).sort_index()
    return weekly.pct_change(fill_method=None).replace([float("inf"), float("-inf")], pd.NA)


def correlation_pairs(returns: pd.DataFrame, minimum_observations: int = 8) -> pd.DataFrame:
    """相関行列を、比較しやすい2指標ずつの一覧に変換する。"""
    rows: list[dict[str, object]] = []
    names = list(returns.columns)
    for position, left_name in enumerate(names):
        for right_name in names[position + 1 :]:
            pair = returns[[left_name, right_name]].dropna()
            if len(pair) < minimum_observations:
                continue
            rows.append(
                {
                    "指標1": left_name,
                    "指標2": right_name,
                    "相関係数": pair[left_name].corr(pair[right_name]),
                    "データ数（週）": len(pair),
                }
            )
    return pd.DataFrame(rows, columns=["指標1", "指標2", "相関係数", "データ数（週）"])


def _correlation_for_last(returns: pd.DataFrame, weeks: int) -> float | None:
    window = returns.tail(weeks)
    if len(window) < 2:
        return None
    value = window["left"].corr(window["right"])
    return None if pd.isna(value) else float(value)
