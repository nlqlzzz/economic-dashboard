import unittest

import pandas as pd

from valuation import (
    assess_current_forward_per,
    build_forecast_eps_revisions,
    build_historical_forward_per,
    forecast_available_on,
    select_current_forecast_eps,
    normalized_pbr_readiness,
    sector_valuation_caution,
    split_basis_status_from_daily_bars,
)
from scripts.diagnose_valuation import _load_adjustment_bars, build_live_report


def _forecast(
    value=100.0,
    fiscal_year="2027",
    disclosure_date="2026-08-01",
    unit="JPY",
    currency="JPY",
    ticker="7203.T",
):
    return {
        "ticker": ticker,
        "metric": "forecast_eps",
        "value": value,
        "fiscal_year": fiscal_year,
        "reference_period": "2027-03-31",
        "disclosure_date": disclosure_date,
        "accounting_standard": "Japan GAAP",
        "consolidated_flag": True,
        "unit": unit,
        "currency": currency,
    }


def _prices():
    index = pd.bdate_range("2026-08-03", periods=5)
    return pd.Series([1000, 1010, 1020, 1030, 1040], index=index, dtype=float)


class ValuationReadinessTest(unittest.TestCase):
    def test_positive_forecast_and_price_calculate_forward_per(self):
        result = assess_current_forward_per(
            pd.DataFrame([_forecast()]), _prices(), split_basis_status="basis_verified"
        )
        self.assertTrue(result.calculable)
        self.assertEqual(result.status, "GO")
        self.assertAlmostEqual(result.forward_per, 10.4)

    def test_non_positive_or_missing_eps_is_not_calculable(self):
        for value in (0, -10, None):
            with self.subTest(value=value):
                result = assess_current_forward_per(
                    pd.DataFrame([_forecast(value=value)]), _prices(),
                    split_basis_status="basis_verified"
                )
                self.assertFalse(result.calculable)
                self.assertIsNone(result.forward_per)

    def test_future_disclosure_is_not_used_for_current_price(self):
        result = assess_current_forward_per(
            pd.DataFrame([_forecast(disclosure_date="2026-09-01")]),
            _prices(),
            split_basis_status="basis_verified",
        )
        self.assertFalse(result.calculable)
        self.assertIn("株価基準日までに公表済み", result.reason)

    def test_unit_and_currency_mismatch_is_rejected(self):
        for unit, currency in (("USD/share", "USD"), (None, "JPY")):
            with self.subTest(unit=unit, currency=currency):
                result = assess_current_forward_per(
                    pd.DataFrame([_forecast(unit=unit, currency=currency)]),
                    _prices(),
                    split_basis_status="basis_verified",
                )
                self.assertFalse(result.calculable)
                self.assertIn("単位または通貨", result.reason)

    def test_unknown_split_basis_stops_a_mathematical_candidate(self):
        result = assess_current_forward_per(pd.DataFrame([_forecast()]), _prices())
        self.assertFalse(result.calculable)
        self.assertIsNone(result.forward_per)
        self.assertIn("per-share basis未確認", result.reason)

    def test_same_fiscal_year_revisions_are_compared(self):
        records = pd.DataFrame([
            _forecast(100, disclosure_date="2026-05-01"),
            _forecast(120, disclosure_date="2026-08-01"),
        ])
        revisions = build_forecast_eps_revisions(records, basis_directly_verified=True)
        latest = revisions.iloc[-1]
        self.assertEqual(latest["previous_forecast_eps"], 100)
        self.assertEqual(latest["change"], 20)
        self.assertEqual(latest["change_pct"], 20)
        self.assertEqual(latest["revision_direction"], "up")

    def test_different_fiscal_years_are_not_revision_compared(self):
        records = pd.DataFrame([
            _forecast(100, fiscal_year="2026", disclosure_date="2026-05-01"),
            _forecast(120, fiscal_year="2027", disclosure_date="2026-08-01"),
        ])
        revisions = build_forecast_eps_revisions(records)
        self.assertTrue(revisions["previous_forecast_eps"].isna().all())
        self.assertTrue(revisions["revision_direction"].eq("comparison_unavailable").all())

    def test_zero_crossing_uses_amount_and_state_not_percentage(self):
        records = pd.DataFrame([
            _forecast(-10, disclosure_date="2026-05-01"),
            _forecast(20, disclosure_date="2026-08-01"),
        ])
        latest = build_forecast_eps_revisions(
            records, basis_directly_verified=True
        ).iloc[-1]
        self.assertEqual(latest["change"], 30)
        self.assertTrue(pd.isna(latest["change_pct"]))
        self.assertEqual(latest["revision_direction"], "turned_positive")

    def test_disclosure_is_effective_only_after_its_date(self):
        records = pd.DataFrame([_forecast(disclosure_date="2026-08-03")])
        self.assertIsNone(forecast_available_on(records, "2026-08-03"))
        self.assertEqual(
            forecast_available_on(records, "2026-08-04")["value"], 100
        )
        history = build_historical_forward_per(
            records, _prices(), split_basis_status="basis_verified"
        )
        self.assertNotIn("2026-08-03", set(history["price_date"]))
        self.assertIn("2026-08-04", set(history["price_date"]))

    def test_sector_cautions_distinguish_bank_and_insurance(self):
        self.assertIn("信用コスト", sector_valuation_caution("銀行"))
        self.assertIn("自然災害", sector_valuation_caution("保険"))
        self.assertNotEqual(
            sector_valuation_caution("銀行"), sector_valuation_caution("自動車・輸送機")
        )

    def test_current_normalized_schema_is_not_pbr_ready(self):
        result = normalized_pbr_readiness(pd.DataFrame([_forecast()]))
        self.assertEqual(result["status"], "NO-GO")
        self.assertEqual(result["available_metrics"], [])

    def test_adjustment_factor_evidence_distinguishes_split_status(self):
        dates = pd.bdate_range("2026-08-03", periods=6)
        aligned = pd.DataFrame({"Date": dates, "AdjFactor": [1.0] * len(dates)})
        changed = aligned.copy()
        changed.loc[2, "AdjFactor"] = 0.5

        self.assertEqual(
            split_basis_status_from_daily_bars(aligned, "2026-08-02", dates[-1]),
            "no_effective_action_detected"
        )
        self.assertEqual(
            split_basis_status_from_daily_bars(changed, "2026-08-02", dates[-1]),
            "corporate_action_detected",
        )
        self.assertEqual(
            split_basis_status_from_daily_bars(aligned.iloc[-1:], "2026-07-01", dates[-1]),
            "unknown",
        )

    def test_live_report_keeps_core20_coverage_numeric_and_partial(self):
        records = pd.DataFrame([
            _forecast(90, disclosure_date="2026-05-01"),
            _forecast(100, disclosure_date="2026-08-01"),
        ])
        prices = pd.DataFrame({"7203.T": _prices()})
        bars = pd.DataFrame({
            "Date": _prices().index,
            "AdjFactor": [1.0] * len(_prices()),
        })
        report = build_live_report(
            records,
            prices,
            pd.DataFrame({"BPS": [500.0], "ShOutFY": [1_000_000]}),
            adjustment_bars={"7203.T": bars},
        )

        self.assertEqual(len(report["rows"]), 20)
        self.assertEqual(report["coverage"]["safe_current_forward_per"], 0)
        self.assertEqual(report["coverage"]["forecast_revision_comparable"], 0)
        self.assertEqual(report["coverage"]["safe_historical_forward_per"], 0)
        self.assertEqual(report["raw_summary_field_non_null_rows"]["BPS"], 1)

    def test_revision_requires_same_reference_period(self):
        first = _forecast(100, disclosure_date="2026-05-01")
        second = _forecast(120, disclosure_date="2026-08-01")
        second["reference_period"] = "2027-06-30"
        revisions = build_forecast_eps_revisions(
            pd.DataFrame([first, second]), basis_directly_verified=True
        )
        self.assertTrue(revisions["previous_forecast_eps"].isna().all())

    def test_split_between_forecasts_is_not_counted_as_revision(self):
        records = pd.DataFrame([
            _forecast(300, disclosure_date="2026-05-01"),
            _forecast(100, disclosure_date="2026-08-01"),
        ])
        dates = pd.bdate_range("2026-05-04", "2026-08-03")
        bars = pd.DataFrame({"Date": dates, "AdjFactor": [1.0] * len(dates)})
        bars.loc[bars["Date"].eq(pd.Timestamp("2026-07-01")), "AdjFactor"] = 1 / 3
        latest = build_forecast_eps_revisions(
            records, adjustment_bars=bars, basis_directly_verified=True
        ).iloc[-1]
        self.assertEqual(latest["basis_status"], "basis_changed")
        self.assertEqual(latest["revision_direction"], "basis_changed")
        self.assertTrue(pd.isna(latest["change_pct"]))

    def test_revision_without_direct_basis_evidence_is_unverified(self):
        records = pd.DataFrame([
            _forecast(100, disclosure_date="2026-05-01"),
            _forecast(120, disclosure_date="2026-08-01"),
        ])
        latest = build_forecast_eps_revisions(records).iloc[-1]
        self.assertEqual(latest["basis_status"], "basis_unverified")
        self.assertEqual(latest["revision_direction"], "basis_unverified")

    def test_expired_or_invalid_forecast_is_not_used_in_history(self):
        expired = _forecast(disclosure_date="2026-08-01")
        expired["reference_period"] = "2026-08-04"
        records = pd.DataFrame([expired])
        self.assertIsNotNone(forecast_available_on(records, "2026-08-04"))
        self.assertIsNone(forecast_available_on(records, "2026-08-05"))
        history = build_historical_forward_per(
            records, _prices(), split_basis_status="basis_verified"
        )
        self.assertEqual(set(history["price_date"]), {"2026-08-03", "2026-08-04"})

    def test_valid_next_forecast_wins_over_expired_current_forecast(self):
        current = _forecast(100, fiscal_year="2026", disclosure_date="2026-05-01")
        current["reference_period"] = "2026-06-30"
        current["forecast_scope"] = "current_fy"
        current["source_field"] = "FEPS"
        next_year = _forecast(130, fiscal_year="2027", disclosure_date="2026-05-01")
        next_year["forecast_scope"] = "next_fy"
        next_year["source_field"] = "NxFEPS"
        selected = select_current_forecast_eps(
            pd.DataFrame([current, next_year]), "2026-08-05"
        )
        self.assertEqual(selected["value"], 130)
        self.assertEqual(selected["source_field"], "NxFEPS")

    def test_next_eps_continues_into_same_year_current_eps_revision(self):
        next_year = _forecast(100, fiscal_year="2027", disclosure_date="2026-05-01")
        next_year["source_field"] = "NxFEPS"
        next_year["forecast_scope"] = "next_fy"
        current = _forecast(120, fiscal_year="2027", disclosure_date="2026-08-01")
        current["source_field"] = "FEPS"
        current["forecast_scope"] = "current_fy"
        latest = build_forecast_eps_revisions(
            pd.DataFrame([next_year, current]), basis_directly_verified=True
        ).iloc[-1]
        self.assertEqual(latest["previous_forecast_eps"], 100)
        self.assertEqual(latest["revision_direction"], "up")

    def test_delayed_jquants_range_keeps_past_basis_evidence_but_stops_current_per(self):
        records = pd.DataFrame([
            _forecast(100, disclosure_date="2026-05-01"),
            _forecast(120, disclosure_date="2026-08-01"),
        ])
        prices = pd.DataFrame({
            "7203.T": pd.Series(
                [1000.0, 1100.0], index=pd.to_datetime(["2026-05-04", "2026-09-15"])
            )
        })
        dates = pd.bdate_range("2026-05-01", "2026-08-31")
        bars = pd.DataFrame({"Date": dates, "AdjFactor": [1.0] * len(dates)})

        class FakeClient:
            def __init__(self):
                self.calls = []
            def get_eq_bars_daily(self, **kwargs):
                self.calls.append(kwargs)
                return bars

        client = FakeClient()
        loaded, failures = _load_adjustment_bars(
            records, prices, 0, client=client
        )
        self.assertEqual(failures, ())
        self.assertNotIn("to_yyyymmdd", client.calls[0])
        revisions = build_forecast_eps_revisions(
            records, adjustment_bars=loaded["7203.T"]
        )
        self.assertEqual(revisions.iloc[-1]["basis_evidence"], "no_effective_action_detected")
        report = build_live_report(
            records, prices, pd.DataFrame(), adjustment_bars=loaded
        )
        toyota = next(row for row in report["rows"] if row["ticker"] == "7203.T")
        self.assertFalse(toyota["calculable"])
        self.assertEqual(toyota["freshness"]["latest_jquants_price_date"], "2026-08-31")
        self.assertEqual(toyota["freshness"]["jquants_price_lag_vs_yahoo_days"], 15)

    def test_adjustment_api_failure_is_safely_classified_without_body(self):
        records = pd.DataFrame([_forecast()])
        prices = pd.DataFrame({"7203.T": _prices()})

        class Response:
            status_code = 429
        class ProviderError(Exception):
            response = Response()
        class FakeClient:
            def get_eq_bars_daily(self, **kwargs):
                raise ProviderError("secret provider response must not be retained")

        _, failures = _load_adjustment_bars(records, prices, 0, client=FakeClient())
        self.assertEqual(failures, ({
            "code": "7203", "category": "rate_limit", "http_status": 429
        },))
        self.assertNotIn("provider", str(failures))


if __name__ == "__main__":
    unittest.main()
