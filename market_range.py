from __future__ import annotations

from datetime import date

import pandas as pd


MARKET_RANGE_PRESETS = ("1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "ALL", "Custom")
MARKET_RANGE_LABELS = {**{value: value for value in MARKET_RANGE_PRESETS}, "Custom": "任意"}
MARKET_RANGE_DEFAULT = "YTD"
MARKET_ALL_START = date(1900, 1, 1)
_OFFSETS = {
    "1M": pd.DateOffset(months=1),
    "3M": pd.DateOffset(months=3),
    "6M": pd.DateOffset(months=6),
    "1Y": pd.DateOffset(years=1),
    "3Y": pd.DateOffset(years=3),
    "5Y": pd.DateOffset(years=5),
}


def calculate_market_range(
    preset: str,
    latest_data_date: object,
    earliest_data_date: object,
    custom_start: object,
    custom_end: object,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Resolve the visible market range; presets are anchored to actual latest data."""
    if preset not in MARKET_RANGE_PRESETS:
        raise ValueError(f"unknown market range preset: {preset}")
    latest = pd.Timestamp(latest_data_date).normalize()
    earliest = pd.Timestamp(earliest_data_date).normalize()
    if preset == "Custom":
        start = pd.Timestamp(custom_start).normalize()
        end = pd.Timestamp(custom_end).normalize()
        if start > end:
            raise ValueError("custom start must be on or before custom end")
        return start, end
    if preset == "ALL":
        return earliest, latest
    if preset == "YTD":
        return pd.Timestamp(year=latest.year, month=1, day=1), latest
    return (latest - _OFFSETS[preset]).normalize(), latest


def market_request_start(
    preset: str,
    today: object,
    custom_start: object,
) -> date:
    """Return a conservative fetch start, including one year for YoY calculation."""
    anchor = pd.Timestamp(today).normalize()
    if preset == "ALL":
        return MARKET_ALL_START
    if preset == "Custom":
        visible_start = pd.Timestamp(custom_start).normalize()
    elif preset == "YTD":
        visible_start = pd.Timestamp(year=anchor.year, month=1, day=1)
    elif preset in _OFFSETS:
        visible_start = anchor - _OFFSETS[preset]
    else:
        raise ValueError(f"unknown market range preset: {preset}")
    return (visible_start - pd.DateOffset(years=1, days=10)).date()


def market_data_bounds(
    series_by_name: dict[str, pd.Series],
    maximum_date: object,
) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """Find shared display bounds from available observations without requiring overlap."""
    maximum = pd.Timestamp(maximum_date).normalize()
    nonempty = []
    for series in series_by_name.values():
        eligible = series.loc[pd.to_datetime(series.index) <= maximum].dropna()
        if not eligible.empty:
            nonempty.append(eligible)
    if not nonempty:
        return None
    earliest = min(pd.Timestamp(series.index.min()).normalize() for series in nonempty)
    latest = max(pd.Timestamp(series.index.max()).normalize() for series in nonempty)
    return earliest, latest


def filter_market_series(
    series_by_name: dict[str, pd.Series],
    start: object,
    end: object,
) -> dict[str, pd.Series]:
    start_at = pd.Timestamp(start).normalize()
    end_at = pd.Timestamp(end).normalize()
    filtered: dict[str, pd.Series] = {}
    for name, series in series_by_name.items():
        index = pd.to_datetime(series.index)
        result = series.loc[(index >= start_at) & (index <= end_at)].copy()
        result.attrs.update(series.attrs)
        if not result.dropna().empty:
            filtered[name] = result
    return filtered
