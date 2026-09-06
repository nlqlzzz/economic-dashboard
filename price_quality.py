from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class PriceQualityResult:
    series: pd.Series
    status: str
    excluded_dates: tuple[pd.Timestamp, ...]
    flagged_dates: tuple[pd.Timestamp, ...]
    reason: str

    @property
    def usable(self) -> bool:
        return self.status in {"ok", "cleaned"}


def inspect_price_series(
    series: pd.Series,
    *,
    extreme_return: float = 0.60,
    recovery_tolerance: float = 0.30,
    max_recovery_observations: int = 5,
) -> PriceQualityResult:
    """Detect temporary scale breaks without erasing persistent market moves.

    A segment is removed only when an extreme move is followed shortly by another
    extreme move that restores the price close to the pre-break level. Unpaired
    extreme moves are flagged and block downstream regression rather than being
    silently repaired.
    """
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    if len(clean) < 3:
        return PriceQualityResult(clean, "ok", (), (), "")

    excluded: set[pd.Timestamp] = set()
    paired_boundaries: set[pd.Timestamp] = set()
    values = clean.to_numpy(dtype=float)
    dates = list(pd.to_datetime(clean.index))
    for left in range(len(values) - 2):
        base = values[left]
        if base <= 0:
            continue
        entry_return = values[left + 1] / base - 1.0
        if abs(entry_return) < extreme_return:
            continue
        end_limit = min(len(values), left + max_recovery_observations + 2)
        for recovery in range(left + 2, end_limit):
            prior = values[recovery - 1]
            if prior <= 0:
                continue
            recovery_return = values[recovery] / prior - 1.0
            restored = abs(values[recovery] / base - 1.0) <= recovery_tolerance
            opposite = entry_return * recovery_return < 0
            if abs(recovery_return) >= extreme_return and restored and opposite:
                excluded.update(dates[left + 1 : recovery])
                paired_boundaries.update((dates[left + 1], dates[recovery]))
                break

    cleaned = clean.drop(index=list(excluded), errors="ignore")
    remaining_returns = cleaned.pct_change(fill_method=None).abs()
    flagged = tuple(
        pd.Timestamp(value)
        for value in remaining_returns[remaining_returns >= extreme_return].index
        if pd.Timestamp(value) not in paired_boundaries
    )
    if flagged:
        return PriceQualityResult(
            cleaned,
            "blocked",
            tuple(sorted(excluded)),
            flagged,
            "復帰を確認できない極端な価格変動があり、分析を停止しました。",
        )
    if excluded:
        return PriceQualityResult(
            cleaned,
            "cleaned",
            tuple(sorted(excluded)),
            (),
            f"一時的な価格水準の不連続を{len(excluded)}観測除外しました。",
        )
    return PriceQualityResult(cleaned, "ok", (), (), "")
