from __future__ import annotations

import pandas as pd


def build_market_factor_hypotheses(
    stress_result: dict[str, object],
    series_by_name: dict[str, pd.Series],
    macro_regime: dict[str, object],
    maximum_hypotheses: int = 3,
) -> dict[str, object]:
    """観測済みデータと整合する市場変動の要因候補をルールベースで返す。"""
    components = _component_lookup(stress_result.get("components"))
    unavailable: list[str] = list(stress_result.get("unavailable", []))
    changes = {
        "S&P 500指数": _latest_percent_change(series_by_name.get("S&P 500指数")),
        "VIX指数": _latest_percent_change(series_by_name.get("VIX指数")),
        "USD/JPY": _latest_percent_change(series_by_name.get("USD/JPY")),
        "UST 10Y": _latest_point_change(series_by_name.get("UST 10Y"), 100),
    }
    for name, change in changes.items():
        if change is None:
            unavailable.append(f"{name}: 直近変化を計算できませんでした")

    candidates = [
        _risk_hypothesis(components, changes),
        _rates_hypothesis(components, changes, macro_regime),
        _fx_hypothesis(components, changes),
        _macro_hypothesis(macro_regime),
    ]
    available = [candidate for candidate in candidates if candidate["observations"]]
    available.sort(key=lambda candidate: candidate["rank_score"], reverse=True)
    hypotheses = []
    for candidate in available[:maximum_hypotheses]:
        candidate = candidate.copy()
        candidate.pop("rank_score")
        hypotheses.append(candidate)

    dates = [
        pd.Timestamp(component["基準日"])
        for component in components.values()
        if pd.notna(component.get("基準日"))
    ]
    return {
        "hypotheses": hypotheses,
        "unavailable": unavailable,
        "observed_at": max(dates) if dates else None,
        "input_coverage": stress_result.get("coverage", 0),
        "total_inputs": stress_result.get("total_components", 0),
    }


def _risk_hypothesis(
    components: dict[str, dict[str, object]],
    changes: dict[str, float | None],
) -> dict[str, object]:
    names = ["VIX水準", "S&P 500 20日実現ボラ", "S&P 500 60日高値からの下落"]
    percentiles = _percentiles(components, names)
    average = sum(percentiles) / len(percentiles) if percentiles else 50.0
    if average >= 60:
        title = "リスク回避・株価不安定化の可能性"
        direction = "高い"
    elif average <= 40:
        title = "リスク選好・株価安定化の可能性"
        direction = "低い"
    else:
        title = "株式市場の不安定さは中立圏"
        direction = "中立圏の"

    observations = [
        _percentile_text(components[name]) for name in names if name in components
    ]
    sp_change = changes["S&P 500指数"]
    vix_change = changes["VIX指数"]
    if sp_change is not None:
        observations.append(f"S&P 500直前観測値比は{sp_change:+.2f}%")
    if vix_change is not None:
        observations.append(f"VIX直前観測値比は{vix_change:+.2f}%")
    counter = []
    if sp_change is not None and vix_change is not None and sp_change * vix_change > 0:
        counter.append("株価とVIXが同方向で、典型的なリスク選好・回避の組合せではありません")
    return _candidate(
        title,
        f"株価・VIX関連3項目の平均的な位置が過去5年比で{direction}状態です。",
        observations,
        counter,
        abs(average - 50) + len(observations) * 3,
    )


def _rates_hypothesis(
    components: dict[str, dict[str, object]],
    changes: dict[str, float | None],
    macro_regime: dict[str, object],
) -> dict[str, object]:
    component = components.get("米10年金利 日次変化幅")
    yield_change = changes["UST 10Y"]
    sp_change = changes["S&P 500指数"]
    if yield_change is None:
        title = "金利変動の影響を確認"
    elif yield_change > 0:
        title = "金利上昇による株価圧力の可能性"
    elif yield_change < 0:
        title = "金利低下による株価支援の可能性"
    else:
        title = "金利要因は限定的な可能性"
    observations = []
    if component:
        observations.append(_percentile_text(component))
    if yield_change is not None:
        observations.append(f"米10年金利の直前観測値からの変化は{yield_change:+.1f}bp")
    policy = macro_regime.get("policy", {})
    inflation = macro_regime.get("inflation", {})
    if policy.get("status"):
        observations.append(f"金融政策評価は{policy['status']}")
    if inflation.get("status"):
        observations.append(f"物価評価は{inflation['status']}")
    counter = []
    if yield_change is not None and sp_change is not None and yield_change * sp_change > 0:
        counter.append("金利と株価が同方向で、単純な金利感応度だけでは説明しにくい動きです")
    percentile = float(component["過去5年percentile"]) if component else 50.0
    return _candidate(
        title,
        "金利の変化方向・変化幅と、物価・金融政策の背景を組み合わせた候補です。",
        observations,
        counter,
        abs(percentile - 50) + len(observations) * 3,
    )


