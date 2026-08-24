import unittest

import pandas as pd

from data_status import build_data_status_frame


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
        )

        self.assertEqual(frame.iloc[0]["取得区分"], "一次")
        self.assertEqual(frame.iloc[1]["取得区分"], "代替（近似）")
        self.assertEqual(frame.iloc[1]["データ元"], "Yahoo Finance")
        self.assertEqual(frame.iloc[1]["実ティッカー"], "ETF")
        self.assertEqual(frame.iloc[1]["取得確認日時"], "2026-08-24 21:35:00")

    def test_handles_series_without_fetch_timestamp(self) -> None:
        series = pd.Series(
            [100.0], index=pd.to_datetime(["2026-08-24"])
        )
        frame = build_data_status_frame(
            {"指標": series},
            {"指標": {"source": "fred", "ticker": "TEST"}},
            {"fred": "FRED"},
        )

        self.assertEqual(frame.iloc[0]["取得確認日時"], "—")


if __name__ == "__main__":
    unittest.main()
