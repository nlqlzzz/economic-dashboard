import unittest

import pandas as pd

from macro_regime import build_macro_focus_guide, build_us_macro_assessment_history


class MacroAssessmentHistoryTest(unittest.TestCase):
    def test_builds_focus_guide_for_each_macro_dimension(self) -> None:
        regime = {
            "labor": {"status": "悪化"},
            "inflation": {"status": "上昇"},
            "policy": {"status": "引き締め"},
            "curve": {"status": "逆イールド"},
        }

        guide = build_macro_focus_guide(regime)

        self.assertEqual(
            [item["dimension"] for item in guide],
            ["景気", "物価", "金融政策", "イールドカーブ"],
        )
        self.assertIn("VIX指数", guide[0]["indicators"])
        self.assertIn("WTI原油先物", guide[1]["indicators"])
        self.assertIn("UST 2Y", guide[2]["indicators"])
        self.assertIn("VIX指数", guide[3]["indicators"])

    def test_builds_historical_labels_and_scores(self) -> None:
        dates = pd.date_range("2024-01-01", periods=18, freq="MS")
        cpi = pd.Series([100 + index for index in range(18)], index=dates)
        unemployment = pd.Series(
            [4.0] * 15 + [4.1, 4.2, 4.3], index=dates
        )
        fed_funds = pd.Series(
            [5.5] * 15 + [5.4, 5.2, 5.0], index=dates
        )
        ust_2y = pd.Series([4.5] * 18, index=dates)
        ust_10y = pd.Series([4.0] * 17 + [4.8], index=dates)

        labels, scores = build_us_macro_assessment_history(
            cpi, unemployment, fed_funds, ust_2y, ust_10y
        )

        self.assertEqual(
            labels.iloc[-1].to_dict(),
            {
                "景気": "悪化",
                "物価": "鈍化",
                "金融政策": "緩和",
                "イールドカーブ": "順イールド",
            },
        )
        self.assertEqual(
            scores.iloc[-1].to_dict(),
            {
                "景気": -1,
                "物価": 1,
                "金融政策": 1,
                "イールドカーブ": 1,
            },
        )
        self.assertEqual(labels.columns.tolist(), scores.columns.tolist())


if __name__ == "__main__":
    unittest.main()
