import unittest

from indicators import INDICATORS
from watchlist_storage import load_watchlists


class MarketIndicatorDefinitionsTest(unittest.TestCase):
    def test_requested_market_indicators_are_available(self):
        expected_tickers = {
            "金先物": "GC=F",
            "銀先物": "SI=F",
            "プラチナ先物": "PL=F",
            "NASDAQ総合指数": "^IXIC",
        }

        for name, ticker in expected_tickers.items():
            with self.subTest(name=name):
                self.assertIn(name, INDICATORS)
                self.assertEqual(INDICATORS[name]["ticker"], ticker)
                self.assertEqual(INDICATORS[name]["category"], "マーケット")

    def test_japanese_stocks_use_individual_stock_category(self):
        stock_names = {
            "キオクシア（285A）",
            "東京エレクトロン（8035）",
            "レーザーテック（6920）",
            "ディスコ（6146）",
            "アドバンテスト（6857）",
            "三菱商事（8058）",
            "三菱UFJ（8306）",
            "三菱重工（7011）",
            "任天堂（7974）",
        }

        for name in stock_names:
            with self.subTest(name=name):
                self.assertEqual(INDICATORS[name]["category"], "個別株")

        self.assertNotIn(
            "注目銘柄", {info["category"] for info in INDICATORS.values()}
        )

    def test_existing_watchlist_keeps_individual_stock_names(self):
        saved = '{"日本株":["任天堂（7974）","三菱UFJ（8306）"]}'

        watchlists = load_watchlists(saved, INDICATORS)

        self.assertEqual(
            watchlists["日本株"], ["任天堂（7974）", "三菱UFJ（8306）"]
        )


if __name__ == "__main__":
    unittest.main()
