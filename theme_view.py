from __future__ import annotations

import pandas as pd

from price_quality import PriceQualityResult, inspect_price_series
from utils import change_from_previous, latest_value, percent_change_since


THEME_DEFINITIONS = {
    "半導体": {
        "description": "日米半導体株の値動きと、日本の実体経済・在庫循環・設備投資をまとめて確認します。",
        "indicators": [
            "SOX指数",
            "NASDAQ総合指数",
            "S&P 500指数",
            "東京エレクトロン（8035）",
            "アドバンテスト（6857）",
            "ディスコ（6146）",
            "キオクシア（285A）",
            "USD/JPY",
            "UST 10Y",
            "VIX指数",
        ],
        "relative_pair": ("SOX指数", "S&P 500指数"),
        "relative_pairs": [
            ("SOX指数", "S&P 500指数"),
            ("東京エレクトロン（8035）", "SOX指数"),
            ("アドバンテスト（6857）", "SOX指数"),
            ("ディスコ（6146）", "SOX指数"),
            ("キオクシア（285A）", "SOX指数"),
        ],
        "correlation_pair": ("SOX指数", "UST 10Y"),
        "correlation_pairs": [
            ("SOX指数", "UST 10Y"),
            ("東京エレクトロン（8035）", "SOX指数"),
            ("アドバンテスト（6857）", "SOX指数"),
            ("ディスコ（6146）", "SOX指数"),
            ("キオクシア（285A）", "SOX指数"),
            ("東京エレクトロン（8035）", "USD/JPY"),
            ("アドバンテスト（6857）", "USD/JPY"),
            ("ディスコ（6146）", "USD/JPY"),
            ("キオクシア（285A）", "USD/JPY"),
        ],
        "event_types": ["cpi", "fomc"],
    },
    "米国株": {
        "description": "主要株価指数を、長期金利とリスク警戒度とともに確認します。",
        "indicators": ["S&P 500指数", "NASDAQ総合指数", "SOX指数", "UST 10Y", "VIX指数"],
        "relative_pair": ("NASDAQ総合指数", "S&P 500指数"),
        "correlation_pair": ("NASDAQ総合指数", "UST 10Y"),
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


def theme_relationship_pairs(
    theme: dict[str, object], relationship: str
) -> list[tuple[str, str]]:
    """テーマの比較候補を返し、従来の単一ペア定義も受け付ける。"""
    configured = theme.get(f"{relationship}_pairs")
    if isinstance(configured, list):
        pairs = [
            (str(pair[0]), str(pair[1]))
            for pair in configured
            if isinstance(pair, (list, tuple)) and len(pair) == 2
        ]
        if pairs:
            return pairs
    fallback = theme.get(f"{relationship}_pair")
    if isinstance(fallback, (list, tuple)) and len(fallback) == 2:
        return [(str(fallback[0]), str(fallback[1]))]
    return []


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
    result = relative_strength_with_quality(left, right)
    return result["series"], result["one_month"]


def relative_strength_with_quality(left: pd.Series, right: pd.Series) -> dict[str, object]:
    """Calculate only from quality-checked, date-aligned price observations."""
    left_quality = inspect_price_series(left)
    right_quality = inspect_price_series(right)
    if not left_quality.usable or not right_quality.usable:
        return {
            "series": pd.Series(dtype=float), "one_month": None,
            "left_quality": left_quality, "right_quality": right_quality,
            "reason": "価格系列に確認できない極端変動があるため、相対強度分析を表示できません。",
        }
    # concat/dropna is deliberately after the exclusions: neither side may retain
    # a price for a removed observation date.
    pair = pd.concat({"left": left_quality.series, "right": right_quality.series}, axis=1).dropna()
    if pair.empty or pair.iloc[0].eq(0).any():
        return {"series": pd.Series(dtype=float), "one_month": None,
                "left_quality": left_quality, "right_quality": right_quality,
                "reason": "共通する有効な価格観測が不足しています。"}
    ratio = (pair["left"] / pair["left"].iloc[0]) / (
        pair["right"] / pair["right"].iloc[0]
    ) * 100
    one_month = percent_change_since(ratio, ratio.index[-1] - pd.DateOffset(months=1))
    return {"series": ratio, "one_month": one_month,
            "left_quality": left_quality, "right_quality": right_quality, "reason": ""}


def quality_check_theme_series(
    series_by_name: dict[str, pd.Series], indicator_metadata: dict[str, dict[str, object]],
) -> tuple[dict[str, pd.Series], dict[str, PriceQualityResult]]:
    """Clean temporary price scale breaks once for all theme price calculations."""
    usable: dict[str, pd.Series] = {}
    results: dict[str, PriceQualityResult] = {}
    for name, series in series_by_name.items():
        if indicator_metadata[name].get("category") == "金利":
            usable[name] = series
            continue
        result = inspect_price_series(series)
        results[name] = result
        if result.usable:
            usable[name] = result.series
    return usable, results


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
