import importlib.util
from pathlib import Path
import unittest

import numpy as np
import pandas as pd


SCRIPT_PATH = Path(__file__).parent / "scripts" / "diagnose_japan_equity_macro.py"
SPEC = importlib.util.spec_from_file_location("diagnose_japan_equity_macro", SCRIPT_PATH)
diagnostic = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(diagnostic)


class JapanEquityMacroDiagnosticTest(unittest.TestCase):
    def test_removes_isolated_topix_bad_print(self):
        index = pd.bdate_range("2026-03-27", periods=4)
        series = pd.Series([380.0, 38.0, 38.2, 384.0], index=index)

        cleaned, excluded = diagnostic.remove_isolated_price_anomalies(series)

        self.assertEqual(excluded, [str(index[1].date()), str(index[2].date())])
        self.assertNotIn(index[1], cleaned.index)
        self.assertNotIn(index[2], cleaned.index)
        self.assertIn(index[3], cleaned.index)

    def test_return_variants_remove_market_component(self):
        index = pd.bdate_range("2024-01-01", periods=300)
        market_returns = pd.Series(np.sin(np.arange(300) / 9) * 0.01, index=index)
        stock_returns = 0.0003 + 1.5 * market_returns
        market = 100 * (1 + market_returns).cumprod()
        stock = 100 * (1 + stock_returns).cumprod()

        variants, fit = diagnostic.return_variants(stock, market, beta_window=252)

        self.assertAlmostEqual(fit["beta"], 1.5, places=5)
        self.assertLess(float(variants["Residual"].abs().max()), 1e-8)
        self.assertGreater(float(variants["Active"].std()), 0)

    def test_ols_reports_added_driver_explanatory_power(self):
        index = pd.bdate_range("2024-01-01", periods=252)
        market = pd.Series(np.sin(np.arange(252) / 8), index=index)
        driver = pd.Series(np.cos(np.arange(252) / 11), index=index)
        target = 0.4 * market + 0.8 * driver

        market_fit = diagnostic.ols(target, pd.DataFrame({"TOPIX": market}))
        full_fit = diagnostic.ols(target, pd.DataFrame({"TOPIX": market, "Driver": driver}))

        self.assertGreater(full_fit["adjusted_r2"], market_fit["adjusted_r2"])
        self.assertAlmostEqual(full_fit["coefficients"]["Driver"], 0.8, places=5)


if __name__ == "__main__":
    unittest.main()
