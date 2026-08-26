import unittest
from copy import deepcopy

import pandas as pd

from economic_calendar import (
    build_us_economic_events,
    calendar_display_frame,
    latest_event_results,
    load_event_schedule,
    schedule_coverage_text,
    validate_event_schedule,
)


class EconomicCalendarTest(unittest.TestCase):
    def test_converts_official_release_times_to_tokyo(self) -> None:
        events = build_us_economic_events()
        september_cpi = events[
            (events["event"] == "米CPI")
            & (events["datetime"].dt.strftime("%Y-%m-%d") == "2026-09-11")
        ].iloc[0]

        self.assertEqual(september_cpi["datetime"].hour, 21)
        self.assertEqual(str(september_cpi["datetime"].tzinfo), "Asia/Tokyo")

        december_cpi = events[
            (events["event"] == "米CPI")
            & (events["datetime"].dt.strftime("%Y-%m-%d") == "2026-12-10")
        ].iloc[0]
        self.assertEqual(december_cpi["datetime"].hour, 22)
        self.assertEqual(december_cpi["datetime"].minute, 30)

    def test_loads_valid_schedule_and_formats_coverage(self) -> None:
        schedule = load_event_schedule()

        self.assertEqual(schedule["schema_version"], 1)
        self.assertEqual(
            schedule_coverage_text(schedule),
            "BLS（2026-12まで）、FRB（2027-12まで）",
        )

    def test_rejects_duplicate_events(self) -> None:
        schedule = deepcopy(load_event_schedule())
        schedule["events"].append(deepcopy(schedule["events"][-1]))

        with self.assertRaisesRegex(ValueError, "重複"):
            validate_event_schedule(schedule)

    def test_rejects_events_out_of_order(self) -> None:
        schedule = deepcopy(load_event_schedule())
        schedule["events"][0], schedule["events"][1] = (
            schedule["events"][1],
            schedule["events"][0],
        )

        with self.assertRaisesRegex(ValueError, "昇順"):
            validate_event_schedule(schedule)

    def test_rejects_coverage_that_does_not_match_latest_event(self) -> None:
        schedule = deepcopy(load_event_schedule())
        schedule["sources"]["BLS"]["coverage_end"] = "2026-12-31"

        with self.assertRaisesRegex(ValueError, "最終収録日"):
            validate_event_schedule(schedule)

    def test_formats_latest_and_previous_results(self) -> None:
        dates = pd.date_range("2025-01-01", periods=15, freq="MS")
        results = latest_event_results(
            cpi=pd.Series(range(100, 115), index=dates),
            unemployment=pd.Series([4.0] * 13 + [4.1, 4.2], index=dates),
            payrolls=pd.Series(range(1000, 2500, 100), index=dates),
            fed_funds=pd.Series([5.0] * 13 + [4.75, 4.5], index=dates),
        )

        self.assertEqual(
            results["employment"][0],
            "非農業部門 +10.0万人 / 失業率 4.2%",
        )
        self.assertEqual(results["fomc"], ("4.50%", "4.75%"))

    def test_filters_events_by_selected_period(self) -> None:
        frame = calendar_display_frame(
            build_us_economic_events(),
            {"cpi": ("2.0%", "2.1%")},
            start=pd.Timestamp("2026-09-10", tz="Asia/Tokyo"),
            end=pd.Timestamp("2026-09-12", tz="Asia/Tokyo"),
        )

        self.assertEqual(frame["イベント"].tolist(), ["米CPI"])
        self.assertEqual(frame.iloc[0]["直近結果"], "2.0%")


if __name__ == "__main__":
    unittest.main()
