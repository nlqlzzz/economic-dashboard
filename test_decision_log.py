import json
from pathlib import Path
import unittest
from datetime import datetime

import pandas as pd

from decision_log import (
    DEFAULT_DECISION_MODE,
    TOKYO,
    DecisionLogStorageError,
    DecisionValidationError,
    ReferencePrices,
    SupabaseDecisionStore,
    assert_json_serializable,
    build_decision_record,
    build_decision_snapshot,
    direction_alignment,
    evaluate_forward_checkpoint,
    evaluate_forward_checkpoints,
    prepare_reference_prices,
    validate_decision_input,
)
from decision_log_view import load_decision_log_configuration, password_matches


def _prices(periods: int = 140) -> tuple[pd.Series, pd.Series]:
    index = pd.bdate_range("2026-01-05", periods=periods)
    stock = pd.Series([100 + i for i in range(periods)], index=index, dtype=float)
    benchmark = pd.Series([200 + i * 0.5 for i in range(periods)], index=index, dtype=float)
    return stock, benchmark


def _decision(action: str = "買う") -> dict[str, object]:
    return {
        "decision_action": action,
        "reference_price": 100.0,
        "reference_price_date": "2026-01-05",
        "benchmark_price": 200.0,
        "benchmark_price_date": "2026-01-05",
        "horizon_trading_days": 60,
    }


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows, fail=False):
        self.rows = rows
        self.fail = fail
        self.inserted = None
        self.ticker = None

    def insert(self, record):
        self.inserted = record
        return self

    def select(self, _columns):
        return self

    def eq(self, _column, value):
        self.ticker = value
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, value):
        self.rows = self.rows[:value]
        return self

    def execute(self):
        if self.fail:
            raise RuntimeError("provider response with secret details")
        if self.inserted is not None:
            return _Response([self.inserted])
        rows = self.rows if self.ticker is None else [row for row in self.rows if row.get("ticker") == self.ticker]
        return _Response(rows)


class _Client:
    def __init__(self, rows=None, fail=False):
        self.query = _Query(list(rows or []), fail=fail)

    def table(self, name):
        self.table_name = name
        return self.query


