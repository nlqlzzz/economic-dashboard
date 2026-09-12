from __future__ import annotations

from collections.abc import Iterable, Mapping

import pandas as pd

from japan_equity import (
    build_macro_sensitivity_analysis,
    cumulative_residual_return,
    residual_returns,
    summarize_stock_performance,
)
from price_quality import PriceQualityResult, inspect_price_series


def select_core20_anchors(
    stock: Mapping[str, object],
    reference_stocks: Iterable[Mapping[str, object]],
    *,
    limit: int = 3,
) -> list[dict[str, object]]:
    """Choose transparent reference stocks from shared themes, drivers and sector."""
    candidates: list[dict[str, object]] = []
    target_themes = set(stock.get("macro_themes", ()))
    target_drivers = set(stock.get("primary_drivers", ()))
    for candidate in reference_stocks:
        if candidate.get("ticker") == stock.get("ticker"):
            continue
        themes = sorted(target_themes & set(candidate.get("macro_themes", ())))
        drivers = sorted(target_drivers & set(candidate.get("primary_drivers", ())))
        same_sector = stock.get("sector") == candidate.get("sector")
        score = len(drivers) * 3 + len(themes) * 2 + int(same_sector)
        if score < 2:
            continue
        reasons: list[str] = []
        if themes:
            reasons.append("共通テーマ: " + " / ".join(themes))
        if drivers:
            reasons.append("共通Driver: " + " / ".join(drivers))
        if same_sector:
            reasons.append("同一セクター")
        candidates.append({**dict(candidate), "anchor_reasons": reasons, "_score": score})
    ordered = sorted(candidates, key=lambda item: (-int(item["_score"]), str(item["name"])))
    return [{key: value for key, value in item.items() if key != "_score"} for item in ordered[:limit]]


