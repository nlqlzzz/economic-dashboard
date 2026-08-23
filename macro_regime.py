from __future__ import annotations

import pandas as pd


MACRO_ASSESSMENT_SCORES = {
    "改善": 1,
    "鈍化": 1,
    "緩和": 1,
    "順イールド": 1,
    "横ばい": 0,
    "悪化": -1,
    "上昇": -1,
    "引き締め": -1,
    "逆イールド": -1,
}


def build_us_macro_assessment_history(
    cpi: pd.Series,
    unemployment: pd.Series,
    fed_funds: pd.Series,
    ust_2y: pd.Series,
    ust_10y: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """4つのマクロ評価を月次で再計算し、表示用の判定とスコアを返す。"""
    cpi_yoy = cpi.pct_change(periods=12, fill_method=None) * 100
    combined = pd.concat(
        {
            "cpi_yoy": cpi_yoy,
            "unemployment": unemployment,
            "fed_funds": fed_funds,
            "ust_2y": ust_2y,
            "ust_10y": ust_10y,
        },
        axis=1,
    ).sort_index()
    combined.index = combined.index.to_period("M").to_timestamp("M")
    monthly = combined.groupby(level=0).last().ffill()

    changes = monthly[["cpi_yoy", "unemployment", "fed_funds"]].diff(3)
    labels = pd.DataFrame(index=monthly.index)
    labels["景気"] = changes["unemployment"].map(
        lambda value: _classify_historical_change(value, 0.2, "悪化", "改善")
    )
    labels["物価"] = changes["cpi_yoy"].map(
        lambda value: _classify_historical_change(value, 0.2, "上昇", "鈍化")
    )
    labels["金融政策"] = changes["fed_funds"].map(
        lambda value: _classify_historical_change(value, 0.25, "引き締め", "緩和")
    )
    labels["イールドカーブ"] = (monthly["ust_10y"] - monthly["ust_2y"]).map(
        lambda value: (
            None
            if pd.isna(value)
            else ("順イールド" if value >= 0 else "逆イールド")
        )
    )
    labels = labels.dropna()
    scores = labels.map(lambda value: MACRO_ASSESSMENT_SCORES[value]).astype(int)
    return labels, scores


def build_us_macro_trends(
    cpi: pd.Series,
    unemployment: pd.Series,
    fed_funds: pd.Series,
    ust_2y: pd.Series,
    ust_10y: pd.Series,
) -> dict[str, pd.Series]:
    """マクロ局面判定に使う4系列の推移を表示用に整える。"""
    cpi_yoy = cpi.pct_change(periods=12, fill_method=None).dropna() * 100
    yield_curve = pd.concat(
        {"ust_2y": ust_2y, "ust_10y": ust_10y}, axis=1
    ).dropna()
    trend_start = cpi_yoy.index.min()
    return {
        "CPI前年比": cpi_yoy,
        "失業率": unemployment.dropna().loc[trend_start:],
        "FF金利": fed_funds.dropna().loc[trend_start:],
        "10年−2年金利差": (
            yield_curve["ust_10y"] - yield_curve["ust_2y"]
        ).loc[trend_start:],
    }


def assess_us_macro_regime(
    cpi: pd.Series,
    unemployment: pd.Series,
    fed_funds: pd.Series,
    ust_2y: pd.Series,
    ust_10y: pd.Series,
) -> dict[str, object]:
    """米国のインフレ・雇用・金融政策・長短金利差をルールベースで要約する。"""
    cpi_yoy = cpi.pct_change(periods=12, fill_method=None).dropna() * 100
    inflation_now, inflation_date = _latest(cpi_yoy)
    inflation_before = _value_as_of(cpi_yoy, inflation_date - pd.DateOffset(months=3))
    inflation_change = inflation_now - inflation_before
    inflation_status = _classify_change(inflation_change, threshold=0.2, up="上昇", down="鈍化")

    unemployment_now, unemployment_date = _latest(unemployment)
    unemployment_before = _value_as_of(unemployment, unemployment_date - pd.DateOffset(months=3))
    unemployment_change = unemployment_now - unemployment_before
    labor_status = _classify_change(unemployment_change, threshold=0.2, up="悪化", down="改善")

    fed_funds_now, fed_funds_date = _latest(fed_funds)
    fed_funds_before = _value_as_of(fed_funds, fed_funds_date - pd.DateOffset(months=3))
    fed_funds_change = fed_funds_now - fed_funds_before
    policy_status = _classify_change(fed_funds_change, threshold=0.25, up="引き締め", down="緩和")

    ust_2y_now, ust_2y_date = _latest(ust_2y)
    ust_10y_now, ust_10y_date = _latest(ust_10y)
    curve_spread = ust_10y_now - ust_2y_now
    curve_status = "順イールド" if curve_spread >= 0 else "逆イールド"

    regime, description = _determine_regime(inflation_status, labor_status)
    return {
        "regime": regime,
        "description": description,
        "inflation": {"status": inflation_status, "value": inflation_now, "change": inflation_change, "date": inflation_date},
        "labor": {"status": labor_status, "value": unemployment_now, "change": unemployment_change, "date": unemployment_date},
        "policy": {"status": policy_status, "value": fed_funds_now, "change": fed_funds_change, "date": fed_funds_date},
        "curve": {
            "status": curve_status,
            "spread": curve_spread,
            "ust_2y": ust_2y_now,
            "ust_10y": ust_10y_now,
            "date": min(ust_2y_date, ust_10y_date),
        },
    }


def _latest(series: pd.Series) -> tuple[float, pd.Timestamp]:
    clean = series.dropna()
    if clean.empty:
        raise ValueError("景気局面の判定に必要なデータがありません。")
    return float(clean.iloc[-1]), pd.Timestamp(clean.index[-1])


def _value_as_of(series: pd.Series, reference_date: pd.Timestamp) -> float:
    historical = series.dropna().loc[:reference_date]
    if historical.empty:
        raise ValueError("景気局面の判定に必要な過去データが不足しています。")
    return float(historical.iloc[-1])


def _classify_change(change: float, threshold: float, up: str, down: str) -> str:
    if change >= threshold:
        return up
    if change <= -threshold:
        return down
    return "横ばい"


def _classify_historical_change(
    change: float, threshold: float, up: str, down: str
) -> str | None:
    if pd.isna(change):
        return None
    return _classify_change(float(change), threshold, up, down)


def _determine_regime(inflation: str, labor: str) -> tuple[str, str]:
    if inflation == "上昇" and labor != "悪化":
        return "リフレ・過熱寄り", "インフレは上向きで、雇用は大きく悪化していません。"
    if inflation == "鈍化" and labor == "悪化":
        return "景気減速・ディスインフレ", "インフレは鈍化する一方、雇用は弱含んでいます。"
    if inflation == "鈍化" and labor != "悪化":
        return "ディスインフレ・ソフトランディング寄り", "インフレは鈍化し、雇用はおおむね安定しています。"
    if inflation == "上昇" and labor == "悪化":
        return "スタグフレーション警戒", "インフレ上昇と雇用悪化が同時に見られます。"
    return "転換点・様子見", "インフレと雇用の方向感が明確ではありません。"
