from __future__ import annotations

import numpy as np
import pandas as pd

from correlation_analysis import build_daily_change_frame, correlation_change_summary
from price_quality import PriceQualityResult, inspect_price_series
from utils import percent_change_since


MARKET_PROXY_NAME = "TOPIX連動ETF（1306）"
PRIMARY_WINDOWS = (120, 60, 20)
MARKET_BETA_WINDOW = 252
MARKET_BETA_MINIMUM = 200
SHORT_BETA_WINDOW = 120
SHORT_BETA_MINIMUM = 100
BETA_UNSTABLE_THRESHOLD = 0.30


CORE_20 = (
    {"ticker": "7203.T", "code": "7203", "name": "トヨタ自動車", "sector": "自動車・輸送機", "macro_themes": ("円安", "米国景気", "中国・世界景気"), "primary_drivers": ("USDJPY", "US_GROWTH")},
    {"ticker": "8306.T", "code": "8306", "name": "三菱UFJフィナンシャル・グループ", "sector": "銀行", "macro_themes": ("国内金利上昇", "米国金利", "円安"), "primary_drivers": ("JGB10Y", "UST10Y", "USDJPY")},
    {"ticker": "8058.T", "code": "8058", "name": "三菱商事", "sector": "商社", "macro_themes": ("資源高", "円安", "中国・世界景気"), "primary_drivers": ("WTI", "USDJPY", "GLOBAL_GROWTH")},
    {"ticker": "1605.T", "code": "1605", "name": "INPEX", "sector": "エネルギー", "macro_themes": ("資源高", "円安"), "primary_drivers": ("WTI", "NATURAL_GAS", "USDJPY")},
    {"ticker": "7011.T", "code": "7011", "name": "三菱重工業", "sector": "資本財", "macro_themes": ("防衛", "世界設備投資", "円安", "中国・世界景気"), "primary_drivers": ("DEFENSE", "GLOBAL_CAPEX", "USDJPY")},
    {"ticker": "4063.T", "code": "4063", "name": "信越化学工業", "sector": "化学", "macro_themes": ("AI・テック", "半導体需給", "中国・世界景気", "円安"), "primary_drivers": ("SOX", "SEMICONDUCTOR_DEMAND", "CHINA_GROWTH", "USDJPY")},
    {"ticker": "8802.T", "code": "8802", "name": "三菱地所", "sector": "不動産", "macro_themes": ("国内金利上昇", "国内景気"), "primary_drivers": ("JGB10Y", "BOJ_POLICY", "JAPAN_GROWTH")},
    {"ticker": "8766.T", "code": "8766", "name": "東京海上ホールディングス", "sector": "保険", "macro_themes": ("国内金利上昇", "米国金利", "株式市場"), "primary_drivers": ("JGB10Y", "UST10Y", "EQUITY_MARKET")},
    {"ticker": "9983.T", "code": "9983", "name": "ファーストリテイリング", "sector": "小売", "macro_themes": ("円安", "中国・世界景気", "国内消費"), "primary_drivers": ("USDJPY", "CHINA_GROWTH", "DOMESTIC_CONSUMPTION")},
    {"ticker": "6501.T", "code": "6501", "name": "日立製作所", "sector": "電機・IT", "macro_themes": ("世界設備投資", "AI・テック"), "primary_drivers": ("GLOBAL_CAPEX", "AI_DX", "NASDAQ")},
    {"ticker": "5401.T", "code": "5401", "name": "日本製鉄", "sector": "鉄鋼", "macro_themes": ("中国・世界景気", "資源高", "円安"), "primary_drivers": ("CHINA_GROWTH", "IRON_ORE", "USDJPY", "GLOBAL_GROWTH")},
    {"ticker": "5803.T", "code": "5803", "name": "フジクラ", "sector": "電線・AIインフラ", "macro_themes": ("AI・テック", "資源高"), "primary_drivers": ("SOX", "AI_DATACENTER", "COPPER")},
    {"ticker": "6301.T", "code": "6301", "name": "小松製作所", "sector": "機械", "macro_themes": ("中国・世界景気", "世界設備投資", "円安"), "primary_drivers": ("CHINA_GROWTH", "GLOBAL_CAPEX", "USDJPY")},
    {"ticker": "4519.T", "code": "4519", "name": "中外製薬", "sector": "医薬品", "macro_themes": ("金利", "ディフェンシブ", "株式市場"), "primary_drivers": ("UST10Y", "DEFENSIVE_GROWTH", "EQUITY_MARKET")},
    {"ticker": "2914.T", "code": "2914", "name": "JT", "sector": "生活必需品", "macro_themes": ("円安", "金利", "ディフェンシブ"), "primary_drivers": ("USDJPY", "JGB10Y", "DEFENSIVE")},
    {"ticker": "9503.T", "code": "9503", "name": "関西電力", "sector": "電力", "macro_themes": ("資源高", "国内金利上昇", "電力政策"), "primary_drivers": ("LNG", "WTI", "JGB10Y", "POWER_POLICY")},
    {"ticker": "9020.T", "code": "9020", "name": "JR東日本", "sector": "鉄道", "macro_themes": ("国内消費", "インバウンド", "国内景気"), "primary_drivers": ("DOMESTIC_CONSUMPTION", "INBOUND", "JAPAN_GROWTH")},
    {"ticker": "9432.T", "code": "9432", "name": "NTT", "sector": "通信", "macro_themes": ("国内金利上昇", "ディフェンシブ", "国内景気"), "primary_drivers": ("JGB10Y", "DEFENSIVE", "JAPAN_GROWTH")},
    {"ticker": "9984.T", "code": "9984", "name": "ソフトバンクグループ", "sector": "投資・テクノロジー", "macro_themes": ("AI・テック", "米国金利"), "primary_drivers": ("NASDAQ", "SOX", "UST10Y", "AI")},
    {"ticker": "6098.T", "code": "6098", "name": "リクルートホールディングス", "sector": "人材・サービス", "macro_themes": ("米国景気", "円安"), "primary_drivers": ("US_EMPLOYMENT", "US_GROWTH", "USDJPY")},
)


