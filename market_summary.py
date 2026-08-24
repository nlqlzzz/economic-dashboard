from __future__ import annotations

import pandas as pd

from utils import change_from_previous, latest_value


EQUITY_BENCHMARKS = ["日経平均株価", "S&P 500指数", "SOX指数"]
LONG_TERM_YIELDS = ["UST 10Y", "JGB 10Y"]


def build_market_summary(
    series_by_name: dict[str, pd.Series],
    indicator_metadata: dict[str, dict[str, object]],
) -> dict[str, object]:
    """選択中の指標の直前観測値比から短い市場要約を作る。"""
    changes = {
        name: result[1]
        for name, series in series_by_name.items()
        if (result := change_from_previous(series)) is not None
    }
    benchmark_changes = {
        name: changes[name] for name in EQUITY_BENCHMARKS if name in changes
    }
    headline = _equity_headline(benchmark_changes)
    bullets = []
    if benchmark_changes:
        bullets.append(
            "株価指数: "
            + "、".join(
                f"{name} {_format_rate(rate)}"
                for name, rate in benchmark_changes.items()
            )
        )

    if "USD/JPY" in changes:
        rate = changes["USD/JPY"]
        yen_direction = "円安方向" if rate > 0 else "円高方向" if rate < 0 else "横ばい"
        bullets.append(f"為替: USD/JPY {_format_rate(rate)}（{yen_direction}）")

    yield_changes = {
        name: changes[name] for name in LONG_TERM_YIELDS if name in changes
    }
    if yield_changes:
        bullets.append(
            "長期金利: "
            + "、".join(
                f"{name}は{'上昇' if rate > 0 else '低下' if rate < 0 else '横ばい'}"
                for name, rate in yield_changes.items()
            )
        )

    if "VIX指数" in changes:
        rate = changes["VIX指数"]
        risk_label = "警戒度上昇" if rate > 0 else "警戒度低下" if rate < 0 else "横ばい"
        bullets.append(f"市場心理: VIX指数 {_format_rate(rate)}（{risk_label}）")

    sector_changes = {
        name: rate
        for name, rate in changes.items()
        if indicator_metadata.get(name, {}).get("category") == "米国セクター"
    }
    if sector_changes:
        strongest = max(sector_changes, key=sector_changes.get)
        weakest = min(sector_changes, key=sector_changes.get)
        if strongest == weakest:
            bullets.append(
                f"米国セクター: {strongest} {_format_rate(sector_changes[strongest])}"
            )
        else:
            bullets.append(
                "米国セクター: "
                f"最も強いのは{strongest} {_format_rate(sector_changes[strongest])}、"
                f"最も弱いのは{weakest} {_format_rate(sector_changes[weakest])}"
            )

    observed_dates = [latest_value(series)[0] for series in series_by_name.values()]
    return {
        "headline": headline,
        "bullets": bullets,
        "latest_date": max(observed_dates) if observed_dates else None,
    }


def _equity_headline(changes: dict[str, float]) -> str:
    if not changes:
        return "選択中の指標から市場概況を確認"
    average = sum(changes.values()) / len(changes)
    if average >= 0.3:
        return "主要株価指数は上向き"
    if average <= -0.3:
        return "主要株価指数は下向き"
    if min(changes.values()) < 0 < max(changes.values()):
        return "主要株価指数はまちまち"
    return "主要株価指数は小動き"


def _format_rate(rate: float) -> str:
    return f"{rate:+.2f}%"
