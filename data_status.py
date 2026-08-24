from __future__ import annotations

import pandas as pd

from utils import latest_value


def build_data_status_frame(
    series_by_name: dict[str, pd.Series],
    indicator_metadata: dict[str, dict[str, object]],
    source_labels: dict[str, str],
) -> pd.DataFrame:
    """選択中の各指標について観測日・取得時刻・取得元を一覧化する。"""
    rows = []
    for name, series in series_by_name.items():
        info = indicator_metadata[name]
        observed_at, _ = latest_value(series)
        actual_source = str(series.attrs.get("source", info["source"]))
        actual_ticker = str(series.attrs.get("ticker", info["ticker"]))
        fetched_at = series.attrs.get("fetched_at")
        rows.append(
            {
                "指標": name,
                "データ最終日": pd.Timestamp(observed_at).strftime("%Y-%m-%d"),
                "取得確認日時": _format_fetched_at(fetched_at),
                "データ元": source_labels.get(actual_source, actual_source),
                "実ティッカー": actual_ticker,
                "取得区分": "代替（近似）" if series.attrs.get("is_fallback") else "一次",
            }
        )
    return pd.DataFrame(rows)


def _format_fetched_at(value: object) -> str:
    if value is None:
        return "—"
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("Asia/Tokyo")
    else:
        timestamp = timestamp.tz_convert("Asia/Tokyo")
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")
