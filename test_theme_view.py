import unittest

import pandas as pd

from theme_view import (
    THEME_DEFINITIONS,
    build_theme_snapshot,
    relative_strength,
    theme_relationship_pairs,
    upcoming_theme_events,
)


class ThemeViewTest(unittest.TestCase):
    def test_defines_five_investment_themes(self):
        self.assertEqual(list(THEME_DEFINITIONS), ["半導体", "米国株", "日本株", "円", "Gold"])
        for theme in THEME_DEFINITIONS.values():
            self.assertGreaterEqual(len(theme["indicators"]), 5)
            self.assertEqual(len(theme["correlation_pair"]), 2)

    def test_semiconductor_theme_connects_japan_stocks_and_market_factors(self):
        semiconductor = THEME_DEFINITIONS["半導体"]

        self.assertTrue(
            {
                "東京エレクトロン（8035）",
                "アドバンテスト（6857）",
                "ディスコ（6146）",
                "キオクシア（285A）",
                "SOX指数",
                "USD/JPY",
                "UST 10Y",
                "VIX指数",
            }.issubset(semiconductor["indicators"])
        )
        self.assertIn(
            ("東京エレクトロン（8035）", "SOX指数"),
            theme_relationship_pairs(semiconductor, "relative"),
        )
        self.assertIn(
            ("東京エレクトロン（8035）", "USD/JPY"),
            theme_relationship_pairs(semiconductor, "correlation"),
        )

    def test_relationship_pairs_keep_single_pair_themes_compatible(self):
        self.assertEqual(
            theme_relationship_pairs(THEME_DEFINITIONS["米国株"], "relative"),
            [("NASDAQ総合指数", "S&P 500指数")],
        )

    def test_snapshot_uses_returns_for_prices_and_basis_points_for_yields(self):
        index = pd.date_range("2025-01-01", periods=25, freq="B")
        snapshot = build_theme_snapshot(
            {
                "株": pd.Series(range(100, 125), index=index, dtype=float),
                "金利": pd.Series(range(400, 425), index=index, dtype=float) / 100,
            },
            {
                "株": {"category": "マーケット", "unit": "pt"},
                "金利": {"category": "金利", "unit": "%"},
            },
        ).set_index("指標")

        self.assertEqual(snapshot.loc["株", "変化単位"], "%")
        self.assertEqual(snapshot.loc["金利", "変化単位"], "bp")
        self.assertAlmostEqual(snapshot.loc["金利", "直前変化"], 1.0)

    def test_relative_strength_reports_outperformance(self):
        index = pd.date_range("2025-01-01", periods=30, freq="B")
        left = pd.Series(range(100, 130), index=index, dtype=float)
        right = pd.Series(
            [100 + position // 2 for position in range(30)], index=index, dtype=float
        )

        ratio, one_month = relative_strength(left, right)

        self.assertAlmostEqual(ratio.iloc[0], 100.0)
        self.assertGreater(ratio.iloc[-1], 100.0)
        self.assertGreater(one_month, 0)

    def test_filters_upcoming_events_by_theme(self):
        events = pd.DataFrame(
            {
                "datetime": pd.to_datetime(
                    ["2026-09-01 21:30+09:00", "2026-09-02 21:30+09:00"]
                ),
                "event": ["米CPI", "米雇用統計"],
                "event_type": ["cpi", "employment"],
            }
        )

        selected = upcoming_theme_events(
            events, ["cpi"], pd.Timestamp("2026-08-25"), limit=3
        )

        self.assertEqual(list(selected["event"]), ["米CPI"])


if __name__ == "__main__":
    unittest.main()
