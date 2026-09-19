import unittest
from unittest.mock import Mock, patch
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import requests

from global_semiconductor_demand import SEMICONDUCTOR_DATA_COLUMNS
from taiwan_export_orders_archive import (
    TaiwanArchiveRelease,
    TaiwanArchiveHttpClient,
    build_taiwan_news_archive_search_form,
    discover_taiwan_export_order_releases,
    parse_taiwan_archive_article,
    parse_taiwan_news_archive_search_result,
    load_taiwan_archive_snapshot,
    load_taiwan_archive_manifest,
    taiwan_archive_missing_months,
    validate_taiwan_archive_snapshot,
    parse_taiwan_export_orders_archive_text,
    parse_taiwan_export_orders_archive_attachment,
)
from data_loader import _load_taiwan_semiconductor_orders_archive


def release_text(
    roc_period: str,
    release: str,
    information_value: str,
    information_yoy_direction: str,
    information_yoy: str,
    electronic_value: str,
    electronic_yoy_direction: str,
    electronic_yoy: str,
) -> str:
    return f"""
    {roc_period}月份外銷訂單統計 DATE {release}
    資訊通信產品：{information_value}億美元，較上月減1.0%，
    較上年同月{information_yoy_direction}{information_yoy}%。
    電子產品：{electronic_value}億美元，較上月減1.0%，
    較上年同月{electronic_yoy_direction}{electronic_yoy}%。
    """


