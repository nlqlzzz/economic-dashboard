import unittest

import pandas as pd

from economic_calendar import (
    build_us_economic_events,
    calendar_display_frame,
    latest_event_results,
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