def _fx_hypothesis(
    components: dict[str, dict[str, object]], changes: dict[str, float | None]
) -> dict[str, object]:
    component = components.get("USD/JPY 20日実現ボラ")
    fx_change = changes["USD/JPY"]
    observations = []
    if component:
        observations.append(_percentile_text(component))
    if fx_change is not None:
        direction = "円安" if fx_change > 0 else "円高" if fx_change < 0 else "横ばい"
        observations.append(f"USD/JPY直前観測値比は{fx_change:+.2f}%（{direction}方向）")
    percentile = float(component["過去5年percentile"]) if component else 50.0
    return _candidate(
        "為替市場の再評価を伴う可能性",
        "USD/JPYの方向と変動率から、株式・金利と並行した為替要因を確認します。",
        observations,
        [],
        abs(percentile - 50) + len(observations) * 3,
    )


def _macro_hypothesis(macro_regime: dict[str, object]) -> dict[str, object]:
    observations = []
    for key, label in [
        ("labor", "景気"),
        ("inflation", "物価"),
        ("policy", "金融政策"),
        ("curve", "イールドカーブ"),
    ]:
        status = macro_regime.get(key, {}).get("status")
        if status:
            observations.append(f"{label}評価は{status}")
    regime = macro_regime.get("regime", "現在のマクロ局面")
    return _candidate(
        f"マクロ背景: {regime}",
        "月次・日次の更新頻度が異なるため、当日の原因ではなく市場を取り巻く背景として扱います。",
        observations,
        [],
        len(observations) * 4,
    )


def _candidate(
    title: str,
    interpretation: str,
    observations: list[str],
    counter_evidence: list[str],
    rank_score: float,
) -> dict[str, object]:
    net_observations = max(len(observations) - len(counter_evidence), 0)
    strength = (
        "強い"
        if net_observations >= 4
        else "中程度" if net_observations >= 2 else "限定的"
    )
    return {
        "title": title,
        "strength": strength,
        "interpretation": interpretation,
        "observations": observations,
        "counter_evidence": counter_evidence,
        "observation_count": len(observations),
        "rank_score": net_observations * 100 + rank_score - len(counter_evidence) * 10,
    }


def _component_lookup(value: object) -> dict[str, dict[str, object]]:
    if not isinstance(value, pd.DataFrame) or value.empty or "項目" not in value:
        return {}
    return {str(row["項目"]): row.to_dict() for _, row in value.iterrows()}


def _percentiles(
    components: dict[str, dict[str, object]], names: list[str]
) -> list[float]:
    return [
        float(components[name]["過去5年percentile"])
        for name in names
        if name in components
    ]


def _percentile_text(component: dict[str, object]) -> str:
    return (
        f"{component['項目']}は過去5年の{float(component['過去5年percentile']):.1f}"
        f"percentile（過去観測{int(component['サンプル数'])}件）"
    )


def _latest_percent_change(series: pd.Series | None) -> float | None:
    clean = _clean_series(series)
    if len(clean) < 2 or clean.iloc[-2] == 0:
        return None
    return float((clean.iloc[-1] / clean.iloc[-2] - 1) * 100)


def _latest_point_change(series: pd.Series | None, multiplier: float) -> float | None:
    clean = _clean_series(series)
    if len(clean) < 2:
        return None
    return float((clean.iloc[-1] - clean.iloc[-2]) * multiplier)


def _clean_series(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series(dtype=float)
    return (
        series.astype(float)
        .replace([float("inf"), float("-inf")], pd.NA)
        .dropna()
        .sort_index()
    )
