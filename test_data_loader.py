import unittest
from unittest.mock import patch

import pandas as pd

from data_loader import load_indicator_data


class IndicatorFallbackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.info = {
            "source": "yfinance",
            "ticker": "PRIMARY",
            "unit": "ポイント",
            "fallbacks": [
                {
                    "source": "yfinance",
                    "ticker": "FALLBACK",
                    "unit": "米ドル",
                    "label": "代替ETF（近似）",
                }
            ],
        }

    @patch("data_loader.load_data")
    def test_uses_primary_ticker_when_available(self, mock_load_data) -> None:
        mock_load_data.return_value = pd.Series(
            [100.0], index=pd.to_datetime(["2026-08-24"])
        )

        series = load_indicator_data(self.info, "2026-08-01")

        self.assertFalse(series.attrs["is_fallback"])
        self.assertEqual(series.attrs["ticker"], "PRIMARY")
        self.assertEqual(series.attrs["unit"], "ポイント")
        mock_load_data.assert_called_once_with("yfinance", "PRIMARY", "2026-08-01")

    @patch("data_loader.load_data")
    def test_uses_labeled_fallback_after_primary_failure(self, mock_load_data) -> None:
        fallback_series = pd.Series(
            [50.0], index=pd.to_datetime(["2026-08-24"])
        )
        mock_load_data.side_effect = [ValueError("primary unavailable"), fallback_series]

        series = load_indicator_data(self.info, "2026-08-01")

        self.assertTrue(series.attrs["is_fallback"])
        self.assertEqual(series.attrs["ticker"], "FALLBACK")
        self.assertEqual(series.attrs["unit"], "米ドル")
        self.assertEqual(series.attrs["fallback_label"], "代替ETF（近似）")

    @patch("data_loader.load_data")
    def test_reports_all_candidates_when_none_are_available(self, mock_load_data) -> None:
        mock_load_data.side_effect = ValueError("unavailable")

        with self.assertRaisesRegex(ValueError, "PRIMARY.*FALLBACK"):
            load_indicator_data(self.info, "2026-08-01")


if __name__ == "__main__":
    unittest.main()