class TaiwanArchiveParserTest(unittest.TestCase):
    def test_discovers_only_explicit_links_from_2021(self) -> None:
        html = """
        <a href="/Mns/dos/content/Content.aspx?menu_id=35116">110年1月</a>
        <a href="/Mns/dos/content/Content.aspx?menu_id=35057">109年12月</a>
        <a href="javascript:void(0)">114年1月</a>
        <a data-url="/Mns/dos/content/Content.aspx?menu_id=43542">114年1月</a>
        """
        releases = discover_taiwan_export_order_releases(
            html, "https://www.moea.gov.tw/archive"
        )
        self.assertEqual([item.reference_period for item in releases], [
            pd.Timestamp("2021-01-01"), pd.Timestamp("2025-01-01")
        ])
        self.assertIn("menu_id=43542", releases[-1].article_url)

    def test_discovery_prefers_official_article_over_same_month_table(self) -> None:
        html = """
        <a href="/MNS/populace/news/News.aspx?news_id=118607">114年1月</a>
        <a href="/Mns/DOS/content/wHandMenuFile.ashx?file_id=36078">114年1月</a>
        """
        releases = discover_taiwan_export_order_releases(
            html, "https://www.moea.gov.tw/archive"
        )
        self.assertEqual(len(releases), 1)
        self.assertIn("News.aspx", releases[0].article_url)

    def test_rejects_pre_2021_start(self) -> None:
        with self.assertRaisesRegex(ValueError, "2021-01"):
            discover_taiwan_export_order_releases("", start_period="2020-12")

    def test_official_news_search_resolves_only_exact_month(self) -> None:
        form = build_taiwan_news_archive_search_form(
            '<input type="hidden" name="__VIEWSTATE" value="state">',
            pd.Timestamp("2023-06-01"),
        )
        self.assertEqual(
            form["ctl00$holderContent$txtQ_Title"], "112年6月外銷訂單統計"
        )
        result = """
        <a href="../news/News.aspx?kind=1&amp;menu_id=40&amp;news_id=110612">
          112年6月外銷訂單統計
        </a>
        """
        url = parse_taiwan_news_archive_search_result(
            result, pd.Timestamp("2023-06-01"),
            "https://www.moea.gov.tw/MNS/populace/news/News.aspx",
        )
        self.assertIn("news_id=110612", url)

    def test_article_uses_actual_timestamp_and_prefers_stable_press_pdf(self) -> None:
        html = """
        <h1>114年1月外銷訂單統計</h1><time>2025-02-20 16:00</time>
        <a href="/Mns/populace/news/wHandNews_File.ashx?file_id=123566">
          <img alt="開啟新聞稿.pdf檔">
        </a>
        <a href="/Mns/populace/news/wHandNews_File.ashx?file_id=123570"
           title="新聞稿全部附表 XLSX">XLSX</a>
        """
        period, released, attachment = parse_taiwan_archive_article(
            html, "https://www.moea.gov.tw/article"
        )
        self.assertEqual(period, pd.Timestamp("2025-01-01"))
        self.assertEqual(released, pd.Timestamp("2025-02-20 16:00"))
        self.assertIn("file_id=123566", attachment)

    def test_article_rejects_unknown_release_date(self) -> None:
        html = """
        <h1>114年1月外銷訂單統計</h1>
        <a href="/Mns/populace/news/wHandNews_File.ashx?file_id=1"
           title="新聞稿 PDF">PDF</a>
        """
        with self.assertRaisesRegex(ValueError, "実公表日"):
            parse_taiwan_archive_article(html, "https://www.moea.gov.tw/article")

    def test_2025_vintage_preserves_revision_difference(self) -> None:
        frame = parse_taiwan_export_orders_archive_text(
            release_text("114年1月", "114.2.20 16:00", "120.6", "減", "13.3", "177.1", "增", "1.5"),
            "https://official.example/2025-01.pdf",
            pd.Timestamp("2026-09-19", tz="Asia/Tokyo"),
        )
        by_series = frame.set_index("series_id")
        information = by_series.loc["taiwan_information_communication_export_orders"]
        electronic = by_series.loc["taiwan_electronic_export_orders"]
        self.assertEqual(information["value"], 12_060)
        self.assertEqual(electronic["value"], 17_710)
        self.assertNotEqual(information["value"], 12_445)
        self.assertNotEqual(electronic["value"], 18_252)
        self.assertEqual(information["yoy"], -13.3)
        self.assertEqual(electronic["yoy"], 1.5)
        self.assertEqual(information["release_date"], pd.Timestamp("2025-02-20 16:00"))
        self.assertEqual(tuple(frame.columns), SEMICONDUCTOR_DATA_COLUMNS)
        self.assertFalse(frame["yoy_is_derived"].any())
        self.assertEqual(set(frame["data_vintage"]), {"as_published_monthly_release"})

    def test_2023_fixture_converts_hundred_million_usd(self) -> None:
        frame = parse_taiwan_export_orders_archive_text(
            release_text("112年6月", "112.7.20 16:00", "123.0", "減", "27.4", "146.2", "減", "22.0"),
            "https://official.example/2023-06.pdf",
            pd.Timestamp("2026-09-19"),
        ).set_index("series_id")
        self.assertEqual(frame.loc["taiwan_information_communication_export_orders", "value"], 12_300)
        self.assertEqual(frame.loc["taiwan_electronic_export_orders", "value"], 14_620)

    def test_2021_date_only_does_not_invent_time(self) -> None:
        frame = parse_taiwan_export_orders_archive_text(
            release_text("110年1月", "110.2.24", "150.9", "增", "55.6", "169.3", "增", "64.3"),
            "https://official.example/2021-01.pdf",
            pd.Timestamp("2026-09-19"),
        )
        self.assertEqual(frame.iloc[0]["release_date"], pd.Timestamp("2021-02-24"))
        self.assertEqual(frame.iloc[0]["release_date"].hour, 0)

    def test_legacy_product_paragraph_allows_long_explanation_before_yoy(self) -> None:
        text = """
        110年8月份外銷訂單統計 DATE 110.9.24 16:00
        1.資訊通信產品：151.0億美元，主要因伺服器、網通產品及手機需求增加，
        加上遠距應用延續，客戶持續備貨；惟部分零組件供應仍受限制，
        各產品表現互有增減，較上年同月增12.3%。
        2.電子產品：170.0億美元，因新興科技應用需求持續，供應鏈積極備貨，
        加上晶圓代工產能需求暢旺，帶動接單表現，較上年同月增18.4%。
        3.光學器材：20.0億美元，較上年同月減1.0%。
        """
        frame = parse_taiwan_export_orders_archive_text(
            text, "https://official.example/2021-08.pdf", pd.Timestamp("2026-09-19")
        ).set_index("series_id")
        self.assertEqual(frame.loc["taiwan_information_communication_export_orders", "value"], 15_100)
        self.assertEqual(frame.loc["taiwan_information_communication_export_orders", "yoy"], 12.3)
        self.assertEqual(frame.loc["taiwan_electronic_export_orders", "value"], 17_000)
        self.assertEqual(frame.loc["taiwan_electronic_export_orders", "yoy"], 18.4)

    def test_product_paragraph_accepts_official_ze_modifier(self) -> None:
        text = """
        112年5月份外銷訂單統計 DATE 112.6.20 16:00
        1.資訊通信產品：126.0億美元，較上年同月則減9.5%。
        2.電子產品：154.7億美元，較上年同月則減16.6%。
        """
        frame = parse_taiwan_export_orders_archive_text(
            text, "https://official.example/2023-05.pdf", pd.Timestamp("2026-09-19")
        ).set_index("series_id")
        self.assertEqual(frame.loc["taiwan_information_communication_export_orders", "yoy"], -9.5)
        self.assertEqual(frame.loc["taiwan_electronic_export_orders", "yoy"], -16.6)

    def test_schema_mismatch_fails_without_current_csv_fallback(self) -> None:
        text = "114年1月份外銷訂單統計 DATE 114.2.20 電子產品：177.1億美元，較上年同月增1.5%。"
        with self.assertRaisesRegex(ValueError, "資訊與通信產品"):
            parse_taiwan_export_orders_archive_text(
                text, "https://official.example/broken.pdf", pd.Timestamp("2026-09-19")
            )

    @patch("taiwan_export_orders_archive._spreadsheet_to_text")
    def test_attachment_rejects_reference_period_mismatch(self, spreadsheet_text) -> None:
        spreadsheet_text.return_value = release_text(
            "114年2月", "114.3.20 16:00", "120.0", "增", "1.0", "150.0", "增", "2.0"
        )
        with self.assertRaisesRegex(ValueError, "対象月"):
            parse_taiwan_export_orders_archive_attachment(
                b"PK fixture", "https://official.example/wrong.xlsx", pd.Timestamp("2026-09-19"),
                reference_period=pd.Timestamp("2026-02-01"), release_date=None,
            )


