import unittest
from unittest.mock import patch

import pandas as pd
import requests

from data_loader import (
    DataSchemaError,
    DataUnavailableError,
    IndicatorDataError,
    RetryFailure,
    _download_estat_electronic_computer_orders,
    _discover_korea_monthly_trade_release,
    _discover_korea_monthly_trade_releases,
    _discover_korea_release_links,
    _korea_release_title_kind,
    _parse_meti_iip_workbook,
    _parse_estat_electronic_computer_orders,
    _load_with_retry,
    load_indicator_data,
    load_korea_semiconductor_exports,
    load_korea_semiconductor_monthly_history,
    load_yfinance_batch,
    merge_korea_semiconductor_exports,
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

    @patch("data_loader.yf.download")
    def test_batch_yfinance_keeps_available_tickers_and_reports_missing(
        self, mock_download
    ) -> None:
        index = pd.date_range("2026-01-01", periods=3, freq="B")
        mock_download.return_value = pd.DataFrame(
            {
                ("Close", "7203.T"): [100.0, 101.0, 102.0],
                ("Close", "8306.T"): [None, None, None],
            },
            index=index,
        )

        frame = load_yfinance_batch.__wrapped__(
            ("7203.T", "8306.T"), "2026-01-01"
        )

        self.assertEqual(list(frame.columns), ["7203.T"])
        self.assertEqual(frame.attrs["missing_tickers"], ["8306.T"])
        mock_download.assert_called_once()


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


class EstatElectronicComputerOrdersParserTest(unittest.TestCase):
    def test_extracts_electronic_computers_including_semiconductor_series(self) -> None:
        payload = {
            "GET_STATS_DATA": {
                "RESULT": {"STATUS": 0},
                "STATISTICAL_DATA": {
                    "TABLE_INF": {"UPDATED_DATE": "2026-08-19"},
                    "CLASS_INF": {
                        "CLASS_OBJ": [
                            {
                                "@id": "cat01",
                                "@name": "機種分類(大中分類)",
                                "CLASS": [
                                    {"@code": "100", "@name": "電子計算機等"},
                                    {
                                        "@code": "101",
                                        "@name": "電子・通信機械_電子計算機等",
                                    },
                                ],
                            },
                            {
                                "@id": "time",
                                "@name": "時間軸(月次)",
                                "CLASS": [
                                    {"@code": "202605", "@name": "2026年5月"},
                                    {"@code": "202606", "@name": "2026年6月"},
                                ],
                            },
                        ]
                    },
                    "DATA_INF": {
                        "VALUE": [
                            {"@cat01": "100", "@time": "202606", "$": "999"},
                            {"@cat01": "101", "@time": "202605", "$": "120"},
                            {"@cat01": "101", "@time": "202606", "$": "150"},
                        ]
                    },
                },
            }
        }

        series, released_at = _parse_estat_electronic_computer_orders(payload)

        self.assertEqual(list(series), [120.0, 150.0])
        self.assertEqual(series.index[-1], pd.Timestamp("2026-06-01"))
        self.assertEqual(series.name, "電子計算機等受注（半導体製造装置を含む）")
        self.assertEqual(released_at, pd.Timestamp("2026-08-19"))

    def test_rejects_missing_electronic_computer_series(self) -> None:
        payload = {
            "GET_STATS_DATA": {
                "RESULT": {"STATUS": 0},
                "STATISTICAL_DATA": {
                    "CLASS_INF": {
                        "CLASS_OBJ": [
                            {
                                "@id": "cat01",
                                "@name": "機種分類",
                                "CLASS": {"@code": "100", "@name": "電子計算機等"},
                            },
                            {
                                "@id": "time",
                                "@name": "時間軸",
                                "CLASS": {"@code": "202606", "@name": "2026年6月"},
                            },
                        ]
                    },
                    "DATA_INF": {"VALUE": []},
                },
            }
        }

        with self.assertRaisesRegex(DataSchemaError, "電子計算機等"):
            _parse_estat_electronic_computer_orders(payload)

    @patch("data_loader.time.sleep")
    def test_does_not_retry_changed_estat_classification(self, mock_sleep) -> None:
        loader = unittest.mock.Mock(side_effect=DataSchemaError("changed metadata"))

        with self.assertRaises(RetryFailure) as raised:
            _load_with_retry(loader)

        self.assertEqual(loader.call_count, 1)
        self.assertIsInstance(raised.exception.error, DataSchemaError)
        mock_sleep.assert_not_called()

    @patch("data_loader.requests.get")
    def test_http_error_does_not_expose_app_id(self, mock_get) -> None:
        mock_get.return_value.status_code = 403

        with self.assertRaises(requests.HTTPError) as context:
            _download_estat_electronic_computer_orders("private-app-id")

        self.assertNotIn("private-app-id", str(context.exception))


class KoreaSemiconductorLoaderTest(unittest.TestCase):
    @patch("data_loader._discover_korea_monthly_trade_releases")
    @patch("data_loader.requests.get")
    def test_discovers_latest_motir_release_from_javascript_archive(
        self, mock_get, mock_archive
    ) -> None:
        empty = unittest.mock.Mock(text="<html>no direct monthly link</html>")
        empty.raise_for_status.return_value = None
        mock_get.return_value = empty
        mock_archive.return_value = [
            ("2026년 7월 정보통신산업(ICT) 수출입 동향", "https://official.example/ict"),
            ("2026년 8월 수출입동향", "https://official.example/general"),
        ]

        url = _discover_korea_monthly_trade_release()

        self.assertEqual(url, "https://official.example/general")

    @patch("data_loader.time.sleep")
    @patch("data_loader._download_text")
    @patch("data_loader._discover_korea_monthly_trade_release")
    @patch("data_loader._discover_korea_release_links")
    def test_keeps_motir_monthly_when_kcs_discovery_times_out(
        self,
        mock_kcs_discover,
        mock_monthly_discover,
        mock_download,
        mock_sleep,
    ) -> None:
        mock_kcs_discover.side_effect = requests.ConnectTimeout("KCS timeout")
        mock_monthly_discover.return_value = "https://official.example/monthly"
        mock_download.return_value = """
        <h1>2026년 8월 수출입동향</h1>
        <p>등록일 2026-09-01</p>
        <p>반도체 수출(466.5억 달러, +209.0%)</p>
        """

        frame = load_korea_semiconductor_exports.__wrapped__()

        official = frame[~frame["is_derived"]]
        self.assertEqual(
            list(official["series_id"]),
            ["korea_semiconductor_exports_monthly"],
        )
        self.assertEqual(frame.attrs["missing_periods"], ["1_10", "1_20"])
        self.assertIn("KCS timeout", frame.attrs["load_warnings"][0])

    @patch("data_loader._download_text")
    @patch("data_loader._discover_korea_monthly_trade_release")
    @patch("data_loader._discover_korea_release_links")
    def test_replaces_stale_kcs_monthly_with_current_motir_monthly(
        self, mock_kcs_discover, mock_monthly_discover, mock_download
    ) -> None:
        mock_kcs_discover.return_value = [
            ("1-20", "https://official.example/20"),
            ("monthly-old", "https://official.example/monthly-old"),
        ]
        mock_monthly_discover.return_value = "https://official.example/monthly-current"
        bodies = {
            "https://official.example/20": (
                "<h1>2026년 8월 1일 ~ 8월 20일 수출입 현황 [잠정치]</h1>"
                "<p>반도체(260억 달러)</p>"
            ),
            "https://official.example/monthly-old": (
                "<h1>2026년 7월 수출입 현황 [확정치]</h1>"
                "<p>반도체 수출(412억 달러)</p>"
            ),
            "https://official.example/monthly-current": (
                "<h1>2026년 8월 수출입동향</h1>"
                "<p>등록일 2026-09-01</p>"
                "<p>반도체 수출(466.5억 달러, +209.0%)</p>"
            ),
        }
        mock_download.side_effect = lambda url: bodies[url]

        frame = load_korea_semiconductor_exports.__wrapped__()

        monthly = frame[
            frame["series_id"] == "korea_semiconductor_exports_monthly"
        ].iloc[0]
        self.assertEqual(monthly["reference_period"], pd.Timestamp("2026-08-01"))
        self.assertEqual(monthly["value"], 46_650)
        self.assertEqual(monthly["source_name"], "韓国産業通商部 輸出入動向")

    @patch("data_loader._download_text")
    @patch("data_loader._discover_korea_monthly_trade_release")
    @patch("data_loader._discover_korea_release_links")
    def test_enriches_current_kcs_monthly_when_yoy_is_missing(
        self, mock_kcs_discover, mock_monthly_discover, mock_download
    ) -> None:
        mock_kcs_discover.return_value = [
            ("monthly", "https://official.example/kcs-monthly"),
        ]
        mock_monthly_discover.return_value = "https://official.example/motir-monthly"
        bodies = {
            "https://official.example/kcs-monthly": (
                "<h1>2026년 8월 월간 수출입 현황 [확정치]</h1>"
                "<p>반도체 수출(412억 달러)</p>"
            ),
            "https://official.example/motir-monthly": (
                "<h1>2026년 8월 수출입 동향</h1>"
                "<p>등록일 2026-09-01</p>"
                "<p>반도체 수출(466.5억 달러, +209.0%)</p>"
            ),
        }
        mock_download.side_effect = lambda url: bodies[url]

        frame = load_korea_semiconductor_exports.__wrapped__()

        monthly = frame[frame["series_id"] == "korea_semiconductor_exports_monthly"].iloc[0]
        self.assertEqual(monthly["yoy"], 209.0)
        self.assertEqual(monthly["source_name"], "韓国産業通商部 輸出入動向")

    @patch("data_loader.requests.get")
    def test_discovers_motir_monthly_release_from_press_list_fallback(
        self, mock_get
    ) -> None:
        home = unittest.mock.Mock(text="<html>no monthly link</html>")
        home.raise_for_status.return_value = None
        listing = unittest.mock.Mock(
            text=(
                '<a href="/kor/article/ATCL3f49a5a8c/172145/view">'
                "2026년 8월 수출입동향</a>"
            )
        )
        listing.raise_for_status.return_value = None
        mock_get.side_effect = [home, listing]

        url = _discover_korea_monthly_trade_release()

        self.assertEqual(
            url,
            "https://www.motir.go.kr/kor/article/ATCL3f49a5a8c/172145/view",
        )

    @patch("data_loader.requests.get")
    def test_discovers_current_kcs_data_attribute_link(self, mock_get) -> None:
        rss = """<?xml version="1.0" encoding="UTF-8"?>
        <rss><channel><item>
          <title>2026년 8월 1일 ~ 8월 20일 수출입 현황 [잠정치]</title>
          <link>https://official.example/20</link>
          <description>반도체(260 억 달러)</description>
        </item><item>
          <title>2026년 8월 수출입 현황 [잠정치]</title>
          <link>https://official.example/monthly</link>
        </item></channel></rss>""".encode("utf-8")
        listing = """
        <a href="javascript:" data-id="10172763"
           data-url="baccec5a7b47a665ac4d22878c83804b"
           title="2026년 8월 1일 ~ 8월 10일 수출입 현황 [잠정치]">
          2026년 8월 1일 ~ 8월 10일 수출입 현황 [잠정치]
        </a>
        """

        rss_response = unittest.mock.Mock(content=rss)
        rss_response.raise_for_status.return_value = None
        list_response = unittest.mock.Mock(text=listing)
        list_response.raise_for_status.return_value = None
        mock_get.side_effect = [rss_response, list_response]

        links = _discover_korea_release_links()

        one_to_ten = next(link for link in links if "1일 ~ 8월 10일" in link[0])
        self.assertIn("nttSn=10172763", one_to_ten[1])
        self.assertIn("nttSnUrl=baccec5a7b47a665ac4d22878c83804b", one_to_ten[1])

    @patch("data_loader.requests.get")
    def test_discovers_motir_monthly_release_from_official_home(self, mock_get) -> None:
        response = unittest.mock.Mock(
            text=(
                '<a href="/kor/article/ATCL3f49a5a8c/172145/view">'
                "2026년 8월 수출입동향</a>"
            )
        )
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        url = _discover_korea_monthly_trade_release()

        self.assertEqual(
            url,
            "https://www.motir.go.kr/kor/article/ATCL3f49a5a8c/172145/view",
        )

    def test_filters_nonstandard_trade_release_titles(self) -> None:
        self.assertEqual(
            _korea_release_title_kind(
                "2026년 8월 1일 ~ 8월 10일 수출입 현황 [잠정치]"
            ),
            "1_10",
        )
        self.assertEqual(
            _korea_release_title_kind("2026년 8월 수출입 현황 [잠정치]"),
            "monthly",
        )
        self.assertIsNone(
            _korea_release_title_kind("2026년 7월 기업규모별 수출입 현황")
        )
        self.assertIsNone(
            _korea_release_title_kind("2026년 7월 수출입 운송비용 현황")
        )

    @patch(
        "data_loader._discover_korea_monthly_trade_release",
        side_effect=DataUnavailableError("monthly unavailable"),
    )
    @patch("data_loader._download_text")
    @patch("data_loader._discover_korea_release_links")
    def test_uses_official_rss_body_when_article_link_has_no_body(
        self, mock_discover, mock_download, mock_monthly_discover
    ) -> None:
        mock_discover.return_value = [
            (
                "2026년 8월 1일 ~ 8월 20일 수출입 현황 [잠정치]",
                "https://official.example/rss-link",
                (
                    "<p>등록일 2026.08.21</p>"
                    "<p>반도체(260 억 달러) 수출 동기간 역대최대</p>"
                ),
            )
        ]

        frame = load_korea_semiconductor_exports.__wrapped__()

        official = frame[~frame["is_derived"]].iloc[0]
        self.assertEqual(
            official["series_id"], "korea_semiconductor_exports_1_20"
        )
        self.assertEqual(official["value"], 26_000)
        self.assertTrue(pd.isna(official["yoy"]))
        mock_download.assert_not_called()

    @patch("data_loader._download_text")
    @patch("data_loader._discover_korea_release_links")
    def test_loads_all_three_publication_periods_without_external_access(
        self, mock_discover, mock_download
    ) -> None:
        mock_discover.return_value = [
            ("1-10", "https://official.example/10"),
            ("1-20", "https://official.example/20"),
            ("monthly", "https://official.example/monthly"),
        ]
        bodies = {
            "https://official.example/10": (
                "<h1>2026년 8월 1일 ~ 8월 10일 수출입 현황 [잠정치]</h1>"
                "<p>등록일 2026.08.11 반도체(100 억 달러) 반도체(45.0%)</p>"
            ),
            "https://official.example/20": (
                "<h1>2026년 8월 1일 ~ 8월 20일 수출입 현황 [잠정치]</h1>"
                "<p>등록일 2026.08.21 반도체(260 억 달러) 반도체(50.0%)</p>"
            ),
            "https://official.example/monthly": (
                "<h1>2026년 8월 수출입 현황 [잠정치]</h1>"
                "<p>등록일 2026.09.01 반도체(400 억 달러) 반도체(55.0%)</p>"
            ),
        }
        mock_download.side_effect = lambda url: bodies[url]

        frame = load_korea_semiconductor_exports.__wrapped__()

        official = frame[~frame["is_derived"]]
        self.assertEqual(
            set(official["series_id"]),
            {
                "korea_semiconductor_exports_1_10",
                "korea_semiconductor_exports_1_20",
                "korea_semiconductor_exports_monthly",
            },
        )
        self.assertEqual(set(official["is_partial_period"]), {True, False})
        self.assertTrue(official["release_date"].notna().all())

    @patch(
        "data_loader._discover_korea_monthly_trade_release",
        side_effect=DataUnavailableError("monthly unavailable"),
    )
    @patch("data_loader._download_text")
    @patch("data_loader._discover_korea_release_links")
    def test_keeps_available_period_when_another_period_cannot_be_parsed(
        self, mock_discover, mock_download, mock_monthly_discover
    ) -> None:
        mock_discover.return_value = [
            ("1-20", "https://official.example/20"),
            ("monthly", "https://official.example/monthly"),
        ]
        mock_download.side_effect = [
            (
                "<h1>2026년 8월 1일 ~ 8월 20일 수출입 현황 [잠정치]</h1>"
                "<p>등록일 2026.08.21 반도체(260억 달러)</p>"
            ),
            "<h1>2026년 8월 수출입 현황 [잠정치]</h1><p>반도체 역대최대</p>",
        ]

        frame = load_korea_semiconductor_exports.__wrapped__()

        self.assertEqual(
            list(frame[~frame["is_derived"]]["series_id"]),
            ["korea_semiconductor_exports_1_20"],
        )
        self.assertEqual(frame.attrs["missing_periods"], ["1_10", "monthly"])


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

    @patch("data_loader.requests.get")
    def test_discovers_motir_monthly_archive_javascript_links(self, mock_get) -> None:
        response = unittest.mock.Mock(
            text="""
            <a href="javascript:article.view('163769');"><i>2021년 1월 수출입 동향</i></a>
            <a href="javascript:article.view('169932');"><i>2024년 11월 정보통신산업(ICT) 수출입 동향</i></a>
            <a href="javascript:article.view('172145');"><i>2026년 8월 수출입동향</i></a>
            """
        )
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        links = _discover_korea_monthly_trade_releases("2021-01-01")

        self.assertEqual(len(links), 3)
        self.assertEqual(links[0][1], "https://www.motir.go.kr/kor/article/ATCL3f49a5a8c/163769/view")
        self.assertIn("169932", links[1][1])
        self.assertIn("172145", links[2][1])

    @patch("data_loader._download_text")
    @patch("data_loader._discover_korea_monthly_trade_releases")
    def test_loads_monthly_history_with_official_yoy_and_release_dates(
        self, mock_discover, mock_download
    ) -> None:
        first_url = "https://official.example/2021-01"
        second_url = "https://official.example/2026-08"
        mock_discover.return_value = [
            ("2021년 1월 수출입 동향", first_url),
            ("2026년 8월 수출입동향", second_url),
        ]
        bodies = {
            first_url: """
                <h1>2021년 1월 수출입 동향</h1><p>등록일 2021-02-01</p>
                <p>반도체 수출(87.2억 달러, +21.7%)은 7개월 연속 증가했다.</p>
            """,
            second_url: """
                <h1>2026년 8월 수출입동향</h1><p>등록일 2026-09-01</p>
                <p>반도체 수출(466.5억 달러, +209.0%)은 역대 최대였다.</p>
            """,
        }
        mock_download.side_effect = lambda url: bodies[url]

        frame = load_korea_semiconductor_monthly_history.__wrapped__()

        self.assertEqual(len(frame), 2)
        self.assertEqual(frame.iloc[0]["reference_period"], pd.Timestamp("2021-01-01"))
        self.assertEqual(frame.iloc[0]["release_date"], pd.Timestamp("2021-02-01"))
        self.assertEqual(frame.iloc[0]["yoy"], 21.7)
        self.assertFalse(frame["yoy_is_derived"].any())
        self.assertEqual(frame.attrs["loaded_release_count"], 2)

    @patch("data_loader._download_text")
    @patch("data_loader._discover_korea_monthly_trade_releases")
    def test_monthly_history_prefers_structured_ict_releases(
        self, mock_discover, mock_download
    ) -> None:
        ict_url = "https://official.example/ict"
        mock_discover.return_value = [
            ("2024년 11월 수출입 동향", "https://official.example/general"),
            ("2024년 11월 정보통신산업(ICT) 수출입 동향", ict_url),
        ]
        mock_download.return_value = """
            <h1>2024년 11월 정보통신산업(ICT) 수출입 동향</h1>
            <p>등록일 2024-12-16</p>
            <p>○ (반도체 : 124.6 억불, 30.3%↑)</p>
        """

        frame = load_korea_semiconductor_monthly_history.__wrapped__()

        mock_download.assert_called_once_with(ict_url)
        self.assertEqual(frame.attrs["discovered_release_count"], 2)
        self.assertEqual(frame.attrs["requested_release_count"], 1)

    def test_merges_monthly_history_with_partial_current_data(self) -> None:
        base = {
            "region": "Korea", "series_name": "Korea", "unit": "million USD",
            "frequency": "monthly", "source_name": "official", "source_url": "url",
            "publication_stage": "preliminary_monthly", "working_days": None,
            "currency": "USD", "is_derived": False, "data_vintage": "preliminary_monthly",
            "yoy_is_derived": False, "fetched_at": pd.Timestamp("2026-09-02"),
        }
        history = pd.DataFrame([
            {**base, "series_id": "korea_semiconductor_exports_monthly",
             "reference_period": pd.Timestamp("2026-07-01"), "release_date": pd.Timestamp("2026-08-01"),
             "value": 41000.0, "yoy": 100.0, "is_partial_period": False,
             "period_start": pd.Timestamp("2026-07-01"), "period_end": pd.Timestamp("2026-07-31")},
        ])
        latest = pd.DataFrame([
            {**base, "series_id": "korea_semiconductor_exports_1_20",
             "reference_period": pd.Timestamp("2026-08-01"), "release_date": pd.Timestamp("2026-08-21"),
             "value": 26000.0, "yoy": 25.0, "is_partial_period": True,
             "period_start": pd.Timestamp("2026-08-01"), "period_end": pd.Timestamp("2026-08-20")},
            {**base, "series_id": "korea_semiconductor_exports_monthly",
             "reference_period": pd.Timestamp("2026-08-01"), "release_date": pd.Timestamp("2026-09-01"),
             "value": 46650.0, "yoy": None, "is_partial_period": False,
             "period_start": pd.Timestamp("2026-08-01"), "period_end": pd.Timestamp("2026-08-31")},
        ])

        result = merge_korea_semiconductor_exports(latest, history)

        self.assertEqual(len(result), 2)
        self.assertEqual(result.attrs["monthly_history_count"], 1)
        self.assertEqual(result.attrs["monthly_history_start"], pd.Timestamp("2026-07-01"))
        self.assertEqual(result.attrs["excluded_incomplete_monthly"], 1)

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
