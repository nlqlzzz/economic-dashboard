from __future__ import annotations

import pandas as pd


EVENT_SOURCE_URLS = {
    "CPI": "https://www.bls.gov/schedule/",
    "米雇用統計": "https://www.bls.gov/schedule/",
    "FOMC": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    "PCE": "https://www.bea.gov/news/schedule/",
}

EVENT_HISTORY = {
    "CPI": [
        "2024-01-11", "2024-02-13", "2024-03-12", "2024-04-10",
        "2024-05-15", "2024-06-12", "2024-07-11", "2024-08-14",
        "2024-09-11", "2024-10-10", "2024-11-13", "2024-12-11",
        "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-10",
        "2025-05-13", "2025-06-11", "2025-07-15", "2025-08-12",
        "2025-09-11", "2025-10-24", "2025-12-18",
    ],
    "米雇用統計": [
        "2024-01-05", "2024-02-02", "2024-03-08", "2024-04-05",
        "2024-05-03", "2024-06-07", "2024-07-05", "2024-08-02",
        "2024-09-06", "2024-10-04", "2024-11-01", "2024-12-06",
        "2025-01-10", "2025-02-07", "2025-03-07", "2025-04-04",
        "2025-05-02", "2025-06-06", "2025-07-03", "2025-08-01",
        "2025-09-05", "2025-11-20", "2025-12-16",
    ],
    "FOMC": [
        "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
        "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
        "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
        "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    ],
    "PCE": [
        "2024-01-26", "2024-02-29", "2024-03-29", "2024-04-26",
        "2024-05-31", "2024-06-28", "2024-07-26", "2024-08-30",
        "2024-09-27", "2024-10-31", "2024-11-27", "2024-12-20",
        "2025-01-31", "2025-02-28", "2025-03-28", "2025-04-30",
        "2025-05-30", "2025-06-27", "2025-07-31", "2025-08-29",
        "2025-09-26", "2025-12-05",
    ],
}

EVENT_ASSET_DEFINITIONS = {
    "S&P 500": ("S&P 500指数", "return"),
    "NASDAQ": ("NASDAQ総合指数", "return"),
    "SOX": ("SOX指数", "return"),
    "USD/JPY": ("USD/JPY", "return"),
    "米10年金利": ("UST 10Y", "change_bp"),
}

EVENT_HORIZONS = {0: "当日", 1: "翌営業日", 5: "5営業日後", 20: "20営業日後"}


def analyze_event_reactions(
    event_dates: list[str] | pd.DatetimeIndex,
    asset_series: dict[str, pd.Series],
    methods_by_asset: dict[str, str],
    horizons: tuple[int, ...] = (0, 1, 5, 20),
    low_sample_threshold: int = 12,
) -> pd.DataFrame:
    """イベント直前の終値から各営業日後までの変化を資産別に集計する。"""
    dates = pd.DatetimeIndex(pd.to_datetime(event_dates)).normalize()
    rows: list[dict[str, object]] = []
    for asset_name, series in asset_series.items():
        clean = series.dropna().sort_index()
        clean.index = pd.DatetimeIndex(clean.index).tz_localize(None).normalize()
        method = methods_by_asset.get(asset_name, "return")
        unit = "%" if method == "return" else "bp" if method == "change_bp" else None
        if unit is None:
            raise ValueError(f"未対応の計算方法です: {method}")
        for horizon in horizons:
            reactions: list[float] = []
            for event_date in dates:
                before = clean.loc[clean.index < event_date]
                on_or_after = clean.loc[clean.index >= event_date]
                if before.empty or len(on_or_after) <= horizon:
                    continue
                base = float(before.iloc[-1])
                target = float(on_or_after.iloc[horizon])
                if method == "return":
                    if base == 0:
                        continue
                    reaction = (target / base - 1) * 100
                else:
                    reaction = (target - base) * 100
                reactions.append(float(reaction))

            sample_count = len(reactions)
            values = pd.Series(reactions, dtype=float)
            rows.append(
                {
                    "資産": asset_name,
                    "期間": EVENT_HORIZONS[horizon],
                    "平均": None if values.empty else float(values.mean()),
                    "中央値": None if values.empty else float(values.median()),
                    "上昇確率": None if values.empty else float((values > 0).mean() * 100),
                    "サンプル数": sample_count,
                    "単位": unit,
                    "注意": "サンプル少" if sample_count < low_sample_threshold else "",
                }
            )
    return pd.DataFrame(rows)
