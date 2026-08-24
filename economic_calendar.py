from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd


OFFICIAL_SCHEDULE_URLS = {
    "BLS": "https://www.bls.gov/schedule/2026/home.htm",
    "FRB": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
}

_BLS_RELEASES = [
    ("2026-09-04", "米雇用統計", "employment"),
    ("2026-09-11", "米CPI", "cpi"),
    ("2026-10-02", "米雇用統計", "employment"),
    ("2026-10-14", "米CPI", "cpi"),
    ("2026-11-06", "米雇用統計", "employment"),
    ("2026-11-10", "米CPI", "cpi"),
    ("2026-12-04", "米雇用統計", "employment"),
    ("2026-12-10", "米CPI", "cpi"),
]

_FOMC_DECISIONS = [
    "2026-09-16",
    "2026-10-28",
    "2026-12-09",
    "2027-01-27",
    "2027-03-17",
    "2027-04-28",
    "2027-06-09",
    "2027-07-28",
    "2027-09-15",
    "2027-10-27",
    "2027-12-08",
]


def build_us_economic_events() -> pd.DataFrame:
    """公式発表済み日程から主要な米国経済イベントを日本時間で返す。"""
    eastern = ZoneInfo("America/New_York")
    tokyo = ZoneInfo("Asia/Tokyo")
    events = []
    for date_text, name, event_type in _BLS_RELEASES:
        released_at = datetime.strptime(
            f"{date_text} 08:30", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=eastern)
        events.append(
            {
                "datetime": released_at.astimezone(tokyo),
                "event": name,
                "event_type": event_type,
                "importance": "高",
                "source": "BLS",
            }
        )
    for date_text in _FOMC_DECISIONS:
        released_at = datetime.strptime(
            f"{date_text} 14:00", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=eastern)
        events.append(
            {
                "datetime": released_at.astimezone(tokyo),
                "event": "FOMC政策金利発表",
                "event_type": "fomc",
                "importance": "高",
                "source": "FRB",
            }
        )
    return pd.DataFrame(events).sort_values("datetime").reset_index(drop=True)


def latest_event_results(
    cpi: pd.Series,
    unemployment: pd.Series,
    payrolls: pd.Series,
    fed_funds: pd.Series,
) -> dict[str, tuple[str, str]]:
    """各イベントに対応する直近結果と前回値を表示用に整える。"""
    cpi_yoy = cpi.pct_change(12, fill_method=None).dropna() * 100
    payroll_changes = payrolls.diff().dropna() / 10
    return {
        "cpi": _latest_pair(cpi_yoy, "{:.2f}%"),
        "employment": _employment_pair(payroll_changes, unemployment.dropna()),
        "fomc": _latest_pair(fed_funds.dropna(), "{:.2f}%"),
    }


def calendar_display_frame(
    events: pd.DataFrame,
    results: dict[str, tuple[str, str]],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """指定期間のイベントを日本語の表示列に変換する。"""
    start_at = _tokyo_timestamp(start)
    end_at = _tokyo_timestamp(end)
    selected = events[
        (events["datetime"] >= start_at) & (events["datetime"] <= end_at)
    ].copy()
    rows = []
    for event in selected.to_dict("records"):
        latest, previous = results.get(event["event_type"], ("—", "—"))
        rows.append(
            {
                "日本時間": event["datetime"].strftime("%Y-%m-%d %H:%M"),
                "イベント": event["event"],
                "重要度": event["importance"],
                "予想": "—",
                "直近結果": latest,
                "前回値": previous,
                "日程元": event["source"],
            }
        )
    return pd.DataFrame(rows)


def _latest_pair(series: pd.Series, format_text: str) -> tuple[str, str]:
    clean = series.dropna()
    if len(clean) < 2:
        return "—", "—"
    return format_text.format(float(clean.iloc[-1])), format_text.format(
        float(clean.iloc[-2])
    )


def _employment_pair(
    payroll_changes: pd.Series, unemployment: pd.Series
) -> tuple[str, str]:
    if len(payroll_changes) < 2 or len(unemployment) < 2:
        return "—", "—"

    def format_result(payroll: float, jobless_rate: float) -> str:
        return f"非農業部門 {payroll:+.1f}万人 / 失業率 {jobless_rate:.1f}%"

    return (
        format_result(float(payroll_changes.iloc[-1]), float(unemployment.iloc[-1])),
        format_result(float(payroll_changes.iloc[-2]), float(unemployment.iloc[-2])),
    )


def _tokyo_timestamp(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("Asia/Tokyo")
    return timestamp.tz_convert("Asia/Tokyo")
