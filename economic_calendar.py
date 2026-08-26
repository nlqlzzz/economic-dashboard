from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


SCHEDULE_CONFIG_PATH = (
    Path(__file__).resolve().parent / "config" / "us_economic_events.json"
)
EVENT_DEFINITIONS = {
    "employment": {"event": "米雇用統計", "source": "BLS"},
    "cpi": {"event": "米CPI", "source": "BLS"},
    "fomc": {"event": "FOMC政策金利発表", "source": "FRB"},
}


def load_event_schedule(path: str | Path | None = None) -> dict[str, object]:
    """JSONの日程設定を読み込み、構造と内容を検証して返す。"""
    config_path = Path(path) if path is not None else SCHEDULE_CONFIG_PATH
    try:
        schedule = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"経済イベント日程を読み込めません: {error}") from error
    validate_event_schedule(schedule)
    return schedule


def validate_event_schedule(schedule: object) -> None:
    """日程設定のスキーマ、重複、順序、収録期限を検証する。"""
    if not isinstance(schedule, dict) or schedule.get("schema_version") != 1:
        raise ValueError("経済イベント日程のschema_versionは1にしてください。")
    sources = schedule.get("sources")
    events = schedule.get("events")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("経済イベント日程にsourcesが必要です。")
    if not isinstance(events, list) or not events:
        raise ValueError("経済イベント日程にeventsが必要です。")

    coverage: dict[str, datetime] = {}
    for source_name, source in sources.items():
        if not isinstance(source, dict):
            raise ValueError(f"{source_name}の出所設定が不正です。")
        for field in ("url", "timezone", "release_time", "coverage_end"):
            if not isinstance(source.get(field), str) or not source[field]:
                raise ValueError(f"{source_name}の{field}が必要です。")
        try:
            ZoneInfo(source["timezone"])
            datetime.strptime(source["release_time"], "%H:%M")
            coverage[source_name] = datetime.strptime(
                source["coverage_end"], "%Y-%m-%d"
            )
        except (ValueError, KeyError) as error:
            raise ValueError(f"{source_name}の日付・時刻設定が不正です。") from error

    seen: set[tuple[str, str]] = set()
    event_datetimes: list[datetime] = []
    latest_by_source: dict[str, datetime] = {}
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError(f"events[{index}]が不正です。")
        date_text = event.get("date")
        event_type = event.get("event_type")
        source_name = event.get("source")
        if event_type not in EVENT_DEFINITIONS:
            raise ValueError(f"未対応のevent_typeです: {event_type}")
        if source_name not in sources:
            raise ValueError(f"未登録のsourceです: {source_name}")
        if EVENT_DEFINITIONS[event_type]["source"] != source_name:
            raise ValueError(f"{event_type}のsourceが不正です。")
        try:
            event_date = datetime.strptime(str(date_text), "%Y-%m-%d")
        except ValueError as error:
            raise ValueError(f"events[{index}]のdateが不正です。") from error
        key = (str(date_text), str(event_type))
        if key in seen:
            raise ValueError(f"経済イベント日程が重複しています: {key}")
        seen.add(key)
        event_datetimes.append(event_date)
        latest_by_source[source_name] = max(
            event_date, latest_by_source.get(source_name, event_date)
        )

    if event_datetimes != sorted(event_datetimes):
        raise ValueError("経済イベント日程は日付の昇順にしてください。")
    for source_name, coverage_end in coverage.items():
        if latest_by_source.get(source_name) != coverage_end:
            raise ValueError(
                f"{source_name}のcoverage_endを最終収録日と一致させてください。"
            )


_DEFAULT_SCHEDULE = load_event_schedule()
OFFICIAL_SCHEDULE_URLS = {
    name: source["url"]
    for name, source in _DEFAULT_SCHEDULE["sources"].items()
}


def build_us_economic_events(
    schedule: dict[str, object] | None = None,
) -> pd.DataFrame:
    """公式発表済み日程から主要な米国経済イベントを日本時間で返す。"""
    active_schedule = _DEFAULT_SCHEDULE if schedule is None else schedule
    validate_event_schedule(active_schedule)
    tokyo = ZoneInfo("Asia/Tokyo")
    events = []
    for item in active_schedule["events"]:
        event_type = item["event_type"]
        source_name = item["source"]
        source = active_schedule["sources"][source_name]
        released_at = datetime.strptime(
            f"{item['date']} {source['release_time']}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=ZoneInfo(source["timezone"]))
        events.append(
            {
                "datetime": released_at.astimezone(tokyo),
                "event": EVENT_DEFINITIONS[event_type]["event"],
                "event_type": event_type,
                "importance": "高",
                "source": source_name,
            }
        )
    return pd.DataFrame(events).sort_values("datetime").reset_index(drop=True)


def schedule_coverage_text(schedule: dict[str, object] | None = None) -> str:
    """画面表示用に出所別の最終収録年月を返す。"""
    active_schedule = _DEFAULT_SCHEDULE if schedule is None else schedule
    validate_event_schedule(active_schedule)
    return "、".join(
        f"{source_name}（{source['coverage_end'][:7]}まで）"
        for source_name, source in active_schedule["sources"].items()
    )


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
