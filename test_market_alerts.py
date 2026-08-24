import unittest

import pandas as pd

from market_alerts import detect_market_moves


class MarketAlertsTest(unittest.TestCase):
    def test_detects_moves_at_or_above_each_threshold(self) -> None:
        dates = pd.to_datetime(["2026-07-23", "2026-08-17", "2026-08-23"])
        series_by_name = {
            "上昇指標": pd.Series([100.0, 104.0, 110.0], index=dates),
            "安定指標": pd.Series([100.0, 100.2, 100.4], index=dates),
        }

        alerts = detect_market_moves(
            series_by_name,
            {"直前観測値比": 5.0, "1週間": 5.0, "1か月": 9.0},
        )

        self.assertEqual(set(alerts["指標"]), {"上昇指標"})
        self.assertEqual(
            set(alerts["期間"]), {"直前観測値比", "1週間", "1か月"}
        )
        self.assertTrue((alerts["方向"] == "上昇").all())

    def test_detects_falling_move_and_sorts_by_severity(self) -> None:
        dates = pd.to_datetime(["2026-08-01", "2026-08-22", "2026-08-23"])
        series_by_name = {
            "下落指標": pd.Series([100.0, 90.0, 80.0], index=dates),
        }

        alerts = detect_market_moves(
            series_by_name,
            {"直前観測値比": 5.0, "1週間": 5.0, "1か月": 5.0},
        )

        self.assertTrue((alerts["方向"] == "下落").all())
        self.assertTrue(alerts["重要度"].is_monotonic_decreasing)

    def test_returns_empty_frame_when_no_move_exceeds_threshold(self) -> None:
        dates = pd.to_datetime(["2026-08-22", "2026-08-23"])
        alerts = detect_market_moves(
            {"指標": pd.Series([100.0, 100.1], index=dates)},
            {"直前観測値比": 5.0, "1週間": 5.0, "1か月": 5.0},
        )

        self.assertTrue(alerts.empty)
        self.assertEqual(alerts.columns[0], "指標")


if __name__ == "__main__":
    unittest.main()
