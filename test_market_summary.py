import unittest

import pandas as pd

from market_summary import build_market_summary


class MarketSummaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dates = pd.to_datetime(["2026-08-21", "2026-08-24"])
        self.metadata = {
            "S&P 500指数": {"category": "マーケット"},
            "日経平均株価": {"category": "マーケット"},
            "USD/JPY": {"category": "為替"},
            "UST 10Y": {"category": "金利"},
            "VIX指数": {"category": "マーケット"},
            "情報技術（XLK）": {"category": "米国セクター"},
            "公益事業（XLU）": {"category": "米国セクター"},
        }

    def test_summarizes_equities_fx_yields_sentiment_and_sectors(self) -> None:
        series = {
            "S&P 500指数": pd.Series([100.0, 101.0], index=self.dates),
            "日経平均株価": pd.Series([100.0, 102.0], index=self.dates),
            "USD/JPY": pd.Series([150.0, 151.5], index=self.dates),
            "UST 10Y": pd.Series([4.0, 4.1], index=self.dates),
            "VIX指数": pd.Series([20.0, 19.0], index=self.dates),
            "情報技術（XLK）": pd.Series([100.0, 103.0], index=self.dates),
            "公益事業（XLU）": pd.Series([100.0, 99.0], index=self.dates),
        }

        summary = build_market_summary(series, self.metadata)

        self.assertEqual(summary["headline"], "主要株価指数は上向き")
        summary_text = " ".join(summary["bullets"])
        self.assertIn("円安方向", summary_text)
        self.assertIn("UST 10Yは上昇", summary_text)
        self.assertIn("警戒度低下", summary_text)
        self.assertIn("最も強いのは情報技術（XLK）", summary_text)
        self.assertIn("最も弱いのは公益事業（XLU）", summary_text)

    def test_reports_mixed_equity_market(self) -> None:
        summary = build_market_summary(
            {
                "S&P 500指数": pd.Series([100.0, 101.0], index=self.dates),
                "日経平均株価": pd.Series([100.0, 99.0], index=self.dates),
            },
            self.metadata,
        )

        self.assertEqual(summary["headline"], "主要株価指数はまちまち")

    def test_handles_series_without_previous_observation(self) -> None:
        summary = build_market_summary(
            {"S&P 500指数": pd.Series([100.0], index=self.dates[:1])},
            self.metadata,
        )

        self.assertEqual(summary["headline"], "選択中の指標から市場概況を確認")
        self.assertEqual(summary["bullets"], [])


if __name__ == "__main__":
    unittest.main()
