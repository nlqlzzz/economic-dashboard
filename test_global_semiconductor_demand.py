import unittest

import pandas as pd

from global_semiconductor_demand import (
    classify_demand_direction,
    parse_korea_customs_release,
    parse_korea_monthly_trade_release,
    parse_taiwan_export_orders_csv,
    summarize_global_demand,
)


class GlobalSemiconductorDemandTest(unittest.TestCase):
    def test_parses_official_motir_monthly_semiconductor_exports(self) -> None:
        html = """
        <h1>2026년 8월 수출입동향</h1>
        <p>등록일 2026-09-01</p>
        <p>반도체 수출 467억 달러로 역대 최대 기록 경신</p>
        <p>반도체 수출(466.5억 달러, +209.0%)은 역대 최대 기록을 경신했다.</p>
        """

        frame = parse_korea_monthly_trade_release(
            html, "https://official.example/monthly", pd.Timestamp("2026-09-02")
        )

        row = frame.iloc[0]
        self.assertEqual(row["series_id"], "korea_semiconductor_exports_monthly")
        self.assertEqual(row["value"], 46_650)
        self.assertEqual(row["yoy"], 209.0)
        self.assertEqual(row["release_date"], pd.Timestamp("2026-09-01"))
        self.assertFalse(row["is_partial_period"])

    def test_parses_taiwan_orders_and_keeps_release_date_unknown(self) -> None:
        lines = ["統計項目,貨品別,資料期(民國年),統計值(金額),計量單位"]
        for year in (112, 113):
            for month in range(1, 13):
                value = 100 + (year - 112) * 20 + month
                lines.append(
                    f"外銷訂單金額_美元,電子產品,{year:03d}{month:02d},{value},百萬美元"
                )
        frame = parse_taiwan_export_orders_csv(
            "\n".join(lines).encode(),
            "https://official.example/taiwan.csv",
            pd.Timestamp("2026-09-01", tz="Asia/Tokyo"),
        )

        latest = frame.iloc[-1]
        self.assertEqual(latest["reference_period"], pd.Timestamp("2024-12-01"))
        self.assertTrue(pd.isna(latest["release_date"]))
        self.assertAlmostEqual(latest["yoy"], (132 / 112 - 1) * 100)
        self.assertTrue(latest["yoy_is_derived"])
        self.assertFalse(latest["is_partial_period"])

    def test_rejects_taiwan_schema_change(self) -> None:
        with self.assertRaises(ValueError):
            parse_taiwan_export_orders_csv(
                b"wrong,column\n1,2",
                "https://official.example/taiwan.csv",
                pd.Timestamp("2026-09-01", tz="Asia/Tokyo"),
            )

    def test_parses_korea_partial_release_and_marks_derived_values(self) -> None:
        html = """
        <html><body>
        <h1>2026년 8월 1일 ~ 8월 10일 수출입 현황 [잠정치]</h1>
        <div>등록일 2026.08.11</div>
        <p>반도체(100 억 달러) 수출 역대최대</p>
        <p>주요품목은 반도체(45.0%) 증가</p>
        <p>※조업일수[(’25)7.0 일,(’26)7.0 일]고려</p>
        </body></html>
        """
        frame = parse_korea_customs_release(
            html,
            "https://official.example/korea",
            pd.Timestamp("2026-09-01", tz="Asia/Tokyo"),
        )

        official = frame[~frame["is_derived"]].iloc[0]
        derived = frame[frame["is_derived"]].iloc[0]
        self.assertEqual(official["value"], 10000.0)
        self.assertEqual(official["release_date"], pd.Timestamp("2026-08-11"))
        self.assertEqual(official["period_end"], pd.Timestamp("2026-08-10"))
        self.assertEqual(official["publication_stage"], "preliminary_partial")
        self.assertTrue(official["is_partial_period"])
        self.assertEqual(derived["unit"], "million USD per working day")
        self.assertTrue(derived["yoy_is_derived"])

    def test_does_not_derive_working_day_adjustment_when_prior_days_missing(self) -> None:
        html = """
        <h1>2026년 8월 1일 ~ 8월 20일 수출입 현황 [잠정치]</h1>
        <div>등록일 2026.08.21</div>
        <p>반도체(260 억 달러) 수출, 반도체(50.0%) 증가</p>
        """
        frame = parse_korea_customs_release(
            html,
            "https://official.example/korea",
            pd.Timestamp("2026-09-01", tz="Asia/Tokyo"),
        )

        self.assertEqual(len(frame), 1)
        self.assertFalse(frame.iloc[0]["is_derived"])
        self.assertTrue(pd.isna(frame.iloc[0]["working_days"]))

    def test_accepts_official_amount_when_semiconductor_yoy_is_not_in_text(self) -> None:
        html = """
        <h1>2026년 8월 1일 ~ 8월 20일 수출입 현황 [잠정치]</h1>
        <div>등록일 2026.08.21</div>
        <p>동기간 수출 역대최대 / 반도체(260억 달러) 수출 동기간 역대최대</p>
        <p>※조업일수[(’25)14.5일,(’26)14.0일]고려</p>
        """

        frame = parse_korea_customs_release(
            html,
            "https://official.example/korea",
            pd.Timestamp("2026-09-01", tz="Asia/Tokyo"),
        )

        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["value"], 26000.0)
        self.assertTrue(pd.isna(frame.iloc[0]["yoy"]))
        self.assertFalse(frame.iloc[0]["is_derived"])

    def test_accepts_monthly_semiconductor_export_wording(self) -> None:
        html = """
        <h1>2026년 7월 월간 수출입 현황 [확정치]</h1>
        <div>등록일 2026.08.18</div>
        <p>반도체 수출(412억 달러) 2개월 연속 증가</p>
        """

        frame = parse_korea_customs_release(
            html,
            "https://official.example/korea",
            pd.Timestamp("2026-09-01", tz="Asia/Tokyo"),
        )

        self.assertEqual(frame.iloc[0]["value"], 41200.0)
        self.assertTrue(pd.isna(frame.iloc[0]["yoy"]))

    def test_distinguishes_korea_monthly_from_partial_period(self) -> None:
        html = """
        <h1>2026년 7월 월간 수출입 현황 [확정치]</h1>
        <div>등록일 2026.08.18</div>
        <p>반도체(412 억 달러), 반도체(60.0%) 증가</p>
        """
        frame = parse_korea_customs_release(
            html,
            "https://official.example/korea",
            pd.Timestamp("2026-09-01", tz="Asia/Tokyo"),
        )
        row = frame.iloc[0]
        self.assertFalse(row["is_partial_period"])
        self.assertEqual(row["publication_stage"], "final_monthly")
        self.assertEqual(row["period_end"], pd.Timestamp("2026-07-31"))

    def test_classification_exposes_evidence_and_handles_missing_country(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "region": "Taiwan",
                    "series_id": "orders",
                    "series_name": "台湾受注",
                    "reference_period": pd.Timestamp("2026-07-01"),
                    "release_date": pd.NaT,
                    "value": 120.0,
                    "unit": "million USD",
                    "yoy": 10.0,
                    "frequency": "monthly",
                    "source_name": "official",
                    "source_url": "https://official.example",
                    "publication_stage": "official_monthly",
                    "is_partial_period": False,
                    "period_start": pd.Timestamp("2026-07-01"),
                    "period_end": pd.Timestamp("2026-07-31"),
                    "working_days": None,
                    "fetched_at": pd.Timestamp("2026-09-01"),
                    "currency": "USD",
                    "is_derived": False,
                    "data_vintage": None,
                    "yoy_is_derived": True,
                }
            ]
        )
        summary = summarize_global_demand(frame)
        taiwan = classify_demand_direction(summary, "Taiwan")
        korea = classify_demand_direction(summary, "Korea")

        self.assertEqual(taiwan["status"], "Improving")
        self.assertTrue(taiwan["evidence"])
        self.assertEqual(korea["status"], "Unavailable")


if __name__ == "__main__":
    unittest.main()
