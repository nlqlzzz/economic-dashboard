import unittest

import pandas as pd

from market_hypotheses import build_market_factor_hypotheses


class MarketFactorHypothesesTest(unittest.TestCase):
    def setUp(self) -> None:
        dates = pd.date_range("2026-01-01", periods=3, freq="B")
        self.series = {
            "S&P 500指数": pd.Series([100, 101, 99], index=dates),
            "VIX指数": pd.Series([15, 16, 19], index=dates),
            "UST 10Y": pd.Series([4.0, 4.02, 4.08], index=dates),
            "USD/JPY": pd.Series([150, 151, 152], index=dates),
        }
        self.stress_result = {
            "coverage": 5,
            "total_components": 5,
            "unavailable": [],
            "components": pd.DataFrame(
                [
                    self._component("VIX水準", 90),
                    self._component("S&P 500 20日実現ボラ", 80),
                    self._component("S&P 500 60日高値からの下落", 85),
                    self._component("米10年金利 日次変化幅", 75),
                    self._component("USD/JPY 20日実現ボラ", 60),
                ]
            ),
        }
        self.macro = {
            "regime": "リフレ・過熱寄り",
            "labor": {"status": "改善"},
            "inflation": {"status": "上昇"},
            "policy": {"status": "引き締め"},
            "curve": {"status": "順イールド"},
        }

    def _component(self, name: str, percentile: float) -> dict[str, object]:
        return {
            "項目": name,
            "過去5年percentile": percentile,
            "サンプル数": 1000,
            "基準日": pd.Timestamp("2026-08-25"),
        }

    def test_returns_ranked_explainable_hypotheses(self) -> None:
        result = build_market_factor_hypotheses(
            self.stress_result, self.series, self.macro
        )

        self.assertEqual(len(result["hypotheses"]), 3)
        self.assertIn("リスク回避", result["hypotheses"][0]["title"])
        self.assertGreaterEqual(result["hypotheses"][0]["observation_count"], 3)
        self.assertTrue(result["hypotheses"][0]["observations"])
        strength_order = {"強い": 3, "中程度": 2, "限定的": 1}
        strengths = [
            strength_order[item["strength"]] for item in result["hypotheses"]
        ]
        self.assertEqual(strengths, sorted(strengths, reverse=True))
        self.assertEqual(result["input_coverage"], 5)
        self.assertEqual(result["observed_at"], pd.Timestamp("2026-08-25"))

    def test_reports_counter_evidence_when_rates_and_equities_move_together(self) -> None:
        dates = self.series["S&P 500指数"].index
        same_direction = self.series.copy()
        same_direction["S&P 500指数"] = pd.Series([100, 101, 102], index=dates)

        result = build_market_factor_hypotheses(
            self.stress_result, same_direction, self.macro, maximum_hypotheses=4
        )

        rates = next(
            item for item in result["hypotheses"] if "金利" in item["title"]
        )
        self.assertTrue(rates["counter_evidence"])

    def test_continues_with_missing_series_and_discloses_it(self) -> None:
        result = build_market_factor_hypotheses(
            self.stress_result,
            {"S&P 500指数": self.series["S&P 500指数"]},
            self.macro,
        )

        self.assertTrue(result["hypotheses"])
        self.assertTrue(any("VIX指数" in item for item in result["unavailable"]))

    def test_limits_output_to_requested_count(self) -> None:
        result = build_market_factor_hypotheses(
            self.stress_result,
            self.series,
            self.macro,
            maximum_hypotheses=2,
        )

        self.assertEqual(len(result["hypotheses"]), 2)


if __name__ == "__main__":
    unittest.main()
