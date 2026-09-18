"""Point-in-time company forecast update comparisons for comparable cohorts."""
from __future__ import annotations

from typing import Any

import pandas as pd


FORECAST_UPDATE_SCHEMA_VERSION = 1
FORECAST_UPDATE_METRICS = (
    "forecast_revenue",
    "forecast_operating_profit",
    "forecast_net_income",
)
COHORT_COLUMNS = (
    "ticker",
    "fiscal_year",
    "reference_period",
    "accounting_standard",
    "consolidated_flag",
    "currency",
    "unit",
)


def build_company_forecast_updates(
    records: pd.DataFrame,
    *,
    as_of: object | None = None,
) -> dict[str, object]:
    """Build comparable forecast changes without crossing fiscal definitions.

    Only revenue, operating profit, and net income are compared. EPS remains an
    original disclosure value elsewhere because its per-share basis is not
    verified. ``as_of`` is inclusive at date precision; callers must only pass
    records actually available at capture time.
    """
    empty = {
        "status": "Unavailable",
        "reason": "比較可能な同一年度の会社予想がありません。",
        "latest": [],
        "history": pd.DataFrame(),
        "schema_version": FORECAST_UPDATE_SCHEMA_VERSION,
    }
    if records.empty or "metric" not in records:
        return empty
    frame = records[records["metric"].isin(FORECAST_UPDATE_METRICS)].copy()
    for column in (*COHORT_COLUMNS, "disclosure_date", "value", "source_field", "forecast_scope"):
        if column not in frame:
            frame[column] = pd.NA
    frame["_disclosure"] = pd.to_datetime(frame["disclosure_date"], errors="coerce")
    frame["_reference"] = pd.to_datetime(frame["reference_period"], errors="coerce")
    frame["_value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna(
        subset=[*COHORT_COLUMNS, "_disclosure", "_reference", "_value"]
    )
    if as_of is not None:
        cutoff = pd.Timestamp(as_of)
        if cutoff.tzinfo is not None:
            cutoff = cutoff.tz_convert("Asia/Tokyo").tz_localize(None)
        frame = frame[frame["_disclosure"].dt.normalize().le(cutoff.normalize())]
    if frame.empty:
        return empty

    comparisons: list[dict[str, Any]] = []
    group_columns = [*COHORT_COLUMNS, "metric"]
    for keys, group in frame.groupby(group_columns, dropna=False):
        ordered = (
            group.sort_values(["_disclosure", "source_field"], na_position="last")
            .drop_duplicates("_disclosure", keep="last")
            .reset_index(drop=True)
        )
        if len(ordered) < 2:
            continue
        cohort = dict(zip(group_columns, keys))
        for index in range(1, len(ordered)):
            previous = ordered.iloc[index - 1]
            current = ordered.iloc[index]
            previous_value = float(previous["_value"])
            current_value = float(current["_value"])
            transition = _transition_status(
                str(cohort["metric"]), previous_value, current_value
            )
            change_pct = (
                (current_value / previous_value - 1.0) * 100.0
                if previous_value > 0
                and not (
                    str(cohort["metric"]) in {"forecast_operating_profit", "forecast_net_income"}
                    and current_value <= 0
                )
                else None
            )
            comparisons.append({
                **cohort,
                "previous_value": previous_value,
                "current_value": current_value,
                "absolute_change": current_value - previous_value,
                "change_pct": change_pct,
                "transition_status": transition,
                "previous_disclosure_date": previous["_disclosure"].date().isoformat(),
                "latest_disclosure_date": current["_disclosure"].date().isoformat(),
                "previous_source_field": _optional_text(previous.get("source_field")),
                "current_source_field": _optional_text(current.get("source_field")),
                "previous_forecast_scope": _optional_text(previous.get("forecast_scope")),
                "current_forecast_scope": _optional_text(current.get("forecast_scope")),
            })
    if not comparisons:
        return empty

    history = pd.DataFrame(comparisons).sort_values(
        ["latest_disclosure_date", "reference_period", "metric"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    identity = list(COHORT_COLUMNS)
    candidates = (
        history.groupby(identity, dropna=False)
        .agg(
            latest_disclosure_date=("latest_disclosure_date", "max"),
            metric_count=("metric", "nunique"),
        )
        .reset_index()
        .sort_values(
            ["latest_disclosure_date", "reference_period", "metric_count"],
            ascending=[False, False, False],
        )
    )
    chosen = candidates.iloc[0]
    selected = history.copy()
    for column in identity:
        selected = selected[selected[column].eq(chosen[column])]
    latest_event_date = selected["latest_disclosure_date"].max()
    latest_rows = (
        selected[selected["latest_disclosure_date"].eq(latest_event_date)]
        .sort_values("latest_disclosure_date")
        .drop_duplicates("metric", keep="last")
        .sort_values("metric")
    )
    return {
        "status": "Available",
        "reason": "",
        "latest": latest_rows.to_dict("records"),
        "history": history,
        "schema_version": FORECAST_UPDATE_SCHEMA_VERSION,
    }


def forecast_update_snapshot(updates: object) -> dict[str, object]:
    """Return the small stable structure stored in a Decision Log snapshot."""
    if not isinstance(updates, dict) or updates.get("status") != "Available":
        return {
            "schema_version": FORECAST_UPDATE_SCHEMA_VERSION,
            "status": "Unavailable",
            "reason": "比較可能な同一年度の会社予想がありません。",
            "metrics": {},
        }
    rows = list(updates.get("latest") or [])
    if not rows:
        return {
            "schema_version": FORECAST_UPDATE_SCHEMA_VERSION,
            "status": "Unavailable",
            "reason": "比較可能な同一年度の会社予想がありません。",
            "metrics": {},
        }
    first = rows[0]
    metrics: dict[str, object] = {}
    for row in rows:
        metrics[str(row["metric"])] = {
            "current_value": row.get("current_value"),
            "previous_value": row.get("previous_value"),
            "absolute_change": row.get("absolute_change"),
            "change_pct": row.get("change_pct"),
            "transition_status": row.get("transition_status"),
            "source_field": row.get("current_source_field"),
            "forecast_scope": row.get("current_forecast_scope"),
            "previous_disclosure_date": row.get("previous_disclosure_date"),
            "latest_disclosure_date": row.get("latest_disclosure_date"),
        }
    return {
        "schema_version": FORECAST_UPDATE_SCHEMA_VERSION,
        "status": "Available",
        "fiscal_year": first.get("fiscal_year"),
        "reference_period": _date_text(first.get("reference_period")),
        "latest_disclosure_date": max(str(row["latest_disclosure_date"]) for row in rows),
        "previous_disclosure_date": min(str(row["previous_disclosure_date"]) for row in rows),
        "accounting_standard": first.get("accounting_standard"),
        "consolidated_flag": first.get("consolidated_flag"),
        "currency": first.get("currency"),
        "unit": first.get("unit"),
        "metrics": metrics,
    }


def select_company_forecast_update_cohort(
    updates: object,
    current_forecast: object,
) -> dict[str, object]:
    """Select updates matching the forecast currently shown in the UI.

    Historical cohorts remain attached for the detail view, but are never used
    as a fallback for the main current-forecast comparison.
    """
    history = updates.get("history") if isinstance(updates, dict) else None
    if not isinstance(history, pd.DataFrame):
        history = pd.DataFrame()
    unavailable = {
        "status": "Unavailable",
        "reason": "現在表示中の対象年度には比較可能な前回予想がありません。",
        "latest": [],
        "history": history,
        "schema_version": FORECAST_UPDATE_SCHEMA_VERSION,
    }
    if (
        not isinstance(current_forecast, pd.DataFrame)
        or current_forecast.empty
        or history.empty
    ):
        return unavailable
    current = current_forecast.iloc[0]
    selected = history.copy()
    for column in COHORT_COLUMNS:
        value = current.get(column)
        if value is None or pd.isna(value):
            return unavailable
        selected = selected[selected[column].eq(value)]
    if selected.empty:
        return unavailable
    latest_event_date = selected["latest_disclosure_date"].max()
    latest = (
        selected[selected["latest_disclosure_date"].eq(latest_event_date)]
        .drop_duplicates("metric", keep="last")
        .sort_values("metric")
    )
    return {
        "status": "Available",
        "reason": "",
        "latest": latest.to_dict("records"),
        "history": history,
        "schema_version": FORECAST_UPDATE_SCHEMA_VERSION,
    }


def build_forecast_history_observations(
    history: pd.DataFrame,
    cohort: dict[str, object],
    metric: str,
) -> pd.DataFrame:
    """Reconstruct discrete disclosure snapshots for one cohort and metric."""
    columns = (
        "disclosure_date", "forecast_value", "previous_value",
        "absolute_change", "change_pct", "transition_status",
    )
    if metric not in FORECAST_UPDATE_METRICS or history.empty:
        return pd.DataFrame(columns=columns)
    selected = history[history["metric"].eq(metric)].copy()
    for column in COHORT_COLUMNS:
        value = cohort.get(column)
        if value is None or pd.isna(value):
            return pd.DataFrame(columns=columns)
        selected = selected[selected[column].eq(value)]
    if selected.empty:
        return pd.DataFrame(columns=columns)
    selected = selected.sort_values("latest_disclosure_date")
    first = selected.iloc[0]
    rows: list[dict[str, object]] = [{
        "disclosure_date": first["previous_disclosure_date"],
        "forecast_value": first["previous_value"],
        "previous_value": None,
        "absolute_change": None,
        "change_pct": None,
        "transition_status": None,
    }]
    for _, row in selected.iterrows():
        rows.append({
            "disclosure_date": row["latest_disclosure_date"],
            "forecast_value": row["current_value"],
            "previous_value": row["previous_value"],
            "absolute_change": row["absolute_change"],
            "change_pct": row["change_pct"],
            "transition_status": row["transition_status"],
        })
    return (
        pd.DataFrame(rows, columns=columns)
        .drop_duplicates("disclosure_date", keep="last")
        .sort_values("disclosure_date")
        .reset_index(drop=True)
    )


def _transition_status(metric: str, previous: float, current: float) -> str:
    if current == previous:
        return "unchanged"
    if metric in {"forecast_operating_profit", "forecast_net_income"}:
        if previous <= 0 < current:
            return "turned_positive"
        if previous >= 0 > current:
            return "turned_negative"
        if previous < 0 and current < 0:
            return "loss_narrowing" if current > previous else "loss_widening"
    if previous == 0:
        return "from_zero_increase" if current > 0 else "from_zero_decrease"
    return "increase" if current > previous else "decrease"


def _optional_text(value: object) -> str | None:
    return None if value is None or pd.isna(value) else str(value)


def _date_text(value: object) -> str | None:
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date().isoformat()