def build_stock_detail_analysis(
    stock: Mapping[str, object],
    stock_prices: pd.Series,
    topix_quality: PriceQualityResult,
    macro_series: dict[str, pd.Series],
    reference_stocks: Iterable[Mapping[str, object]],
    reference_prices: pd.DataFrame,
    *,
    shared_macro_analysis: dict[str, pd.DataFrame] | None = None,
    fundamentals: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build a ticker-driven detail payload without assuming the ticker is Core 20."""
    stock_quality = inspect_price_series(stock_prices)
    usable_stock_prices = stock_quality.series if stock_quality.usable else pd.Series(dtype=float)
    usable_topix = topix_quality.series if topix_quality.usable else pd.Series(dtype=float)
    performance = summarize_stock_performance(usable_stock_prices, usable_topix)
    performance["current"] = _latest(usable_stock_prices)

    macro = _macro_for_stock(
        dict(stock), usable_stock_prices, topix_quality, macro_series, performance, shared_macro_analysis
    )
    residual, _ = residual_returns(usable_stock_prices, usable_topix) if (
        stock_quality.usable and topix_quality.usable
    ) else (pd.Series(dtype=float), {"available": False})
    residual_periods = {
        "residual_5d": cumulative_residual_return(residual, 5),
        "residual_1m": cumulative_residual_return(residual, 21),
        "residual_3m": cumulative_residual_return(residual, 63),
    }
    anchors = select_core20_anchors(stock, reference_stocks)
    anchor_comparison = _build_anchor_comparison(
        stock, performance, macro, anchors, reference_prices, usable_topix, shared_macro_analysis
    )
    movement = classify_stock_specific_move(macro, residual_periods, anchor_comparison)
    fundamentals = fundamentals or {"status": "Unavailable"}
    return {
        "stock": dict(stock),
        "quality": stock_quality,
        "performance": performance,
        "market_exposure": macro["market_exposure"],
        "primary_drivers": macro["primary_drivers"],
        "observed_correlations": macro["observed_correlations"],
        "regression": macro["regression"],
        "explainability": macro["explainability"],
        "residual_periods": residual_periods,
        "anchors": anchor_comparison,
        "movement": movement,
        "interpretation": build_interpretation(stock, macro, residual_periods, movement, fundamentals),
        "next_analysis": next_analysis_guidance(macro, movement),
        "fundamentals": fundamentals,
    }


def classify_stock_specific_move(
    macro: Mapping[str, object],
    residual_periods: Mapping[str, float | None],
    anchors: list[Mapping[str, object]],
) -> dict[str, str]:
    explainability = str(macro.get("explainability", {}).get("classification", "Unavailable"))
    residual_3m = residual_periods.get("residual_3m")
    # The first Anchor is the closest transparent match. A lower-ranked, broader
    # theme match must not override a close economic reference for classification.
    anchor_gap = (
        abs(float(anchors[0]["return_gap_3m"]))
        if anchors and anchors[0].get("return_gap_3m") is not None
        else 0.0
    )
    large_residual = residual_3m is not None and abs(float(residual_3m)) >= 10
    if explainability == "Macro-unexplained" or (large_residual and anchor_gap >= 10):
        return {
            "classification": "Stock-specific / Unexplained",
            "reason": "現在登録された市場・Macro Driver・Core20 Anchorでは、最近の値動きを十分説明できません。",
        }
    if explainability in {"High", "Medium"} and not large_residual and anchor_gap < 10:
        return {
            "classification": "Macro-consistent",
            "reason": "市場調整後のPrimary DriverとAnchor比較は、最近の値動きと概ね整合的です。",
        }
    return {
        "classification": "Mixed",
        "reason": "市場・Macro・Anchorのシグナルが混在しており、単一の説明には絞れません。",
    }


def build_interpretation(
    stock: Mapping[str, object],
    macro: Mapping[str, object],
    residual_periods: Mapping[str, float | None],
    movement: Mapping[str, str],
    fundamentals: Mapping[str, object] | None = None,
) -> str:
    explainability = str(macro.get("explainability", {}).get("classification", "Unavailable"))
    earnings = str((fundamentals or {}).get("momentum", "Unavailable"))
    drivers = [row for row in macro.get("primary_drivers", []) if row.get("stability") == "High"]
    if movement["classification"] == "Stock-specific / Unexplained":
        if earnings in {"Strong", "Improving"}:
            residual_1m = residual_periods.get("residual_1m")
            if residual_1m is not None and float(residual_1m) < 0:
                return "直近1か月の市場調整後リターンは下落、比較可能な最新決算は改善です。方向は一致しておらず、業績だけで値動きは説明できません。"
            if residual_1m is not None and float(residual_1m) > 0:
                return "直近1か月の市場調整後リターンと比較可能な最新決算はともに改善です。ただし、開示時点や他の企業固有材料を確認しない限り因果関係は判断できません。"
            return "比較可能な最新決算は改善ですが、市場・Macroでの説明力は限定的です。業績だけで最近の値動きの原因は判断できません。"
        if earnings in {"Weakening", "Mixed"}:
            return "Market / Macroと比較可能な最新決算だけでは、最近の値動きを十分説明できていません。企業開示などの追加情報を確認する余地があります。"
        return (
            "TOPIX比・市場調整後Residualに注目すべき動きが残る一方、現在登録されているPrimary Driverの説明力は限定的です。"
            "企業固有要因を確認する価値があります。"
        )
    if drivers:
        driver = drivers[0]
        direction = "正" if float(driver["correlation_120d"]) > 0 else "負"
        return f"市場調整後の{driver['driver']}との{direction}の相関は複数期間で確認されています。ただし相関だけから、足元のMacro環境が追い風・逆風であることや最近の値動きの要因は判断できません。"
    if explainability == "Unavailable":
        return "市場調整後の定量分析に必要なデータまたはPrimary Driver Proxyが不足しています。"
    return "Primary Driverとの関係は確認できますが、期間ごとの安定性または説明力は限定的です。"


def next_analysis_guidance(macro: Mapping[str, object], movement: Mapping[str, str]) -> str:
    explainability = str(macro.get("explainability", {}).get("classification", "Unavailable"))
    if movement["classification"] == "Stock-specific / Unexplained" or explainability in {"Low", "Macro-unexplained"}:
        return "次の確認候補: 最新の業績・会社予想・企業開示を、対象期と開示日をそろえて確認。"
    if explainability in {"High", "Medium"}:
        return "次の確認候補: Primary Driverの方向・安定性の変化を重点的に確認。"
    return "次の確認候補: 利用可能なPrimary Driver Proxyとデータ品質を確認。"


def _macro_for_stock(
    stock: dict[str, object],
    prices: pd.Series,
    topix_quality: PriceQualityResult,
    macros: dict[str, pd.Series],
    performance: Mapping[str, float | None],
    shared: dict[str, pd.DataFrame] | None,
) -> dict[str, object]:
    ticker = str(stock["ticker"])
    if shared is not None and not shared.get("market_exposure", pd.DataFrame()).empty:
        selected = {key: _rows_for_ticker(frame, ticker) for key, frame in shared.items()}
        if not selected["market_exposure"].empty:
            return _first_macro_rows(selected)
    market_map = pd.DataFrame([{
        "ticker": ticker,
        "relative_1m": performance.get("relative_1m"),
        "relative_3m": performance.get("relative_3m"),
    }])
    generated = build_macro_sensitivity_analysis(
        pd.DataFrame({ticker: prices}), macros, topix_quality, market_map, stocks=(stock,)
    )
    return _first_macro_rows(generated)


def _first_macro_rows(frames: Mapping[str, pd.DataFrame]) -> dict[str, object]:
    return {
        "market_exposure": _first_row(frames.get("market_exposure", pd.DataFrame())),
        "primary_drivers": frames.get("primary_drivers", pd.DataFrame()).to_dict("records"),
        "observed_correlations": frames.get("observed_correlations", pd.DataFrame()),
        "regression": _first_row(frames.get("regression", pd.DataFrame())),
        "explainability": _first_row(frames.get("explainability", pd.DataFrame())),
    }


def _build_anchor_comparison(
    stock: Mapping[str, object],
    performance: Mapping[str, float | None],
    macro: Mapping[str, object],
    anchors: list[Mapping[str, object]],
    reference_prices: pd.DataFrame,
    topix: pd.Series,
    shared_macro: dict[str, pd.DataFrame] | None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for anchor in anchors:
        ticker = str(anchor["ticker"])
        series = reference_prices[ticker] if ticker in reference_prices else pd.Series(dtype=float)
        quality = inspect_price_series(series)
        anchor_performance = summarize_stock_performance(
            quality.series if quality.usable else pd.Series(dtype=float), topix
        )
        anchor_exposure = _first_row(_rows_for_ticker(
            (shared_macro or {}).get("market_exposure", pd.DataFrame()), ticker
        ))
        common_drivers = set(stock.get("primary_drivers", ())) & set(anchor.get("primary_drivers", ()))
        anchor_driver_rows = _rows_for_ticker(
            (shared_macro or {}).get("primary_drivers", pd.DataFrame()), ticker
        ).to_dict("records")
        target_driver_rows = list(macro.get("primary_drivers", []))
        rows.append({
            **dict(anchor),
            "status": "Available" if quality.usable and not series.dropna().empty else "Unavailable",
            "return_1m": anchor_performance["return_1m"],
            "return_3m": anchor_performance["return_3m"],
            "relative_1m": anchor_performance["relative_1m"],
            "relative_3m": anchor_performance["relative_3m"],
            "market_beta_252d": anchor_exposure.get("market_beta_252d"),
            "return_gap_1m": _difference(performance.get("return_1m"), anchor_performance["return_1m"]),
            "return_gap_3m": _difference(performance.get("return_3m"), anchor_performance["return_3m"]),
            "common_drivers": sorted(common_drivers),
            "shared_driver_sensitivities": _shared_driver_sensitivities(
                sorted(common_drivers), target_driver_rows, anchor_driver_rows
            ),
            "quality_reason": quality.reason,
        })
    return rows


def _shared_driver_sensitivities(
    drivers: list[str], target_rows: list[Mapping[str, object]], anchor_rows: list[Mapping[str, object]]
) -> list[str]:
    values: list[str] = []
    for driver in drivers:
        target = next((row.get("correlation_120d") for row in target_rows if row.get("driver") == driver), None)
        anchor = next((row.get("correlation_120d") for row in anchor_rows if row.get("driver") == driver), None)
        if target is None or anchor is None or pd.isna(target) or pd.isna(anchor):
            continue
        values.append(f"{driver}: 対象 {float(target):+.2f} / Anchor {float(anchor):+.2f}")
    return values


def _rows_for_ticker(frame: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if frame.empty or "ticker" not in frame:
        return pd.DataFrame()
    return frame[frame["ticker"].eq(ticker)].copy()


def _first_row(frame: pd.DataFrame) -> dict[str, object]:
    return {} if frame.empty else frame.iloc[0].to_dict()


def _latest(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    return None if clean.empty else float(clean.iloc[-1])


def _difference(left: object, right: object) -> float | None:
    if left is None or right is None or pd.isna(left) or pd.isna(right):
        return None
    return float(left) - float(right)
