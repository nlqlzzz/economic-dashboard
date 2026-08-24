from __future__ import annotations

import pandas as pd


FORWARD_HORIZONS = {1: "1か月後", 3: "3か月後", 6: "6か月後"}

REGIME_ASSET_DEFINITIONS = {
    "S&P 500": ("S&P 500指数", "return"),
    "NASDAQ": ("NASDAQ総合指数", "return"),
    "SOX": ("SOX指数", "return"),
    "日経平均": ("日経平均株価", "return"),
    "TOPIX（1306 ETF近似）": ("TOPIX連動ETF（1306）", "return"),
    "USD/JPY": ("USD/JPY", "return"),
    "Gold": ("Gold先物", "return"),
    "米10年金利": ("UST 10Y", "change_bp"),
}


def current_regime_labels(regime: dict[str, object]) -> dict[str, str]:
    """最新マクロ判定を履歴と同じ4評価の形式へ変換する。"""
    return {
        "景気": regime["labor"]["status"],
        "物価": regime["inflation"]["status"],
        "金融政策": regime["policy"]["status"],
        "イールドカーブ": regime["curve"]["status"],
    }


def analyze_regime_forward_performance(
    regime_history: pd.DataFrame,
    current_labels: dict[str, str],
    asset_series: dict[str, pd.Series],
    methods_by_asset: dict[str, str],
    minimum_matching_dimensions: int = 4,
    horizons: tuple[int, ...] = (1, 3, 6),
    low_sample_threshold: int = 12,
) -> pd.DataFrame:
    """現在と同一または近い過去レジーム後の資産パフォーマンスを集計する。"""
    dimensions = list(current_labels)
    missing_dimensions = [
        dimension for dimension in dimensions if dimension not in regime_history
    ]
    if missing_dimensions:
        raise ValueError(f"レジーム履歴に評価軸がありません: {missing_dimensions}")
    if not 1 <= minimum_matching_dimensions <= len(dimensions):
        raise ValueError("一致条件は1以上、評価軸数以下にしてください。")

    similarity = sum(
        regime_history[dimension].eq(current_labels[dimension]).astype(int)
        for dimension in dimensions
    )
    matching_dates = regime_history.index[
        similarity >= minimum_matching_dimensions
    ]
    rows = []
    for asset_name, series in asset_series.items():
        method = methods_by_asset.get(asset_name, "return")
        monthly = _monthly_last(series)
        for months in horizons:
            forward = _forward_values(monthly, months, method)
            sample = forward.reindex(matching_dates).dropna()
            count = len(sample)
            rows.append(
                {
                    "資産": asset_name,
                    "期間": FORWARD_HORIZONS.get(months, f"{months}か月後"),
                    "平均": None if sample.empty else float(sample.mean()),
                    "中央値": None if sample.empty else float(sample.median()),
                    "上昇確率": None if sample.empty else float((sample > 0).mean() * 100),
                    "サンプル数": count,
                    "注意": "サンプル少" if count < low_sample_threshold else "",
                    "単位": "bp" if method == "change_bp" else "%",
                }
            )
    return pd.DataFrame(rows)


def _monthly_last(series: pd.Series) -> pd.Series:
    clean = series.dropna().sort_index().copy()
    clean.index = pd.to_datetime(clean.index).to_period("M").to_timestamp("M")
    return clean.groupby(level=0).last()


def _forward_values(series: pd.Series, months: int, method: str) -> pd.Series:
    future = series.shift(-months)
    if method == "return":
        return (future / series - 1) * 100
    if method == "change_bp":
        return (future - series) * 100
    raise ValueError(f"未対応の将来変化計算です: {method}")
