from __future__ import annotations

import pandas as pd

from utils import latest_value


FRESHNESS_POLICIES = {
    "business_daily": {
        "label": "営業日次",
        "maximum_lag": 2,
        "lag_unit": "営業日",
    },
    "calendar_daily": {
        "label": "暦日次",
        "maximum_lag": 2,
        "lag_unit": "日",
    },
    "monthly": {
        "label": "月次",
        "maximum_lag": 62,
        "lag_unit": "日",
    },
}


def build_data_status_frame(
    series_by_name: dict[str, pd.Series],
    indicator_metadata: dict[str, dict[str, object]],
    source_labels: dict[str, str],
    as_of: object | None = None,
) -> pd.DataFrame:
    """選択中の各指標について観測日・鮮度・取得元を一覧化する。"""
    reference_date = _reference_date(as_of)
    rows = []
    for name, series in series_by_name.items():
        info = indicator_metadata[name]
        observed_at, _ = latest_value(series)
        frequency = str(info.get("update_frequency", "business_daily"))
        freshness = assess_data_freshness(observed_at, frequency, reference_date)
        actual_source = str(series.attrs.get("source", info["source"]))
        actual_ticker = str(series.attrs.get("ticker", info["ticker"]))
        fetched_at = series.attrs.get("fetched_at")
        rows.append(
            {
                "指標": name,
                "データ最終日": pd.Timestamp(observed_at).strftime("%Y-%m-%d"),
                "更新頻度": freshness["更新頻度"],
                "鮮度": freshness["鮮度"],
                "遅延幅": freshness["遅延幅"],
                "取得試行": _format_fetch_attempts(series.attrs.get("fetch_attempts")),
                "取得時間": _format_fetch_duration(
                    series.attrs.get("fetch_duration_seconds")
                ),
                "取得確認日時": _format_fetched_at(fetched_at),
                "データ元": source_labels.get(actual_source, actual_source),
                "実ティッカー": actual_ticker,
                "取得区分": "代替（近似）" if series.attrs.get("is_fallback") else "一次",
            }
        )
    return pd.DataFrame(rows)


def assess_data_freshness(
    observed_at: object, update_frequency: str, as_of: object | None = None
) -> dict[str, object]:
    """更新頻度ごとの通常ラグを考慮して、最終観測日の鮮度を判定する。"""
    if update_frequency not in FRESHNESS_POLICIES:
        raise ValueError(f"未対応の更新頻度です: {update_frequency}")

    observed_date = pd.Timestamp(observed_at).tz_localize(None).normalize()
    reference_date = _reference_date(as_of)
    policy = FRESHNESS_POLICIES[update_frequency]
    if update_frequency == "business_daily":
        lag = len(
            pd.bdate_range(
                start=observed_date + pd.offsets.BDay(1), end=reference_date
            )
        )
    else:
        lag = max(0, int((reference_date - observed_date).days))

    is_stale = lag > int(policy["maximum_lag"])
    return {
        "更新頻度": policy["label"],
        "鮮度": "⚠ 要確認" if is_stale else "正常",
        "遅延幅": f"{lag}{policy['lag_unit']}",
        "要確認": is_stale,
    }


def _reference_date(value: object | None) -> pd.Timestamp:
    if value is None:
        return pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None).normalize()
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("Asia/Tokyo").tz_localize(None)
    return timestamp.normalize()


def _format_fetched_at(value: object) -> str:
    if value is None:
        return "—"
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("Asia/Tokyo")
    else:
        timestamp = timestamp.tz_convert("Asia/Tokyo")
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def _format_fetch_attempts(value: object) -> str:
    if value is None:
        return "—"
    attempts = int(value)
    return f"{attempts}回（再試行）" if attempts > 1 else "1回"


def _format_fetch_duration(value: object) -> str:
    if value is None:
        return "—"
    return f"{float(value):.2f}秒"
