"""Japan Core 20 Macro Sensitivity offline diagnostic.

This script deliberately lives outside the production UI.  It reuses the production
loaders and masters, but does not change the dashboard's calculations or state.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from data_loader import load_indicator_data, load_yfinance_batch
from indicators import INDICATORS
from japan_equity import CORE_20, MACRO_PROXY_MAP, MACRO_SERIES, core_tickers


WINDOWS = (20, 60, 120, 252)
STABILITY_WINDOWS = (20, 60, 120)
TOPIX_NAME = "TOPIX連動ETF（1306）"
TOPIX_TICKER = "1306.T"


def remove_isolated_price_anomalies(
    series: pd.Series, threshold: float = 0.25
) -> tuple[pd.Series, list[str]]:
    """Remove an isolated bad print bracketed by two extreme inverse moves."""
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index().copy()
    excluded: list[str] = []
    position = 1
    while position < len(clean):
        previous = float(clean.iloc[position - 1])
        if abs(float(clean.iloc[position]) / previous - 1) <= threshold:
            position += 1
            continue
        recovery = None
        for candidate in range(position + 1, min(position + 6, len(clean))):
            if abs(float(clean.iloc[candidate]) / previous - 1) < threshold:
                recovery = candidate
                break
        if recovery is None:
            position += 1
            continue
        excluded.extend(
            str(clean.index[item].date()) for item in range(position, recovery)
        )
        position = recovery + 1
    return clean.drop(pd.to_datetime(excluded)), excluded


def transform_macro(name: str, series: pd.Series) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    return clean.diff() if name in {"JGB 10Y", "UST 10Y"} else clean.pct_change(fill_method=None) * 100


def return_variants(stock: pd.Series, topix: pd.Series, beta_window: int = 252) -> tuple[pd.DataFrame, dict[str, float]]:
    prices = pd.concat({"stock": stock, "topix": topix}, axis=1).dropna()
    returns = prices.pct_change(fill_method=None).dropna() * 100
    if len(returns) < 20:
        return pd.DataFrame(), {"alpha": float("nan"), "beta": float("nan"), "n": len(returns)}
    estimate = returns.tail(min(beta_window, len(returns)))
    fit = ols(estimate["stock"], pd.DataFrame({"TOPIX": estimate["topix"]}))
    beta = fit["coefficients"].get("TOPIX", float("nan"))
    alpha = fit["coefficients"].get("intercept", 0.0)
    variants = pd.DataFrame(index=returns.index)
    variants["Raw"] = returns["stock"]
    variants["Active"] = returns["stock"] - returns["topix"]
    variants["Residual"] = returns["stock"] - alpha - beta * returns["topix"]
    return variants, {"alpha": alpha, "beta": beta, "n": fit["n"], "r2": fit["r2"]}


def window_correlations(variants: pd.DataFrame, macros: dict[str, pd.Series]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    transformed = {name: transform_macro(name, series) for name, series in macros.items()}
    for variant in variants.columns:
        for macro_name, macro in transformed.items():
            pair = pd.concat(
                {"return": variants[variant], "macro": macro}, axis=1, sort=True
            ).dropna()
            for window in WINDOWS:
                selected = pair.tail(window)
                corr = selected["return"].corr(selected["macro"]) if len(selected) >= window else np.nan
                rows.append({
                    "variant": variant,
                    "macro": macro_name,
                    "window": window,
                    "correlation": _finite(corr),
                    "observations": len(selected),
                })
    return rows


def stability(correlations: pd.DataFrame, variant: str, macros: tuple[str, ...]) -> dict[str, object]:
    selected = correlations[
        correlations["variant"].eq(variant)
        & correlations["macro"].isin(macros)
        & correlations["window"].isin(STABILITY_WINDOWS)
    ]
    if selected.empty:
        return {"score": None, "stable": False, "sign_consistent": False, "mean_abs": None, "range": None}
    by_macro: list[dict[str, object]] = []
    for macro, group in selected.groupby("macro"):
        values = group.set_index("window")["correlation"].dropna()
        if len(values) < 3:
            continue
        signs = np.sign(values.to_numpy(dtype=float))
        sign_consistent = bool(np.all(signs > 0) or np.all(signs < 0))
        mean_abs = float(values.abs().mean())
        corr_range = float(values.max() - values.min())
        persistence = float((values.abs() >= 0.2).mean())
        score = (
            0.35 * float(sign_consistent)
            + 0.30 * persistence
            + 0.25 * min(mean_abs / 0.5, 1.0)
            + 0.10 * max(0.0, 1.0 - corr_range / 0.5)
        )
        by_macro.append({
            "macro": macro,
            "score": score,
            "stable": sign_consistent and persistence >= (2 / 3) and corr_range <= 0.5,
            "sign_consistent": sign_consistent,
            "mean_abs": mean_abs,
            "range": corr_range,
        })
    if not by_macro:
        return {"score": None, "stable": False, "sign_consistent": False, "mean_abs": None, "range": None}
    return max(by_macro, key=lambda row: float(row["score"]))


def ols(y: pd.Series, x: pd.DataFrame) -> dict[str, object]:
    data = pd.concat(
        {"y": y, **{name: x[name] for name in x}}, axis=1, sort=True
    ).dropna()
    n = len(data)
    k = len(x.columns) + 1
    if n <= k + 1:
        return {"n": n, "r2": None, "adjusted_r2": None, "coefficients": {}, "t_values": {}}
    matrix = np.column_stack([np.ones(n), data[x.columns].to_numpy(dtype=float)])
    target = data["y"].to_numpy(dtype=float)
    coefficients, _, _, _ = np.linalg.lstsq(matrix, target, rcond=None)
    fitted = matrix @ coefficients
    residual = target - fitted
    ss_res = float(residual @ residual)
    centered = target - target.mean()
    ss_total = float(centered @ centered)
    r2 = float(1 - ss_res / ss_total) if ss_total > 0 else np.nan
    adjusted = float(1 - (1 - r2) * (n - 1) / (n - k)) if n > k else np.nan
    variance = ss_res / (n - k)
    covariance = variance * np.linalg.pinv(matrix.T @ matrix)
    standard_errors = np.sqrt(np.diag(covariance))
    t_values = np.divide(coefficients, standard_errors, out=np.full_like(coefficients, np.nan), where=standard_errors > 0)
    names = ["intercept", *x.columns]
    return {
        "n": n,
        "r2": _finite(r2),
        "adjusted_r2": _finite(adjusted),
        "coefficients": {name: _finite(value) for name, value in zip(names, coefficients)},
        "t_values": {name: _finite(value) for name, value in zip(names, t_values)},
        "residual_std": _finite(np.std(residual, ddof=k)),
    }


def regression_comparison(variants: pd.DataFrame, macros: dict[str, pd.Series], primary: tuple[str, ...]) -> dict[str, object]:
    if variants.empty:
        return {}
    y = variants["Raw"]
    topix = transform_macro(TOPIX_NAME, macros[TOPIX_NAME]).rename("TOPIX")
    drivers = {
        name: transform_macro(name, macros[name])
        for name in primary
        if name != TOPIX_NAME and name in macros
    }
    combined = pd.concat(
        {"y": y, "TOPIX": topix, **drivers}, axis=1, sort=True
    ).dropna().tail(252)
    if combined.empty:
        return {}
    market = ols(combined["y"], combined[["TOPIX"]])
    extended = ols(combined["y"], combined[["TOPIX", *drivers]])
    market_adj = market.get("adjusted_r2")
    extended_adj = extended.get("adjusted_r2")
    delta = None if market_adj is None or extended_adj is None else float(extended_adj) - float(market_adj)
    return {"market_only": market, "market_plus_primary": extended, "adjusted_r2_change": _finite(delta)}


def ranking_stats(correlations: pd.DataFrame, primary: tuple[str, ...], variant: str) -> dict[str, object]:
    rankings: dict[str, list[str]] = {}
    for window in STABILITY_WINDOWS:
        selected = correlations[
            correlations["variant"].eq(variant) & correlations["window"].eq(window)
        ].dropna(subset=["correlation"]).copy()
        selected["absolute"] = selected["correlation"].abs()
        rankings[str(window)] = selected.nlargest(3, "absolute")["macro"].tolist()
    sets = [set(rankings[str(window)]) for window in STABILITY_WINDOWS]
    common = set.intersection(*sets) if all(sets) else set()
    top1 = rankings["60"][0] if rankings["60"] else None
    return {
        "rankings": rankings,
        "common_top3_count": len(common),
        "common_top3": sorted(common),
        "top_60d": top1,
        "top_60d_is_primary": top1 in primary if top1 else False,
    }


def explainability(primary_stability: dict[str, object], regression: dict[str, object]) -> tuple[str, str]:
    score = primary_stability.get("score")
    delta = regression.get("adjusted_r2_change")
    if score is not None and score >= 0.70 and delta is not None and delta >= 0.02:
        return "High", "Primary Driverが複数期間で安定し、追加回帰の調整済みR²も改善"
    if score is not None and score >= 0.50 and (delta is None or delta > 0):
        return "Medium", "Primary Driverに一定の安定性または説明力改善がある"
    return "Low", "期間安定性またはPrimary Driver追加による説明力改善が限定的"


def diagnose(prices: pd.DataFrame, macros: dict[str, pd.Series]) -> dict[str, object]:
    stocks: list[dict[str, object]] = []
    all_correlations: list[dict[str, object]] = []
    for stock in CORE_20:
        ticker = str(stock["ticker"])
        if ticker not in prices or prices[ticker].dropna().empty:
            stocks.append({"ticker": ticker, "name": stock["name"], "status": "Unavailable"})
            continue
        variants, market_fit = return_variants(prices[ticker], macros[TOPIX_NAME], 252)
        _, market_fit_120 = return_variants(prices[ticker], macros[TOPIX_NAME], 120)
        corr = pd.DataFrame(window_correlations(variants, macros))
        primary = tuple(dict.fromkeys(
            proxy for driver in stock["primary_drivers"]
            if (proxy := MACRO_PROXY_MAP.get(str(driver))) in macros
        ))
        stability_by_variant = {variant: stability(corr, variant, primary) for variant in variants.columns}
        rankings = {variant: ranking_stats(corr, primary, variant) for variant in variants.columns}
        regression = regression_comparison(variants, macros, primary)
        label, reason = explainability(stability_by_variant["Residual"], regression)
        latest_date = variants.index.max()
        three_month_start = latest_date - pd.DateOffset(months=3)
        recent = variants.loc[variants.index >= three_month_start]
        price_pair = pd.concat({"stock": prices[ticker], "topix": macros[TOPIX_NAME]}, axis=1).dropna()
        price_pair = price_pair.loc[price_pair.index >= three_month_start]
        stock_return = _period_return(price_pair["stock"])
        topix_return = _period_return(price_pair["topix"])
        record = {
            "ticker": ticker,
            "code": stock["code"],
            "name": stock["name"],
            "status": "Available",
            "primary_proxies": list(primary),
            "market_beta_252d": market_fit,
            "market_beta_120d": market_fit_120,
            "market_beta_window_difference": _finite(
                market_fit_120.get("beta", np.nan) - market_fit.get("beta", np.nan)
            ),
            "stability": stability_by_variant,
            "ranking": rankings,
            "regression": regression,
            "macro_explainability": label,
            "explainability_reason": reason,
            "recent_3m": {
                "stock_return_pct": stock_return,
                "topix_return_pct": topix_return,
                "active_return_pt": _finite(None if stock_return is None or topix_return is None else stock_return - topix_return),
                "residual_sum_pt": _finite(recent["Residual"].sum()),
                "start": str(price_pair.index.min().date()) if not price_pair.empty else None,
                "end": str(price_pair.index.max().date()) if not price_pair.empty else None,
            },
            "correlations": corr.to_dict("records"),
        }
        stocks.append(record)
        all_correlations.extend([{"ticker": ticker, "name": stock["name"], **row} for row in corr.to_dict("records")])
    return build_output(stocks, pd.DataFrame(all_correlations), prices, macros)


def build_output(stocks: list[dict[str, object]], correlations: pd.DataFrame, prices: pd.DataFrame, macros: dict[str, pd.Series]) -> dict[str, object]:
    available = [stock for stock in stocks if stock.get("status") == "Available"]
    topix_raw_top1 = sum(stock["ranking"]["Raw"]["top_60d"] == TOPIX_NAME for stock in available)
    topix_raw_top3 = sum(TOPIX_NAME in stock["ranking"]["Raw"]["rankings"]["60"] for stock in available)
    active_improved = sum(_score(stock, "Active") > _score(stock, "Raw") for stock in available)
    residual_improved = sum(_score(stock, "Residual") > _score(stock, "Raw") for stock in available)
    primary_sign_consistent = sum(bool(stock["stability"]["Residual"].get("sign_consistent")) for stock in available)
    unstable = sum(
        stock["stability"]["Residual"].get("range") is not None
        and float(stock["stability"]["Residual"]["range"]) > 0.5
        for stock in available
    )
    return {
        "generated_at": str(pd.Timestamp.now(tz="Asia/Tokyo")),
        "methodology": {
            "return_units": "daily percentage points; yields use daily percentage-point changes",
            "active_return": "stock return minus TOPIX ETF return; not risk-free excess return",
            "residual_return": "residual from stock = alpha + beta * TOPIX ETF using latest 252 common observations",
            "windows": list(WINDOWS),
            "topix_proxy": TOPIX_TICKER,
        },
        "coverage": {
            "prices_start": str(prices.index.min().date()) if not prices.empty else None,
            "prices_end": str(prices.index.max().date()) if not prices.empty else None,
            "available_stocks": len(available),
            "missing_stocks": [stock["ticker"] for stock in stocks if stock.get("status") != "Available"],
            "macros": {
                name: {
                    "start": str(series.dropna().index.min().date()) if not series.dropna().empty else None,
                    "end": str(series.dropna().index.max().date()) if not series.dropna().empty else None,
                    "observations": int(series.dropna().shape[0]),
                }
                for name, series in macros.items()
            },
        },
        "aggregate": {
            "raw_topix_top1_60d": topix_raw_top1,
            "raw_topix_top3_60d": topix_raw_top3,
            "active_primary_stability_improved": active_improved,
            "residual_primary_stability_improved": residual_improved,
            "residual_primary_sign_consistent": primary_sign_consistent,
            "residual_large_period_change": unstable,
            "explainability": {
                label: sum(stock["macro_explainability"] == label for stock in available)
                for label in ("High", "Medium", "Low")
            },
        },
        "stocks": stocks,
    }


def _score(stock: dict[str, object], variant: str) -> float:
    value = stock["stability"][variant].get("score")
    return float(value) if value is not None else -1.0


def _period_return(series: pd.Series) -> float | None:
    clean = series.dropna()
    if len(clean) < 2 or float(clean.iloc[0]) == 0:
        return None
    return float((clean.iloc[-1] / clean.iloc[0] - 1) * 100)


def _finite(value: object) -> float | None:
    if value is None or pd.isna(value) or not np.isfinite(float(value)):
        return None
    return float(value)


def load_inputs(start_date: str) -> tuple[pd.DataFrame, dict[str, pd.Series], list[str]]:
    prices = load_yfinance_batch((*core_tickers(), TOPIX_TICKER), start_date)
    macros: dict[str, pd.Series] = {TOPIX_NAME: prices[TOPIX_TICKER]}
    failures: list[str] = []
    for name in MACRO_SERIES:
        if name == TOPIX_NAME:
            continue
        try:
            macros[name] = load_indicator_data(INDICATORS[name], start_date)
        except Exception as error:  # diagnostic must retain partial results
            failures.append(f"{name}: {error}")
    return prices.reindex(columns=[ticker for ticker in core_tickers() if ticker in prices]), macros, failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=str((pd.Timestamp.today() - pd.DateOffset(years=3)).date()))
    parser.add_argument("--output", default="japan_equity_macro_diagnostic.json")
    args = parser.parse_args()
    prices, macros, failures = load_inputs(args.start)
    macros[TOPIX_NAME], excluded_topix_dates = remove_isolated_price_anomalies(
        macros[TOPIX_NAME]
    )
    result = diagnose(prices, macros)
    result["coverage"]["macro_failures"] = failures
    result["coverage"]["topix_excluded_anomaly_dates"] = excluded_topix_dates
    output = Path(args.output)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output} ({result['coverage']['available_stocks']} stocks, {len(macros)} macros)")


if __name__ == "__main__":
    main()
