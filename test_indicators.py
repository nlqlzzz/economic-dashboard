import unittest

from indicators import INDICATORS


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


if __name__ == "__main__":
    unittest.main()
