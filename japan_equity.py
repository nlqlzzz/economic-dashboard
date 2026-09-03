from __future__ import annotations

import pandas as pd

from correlation_analysis import build_daily_change_frame, correlation_change_summary
from utils import percent_change_since


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
    topix_returns = _period_returns(topix)
    for stock in CORE_20:
        series = prices[stock["ticker"]] if stock["ticker"] in prices else pd.Series(dtype=float)
        returns = _period_returns(series)
        rows.append(
            {
                **stock,
                "current": _latest(series),
                "return_1d": returns["return_1d"],
                "return_5d": returns["return_5d"],
                "return_1m": returns["return_1m"],
                "return_3m": returns["return_3m"],
                "relative_1m": _difference(returns["return_1m"], topix_returns["return_1m"]),
                "relative_3m": _difference(returns["return_3m"], topix_returns["return_3m"]),
                "status": "Available" if not series.dropna().empty else "Unavailable",
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
        for macro_name, macro in macro_series.items():
            if macro.dropna().empty:
                continue
            methods = {ticker: "return", macro_name: _macro_method(macro_name)}
            daily, _ = build_daily_change_frame(
                {ticker: prices[ticker], macro_name: macro}, methods
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


def _period_returns(series: pd.Series) -> dict[str, float | None]:
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    return {
        "return_1d": _positional_return(clean, 1),
        "return_5d": _positional_return(clean, 5),
        "return_1m": _calendar_return(clean, months=1),
        "return_3m": _calendar_return(clean, months=3),
    }


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