MACRO_PROXY_MAP = {
    "USDJPY": "USD/JPY",
    "JGB10Y": "JGB 10Y",
    "UST10Y": "UST 10Y",
    "SOX": "SOX指数",
    "NASDAQ": "NASDAQ総合指数",
    "US_GROWTH": "S&P 500指数",
    "GLOBAL_GROWTH": "S&P 500指数",
    "EQUITY_MARKET": "TOPIX連動ETF（1306）",
    "CHINA_GROWTH": "中国：上海総合指数",
    "WTI": "WTI原油先物",
    "AI": "NASDAQ総合指数",
    "AI_DX": "NASDAQ総合指数",
    "AI_DATACENTER": "SOX指数",
    "SEMICONDUCTOR_DEMAND": "SOX指数",
}


MACRO_SERIES = (
    "USD/JPY",
    "JGB 10Y",
    "UST 10Y",
    "SOX指数",
    "NASDAQ総合指数",
    "S&P 500指数",
    "WTI原油先物",
    "VIX指数",
    "TOPIX連動ETF（1306）",
    "中国：上海総合指数",
)


def core_tickers() -> tuple[str, ...]:
    return tuple(stock["ticker"] for stock in CORE_20)


def build_market_map(
    prices: pd.DataFrame,
    topix: pd.Series,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    topix_quality = inspect_price_series(topix)
    usable_topix = topix_quality.series if topix_quality.usable else pd.Series(dtype=float)
    for stock in CORE_20:
        raw_series = prices[stock["ticker"]] if stock["ticker"] in prices else pd.Series(dtype=float)
        quality = inspect_price_series(raw_series)
        series = quality.series if quality.usable else pd.Series(dtype=float)
        returns = _period_returns(series)
        relative_1m, relative_1m_start, relative_1m_end = _aligned_relative_return(series, usable_topix, months=1)
        relative_3m, relative_3m_start, relative_3m_end = _aligned_relative_return(series, usable_topix, months=3)
        status = _market_map_status(series, usable_topix, quality, returns)
        rows.append(
            {
                **stock,
                "current": _latest(series),
                "return_1d": returns["return_1d"],
                "return_5d": returns["return_5d"],
                "return_1m": returns["return_1m"],
                "return_3m": returns["return_3m"],
                "relative_1m": relative_1m, "relative_3m": relative_3m,
                "relative_1m_start": relative_1m_start, "relative_1m_end": relative_1m_end,
                "relative_3m_start": relative_3m_start, "relative_3m_end": relative_3m_end,
                "status": status, "quality_status": quality.status,
                "quality_reason": quality.reason,
                "excluded_observations": len(quality.excluded_dates),
                "price_basis": "Yahoo Finance auto_adjust=True の調整後終値",
            }
        )
    return pd.DataFrame(rows)


def build_core_snapshot(market_map: pd.DataFrame) -> dict[str, object]:
    available = market_map[market_map["status"].eq("Available")].copy()
    daily = pd.to_numeric(available["return_1d"], errors="coerce")
    relative = pd.to_numeric(available["relative_1m"], errors="coerce")
    monthly = pd.to_numeric(available["return_1m"], errors="coerce")
    strongest = available.loc[monthly.idxmax(), "name"] if monthly.notna().any() else None
    weakest = available.loc[monthly.idxmin(), "name"] if monthly.notna().any() else None
    return {
        "available": len(available),
        "unavailable": len(market_map) - len(available),
        "rising": int((daily > 0).sum()),
        "falling": int((daily < 0).sum()),
        "outperforming": int((relative > 0).sum()),
        "strongest_1m": strongest,
        "weakest_1m": weakest,
    }


def aggregate_by_sector(market_map: pd.DataFrame) -> pd.DataFrame:
    return _aggregate_memberships(market_map, "sector", "sector")


def aggregate_by_theme(market_map: pd.DataFrame) -> pd.DataFrame:
    exploded = market_map.explode("macro_themes").rename(columns={"macro_themes": "theme"})
    return _aggregate_memberships(exploded, "theme", "theme")


def calculate_macro_sensitivity(
    prices: pd.DataFrame,
    macro_series: dict[str, pd.Series],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    master = {stock["ticker"]: stock for stock in CORE_20}
    for ticker, stock in master.items():
        if ticker not in prices or prices[ticker].dropna().empty:
            continue
        stock_quality = inspect_price_series(prices[ticker])
        if not stock_quality.usable:
            continue
        for macro_name, macro in macro_series.items():
            if macro.dropna().empty:
                continue
            method = _macro_method(macro_name)
            macro_quality = inspect_price_series(macro) if method == "return" else None
            usable_macro = macro_quality.series if macro_quality is not None and macro_quality.usable else macro
            if macro_quality is not None and not macro_quality.usable:
                continue
            methods = {ticker: "return", macro_name: method}
            daily, _ = build_daily_change_frame(
                {ticker: stock_quality.series, macro_name: usable_macro}, methods
            )
            summary = correlation_change_summary(daily[ticker], daily[macro_name])
            if summary.empty:
                continue
            values = {str(row["期間"]): row for _, row in summary.iterrows()}
            row20 = values.get("20日")
            row60 = values.get("60日")
            rows.append(
                {
                    "ticker": ticker,
                    "code": stock["code"],
                    "name": stock["name"],
                    "macro": macro_name,
                    "correlation_20d": None if row20 is None else float(row20["現在"]),
                    "correlation_60d": None if row60 is None else float(row60["現在"]),
                    "change_21d": None if row60 is None else row60.get("21日差"),
                    "change_63d": None if row60 is None else row60.get("63日差"),
                    "percentile_60d": None if row60 is None else row60.get("percentile"),
                    "observations": 0 if row60 is None else int(row60["共通観測数"]),
                    "is_expected_driver": macro_name in expected_proxy_names(stock),
                    "information_timing": macro_information_timing(macro_name),
                }
            )
    return pd.DataFrame(rows)


def top_macro_sensitivities(
    sensitivity: pd.DataFrame, ticker: str, limit: int = 3
) -> pd.DataFrame:
    if sensitivity.empty:
        return sensitivity.copy()
    selected = sensitivity[sensitivity["ticker"].eq(ticker)].copy()
    selected["absolute_correlation"] = pd.to_numeric(
        selected["correlation_60d"], errors="coerce"
    ).abs()
    return selected.dropna(subset=["absolute_correlation"]).nlargest(
        limit, "absolute_correlation"
    )


def expected_proxy_names(stock: dict[str, object]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            proxy
            for driver in stock["primary_drivers"]
            if (proxy := MACRO_PROXY_MAP.get(str(driver))) is not None
        )
    )


def build_macro_sensitivity_analysis(
    prices: pd.DataFrame,
    macro_series: dict[str, pd.Series],
    topix_quality: PriceQualityResult,
    market_map: pd.DataFrame,
    stocks: tuple[dict[str, object], ...] | None = None,
) -> dict[str, pd.DataFrame]:
    """Separate market exposure from ex-ante macro-driver relationships."""
    exposure_rows: list[dict[str, object]] = []
    primary_rows: list[dict[str, object]] = []
    observed_rows: list[dict[str, object]] = []
    regression_rows: list[dict[str, object]] = []
    explainability_rows: list[dict[str, object]] = []
    market_lookup = market_map.set_index("ticker") if not market_map.empty else pd.DataFrame()

    for stock in stocks or CORE_20:
        ticker = str(stock["ticker"])
        raw_stock_prices = prices[ticker] if ticker in prices else pd.Series(dtype=float)
        stock_quality = inspect_price_series(raw_stock_prices)
        stock_prices = stock_quality.series if stock_quality.usable else pd.Series(dtype=float)
        relative_1m = _lookup_market_value(market_lookup, ticker, "relative_1m")
        relative_3m = _lookup_market_value(market_lookup, ticker, "relative_3m")
        exposure, residual = _market_exposure(
            stock_prices, topix_quality, relative_1m, relative_3m
        )
        exposure_rows.append({**_stock_identity(stock), **exposure,
                              "quality_status": stock_quality.status,
                              "quality_reason": stock_quality.reason})

        stock_primary = _primary_driver_rows(stock, residual, macro_series)
        primary_rows.extend(stock_primary)
        observed_rows.extend(_observed_correlation_rows(stock, residual, macro_series))
        regression = _primary_regression(stock, stock_prices, topix_quality, macro_series)
        regression_rows.append({**_stock_identity(stock), **regression})
        explainability_rows.append(
            {
                **_stock_identity(stock),
                **classify_macro_explainability(exposure, stock_primary, regression),
            }
        )

    return {
        "market_exposure": pd.DataFrame(exposure_rows),
        "primary_drivers": pd.DataFrame(primary_rows),
        "observed_correlations": pd.DataFrame(observed_rows),
        "regression": pd.DataFrame(regression_rows),
        "explainability": pd.DataFrame(explainability_rows),
    }


def summarize_stock_performance(stock_prices: pd.Series, topix_prices: pd.Series) -> dict[str, float | None]:
    """Return reusable performance fields for a Core 20 or future arbitrary ticker."""
    stock_returns = _period_returns(stock_prices)
    aligned = {months: _aligned_relative_return(stock_prices, topix_prices, months=months) for months in (1, 3, 6)}
    return {
        **stock_returns,
        **{f"relative_{months}m": aligned[months][0] for months in (1, 3, 6)},
        **{f"relative_{months}m_start": aligned[months][1] for months in (1, 3, 6)},
        **{f"relative_{months}m_end": aligned[months][2] for months in (1, 3, 6)},
    }


def cumulative_residual_return(residual: pd.Series, sessions: int) -> float | None:
    """Compound daily model residuals expressed in percentage points."""
    clean = pd.to_numeric(residual, errors="coerce").dropna().tail(sessions)
    if len(clean) < sessions:
        return None
    return float(((1 + clean / 100).prod() - 1) * 100)


def estimate_market_model(
    stock_returns: pd.Series,
    market_returns: pd.Series,
    *,
    window: int = MARKET_BETA_WINDOW,
    minimum_observations: int = MARKET_BETA_MINIMUM,
) -> dict[str, object]:
    pair = pd.concat({"stock": stock_returns, "market": market_returns}, axis=1).dropna().tail(window)
    if len(pair) < minimum_observations or pair["market"].var() <= 0:
        return {"available": False, "observations": len(pair), "reason": "観測数不足または市場分散不足"}
    beta = float(pair["stock"].cov(pair["market"]) / pair["market"].var())
    intercept = float(pair["stock"].mean() - beta * pair["market"].mean())
    correlation = float(pair["stock"].corr(pair["market"]))
    return {
        "available": True,
        "observations": len(pair),
        "beta": beta,
        "intercept": intercept,
        "correlation": correlation,
    }


def residual_returns(
    stock_prices: pd.Series,
    market_prices: pd.Series,
    *,
    window: int = MARKET_BETA_WINDOW,
    minimum_observations: int = MARKET_BETA_MINIMUM,
) -> tuple[pd.Series, dict[str, object]]:
    frame, _ = build_daily_change_frame(
        {"stock": stock_prices, "market": market_prices},
        {"stock": "return", "market": "return"},
    )
    model = estimate_market_model(
        frame["stock"], frame["market"], window=window, minimum_observations=minimum_observations
    )
    if not model["available"]:
        return pd.Series(dtype=float), model
    pair = frame[["stock", "market"]].dropna()
    residual = pair["stock"] - float(model["intercept"]) - float(model["beta"]) * pair["market"]
    residual.name = "Market-adjusted Return"
    return residual, model


def classify_driver_stability(
    correlations: dict[int, float | None], observations: dict[int, int]
) -> tuple[str, str]:
    values = [correlations.get(window) for window in PRIMARY_WINDOWS]
    if observations.get(120, 0) < 120 or values[0] is None:
        return "Unavailable", "120日分の共通観測がありません"
    valid = [float(value) for value in values if value is not None and not pd.isna(value)]
    if len(valid) < 3:
        return "Low", "複数期間を比較できません"
    if max(abs(value) for value in valid) < 0.15 or abs(valid[0]) < 0.10:
        return "Low", "符号が揃っていても関係は弱いです"
    signs = [1 if value > 0.05 else -1 if value < -0.05 else 0 for value in valid]
    same_sign = 0 not in signs and len(set(signs)) == 1
    correlation_range = max(valid) - min(valid)
    strong_windows = sum(abs(value) >= 0.20 for value in valid)
    if same_sign and abs(valid[0]) >= 0.25 and strong_windows >= 2 and correlation_range <= 0.30:
        direction = "正" if signs[0] > 0 else "負"
        return "High", f"複数期間で一貫した{direction}の関係"
    matching_120 = sum((value > 0) == (valid[0] > 0) for value in valid)
    if abs(valid[0]) >= 0.15 and matching_120 >= 2 and strong_windows >= 2 and correlation_range <= 0.50:
        return "Medium", "中長期の方向は概ね共通ですが、強さは変動しています"
    return "Low", "期間によって方向または強さが安定していません"


def top_observed_correlations(
    observed: pd.DataFrame, ticker: str, limit: int = 3
) -> pd.DataFrame:
    if observed.empty:
        return observed.copy()
    selected = observed[
        observed["ticker"].eq(ticker) & ~observed["macro"].eq(MARKET_PROXY_NAME)
    ].copy()
    selected["absolute_correlation"] = pd.to_numeric(selected["correlation_120d"], errors="coerce").abs()
    return selected.dropna(subset=["absolute_correlation"]).nlargest(limit, "absolute_correlation")


def _market_exposure(
    stock_prices: pd.Series,
    topix_quality: PriceQualityResult,
    relative_1m: object,
    relative_3m: object,
) -> tuple[dict[str, object], pd.Series]:
    base = {
        "status": "Unavailable",
        "market_beta_252d": None,
        "market_beta_120d": None,
        "topix_correlation_252d": None,
        "topix_correlation_120d": None,
        "relative_1m": relative_1m,
        "relative_3m": relative_3m,
        "beta_stability": "Unavailable",
        "beta_observations_252d": 0,
        "beta_observations_120d": 0,
        "recent_residual_3m": None,
        "reason": "",
    }
    if stock_prices.dropna().empty:
        return {**base, "reason": "株価を取得できません"}, pd.Series(dtype=float)
    if not topix_quality.usable:
        return {**base, "reason": topix_quality.reason or "TOPIX Proxyの品質を確認できません"}, pd.Series(dtype=float)
    residual, long_model = residual_returns(stock_prices, topix_quality.series)
    frame, _ = build_daily_change_frame(
        {"stock": stock_prices, "market": topix_quality.series},
        {"stock": "return", "market": "return"},
    )
    short_model = estimate_market_model(
        frame["stock"], frame["market"], window=SHORT_BETA_WINDOW, minimum_observations=SHORT_BETA_MINIMUM
    )
    if not long_model["available"]:
        return {**base, "beta_observations_252d": long_model["observations"], "reason": str(long_model["reason"])}, residual
    beta_252 = float(long_model["beta"])
    beta_120 = float(short_model["beta"]) if short_model["available"] else None
    beta_stability = "Unavailable" if beta_120 is None else (
        "Unstable" if abs(beta_252 - beta_120) >= BETA_UNSTABLE_THRESHOLD else "Stable"
    )
    recent_residual = cumulative_residual_return(residual, 63)
    return {
        **base,
        "status": "Available",
        "market_beta_252d": beta_252,
        "market_beta_120d": beta_120,
        "topix_correlation_252d": long_model["correlation"],
        "topix_correlation_120d": short_model.get("correlation"),
        "beta_stability": beta_stability,
        "beta_observations_252d": long_model["observations"],
        "beta_observations_120d": short_model["observations"],
        "recent_residual_3m": None if recent_residual is None else float(recent_residual),
        "reason": topix_quality.reason,
    }, residual


def _primary_driver_rows(
    stock: dict[str, object], residual: pd.Series, macro_series: dict[str, pd.Series]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for driver in stock["primary_drivers"]:
        proxy = MACRO_PROXY_MAP.get(str(driver))
        identity = {**_stock_identity(stock), "driver": str(driver), "proxy": proxy}
        if proxy == MARKET_PROXY_NAME:
            rows.append({**identity, **_unavailable_driver("TOPIXはMarket Exposureで確認します")})
            continue
        if proxy is None:
            rows.append({**identity, **_unavailable_driver("Proxy not available")})
            continue
        if proxy in seen:
            continue
        seen.add(proxy)
        macro = _quality_checked_macro(proxy, macro_series.get(proxy, pd.Series(dtype=float)))
        if residual.empty or macro.dropna().empty:
            rows.append({**identity, **_unavailable_driver("Residual ReturnまたはDriverデータがありません")})
            continue
        transformed, _ = build_daily_change_frame({"macro": macro}, {"macro": _macro_method(proxy)})
        pair = pd.concat({"residual": residual, "macro": transformed["macro"]}, axis=1, sort=False).dropna()
        correlations = {window: _tail_correlation(pair, window) for window in PRIMARY_WINDOWS}
        observations = {window: min(len(pair), window) for window in PRIMARY_WINDOWS}
        stability, reason = classify_driver_stability(correlations, observations)
        corr120 = correlations[120]
        direction = "Weak" if corr120 is None or abs(corr120) < 0.10 else ("Positive" if corr120 > 0 else "Negative")
        rows.append({
            **identity,
            "status": "Available" if corr120 is not None else "Unavailable",
            "correlation_120d": corr120,
            "correlation_60d": correlations[60],
            "correlation_20d": correlations[20],
            "observations_120d": observations[120],
            "observations_60d": observations[60],
            "observations_20d": observations[20],
            "direction": direction,
            "stability": stability,
            "reason": reason,
            "information_timing": macro_information_timing(proxy),
        })
    return rows


def _observed_correlation_rows(
    stock: dict[str, object], residual: pd.Series, macro_series: dict[str, pd.Series]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if residual.empty:
        return rows
    for name, macro in macro_series.items():
        if name == MARKET_PROXY_NAME or macro.dropna().empty:
            continue
        macro = _quality_checked_macro(name, macro)
        if macro.empty:
            continue
        transformed, _ = build_daily_change_frame({"macro": macro}, {"macro": _macro_method(name)})
        pair = pd.concat({"residual": residual, "macro": transformed["macro"]}, axis=1, sort=False).dropna()
        rows.append({
            **_stock_identity(stock), "macro": name,
            "correlation_120d": _tail_correlation(pair, 120),
            "correlation_60d": _tail_correlation(pair, 60),
            "correlation_20d": _tail_correlation(pair, 20),
            "observations": len(pair),
            "information_timing": macro_information_timing(name),
        })
    return rows


def _primary_regression(
    stock: dict[str, object], stock_prices: pd.Series, topix_quality: PriceQualityResult,
    macro_series: dict[str, pd.Series],
) -> dict[str, object]:
    unavailable = {"status": "Unavailable", "observations": 0, "market_adjusted_r2": None,
                   "driver_adjusted_r2": None, "adjusted_r2_improvement": None, "coefficients": {}}
    if stock_prices.dropna().empty or not topix_quality.usable:
        return unavailable
    frame, _ = build_daily_change_frame(
        {"stock": stock_prices, "market": topix_quality.series}, {"stock": "return", "market": "return"}
    )
    proxy_names = [name for name in expected_proxy_names(stock) if name != MARKET_PROXY_NAME and name in macro_series]
    proxy_names = list(dict.fromkeys(proxy_names))
    data = frame[["stock", "market"]].copy()
    for proxy in proxy_names:
        usable = _quality_checked_macro(proxy, macro_series[proxy])
        if usable.empty:
            continue
        transformed, _ = build_daily_change_frame({proxy: usable}, {proxy: _macro_method(proxy)})
        data[proxy] = transformed[proxy]
    proxy_names = [proxy for proxy in proxy_names if proxy in data]
    data = data.dropna().tail(MARKET_BETA_WINDOW)
    if len(data) < 120 or not proxy_names:
        return {**unavailable, "observations": len(data)}
    market_fit = _ols(data["stock"], data[["market"]])
    driver_fit = _ols(data["stock"], data[["market", *proxy_names]])
    if market_fit is None or driver_fit is None:
        return {**unavailable, "observations": len(data)}
    return {
        "status": "Available", "observations": len(data),
        "market_adjusted_r2": market_fit["adjusted_r2"],
        "driver_adjusted_r2": driver_fit["adjusted_r2"],
        "adjusted_r2_improvement": driver_fit["adjusted_r2"] - market_fit["adjusted_r2"],
        "coefficients": {name: driver_fit["coefficients"].get(name) for name in proxy_names},
    }


def _quality_checked_macro(name: str, series: pd.Series) -> pd.Series:
    """Apply scale-break inspection only to price-level macro inputs."""
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    if _macro_method(name) != "return":
        return clean
    quality = inspect_price_series(clean)
    return quality.series if quality.usable else pd.Series(dtype=float)


def macro_information_timing(name: str) -> str:
    if name in {"SOX指数", "NASDAQ総合指数", "S&P 500指数", "WTI原油先物", "VIX指数", "UST 10Y"}:
        return "same_date_ex_post_not_japan_decision_time"
    return "same_date_observation"


def classify_macro_explainability(
    exposure: dict[str, object], drivers: list[dict[str, object]], regression: dict[str, object]
) -> dict[str, object]:
    available = [row for row in drivers if row.get("status") == "Available"]
    if exposure["status"] != "Available" or not available:
        return {"classification": "Unavailable", "reason": "市場調整後分析または利用可能なPrimary Driverがありません"}
    improvement = regression.get("adjusted_r2_improvement")
    improvement_value = float(improvement) if improvement is not None and not pd.isna(improvement) else None
    strongest = max(abs(float(row["correlation_120d"])) for row in available if row["correlation_120d"] is not None)
    stability = {str(row["stability"]) for row in available}
    residual_3m = exposure.get("recent_residual_3m")
    large_unexplained = residual_3m is not None and abs(float(residual_3m)) >= 10
    if strongest < 0.15 and (improvement_value is None or improvement_value <= 0.005) and large_unexplained:
        return {"classification": "Macro-unexplained", "reason": "最近の値動きが大きい一方、現在登録されたPrimary Driverでは十分説明できません"}
    if "High" in stability and improvement_value is not None and improvement_value >= 0.02:
        return {"classification": "High", "reason": "安定したPrimary Driverがあり、回帰の説明力も改善しています"}
    if ("High" in stability or "Medium" in stability) and improvement_value is not None and improvement_value > 0:
        return {"classification": "Medium", "reason": "Primary Driverとの関係は見られますが、安定性または説明力は限定的です"}
    return {"classification": "Low", "reason": "現在登録されたPrimary Driverの関係または説明力は限定的です"}


def _ols(y: pd.Series, x: pd.DataFrame) -> dict[str, object] | None:
    data = pd.concat({"y": y, **{name: x[name] for name in x.columns}}, axis=1).dropna()
    n, predictors = len(data), len(x.columns)
    if n <= predictors + 2:
        return None
    design = np.column_stack([np.ones(n), data[list(x.columns)].to_numpy(dtype=float)])
    try:
        coefficients, _, _, _ = np.linalg.lstsq(design, data["y"].to_numpy(dtype=float), rcond=None)
    except np.linalg.LinAlgError:
        return None
    fitted = design @ coefficients
    residual = data["y"].to_numpy(dtype=float) - fitted
    total = float(((data["y"] - data["y"].mean()) ** 2).sum())
    if total <= 0:
        return None
    r2 = 1 - float(np.dot(residual, residual)) / total
    adjusted = 1 - (1 - r2) * (n - 1) / (n - predictors - 1)
    return {"adjusted_r2": float(adjusted), "coefficients": {name: float(coefficients[i + 1]) for i, name in enumerate(x.columns)}}


def _tail_correlation(pair: pd.DataFrame, window: int) -> float | None:
    selected = pair.tail(window)
    if len(selected) < window:
        return None
    value = selected.iloc[:, 0].corr(selected.iloc[:, 1])
    return None if pd.isna(value) else float(value)


def _unavailable_driver(reason: str) -> dict[str, object]:
    return {"status": "Unavailable", "correlation_120d": None, "correlation_60d": None,
            "correlation_20d": None, "observations_120d": 0, "observations_60d": 0,
            "observations_20d": 0, "direction": "Unavailable", "stability": "Unavailable", "reason": reason}


def _stock_identity(stock: dict[str, object]) -> dict[str, object]:
    return {"ticker": stock["ticker"], "code": stock["code"], "name": stock["name"]}


def _lookup_market_value(frame: pd.DataFrame, ticker: str, column: str) -> object:
    if frame.empty or ticker not in frame.index or column not in frame.columns:
        return None
    return frame.loc[ticker, column]


def _period_returns(series: pd.Series) -> dict[str, float | None]:
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    return {
        "return_1d": _positional_return(clean, 1),
        "return_5d": _positional_return(clean, 5),
        "return_1m": _calendar_return(clean, months=1),
        "return_3m": _calendar_return(clean, months=3),
        "return_6m": _calendar_return(clean, months=6),
        "return_1y": _calendar_return(clean, months=12),
    }


def _aligned_relative_return(stock: pd.Series, market: pd.Series, *, months: int) -> tuple[float | None, pd.Timestamp | None, pd.Timestamp | None]:
    """Return stock-minus-market over exactly the same common endpoints."""
    pair = pd.concat({"stock": stock, "market": market}, axis=1, sort=False).dropna().sort_index()
    if pair.empty:
        return None, None, None
    end = pair.index[-1]
    starts = pair.loc[pair.index <= end - pd.DateOffset(months=months)]
    if starts.empty:
        return None, None, None
    start = starts.index[-1]
    if float(pair.loc[start, "stock"]) == 0 or float(pair.loc[start, "market"]) == 0:
        return None, None, None
    stock_return = (float(pair.loc[end, "stock"]) / float(pair.loc[start, "stock"]) - 1) * 100
    market_return = (float(pair.loc[end, "market"]) / float(pair.loc[start, "market"]) - 1) * 100
    return float(stock_return - market_return), pd.Timestamp(start), pd.Timestamp(end)


def _market_map_status(
    stock: pd.Series,
    market: pd.Series,
    quality: PriceQualityResult,
    returns: dict[str, float | None],
) -> str:
    if quality.status == "blocked":
        return "Quality Blocked"
    if stock.empty:
        return "Unavailable"
    if not market.empty and stock.index[-1] < market.index[-1]:
        newer_market_observations = int((market.index > stock.index[-1]).sum())
        if newer_market_observations > 5:
            return "Stale"
    if returns.get("return_3m") is None:
        return "History Limited"
    return "Available"


def _positional_return(series: pd.Series, periods: int) -> float | None:
    if len(series) <= periods or float(series.iloc[-periods - 1]) == 0:
        return None
    return float((series.iloc[-1] / series.iloc[-periods - 1] - 1) * 100)


def _calendar_return(series: pd.Series, months: int) -> float | None:
    if series.empty:
        return None
    return percent_change_since(series, series.index[-1] - pd.DateOffset(months=months))


def _latest(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    return None if clean.empty else float(clean.iloc[-1])


def _difference(left: object, right: object) -> float | None:
    if left is None or right is None or pd.isna(left) or pd.isna(right):
        return None
    return float(left) - float(right)


def _aggregate_memberships(
    frame: pd.DataFrame, group_column: str, output_column: str
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for group, selected in frame.groupby(group_column, sort=False):
        available = selected[selected["status"].eq("Available")]
        rows.append(
            {
                output_column: group,
                "stock_count": len(selected),
                "available_count": len(available),
                "return_1d": pd.to_numeric(available["return_1d"], errors="coerce").mean(),
                "return_1m": pd.to_numeric(available["return_1m"], errors="coerce").mean(),
                "return_3m": pd.to_numeric(available["return_3m"], errors="coerce").mean(),
            }
        )
    return pd.DataFrame(rows)


def _macro_method(name: str) -> str:
    return "change" if name in {"JGB 10Y", "UST 10Y"} else "return"
