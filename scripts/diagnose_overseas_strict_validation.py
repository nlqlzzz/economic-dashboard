from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_loader import load_korea_semiconductor_monthly_history, load_yfinance_batch
from semiconductor_validation import (
    add_global_condition_signals,
    analyze_release_aware_correlation,
    analyze_release_aware_returns,
    build_overseas_validation_signals,
)
from taiwan_export_orders_archive import load_taiwan_archive_snapshot


ASSETS = {
    "SOX指数": "^SOX",
    "東京エレクトロン（8035）": "8035.T",
    "アドバンテスト（6857）": "6857.T",
    "ディスコ（6146）": "6146.T",
    "キオクシア（285A）": "285A.T",
}
TAIWAN_SERIES = (
    "taiwan_electronic_export_orders",
    "taiwan_information_communication_export_orders",
)


def _records(frame: pd.DataFrame, columns: list[str]) -> list[dict[str, object]]:
    return frame[columns].where(pd.notna(frame[columns]), None).to_dict("records")


def main() -> None:
    taiwan = load_taiwan_archive_snapshot()
    korea = load_korea_semiconductor_monthly_history()
    strict = build_overseas_validation_signals(
        pd.concat([taiwan, korea], ignore_index=True), strict=True
    )
    enriched = add_global_condition_signals(strict)
    prices = load_yfinance_batch(tuple(ASSETS.values()), "2021-01-01")

    assets: dict[str, object] = {}
    for name, ticker in ASSETS.items():
        if ticker not in prices:
            assets[name] = {"status": "unavailable"}
            continue
        correlations = {
            series_id: _records(
                analyze_release_aware_correlation(strict[series_id], prices[ticker]),
                ["期間", "相関", "サンプル数", "注意"],
            )
            for series_id in TAIWAN_SERIES
        }
        conditions = {
            condition: _records(
                analyze_release_aware_returns(enriched[condition], prices[ticker]),
                ["期間", "平均", "中央値", "上昇確率", "サンプル数", "注意"],
            )
            for condition in ("Taiwan Improving", "Taiwan AND Korea Improving")
            if condition in enriched
        }
        assets[name] = {"status": "available", "correlations": correlations, "conditions": conditions}

    report = {
        "taiwan": {
            "months": int(taiwan["reference_period"].nunique()),
            "first_reference_period": taiwan["reference_period"].min(),
            "latest_reference_period": taiwan["reference_period"].max(),
            "first_release": taiwan["release_date"].min(),
            "latest_release": taiwan["release_date"].max(),
        },
        "korea": {
            "months": int(korea["reference_period"].nunique()),
            "first_reference_period": korea["reference_period"].min(),
            "latest_reference_period": korea["reference_period"].max(),
            "first_release": korea["release_date"].min(),
            "latest_release": korea["release_date"].max(),
        },
        "price_missing_tickers": prices.attrs.get("missing_tickers", []),
        "assets": assets,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
