import unittest
from unittest.mock import patch

import pandas as pd
import requests

from data_loader import (
    DataUnavailableError,
    IndicatorDataError,
    RetryFailure,
    _parse_meti_iip_workbook,
    _load_with_retry,
    load_indicator_data,
)


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

        with self.assertRaisesRegex(IndicatorDataError, "PRIMARY.*FALLBACK") as raised:
            load_indicator_data(self.info, "2026-08-01")

        self.assertEqual(len(raised.exception.failures), 2)
        self.assertEqual(raised.exception.failures[0].source, "yfinance")
        self.assertEqual(raised.exception.failures[0].ticker, "PRIMARY")
        self.assertEqual(
            raised.exception.failures[0].error_type, "データなし・設定エラー"
        )

    @patch("data_loader.time.sleep")
    def test_retries_transient_error_once(self, mock_sleep) -> None:
        expected = pd.Series([100.0], index=pd.to_datetime(["2026-08-24"]))
        loader = unittest.mock.Mock(
            side_effect=[requests.Timeout("temporary timeout"), expected]
        )

        series, attempts = _load_with_retry(loader)

        pd.testing.assert_series_equal(series, expected)
        self.assertEqual(attempts, 2)
        mock_sleep.assert_called_once()


class MetiIipParserTest(unittest.TestCase):
    @patch("data_loader.pd.read_excel")
    def test_extracts_semiconductor_row_from_all_four_sheets(
        self, mock_read_excel
    ) -> None:
        frame = pd.DataFrame(
            [
                [None, None, None, None, None],
                [None, None, None, "time-code-1", "time-code-2"],
                ["品目番号", "品目名称", "ウェイト", 202501.0, 202502.0],
                [1105000000, "電子部品・デバイス工業", 500, 101.2, 102.4],
            ]
        )
        mock_read_excel.return_value = frame

        parsed = _parse_meti_iip_workbook(b"workbook")

        self.assertEqual(set(parsed), {"生産", "出荷", "在庫", "在庫率"})
        for series in parsed.values():
            self.assertEqual(
                list(series.index),
                list(pd.to_datetime(["2025-01-01", "2025-02-01"])),
            )
            self.assertEqual(list(series), [101.2, 102.4])

    @patch("data_loader.pd.read_excel")
    def test_rejects_changed_industry_code(self, mock_read_excel) -> None:
        mock_read_excel.return_value = pd.DataFrame(
            [
                [None, None, None, None],
                [None, None, None, "time-code"],
                ["品目番号", "品目名称", "ウェイト", "202501"],
                [9999999999, "別の業種", 500, 101.2],
            ]
        )

        with self.assertRaisesRegex(DataUnavailableError, "1105000000"):
            _parse_meti_iip_workbook(b"workbook")


class RetryBehaviorTest(unittest.TestCase):
    @patch("data_loader.time.sleep")
    def test_does_not_retry_permanent_error(self, mock_sleep) -> None:
        loader = unittest.mock.Mock(side_effect=ValueError("invalid ticker"))

        with self.assertRaises(RetryFailure) as raised:
            _load_with_retry(loader)

        self.assertEqual(loader.call_count, 1)
        mock_sleep.assert_not_called()
        self.assertIsInstance(raised.exception.error, ValueError)

    @patch("data_loader.time.sleep")
    def test_retries_empty_yahoo_result(self, mock_sleep) -> None:
        expected = pd.Series([100.0], index=pd.to_datetime(["2026-08-24"]))
        loader = unittest.mock.Mock(
            side_effect=[DataUnavailableError("empty"), expected]
        )

        series, attempts = _load_with_retry(loader)

        pd.testing.assert_series_equal(series, expected)
        self.assertEqual(attempts, 2)
        mock_sleep.assert_called_once()

    @patch("data_loader.time.sleep")
    def test_retries_server_error_but_not_client_error(self, mock_sleep) -> None:
        server_response = requests.Response()
        server_response.status_code = 503
        server_error = requests.HTTPError("service unavailable", response=server_response)
        expected = pd.Series([100.0], index=pd.to_datetime(["2026-08-24"]))
        server_loader = unittest.mock.Mock(side_effect=[server_error, expected])

        _, attempts = _load_with_retry(server_loader)

        self.assertEqual(attempts, 2)

        client_response = requests.Response()
        client_response.status_code = 404
        client_loader = unittest.mock.Mock(
            side_effect=requests.HTTPError("not found", response=client_response)
        )
        with self.assertRaises(RetryFailure):
            _load_with_retry(client_loader)

        self.assertEqual(client_loader.call_count, 1)
        mock_sleep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