class TaiwanArchiveSnapshotTest(unittest.TestCase):
    def snapshot(self) -> pd.DataFrame:
        first = parse_taiwan_export_orders_archive_text(
            release_text("114年2月", "114.3.20 16:00", "150.0", "增", "5.0", "170.0", "增", "6.0"),
            "https://official.example/2025-02.pdf", pd.Timestamp("2026-09-19"),
        )
        revised = parse_taiwan_export_orders_archive_text(
            release_text("114年1月", "114.2.20 16:00", "120.6", "減", "13.3", "177.1", "增", "1.5"),
            "https://official.example/2025-01.pdf", pd.Timestamp("2026-09-19"),
        )
        return pd.concat([first, revised], ignore_index=True)

    def test_snapshot_round_trip_preserves_strict_vintage(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.csv"
            self.snapshot().to_csv(path, index=False)
            frame = load_taiwan_archive_snapshot(path)
        self.assertEqual(tuple(frame.columns), SEMICONDUCTOR_DATA_COLUMNS)
        self.assertEqual(len(frame), 4)
        value = frame.loc[
            frame["series_id"].eq("taiwan_information_communication_export_orders")
            & frame["reference_period"].eq(pd.Timestamp("2025-01-01")), "value"
        ].item()
        self.assertEqual(value, 12_060)
        self.assertFalse(frame["yoy_is_derived"].any())
        self.assertTrue(frame["release_date"].notna().all())

    def test_snapshot_rejects_duplicate_and_incomplete_month(self) -> None:
        frame = self.snapshot()
        with self.assertRaisesRegex(ValueError, "重複"):
            validate_taiwan_archive_snapshot(pd.concat([frame, frame.iloc[[0]]], ignore_index=True))
        with self.assertRaisesRegex(ValueError, "2系列"):
            validate_taiwan_archive_snapshot(frame.iloc[1:].copy())

    def test_snapshot_rejects_missing_calendar_month(self) -> None:
        january = parse_taiwan_export_orders_archive_text(
            release_text("115年1月", "115.2.20 16:00", "150.0", "增", "5.0", "170.0", "增", "6.0"),
            "https://official.example/2026-01.pdf", pd.Timestamp("2026-09-19"),
        )
        march = parse_taiwan_export_orders_archive_text(
            release_text("115年3月", "115.4.20 16:00", "151.0", "增", "5.1", "171.0", "增", "6.1"),
            "https://official.example/2026-03.pdf", pd.Timestamp("2026-09-19"),
        )
        frame = pd.concat([january, march], ignore_index=True)
        self.assertEqual(taiwan_archive_missing_months(frame), ["2026-02"])
        with self.assertRaisesRegex(ValueError, "2026-02"):
            validate_taiwan_archive_snapshot(frame)

    def test_snapshot_accepts_three_continuous_months(self) -> None:
        january = parse_taiwan_export_orders_archive_text(
            release_text("115年1月", "115.2.20 16:00", "150.0", "增", "5.0", "170.0", "增", "6.0"),
            "https://official.example/2026-01.pdf", pd.Timestamp("2026-09-19"),
        )
        february = parse_taiwan_export_orders_archive_text(
            release_text("115年2月", "115.3.20 16:00", "150.5", "增", "5.0", "170.5", "增", "6.0"),
            "https://official.example/2026-02.pdf", pd.Timestamp("2026-09-19"),
        )
        march = parse_taiwan_export_orders_archive_text(
            release_text("115年3月", "115.4.20 16:00", "151.0", "增", "5.1", "171.0", "增", "6.1"),
            "https://official.example/2026-03.pdf", pd.Timestamp("2026-09-19"),
        )
        frame = pd.concat([january, february, march], ignore_index=True)
        self.assertEqual(taiwan_archive_missing_months(frame), [])
        validate_taiwan_archive_snapshot(frame)

    def test_snapshot_rejects_release_before_reference_month_end(self) -> None:
        frame = self.snapshot()
        frame.loc[frame["reference_period"].eq(pd.Timestamp("2025-01-01")), "release_date"] = pd.Timestamp("2024-12-20")
        with self.assertRaisesRegex(ValueError, "対象月末以前"):
            validate_taiwan_archive_snapshot(frame)

    def test_committed_snapshot_keeps_safe_range_and_2025_vintage(self) -> None:
        frame = load_taiwan_archive_snapshot()
        manifest = load_taiwan_archive_manifest()
        self.assertEqual(len(frame), 84)
        self.assertEqual(frame["reference_period"].nunique(), 42)
        self.assertEqual(frame["reference_period"].min(), pd.Timestamp("2022-08-01"))
        self.assertEqual(frame["reference_period"].max(), pd.Timestamp("2026-01-01"))
        self.assertEqual(manifest["safe_start_month"], "2022-08")
        self.assertEqual(manifest["latest_month"], "2026-01")
        self.assertEqual(manifest["missing_months"], [])
        self.assertEqual(taiwan_archive_missing_months(frame), [])
        january = frame[frame["reference_period"].eq(pd.Timestamp("2025-01-01"))].set_index("series_id")
        self.assertEqual(january.loc["taiwan_information_communication_export_orders", "value"], 12_060)
        self.assertEqual(january.loc["taiwan_electronic_export_orders", "value"], 17_710)


class TaiwanArchiveLoaderTest(unittest.TestCase):
    @patch("data_loader.parse_taiwan_export_orders_archive_attachment")
    @patch("data_loader.discover_taiwan_export_order_releases")
    def test_verified_legacy_pdf_uses_its_own_date_without_current_fallback(
        self, discover, parse_attachment
    ) -> None:
        client = Mock(spec=TaiwanArchiveHttpClient)
        client.minimum_interval_seconds = 3.0
        client.get_text.side_effect = [
            "listing", '<input type="hidden" name="__VIEWSTATE" value="state">',
        ]
        client.post_text.return_value = "no matching news article"
        client.get_attachment.return_value = (b"%PDF fixture", "application/pdf")
        discover.return_value = [
            TaiwanArchiveRelease(
                pd.Timestamp("2021-01-01"), "https://official/book", "110年1月"
            )
        ]
        parsed = parse_taiwan_export_orders_archive_text(
            release_text("110年1月", "110.2.24", "150.9", "增", "55.6", "169.3", "增", "64.3"),
            "https://official/press.pdf", pd.Timestamp("2026-09-19"),
        )
        parsed.attrs["attachment_sha256"] = "legacy"
        parse_attachment.return_value = parsed
        frame = _load_taiwan_semiconductor_orders_archive(
            start_period="2021-01", end_period="2021-01", http_client=client
        )
        self.assertEqual(frame.iloc[0]["release_date"], pd.Timestamp("2021-02-24"))
        self.assertEqual(
            parse_attachment.call_args.kwargs["release_date"],
            pd.Timestamp("2021-02-24"),
        )
        self.assertEqual(parse_attachment.call_args.args[1], "https://official/book")

    @patch("data_loader.parse_taiwan_export_orders_archive_attachment")
    @patch("data_loader.discover_taiwan_export_order_releases")
    def test_official_direct_attachment_must_supply_its_own_release_date(
        self, discover, parse_attachment
    ) -> None:
        client = Mock(spec=TaiwanArchiveHttpClient)
        client.minimum_interval_seconds = 3.0
        client.get_text.side_effect = [
            "listing", '<input type="hidden" name="__VIEWSTATE" value="state">',
        ]
        client.post_text.return_value = "no matching news article"
        client.get_attachment.return_value = (b"%PDF fixture", "application/pdf")
        official_attachment = (
            "https://www.moea.gov.tw/Mns/DOS/content/"
            "wHandMenuFile.ashx?file_id=38754"
        )
        discover.return_value = [
            TaiwanArchiveRelease(pd.Timestamp("2026-02-01"), official_attachment, "115年2月")
        ]
        parsed = parse_taiwan_export_orders_archive_text(
            release_text("115年2月", "115.3.20 16:00", "120.0", "增", "1.0", "150.0", "增", "2.0"),
            official_attachment, pd.Timestamp("2026-09-19"),
        )
        parsed.attrs["attachment_sha256"] = "direct"
        parse_attachment.return_value = parsed
        frame = _load_taiwan_semiconductor_orders_archive(
            start_period="2026-02", end_period="2026-02", http_client=client
        )
        self.assertEqual(len(frame), 2)
        self.assertIsNone(parse_attachment.call_args.kwargs["release_date"])
        self.assertEqual(parse_attachment.call_args.args[1], official_attachment)

    @patch("data_loader.parse_taiwan_export_orders_archive_attachment")
    @patch("data_loader.parse_taiwan_archive_article")
    @patch("data_loader.discover_taiwan_export_order_releases")
    def test_loader_is_independent_and_reports_coverage(
        self, discover, parse_article, parse_attachment
    ) -> None:
        client = Mock(spec=TaiwanArchiveHttpClient)
        client.minimum_interval_seconds = 3.0
        client.get_text.side_effect = [
            "listing", '<input type="hidden" name="__VIEWSTATE" value="state">',
            "article-a", "article-b",
        ]
        client.post_text.side_effect = [
            '<a href="News.aspx?news_id=1">110年1月外銷訂單統計</a>',
            '<a href="News.aspx?news_id=2">110年3月外銷訂單統計</a>',
        ]
        client.get_attachment.side_effect = [
            (b"file-a", "application/pdf"),
            (b"file-b", "application/pdf"),
        ]
        discover.return_value = [
            TaiwanArchiveRelease(pd.Timestamp("2021-01-01"), "https://official/a", "110年1月"),
            TaiwanArchiveRelease(pd.Timestamp("2021-03-01"), "https://official/b", "110年3月"),
        ]
        parse_article.side_effect = [
            (pd.Timestamp("2021-01-01"), pd.Timestamp("2021-02-24"), "https://official/a.xlsx"),
            (pd.Timestamp("2021-03-01"), pd.Timestamp("2021-04-20 16:00"), "https://official/b.xlsx"),
        ]

        def parsed(period: str, digest: str) -> pd.DataFrame:
            frame = parse_taiwan_export_orders_archive_text(
                release_text("110年1月", "110.2.24", "150.9", "增", "55.6", "169.3", "增", "64.3"),
                "https://official/file.xlsx",
                pd.Timestamp("2026-09-19"),
                reference_period=pd.Timestamp(period),
                release_date=pd.Timestamp(period) + pd.offsets.MonthEnd(1),
            )
            frame.attrs["attachment_sha256"] = digest
            return frame

        parse_attachment.side_effect = [parsed("2021-01-01", "aaa"), parsed("2021-03-01", "bbb")]
        frame = _load_taiwan_semiconductor_orders_archive(
            start_period="2021-01", end_period="2021-03", http_client=client
        )
        self.assertEqual(frame.attrs["expected_months"], 3)
        self.assertEqual(frame.attrs["discovered_months"], 2)
        self.assertEqual(frame.attrs["missing_discovery_months"], ["2021-02"])
        self.assertEqual(frame.attrs["attachment_hashes"], {"2021-01": "aaa", "2021-03": "bbb"})
        self.assertEqual(len(frame), 4)

    @patch("data_loader.parse_taiwan_export_orders_archive_attachment")
    @patch("data_loader.parse_taiwan_archive_article")
    @patch("data_loader.discover_taiwan_export_order_releases")
    def test_diagnostic_fetches_only_requested_representative_months(
        self, discover, parse_article, parse_attachment
    ) -> None:
        client = Mock(spec=TaiwanArchiveHttpClient)
        client.minimum_interval_seconds = 3.0
        client.get_text.side_effect = [
            "listing", '<input type="hidden" name="__VIEWSTATE" value="state">',
            "article-2021", "article-2025",
        ]
        client.post_text.side_effect = [
            '<a href="News.aspx?news_id=1">110年1月外銷訂單統計</a>',
            '<a href="News.aspx?news_id=2">114年1月外銷訂單統計</a>',
        ]
        client.get_attachment.side_effect = [
            (b"file-2021", "application/pdf"),
            (b"file-2025", "application/pdf"),
        ]
        discover.return_value = [
            TaiwanArchiveRelease(pd.Timestamp("2021-01-01"), "https://official/2021", "110年1月"),
            TaiwanArchiveRelease(pd.Timestamp("2021-02-01"), "https://official/not-requested", "110年2月"),
            TaiwanArchiveRelease(pd.Timestamp("2025-01-01"), "https://official/2025", "114年1月"),
        ]
        parse_article.side_effect = [
            (pd.Timestamp("2021-01-01"), pd.Timestamp("2021-02-24"), "https://official/2021.pdf"),
            (pd.Timestamp("2025-01-01"), pd.Timestamp("2025-02-20 16:00"), "https://official/2025.pdf"),
        ]

        def parsed(period: str, digest: str) -> pd.DataFrame:
            frame = parse_taiwan_export_orders_archive_text(
                release_text("110年1月", "110.2.24", "150.9", "增", "55.6", "169.3", "增", "64.3"),
                "https://official/file.pdf", pd.Timestamp("2026-09-19"),
                reference_period=pd.Timestamp(period), release_date=pd.Timestamp(period),
            )
            frame.attrs["attachment_sha256"] = digest
            return frame

        parse_attachment.side_effect = [parsed("2021-01-01", "a"), parsed("2025-01-01", "b")]
        frame = _load_taiwan_semiconductor_orders_archive(
            start_period="2021-01", end_period="2025-01",
            reference_periods=(pd.Timestamp("2021-01-01"), pd.Timestamp("2025-01-01")),
            http_client=client,
        )
        requested_urls = [call.args[0] for call in client.get_text.call_args_list]
        self.assertNotIn("https://official/not-requested", requested_urls)
        self.assertEqual(frame.attrs["selected_reference_periods"], ["2021-01", "2025-01"])


class TaiwanArchiveHttpClientTest(unittest.TestCase):
    @staticmethod
    def response(status: int, content: bytes = b"ok", **headers: str) -> requests.Response:
        response = requests.Response()
        response.status_code = status
        response._content = content
        response.headers.update(headers)
        response.url = "https://official.example/file"
        return response

    def test_enforces_interval_between_every_request(self) -> None:
        session = Mock()
        session.get.side_effect = [self.response(200), self.response(200)]
        sleeper = Mock()
        clock = Mock(side_effect=[10.0, 11.0, 14.0])
        client = TaiwanArchiveHttpClient(
            session=session, sleeper=sleeper, clock=clock, minimum_interval_seconds=3.0
        )
        client.get_text("https://official.example/listing")
        client.get_text("https://official.example/article")
        sleeper.assert_called_once_with(2.0)

    def test_429_honors_retry_after(self) -> None:
        session = Mock()
        session.get.side_effect = [
            self.response(429, b"<html>rate limited</html>", **{"Retry-After": "7"}),
            self.response(200, b"ok"),
        ]
        sleeper = Mock()
        client = TaiwanArchiveHttpClient(
            session=session, sleeper=sleeper, clock=lambda: 0.0,
            minimum_interval_seconds=0,
        )
        self.assertEqual(client.get_text("https://official.example"), "ok")
        sleeper.assert_called_once_with(7.0)

    def test_429_uses_bounded_backoff_and_never_parses_html(self) -> None:
        session = Mock()
        session.get.side_effect = [
            self.response(429, b"<html>rate limited</html>") for _ in range(4)
        ]
        sleeper = Mock()
        client = TaiwanArchiveHttpClient(
            session=session, sleeper=sleeper, clock=lambda: 0.0,
            minimum_interval_seconds=0,
        )
        with self.assertRaises(requests.HTTPError):
            client.get_attachment("https://official.example/file.pdf")
        self.assertEqual(session.get.call_count, 4)
        self.assertEqual([call.args[0] for call in sleeper.call_args_list], [5.0, 15.0, 30.0])

    def test_successful_html_error_page_is_not_an_attachment(self) -> None:
        session = Mock()
        session.get.return_value = self.response(
            200, b"<!DOCTYPE html><title>error</title>", **{"Content-Type": "text/html"}
        )
        client = TaiwanArchiveHttpClient(
            session=session, sleeper=Mock(), clock=lambda: 0.0,
            minimum_interval_seconds=0,
        )
        with self.assertRaisesRegex(ValueError, "PDF/XLSX"):
            client.get_attachment("https://official.example/file.pdf")

    def test_decodes_official_utf8_when_http_header_omits_charset(self) -> None:
        session = Mock()
        session.get.return_value = self.response(
            200, "110年1月外銷訂單".encode("utf-8")
        )
        client = TaiwanArchiveHttpClient(
            session=session, sleeper=Mock(), clock=lambda: 0.0,
            minimum_interval_seconds=0,
        )
        self.assertIn("110年1月", client.get_text("https://official.example"))


if __name__ == "__main__":
    unittest.main()
