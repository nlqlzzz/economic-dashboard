import unittest

import pandas as pd

from data_status import assess_data_freshness, build_data_status_frame


class DataStatusTest(unittest.TestCase):
    def test_builds_primary_and_fallback_status_rows(self) -> None:
        dates = pd.to_datetime(["2026-08-22", "2026-08-24"])
        primary = pd.Series([100.0, 101.0], index=dates)
        primary.attrs.update(
            {
                "source": "fred",
                "ticker": "PRIMARY",
                "fetched_at": pd.Timestamp("2026-08-24 21:30", tz="Asia/Tokyo"),
                "is_fallback": False,
            }
        )
        fallback = pd.Series([50.0, 51.0], index=dates)
        fallback.attrs.update(
            {
                "source": "yfinance",
                "ticker": "ETF",
                "fetched_at": pd.Timestamp("2026-08-24 12:35", tz="UTC"),
                "is_fallback": True,
            }
        )
        metadata = {
            "一次指標": {"source": "fred", "ticker": "PRIMARY"},
            "代替指標": {"source": "fred", "ticker": "ORIGINAL"},
        }

        frame = build_data_status_frame(
            {"一次指標": primary, "代替指標": fallback},
            metadata,
            {"fred": "FRED", "yfinance": "Yahoo Finance"},
            as_of="2026-08-25",
        )

        self.assertEqual(frame.iloc[0]["取得区分"], "一次")
        self.assertEqual(frame.iloc[1]["取得区分"], "代替（近似）")
        self.assertEqual(frame.iloc[1]["データ元"], "Yahoo Finance")
        self.assertEqual(frame.iloc[1]["実ティッカー"], "ETF")
        self.assertEqual(frame.iloc[1]["取得確認日時"], "2026-08-24 21:35:00")
        self.assertEqual(frame.iloc[0]["更新頻度"], "営業日次")
        self.assertEqual(frame.iloc[0]["鮮度"], "正常")
        self.assertEqual(frame.iloc[0]["遅延幅"], "1営業日")

    def test_handles_series_without_fetch_timestamp(self) -> None:
        series = pd.Series(
            [100.0], index=pd.to_datetime(["2026-08-24"])
        )
        frame = build_data_status_frame(
            {"指標": series},
            {"指標": {"source": "fred", "ticker": "TEST"}},
            {"fred": "FRED"},
            as_of="2026-08-25",
        )

        self.assertEqual(frame.iloc[0]["取得確認日時"], "—")

    def test_business_daily_ignores_weekend_and_allows_holiday_margin(self) -> None:
        status = assess_data_freshness(
            "2026-08-21", "business_daily", as_of="2026-08-25"
        )

        self.assertEqual(status["遅延幅"], "2営業日")
        self.assertFalse(status["要確認"])

    def test_business_daily_flags_more_than_two_business_days(self) -> None:
        status = assess_data_freshness(
            "2026-08-20", "business_daily", as_of="2026-08-25"
        )

        self.assertEqual(status["鮮度"], "⚠ 要確認")
        self.assertTrue(status["要確認"])

    def test_monthly_allows_normal_publication_lag(self) -> None:
        current = assess_data_freshness("2026-07-01", "monthly", as_of="2026-08-25")
        stale = assess_data_freshness("2026-06-01", "monthly", as_of="2026-08-25")

        self.assertFalse(current["要確認"])
        self.assertTrue(stale["要確認"])

    def test_calendar_daily_counts_weekends(self) -> None:
        status = assess_data_freshness(
            "2026-08-21", "calendar_daily", as_of="2026-08-24"
        )

        self.assertEqual(status["遅延幅"], "3日")
        self.assertTrue(status["要確認"])


if __name__ == "__main__":
    unittest.main()
