"""Point-in-time helpers shared by release-aware validation modules."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from price_quality import PriceQualityResult, inspect_price_series


MAX_TRADING_DAY_ADJUSTMENT_DAYS = 7


@dataclass(frozen=True)
class ReturnObservation:
    value: float | None
    start_date: pd.Timestamp | None
    end_date: pd.Timestamp | None
    status: str
    quality_status: str = "ok"
    excluded_observations: int = 0
    quality_reason: str = ""
    excluded_dates: tuple[pd.Timestamp, ...] = ()


def clean_daily_prices(series: pd.Series, as_of: object | None = None) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index().copy()
    clean.index = pd.DatetimeIndex(clean.index).tz_localize(None).normalize()
    clean = clean[~clean.index.duplicated(keep="last")]
    if as_of is not None:
        clean = clean.loc[clean.index <= pd.Timestamp(as_of).tz_localize(None).normalize()]
    return clean


def evaluate_release_return(
    prices: pd.Series,
    available_at: object,
    months: int,
    *,
    mode: str = "post_release",
    as_of: object | None = None,
) -> ReturnObservation:
    """Evaluate a fully matured calendar-month return.

    ``reaction`` observes the move from the last close before publication.
    ``post_release`` is the conservative, executable-information view for a
    date-only release: entry is the first close strictly after publication.
    Since only closes are available, no unobserved opening execution is assumed.
    """
    if mode not in {"reaction", "post_release"}:
        raise ValueError(f"未対応の評価モードです: {mode}")
    quality = inspect_price_series(clean_daily_prices(prices, as_of))
    if not quality.usable:
        return _observation(None, None, None, "quality_blocked", quality)
    return _evaluate_prepared_return(quality.series, quality, available_at, months, mode=mode, as_of=as_of)


def _evaluate_prepared_return(
    clean: pd.Series,
    quality: PriceQualityResult,
    available_at: object,
    months: int,
    *,
    mode: str,
    as_of: object | None,
) -> ReturnObservation:
    release = pd.Timestamp(available_at).tz_localize(None).normalize()
    if mode == "reaction":
        candidates = clean.loc[clean.index < release]
        start = None if candidates.empty else candidates.index[-1]
    else:
        candidates = clean.loc[clean.index > release]
        start = None if candidates.empty else candidates.index[0]
    if start is None:
        return _observation(None, None, None, "missing_start", quality)
    start_gap = (release - start).days if mode == "reaction" else (start - release).days
    if start_gap > MAX_TRADING_DAY_ADJUSTMENT_DAYS:
        return _observation(None, start, None, "start_too_late", quality)
    maturity = start + pd.DateOffset(months=months)
    cutoff = clean.index[-1] if as_of is None and not clean.empty else pd.Timestamp(as_of).tz_localize(None).normalize() if as_of is not None else None
    if cutoff is None or cutoff < maturity:
        return _observation(None, start, None, "unmatured", quality)
    targets = clean.loc[clean.index >= maturity]
    if targets.empty:
        return _observation(None, start, None, "missing_end", quality)
    end = targets.index[0]
    if (end - maturity).days > MAX_TRADING_DAY_ADJUSTMENT_DAYS:
        return _observation(None, start, end, "end_too_late", quality)
    base = float(clean.loc[start]); target = float(clean.loc[end])
    if base == 0:
        return _observation(None, start, end, "zero_start", quality)
    return _observation(float((target / base - 1) * 100), start, end, "eligible", quality)


def evaluate_paired_release_returns(
    asset: pd.Series,
    benchmark: pd.Series,
    available_at: object,
    months: int,
    *,
    mode: str = "post_release",
    as_of: object | None = None,
) -> tuple[ReturnObservation, ReturnObservation]:
    """Evaluate asset and benchmark over exactly the same observable dates."""
    asset_quality = inspect_price_series(clean_daily_prices(asset, as_of))
    benchmark_quality = inspect_price_series(clean_daily_prices(benchmark, as_of))
    if not asset_quality.usable or not benchmark_quality.usable:
        return (
            _observation(None, None, None, "pair_quality_blocked", asset_quality),
            _observation(None, None, None, "pair_quality_blocked", benchmark_quality),
        )
    common = pd.concat(
        {"asset": asset_quality.series, "benchmark": benchmark_quality.series},
        axis=1, join="inner", sort=False,
    ).dropna()
    asset_result = _evaluate_prepared_return(
        common["asset"], asset_quality, available_at, months, mode=mode, as_of=as_of
    )
    benchmark_result = _evaluate_prepared_return(
        common["benchmark"], benchmark_quality, available_at, months, mode=mode, as_of=as_of
    )
    return asset_result, benchmark_result


def _observation(
    value: float | None,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
    status: str,
    quality: PriceQualityResult,
) -> ReturnObservation:
    return ReturnObservation(
        value, start, end, status, quality.status, len(quality.excluded_dates),
        quality.reason, tuple(quality.excluded_dates),
    )


def condition_onsets(condition: pd.Series) -> pd.DatetimeIndex:
    """Count a sustained True regime once, at the transition into True."""
    state = condition.astype("boolean")
    prior = state.shift(1)
    selected = state.eq(True) & ~prior.eq(True).fillna(False)
    return pd.DatetimeIndex(state.index[selected.fillna(False)])


def exclusion_summary(statuses: list[str]) -> str:
    labels = {
        "unmatured": "未満了", "missing_start": "起点価格なし",
        "missing_end": "終点価格なし", "zero_start": "起点ゼロ", "quality_blocked": "価格品質で停止",
        "pair_quality_blocked": "ペア価格品質で停止", "start_too_late": "起点価格の遅延超過",
        "end_too_late": "終点価格の遅延超過",
    }
    counts = pd.Series([status for status in statuses if status != "eligible"]).value_counts()
    return "、".join(f"{labels.get(status, status)} {count}件" for status, count in counts.items())
