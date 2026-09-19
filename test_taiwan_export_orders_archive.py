import unittest
from unittest.mock import patch

import pandas as pd

from global_semiconductor_demand import SEMICONDUCTOR_DATA_COLUMNS
from taiwan_export_orders_archive import (
    TaiwanArchiveRelease,
    discover_taiwan_export_order_releases,
    parse_taiwan_archive_article,
    parse_taiwan_export_orders_archive_text,
)
from data_loader import load_taiwan_semiconductor_orders_archive


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

    def test_rejects_pre_2021_start(self) -> None:
        with self.assertRaisesRegex(ValueError, "2021-01"):
            discover_taiwan_export_order_releases("", start_period="2020-12")

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

    def test_schema_mismatch_fails_without_current_csv_fallback(self) -> None:
        text = "114年1月份外銷訂單統計 DATE 114.2.20 電子產品：177.1億美元，較上年同月增1.5%。"
        with self.assertRaisesRegex(ValueError, "資訊與通信產品"):
            parse_taiwan_export_orders_archive_text(
                text, "https://official.example/broken.pdf", pd.Timestamp("2026-09-19")
            )


class TaiwanArchiveLoaderTest(unittest.TestCase):
    @patch("data_loader.time.sleep")
    @patch("data_loader.parse_taiwan_export_orders_archive_attachment")
    @patch("data_loader.parse_taiwan_archive_article")
    @patch("data_loader.discover_taiwan_export_order_releases")
    @patch("data_loader._download_bytes")
    @patch("data_loader._download_text")
    def test_loader_is_independent_and_reports_coverage(
        self, download_text, download_bytes, discover, parse_article, parse_attachment, _sleep
    ) -> None:
        download_text.side_effect = ["listing", "article-a", "article-b"]
        download_bytes.side_effect = [b"file-a", b"file-b"]
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
        frame = load_taiwan_semiconductor_orders_archive.__wrapped__(
            start_period="2021-01", end_period="2021-03"
        )
        self.assertEqual(frame.attrs["expected_months"], 3)
        self.assertEqual(frame.attrs["discovered_months"], 2)
        self.assertEqual(frame.attrs["missing_discovery_months"], ["2021-02"])
        self.assertEqual(frame.attrs["attachment_hashes"], {"2021-01": "aaa", "2021-03": "bbb"})
        self.assertEqual(len(frame), 4)


if __name__ == "__main__":
    unittest.main()
