from __future__ import annotations

import pandas as pd


CORRELATION_METHOD_LABELS = {
    "weekly_return": "騰落率（%）",
    "weekly_change": "変化幅（pt）",
    "monthly_change": "変化幅（pt）",
}

DAILY_CHANGE_LABELS = {
    "return": "日次騰落率（%）",
    "change": "日次変化幅（pt）",
}


def build_daily_change_frame(
    series_by_name: dict[str, pd.Series], methods_by_name: dict[str, str]
) -> tuple[pd.DataFrame, dict[str, str]]:
    """価格は日次騰落率、金利・金利差は日次変化幅へ変換する。"""
    transformed: dict[str, pd.Series] = {}
    labels: dict[str, str] = {}
    for name, series in series_by_name.items():
        method = methods_by_name.get(name, "return")
        cleaned = series.sort_index().dropna()
        if method == "return":
            transformed[name] = cleaned.pct_change(fill_method=None) * 100
        elif method == "change":
            transformed[name] = cleaned.diff()
        else:
            raise ValueError(f"未対応の日次変換方法です: {method}")
        labels[name] = DAILY_CHANGE_LABELS[method]

    frame = pd.concat(transformed, axis=1).sort_index()
    return frame.replace([float("inf"), float("-inf")], pd.NA), labels


def correlation_change_summary(
    left: pd.Series,
    right: pd.Series,
    windows: tuple[int, ...] = (20, 60),
    comparison_offsets: tuple[int, ...] = (21, 63),
) -> pd.DataFrame:
    """現在のローリング相関を過去時点・長期分布と比較する。"""
    pair = pd.concat({"left": left, "right": right}, axis=1).dropna()
    rows: list[dict[str, object]] = []
    for window in windows:
        rolling = pair["left"].rolling(window).corr(pair["right"]).dropna()
        if rolling.empty:
            continue

        current = float(rolling.iloc[-1])
        row: dict[str, object] = {
            "期間": f"{window}日",
            "現在": current,
            "percentile": float((rolling <= current).mean() * 100),
            "相関推移数": len(rolling),
            "共通観測数": len(pair),
        }
        for offset in comparison_offsets:
            prior = float(rolling.iloc[-offset - 1]) if len(rolling) > offset else None
            row[f"{offset}日前"] = prior
            row[f"{offset}日差"] = None if prior is None else current - prior
        rows.append(row)
    return pd.DataFrame(rows)


def correlation_change_alerts(
    summary: pd.DataFrame,
    change_threshold: float = 0.25,
    tail_percentile: float = 10,
) -> list[str]:
    """1か月相当の急変または長期分布の両端を短い注意文にする。"""
    alerts: list[str] = []
    for row in summary.to_dict("records"):
        change = row.get("21日差")
        percentile = row.get("percentile")
        if change is not None and abs(float(change)) >= change_threshold:
            direction = "上昇" if float(change) > 0 else "低下"
            alerts.append(
                f"{row['期間']}相関が1か月前から{abs(float(change)):.2f}{direction}"
            )
        if percentile is not None and (
            float(percentile) <= tail_percentile
            or float(percentile) >= 100 - tail_percentile
        ):
            side = "下位" if float(percentile) <= tail_percentile else "上位"
            tail = float(percentile) if side == "下位" else 100 - float(percentile)
            alerts.append(f"{row['期間']}相関は過去分布の{side}{tail:.0f}%")
    return alerts


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


def build_correlation_frame(
    series_by_name: dict[str, pd.Series], methods_by_name: dict[str, str]
) -> tuple[pd.DataFrame, dict[str, str], str]:
    """指標特性に応じた変化量を、比較可能な共通頻度にそろえる。"""
    is_monthly = any(
        methods_by_name.get(name, "weekly_return") == "monthly_change"
        for name in series_by_name
    )
    frequency_label = "月次" if is_monthly else "週次"
    resample_rule = pd.offsets.MonthEnd() if is_monthly else "W-FRI"

    transformed: dict[str, pd.Series] = {}
    labels: dict[str, str] = {}
    for name, series in series_by_name.items():
        method = methods_by_name.get(name, "weekly_return")
        period_end = series.resample(resample_rule).last()
        if method == "weekly_return":
            transformed[name] = period_end.pct_change(fill_method=None) * 100
        else:
            transformed[name] = period_end.diff()
        labels[name] = f"{frequency_label}{CORRELATION_METHOD_LABELS[method]}"

    frame = pd.concat(transformed, axis=1).sort_index()
    return (
        frame.replace([float("inf"), float("-inf")], pd.NA),
        labels,
        frequency_label,
    )


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
                    "データ数": len(pair),
                }
            )
    return pd.DataFrame(rows, columns=["指標1", "指標2", "相関係数", "データ数"])


def linear_regression_summary(
    left: pd.Series, right: pd.Series
) -> tuple[float, float, float] | None:
    """2系列の傾き、切片、相関係数を返す。回帰不能な場合はNone。"""
    pair = pd.concat({"left": left, "right": right}, axis=1).dropna()
    if len(pair) < 2 or pair["left"].nunique() < 2:
        return None

    left_variance = pair["left"].var()
    if pd.isna(left_variance) or left_variance == 0:
        return None

    slope = pair["left"].cov(pair["right"]) / left_variance
    intercept = pair["right"].mean() - slope * pair["left"].mean()
    correlation = pair["left"].corr(pair["right"])
    if pd.isna(slope) or pd.isna(intercept) or pd.isna(correlation):
        return None
    return float(slope), float(intercept), float(correlation)


def rolling_correlation(
    left: pd.Series, right: pd.Series, window: int
) -> pd.Series:
    """欠損のない共通観測値を使い、指定期間のローリング相関を返す。"""
    pair = pd.concat({"left": left, "right": right}, axis=1).dropna()
    if len(pair) < window:
        return pd.Series(dtype=float)
    return pair["left"].rolling(window).corr(pair["right"]).dropna()


def _correlation_for_last(returns: pd.DataFrame, weeks: int) -> float | None:
    window = returns.tail(weeks)
    if len(window) < 2:
        return None
    value = window["left"].corr(window["right"])
    return None if pd.isna(value) else float(value)