class DecisionLogTest(unittest.TestCase):
    def test_default_mode_is_virtual_decision(self) -> None:
        self.assertEqual(DEFAULT_DECISION_MODE, "仮想判断")

    def test_validates_action_horizon_mode_and_reason_limit(self) -> None:
        validate_decision_input("買う", 60, ["業績", "評価水準"], "実判断")
        for arguments in (
            ("買う", 60, [], "実判断"),
            ("待つ", 60, [], "実判断"),
            ("買う", 30, [], "実判断"),
            ("買う", 60, [], "自動判断"),
            ("買う", 60, ["業績", "評価水準", "リスク", "その他"], "実判断"),
            ("買う", 60, ["未定義"], "実判断"),
        ):
            with self.assertRaises(DecisionValidationError):
                validate_decision_input(*arguments)

    def test_reference_uses_latest_quality_checked_common_date(self) -> None:
        stock, benchmark = _prices(30)
        stock = stock.drop(stock.index[-1])
        reference = prepare_reference_prices(stock, benchmark, as_of=benchmark.index[-1])
        self.assertEqual(reference.status, "available")
        self.assertEqual(reference.price_date, stock.index[-1].date().isoformat())
        self.assertEqual(reference.price_date, reference.benchmark_price_date)

    def test_reference_blocks_price_quality_problem(self) -> None:
        stock, benchmark = _prices(30)
        stock.iloc[-3:] *= 0.2
        reference = prepare_reference_prices(stock, benchmark, as_of=benchmark.index[-1])
        self.assertEqual(reference.status, "quality_blocked")

    def test_snapshot_is_json_serializable_and_keeps_required_fields(self) -> None:
        forecast = pd.DataFrame([{
            "metric": "forecast_eps", "value": 280.0, "unit": "JPY/share",
            "currency": "JPY", "fiscal_year": "FY2027", "disclosure_date": pd.Timestamp("2026-08-07"),
        }])
        detail = {
            "stock": {"ticker": "7203.T"},
            "performance": {"return_1m": 3.0, "return_3m": pd.NA, "relative_1m": 1.0, "relative_3m": None},
            "fundamentals": {
                "status": "Available", "momentum": "Improving", "forecast": forecast,
                "latest_period": {"fiscal_year": "FY2027", "fiscal_quarter": "Q1", "disclosure_date": pd.Timestamp("2026-08-07")},
            },
            "market_exposure": {"status": "Available", "market_beta_252d": 1.2},
            "primary_drivers": [{"driver": "USDJPY", "proxy": "USD/JPY", "status": "Available", "correlation_120d": 0.4, "stability": "High"}],
        }
        reference = ReferencePrices("available", 2500.0, "2026-09-11", 420.0, "2026-09-11")
        snapshot = build_decision_snapshot(
            detail, reference, {"investment_checks": ["確認"], "data_limits": []},
            captured_at=datetime(2026, 9, 14, 9, 0, tzinfo=TOKYO),
        )
        assert_json_serializable(snapshot)
        encoded = json.dumps(snapshot, ensure_ascii=False, allow_nan=False)
        self.assertIn("forecast_eps", encoded)
        self.assertEqual(snapshot["fundamentals"]["fiscal_quarter"], "Q1")
        self.assertIsNone(snapshot["returns"]["three_month"])

    def test_record_is_append_only_shape_with_tokyo_timestamp(self) -> None:
        stock = {"ticker": "7203.T", "code": "7203", "name": "トヨタ自動車"}
        reference = ReferencePrices("available", 2500.0, "2026-09-11", 420.0, "2026-09-11")
        record = build_decision_record(
            stock, "保有継続", 60, ["業績"], "comment", "review", "実判断",
            reference, {"snapshot_schema_version": 1},
            decision_at=datetime(2026, 9, 14, 9, 0, tzinfo=TOKYO), decision_id="fixed-id",
        )
        self.assertEqual(record["id"], "fixed-id")
        self.assertEqual(record["decision_source"], "Human")
        self.assertIn("+09:00", record["decision_at"])

    def test_20_60_120_trading_day_evaluation(self) -> None:
        stock, benchmark = _prices(140)
        results = evaluate_forward_checkpoints(_decision(), stock, benchmark, as_of=stock.index[-1])
        self.assertEqual([row.status for row in results], ["evaluated", "evaluated", "evaluated"])
        self.assertEqual(results[0].end_date, stock.index[20].date().isoformat())
        self.assertEqual(results[1].end_date, stock.index[60].date().isoformat())
        self.assertEqual(results[2].end_date, stock.index[120].date().isoformat())

    def test_future_checkpoint_is_pending(self) -> None:
        stock, benchmark = _prices(15)
        result = evaluate_forward_checkpoint(_decision(), stock, benchmark, 20, as_of=stock.index[-1])
        self.assertEqual(result.status, "pending")
        self.assertIsNone(result.stock_return)

    def test_missing_stock_on_benchmark_checkpoint_is_unavailable_not_shifted(self) -> None:
        stock, benchmark = _prices(40)
        expected_end = benchmark.index[20]
        stock = stock.drop(expected_end)
        result = evaluate_forward_checkpoint(_decision(), stock, benchmark, 20, as_of=benchmark.index[-1])
        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.end_date, expected_end.date().isoformat())
        self.assertIn("後日の価格では代用しません", result.reason)

    def test_long_benchmark_gap_does_not_extend_checkpoint(self) -> None:
        stock, benchmark = _prices(50)
        benchmark = benchmark.drop(benchmark.index[8:20])
        result = evaluate_forward_checkpoint(_decision(), stock, benchmark, 20, as_of=stock.index[-1])
        self.assertEqual(result.status, "unavailable")
        self.assertIn("長期欠損", result.reason)

    def test_asset_and_topix_use_same_evaluation_end(self) -> None:
        stock, benchmark = _prices(40)
        result = evaluate_forward_checkpoint(_decision(), stock, benchmark, 20, as_of=stock.index[-1])
        self.assertEqual(result.status, "evaluated")
        end = pd.Timestamp(result.end_date)
        self.assertEqual(float(stock.loc[end]), 120.0)
        self.assertEqual(float(benchmark.loc[end]), 210.0)

    def test_forward_return_uses_current_adjusted_series_for_both_prices(self) -> None:
        stock, benchmark = _prices(40)
        stock.loc[:] = stock * (98.0 / 100.0)
        stock.iloc[20] = 110.0
        result = evaluate_forward_checkpoint(_decision(), stock, benchmark, 20, as_of=stock.index[-1])
        self.assertEqual(result.status, "evaluated")
        self.assertAlmostEqual(result.stock_return, (110.0 / 98.0 - 1) * 100)
        self.assertAlmostEqual(result.stock_reference_change_pct, -2.0)

    def test_large_saved_reference_difference_is_diagnostic_not_a_block(self) -> None:
        stock, benchmark = _prices(40)
        stock.loc[:] = stock / 2
        result = evaluate_forward_checkpoint(_decision(), stock, benchmark, 20, as_of=stock.index[-1])
        self.assertEqual(result.status, "evaluated")
        self.assertAlmostEqual(result.stock_return, 20.0)
        self.assertAlmostEqual(result.stock_reference_change_pct, -50.0)

    def test_direction_alignment_reverses_for_sell_and_skip(self) -> None:
        self.assertEqual(direction_alignment("買う", 1.0), "整合")
        self.assertEqual(direction_alignment("保有継続", -1.0), "非整合")
        self.assertEqual(direction_alignment("売却", -1.0), "整合")
        self.assertEqual(direction_alignment("見送る", 1.0), "非整合")
        self.assertEqual(direction_alignment("売却", 0.0), "中立")

    def test_missing_configuration_disables_only_decision_log(self) -> None:
        configuration = load_decision_log_configuration({})
        self.assertFalse(configuration.available)
        self.assertEqual(configuration.reason, "Decision Logは未設定です。")

    def test_password_comparison_uses_boolean_gate(self) -> None:
        self.assertTrue(password_matches("correct", "correct"))
        self.assertFalse(password_matches("wrong", "correct"))

    def test_store_supports_insert_and_list_but_not_update_or_delete(self) -> None:
        client = _Client([{"ticker": "7203.T"}, {"ticker": "8306.T"}])
        store = SupabaseDecisionStore(client)
        saved = store.insert({"ticker": "7203.T"})
        self.assertEqual(saved["ticker"], "7203.T")
        client = _Client([{"ticker": "7203.T"}, {"ticker": "8306.T"}])
        store = SupabaseDecisionStore(client)
        self.assertEqual(store.list("7203.T"), [{"ticker": "7203.T"}])
        self.assertFalse(hasattr(store, "update"))
        self.assertFalse(hasattr(store, "delete"))

    def test_storage_error_does_not_expose_provider_message(self) -> None:
        store = SupabaseDecisionStore(_Client(fail=True))
        with self.assertRaises(DecisionLogStorageError) as context:
            store.list()
        self.assertNotIn("secret details", str(context.exception))

    def test_migration_enables_rls_and_exposes_no_browser_write_policy(self) -> None:
        sql = Path("supabase/migrations/202609140001_create_investment_decisions.sql").read_text(encoding="utf-8")
        normalized = " ".join(sql.lower().split())
        self.assertIn("enable row level security", normalized)
        self.assertIn("force row level security", normalized)
        self.assertIn("revoke all on table public.investment_decisions from anon, authenticated", normalized)
        self.assertIn("revoke all on table public.investment_decisions from service_role", normalized)
        self.assertIn("grant select, insert on table public.investment_decisions to service_role", normalized)
        self.assertIn("cardinality(reason_tags) between 1 and 3", normalized)
        self.assertNotIn("create policy", normalized)
        self.assertNotIn("grant update", normalized)
        self.assertNotIn("grant delete", normalized)


if __name__ == "__main__":
    unittest.main()
