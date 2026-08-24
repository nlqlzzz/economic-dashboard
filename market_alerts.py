from __future__ import annotations

import pandas as pd

from utils import change_from_previous, latest_value, percent_change_since


def detect_market_moves(
    series_by_name: dict[str, pd.Series],
    thresholds: dict[str, float],
) -> pd.DataFrame:
    """設定した騰落率以上に動いた指標を重要度順で返す。"""
    alerts = []
    for name, series in series_by_name.items():
        observed_at, _ = latest_value(series)
        previous_change = change_from_previous(series)
        rates = {
            "直前観測値比": None if previous_change is None else previous_change[1],
            "1週間": percent_change_since(
                series, observed_at - pd.Timedelta(days=7)
            ),
            "1か月": percent_change_since(
                series, observed_at - pd.DateOffset(months=1)
            ),
        }
        for period, rate in rates.items():
            threshold = thresholds[period]
            if rate is None or abs(rate) < threshold:
                continue
            alerts.append(
                {
                    "指標": name,
                    "期間": period,
                    "方向": "上昇" if rate > 0 else "下落" if rate < 0 else "横ばい",
                    "騰落率": float(rate),
                    "閾値": float(threshold),
                    "データ日": observed_at,
                    "重要度": abs(float(rate)) / threshold,
                }
            )
    if not alerts:
        return pd.DataFrame(
            columns=["指標", "期間", "方向", "騰落率", "閾値", "データ日", "重要度"]
        )
    return pd.DataFrame(alerts).sort_values(
        ["重要度", "騰落率"], ascending=[False, False]
    ).reset_index(drop=True)
