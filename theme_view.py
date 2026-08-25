from __future__ import annotations

import pandas as pd

from utils import change_from_previous, latest_value, percent_change_since


THEME_DEFINITIONS = {
    "半導体": {
        "description": "半導体株の強弱を、米国株・金利・市場心理とまとめて確認します。",
        "indicators": ["SOX指数", "NASDAQ総合指数", "S&P 500指数", "UST 10Y", "VIX指数"],
        "relative_pair": ("SOX指数", "S&P 500指数"),
        "correlation_pair": ("SOX指数", "UST 10Y"),
        "event_types": ["cpi", "fomc"],
    },
    "米国株": {
        "description": "主要株価指数を、長期金利とリスク警戒度とともに確認します。",
        "indicators": ["S&P 500指数", "NASDAQ総合指数", "SOX指数", "UST 10Y", "VIX指数"],
        "relative_pair": ("NASDAQ総合指数", "S&P 500指数"),
        "correlation_pair": ("NASDAQ総合指数", "UST 10Y"),
        "event_types": ["cpi", "employment", "fomc"],
    },
    "日本株": {
        "description": "日本株の動きを、為替と日米金利の両面から確認します。",
        "indicators": ["日経平均株価", "TOPIX連動ETF（1306）", "USD/JPY", "JGB 10Y", "UST 10Y"],
        "relative_pair": ("日経平均株価", "TOPIX連動ETF（1306）"),
        "correlation_pair": ("日経平均株価", "USD/JPY"),
        "event_types": ["cpi", "employment", "fomc"],
    },
    "円": {
        "description": "円相場を、日米金利差と市場のリスク警戒度から確認します。",
        "indicators": ["USD/JPY", "EUR/JPY", "日米金利差 2Y（米国−日本）", "日米金利差 10Y（米国−日本）", "VIX指数"],
        "relative_pair": ("USD/JPY", "EUR/JPY"),
        "correlation_pair": ("USD/JPY", "日米金利差 10Y（米国−日本）"),
        "event_types": ["cpi", "employment", "fomc"],
    },
    "Gold": {
        "description": "金を、他の貴金属・米金利・ドル・市場心理とまとめて確認します。",
        "indicators": ["金先物", "銀先物", "プラチナ先物", "UST 10Y", "USD/JPY", "VIX指数"],
        "relative_pair": ("金先物", "銀先物"),
        "correlation_pair": ("金先物", "UST 10Y"),
        "event_types": ["cpi", "fomc"],
    },
}


def build_theme_snapshot(
    series_by_name: dict[str, pd.Series],
    indicator_metadata: dict[str, dict[str, object]],
) -> pd.DataFrame:
    """テーマ内の指標を直前観測値・1か月変化の一覧にする。"""
    rows: list[dict[str, object]] = []
    for name, series in series_by_name.items():
        clean = series.dropna().sort_index()
        if clean.empty:
            continue
        observed_at, value = latest_value(clean)
        metadata = indicator_metadata[name]
        is_yield = metadata["category"] == "金利"
        previous = change_from_previous(clean)
        if is_yield:
            previous_change = None if previous is None else previous[0] * 100
            month_base = clean.loc[: observed_at - pd.DateOffset(months=1)]
            month_change = None if month_base.empty else (value - float(month_base.iloc[-1])) * 100
            change_unit = "bp"
        else:
            previous_change = None if previous is None else previous[1]
            month_change = percent_change_since(clean, observed_at - pd.DateOffset(months=1))
            change_unit = "%"
        rows.append(
            {
                "指標": name,
                "最新値": float(value),
                "単位": clean.attrs.get("unit", metadata["unit"]),
                "直前変化": previous_change,
                "1か月変化": month_change,
                "変化単位": change_unit,
                "データ日": observed_at,
            }
        )
    return pd.DataFrame(rows)


def relative_strength(
    left: pd.Series, right: pd.Series
) -> tuple[pd.Series, float | None]:
    """2資産の相対強度を開始日=100で返し、直近1か月の変化も計算する。"""
    pair = pd.concat({"left": left, "right": right}, axis=1).dropna()
    if pair.empty or pair.iloc[0].eq(0).any():
        return pd.Series(dtype=float), None
    ratio = (pair["left"] / pair["left"].iloc[0]) / (
        pair["right"] / pair["right"].iloc[0]
    ) * 100
    one_month = percent_change_since(ratio, ratio.index[-1] - pd.DateOffset(months=1))
    return ratio, one_month


def upcoming_theme_events(
    events: pd.DataFrame,
    event_types: list[str],
    now: pd.Timestamp,
    limit: int = 3,
) -> pd.DataFrame:
    """テーマに関連する今後のイベントを近い順に返す。"""
    if events.empty:
        return events.copy()
    event_timezone = events["datetime"].dt.tz
    comparable_now = now
    if event_timezone is not None and now.tzinfo is None:
        comparable_now = now.tz_localize(event_timezone)
    selected = events[
        events["event_type"].isin(event_types) & (events["datetime"] >= comparable_now)
    ].head(limit)
    return selected.reset_index(drop=True)
