from __future__ import annotations

import pandas as pd
import streamlit as st

from japan_equity import CORE_20, build_core_snapshot, expected_proxy_names, top_observed_correlations
from stock_detail import build_stock_detail_analysis


def render_japan_core_equity(
    market_map: pd.DataFrame,
    sector_summary: pd.DataFrame,
    theme_summary: pd.DataFrame,
    sensitivity: dict[str, pd.DataFrame],
    stock_failures: list[str] | None = None,
    macro_failures: list[str] | None = None,
    prices: pd.DataFrame | None = None,
    macro_series: dict[str, pd.Series] | None = None,
    topix_quality: object | None = None,
) -> None:
    st.markdown("### Japan Core 20")
    st.caption(
        "日本の主要大型株20社について、絶対リターン、TOPIX連動ETF比、"
        "直近のマクロ相関を確認します。売買判断や業種指数ではありません。"
    )
    if market_map.empty or not market_map["status"].eq("Available").any():
        st.warning("Core 20の株価を取得できないため、日本株分析を表示できません。")
        return

    _render_snapshot(market_map)
    _render_market_map(market_map)
    _render_aggregates(sector_summary, theme_summary)
    _render_macro_sensitivity(market_map, sensitivity)
    _render_stock_detail(market_map, sensitivity, prices, macro_series, topix_quality)

    failures = [*(stock_failures or []), *(macro_failures or [])]
    if failures:
        with st.expander("取得できなかった系列を見る"):
            for failure in failures:
                st.warning(failure)


def _render_snapshot(market_map: pd.DataFrame) -> None:
    snapshot = build_core_snapshot(market_map)
    st.markdown("#### Japan Core 20 Snapshot")
    first = st.columns(2)
    first[0].metric("上昇", f"{snapshot['rising']}社")
    first[1].metric("下落", f"{snapshot['falling']}社")
    st.metric("TOPIX比＋（1か月）", f"{snapshot['outperforming']}社")
    second = st.columns(2)
    second[0].metric("1か月最強", snapshot["strongest_1m"] or "—")
    second[1].metric("1か月最弱", snapshot["weakest_1m"] or "—")
    if snapshot["unavailable"]:
        st.caption(f"取得済み {snapshot['available']}/20社｜取得不能 {snapshot['unavailable']}社")


def _render_market_map(market_map: pd.DataFrame) -> None:
    st.markdown("#### Market Map")
    st.caption("TOPIX比はTOPIX連動ETF（1306）の同期間リターンとの差です。")
    compact = market_map.copy()
    compact["銘柄"] = compact["name"] + "（" + compact["code"] + "）"
    compact["主テーマ"] = compact["macro_themes"].map(lambda values: " / ".join(values[:2]))
    compact["1日"] = compact["return_1d"].map(_percent)
    compact["1か月"] = compact["return_1m"].map(_percent)
    compact["TOPIX比"] = compact["relative_1m"].map(_point)
    st.dataframe(
        compact[["銘柄", "sector", "1日", "1か月", "TOPIX比", "主テーマ"]].rename(
            columns={"sector": "セクター"}
        ),
        hide_index=True,
        width="stretch",
        height=420,
    )
    with st.expander("5日・3か月を含む詳細を見る"):
        detail = market_map.copy()
        detail["銘柄"] = detail["name"] + "（" + detail["code"] + "）"
        for source, target, formatter in (
            ("current", "現在値", _price),
            ("return_1d", "1日", _percent),
            ("return_5d", "5日", _percent),
            ("return_1m", "1か月", _percent),
            ("return_3m", "3か月", _percent),
            ("relative_1m", "TOPIX比1か月", _point),
            ("relative_3m", "TOPIX比3か月", _point),
        ):
            detail[target] = detail[source].map(formatter)
        st.dataframe(
            detail[["銘柄", "現在値", "1日", "5日", "1か月", "3か月", "TOPIX比1か月", "TOPIX比3か月"]],
            hide_index=True,
            width="stretch",
        )


def _render_aggregates(sector_summary: pd.DataFrame, theme_summary: pd.DataFrame) -> None:
    st.markdown("#### Sector View")
    st.caption("Core 20内の代表銘柄集計であり、TOPIX業種指数の代替ではありません。")
    st.dataframe(_format_aggregate(sector_summary, "sector", "セクター"), hide_index=True, width="stretch", height=300)
    with st.expander("Theme / Driver Viewを見る"):
        st.caption("1銘柄が複数テーマに属するため、銘柄数の合計は20を超えます。")
        st.dataframe(_format_aggregate(theme_summary, "theme", "テーマ"), hide_index=True, width="stretch")


def _render_macro_sensitivity(market_map: pd.DataFrame, sensitivity: dict[str, pd.DataFrame]) -> None:
    st.markdown("#### Macro Sensitivity")
    st.caption(
        "Market Exposureと、市場共通要因を除いたPrimary Driverとの同時点の関係を分けて確認します。"
        "先行性・因果関係・恒常的な感応度を示すものではありません。"
    )
    available = market_map[market_map["status"].eq("Available")]
    options = {f"{row['name']}（{row['code']}）": row["ticker"] for _, row in available.iterrows()}
    label = st.selectbox("確認する銘柄", list(options), key="japan_core_sensitivity_stock")
    ticker = options[label]
    stock = next(item for item in CORE_20 if item["ticker"] == ticker)
    expected = expected_proxy_names(stock)
    exposure = _selected_row(sensitivity.get("market_exposure", pd.DataFrame()), ticker)
    st.markdown("##### Market Exposure")
    if exposure is None or exposure.get("status") != "Available":
        reason = "市場データまたは観測数が不足しています" if exposure is None else exposure.get("reason")
        st.info(f"Unavailable：{reason}")
    else:
        metrics = st.columns(2)
        metrics[0].metric("Market Beta（252D）", _number(exposure.get("market_beta_252d")))
        metrics[1].metric("TOPIX Correlation（252D）", _correlation(exposure.get("topix_correlation_252d")))
        active = st.columns(2)
        active[0].metric("Active Return vs TOPIX（1M）", _point(exposure.get("relative_1m")))
        active[1].metric("Active Return vs TOPIX（3M）", _point(exposure.get("relative_3m")))
        beta_status = exposure.get("beta_stability")
        beta_text = (
            f"252D β {_number(exposure.get('market_beta_252d'))} / 120D β {_number(exposure.get('market_beta_120d'))}"
        )
        if beta_status == "Unstable":
            st.warning(f"β不安定：{beta_text}")
        else:
            st.caption(f"Beta stability: {beta_status}｜{beta_text}")
        if exposure.get("reason"):
            st.caption(str(exposure["reason"]))

    st.markdown("##### Macro Drivers")
    st.write(f"**事前定義済みPrimary Driver:** {' / '.join(stock['primary_drivers'])}")
    st.caption("実データProxy: " + (" / ".join(expected) if expected else "設定なし（概念タグのみ）"))
    primary = sensitivity.get("primary_drivers", pd.DataFrame())
    selected_primary = primary[primary["ticker"].eq(ticker)] if not primary.empty else pd.DataFrame()
    if selected_primary.empty:
        st.info("Primary Driverを分析できません。")
    else:
        for row in selected_primary.to_dict("records"):
            with st.container(border=True):
                st.markdown(f"**{row['driver']}**")
                proxy = row.get("proxy")
                if _missing(proxy):
                    st.caption("実データProxy：未設定。このDriverは現在、定量的なMacro Sensitivity分析の対象外です。")
                else:
                    st.caption(f"Proxy: {proxy}")
                if row.get("status") != "Available":
                    st.write(f"Unavailable｜{row.get('reason', 'データ不足')}")
                    continue
                st.metric("120D Residual correlation", _correlation(row.get("correlation_120d")))
                st.write(
                    f"60D {_correlation(row.get('correlation_60d'))}　/　"
                    f"20D {_correlation(row.get('correlation_20d'))}"
                )
                st.caption(
                    f"Direction: {row.get('direction')}｜Stability: {row.get('stability')}｜"
                    f"120D観測数 {int(row.get('observations_120d', 0))}"
                )
                st.caption(str(row.get("reason", "")))

    explanation = _selected_row(sensitivity.get("explainability", pd.DataFrame()), ticker)
    st.markdown("##### Macro Explainability")
    if explanation is None:
        st.info("Unavailable：判定に必要なデータがありません。")
    else:
        classification = str(explanation.get("classification", "Unavailable"))
        st.markdown(f"### {classification}")
        st.caption(str(explanation.get("reason", "")))
        if classification == "Macro-unexplained":
            st.caption("これは企業固有要因やAlphaを断定する表示ではありません。")

    with st.expander("詳細：Observed / Ex post correlations・回帰を見る"):
        st.caption(
            "Observed correlationsはデータを見た後に相関が高かった系列です。"
            "Primary Driverではなく、因果関係や先行性も意味しません。TOPIXは除外しています。"
        )
        observed = sensitivity.get("observed_correlations", pd.DataFrame())
        top = top_observed_correlations(observed, ticker)
        if top.empty:
            st.info("Observed correlationを計算できません。")
        else:
            detail = top.copy()
            detail["120D"] = detail["correlation_120d"].map(_correlation)
            detail["60D"] = detail["correlation_60d"].map(_correlation)
            detail["20D"] = detail["correlation_20d"].map(_correlation)
            st.dataframe(detail[["macro", "120D", "60D", "20D", "observations"]].rename(
                columns={"macro": "系列", "observations": "共通観測数"}
            ), hide_index=True, width="stretch")
        regression = _selected_row(sensitivity.get("regression", pd.DataFrame()), ticker)
        if regression is None or regression.get("status") != "Available":
            st.caption("回帰詳細：Unavailable")
        else:
            st.write(
                "Adjusted R²：Market only "
                f"{_number(regression.get('market_adjusted_r2'))} → Market + Primary Drivers "
                f"{_number(regression.get('driver_adjusted_r2'))} "
                f"（改善 {_number(regression.get('adjusted_r2_improvement'))}）"
            )
            st.caption(f"共通観測数 {int(regression.get('observations', 0))}｜係数 {regression.get('coefficients', {})}")
        st.caption(
            "株価・指数・FX・商品は日次リターン、金利は日次変化幅を使用。"
            "日本株と米国系列は単純日付結合で、取引時間差は補正していません。"
        )


def _selected_row(frame: pd.DataFrame, ticker: str) -> dict[str, object] | None:
    if frame.empty or "ticker" not in frame:
        return None
    selected = frame[frame["ticker"].eq(ticker)]
    return None if selected.empty else selected.iloc[0].to_dict()


def _render_stock_detail(
    market_map: pd.DataFrame,
    sensitivity: dict[str, pd.DataFrame],
    prices: pd.DataFrame | None,
    macro_series: dict[str, pd.Series] | None,
    topix_quality: object | None,
) -> None:
    st.markdown("#### Stock Detail")
    st.caption("市場 → Primary Driver → Core20 Anchor → 説明しにくい個別的な動きの順に、1銘柄を深掘りします。")
    if prices is None or macro_series is None or topix_quality is None:
        st.info("Stock Detailに必要な価格・マクロデータを取得できません。")
        return
    available = market_map[market_map["status"].eq("Available")]
    options = {f"{row['name']}（{row['code']}）": row["ticker"] for _, row in available.iterrows()}
    if not options:
        return
    label = st.selectbox("詳細を確認する銘柄", list(options), key="japan_core_stock_detail")
    ticker = options[label]
    stock = next(item for item in CORE_20 if item["ticker"] == ticker)
    detail = build_stock_detail_analysis(
        stock,
        prices[ticker],
        topix_quality,
        macro_series,
        CORE_20,
        prices,
        shared_macro_analysis=sensitivity,
    )
    _render_stock_snapshot(detail)
    _render_stock_performance(detail)
    _render_stock_market_exposure(detail)
    _render_stock_drivers(detail)
    _render_stock_anchors(detail)
    _render_stock_specific_move(detail)
    _render_stock_diagnostics(detail)


def _render_stock_snapshot(detail: dict[str, object]) -> None:
    stock = detail["stock"]
    st.markdown("##### Stock Snapshot")
    st.markdown(f"### {stock['name']}（{stock['code']}）")
    st.caption(f"Sector: {stock['sector']}")
    st.write("**Primary Themes:** " + " / ".join(stock["macro_themes"]))
    st.write("**Primary Drivers:** " + " / ".join(stock["primary_drivers"]))
    st.metric("現在値", _price(detail["performance"].get("current")))
    quality = detail["quality"]
    if quality.reason:
        st.caption(f"価格品質: {quality.reason}")


def _render_stock_performance(detail: dict[str, object]) -> None:
    performance = detail["performance"]
    st.markdown("##### Performance")
    first = st.columns(3)
    for column, label, field in zip(first, ("1D", "5D", "1M"), ("return_1d", "return_5d", "return_1m")):
        column.metric(label, _percent(performance.get(field)))
    second = st.columns(3)
    for column, label, field in zip(second, ("3M", "6M", "1Y"), ("return_3m", "return_6m", "return_1y")):
        column.metric(label, _percent(performance.get(field)))
    active = st.columns(2)
    active[0].metric("TOPIX Relative Return（1M）", _point(performance.get("relative_1m")))
    active[1].metric("TOPIX Relative Return（3M）", _point(performance.get("relative_3m")))


def _render_stock_market_exposure(detail: dict[str, object]) -> None:
    exposure = detail["market_exposure"]
    st.markdown("##### Market Exposure")
    if exposure.get("status") != "Available":
        st.info(f"Unavailable：{exposure.get('reason', '市場調整後分析を計算できません。')}")
        return
    metrics = st.columns(2)
    metrics[0].metric("Market Beta（252D）", _number(exposure.get("market_beta_252d")))
    metrics[1].metric("Market Beta（120D）", _number(exposure.get("market_beta_120d")))
    metrics = st.columns(2)
    metrics[0].metric("TOPIX Correlation（252D）", _correlation(exposure.get("topix_correlation_252d")))
    metrics[1].metric("Beta stability", str(exposure.get("beta_stability", "Unavailable")))
    beta = exposure.get("market_beta_252d")
    if beta is not None:
        if float(beta) >= 1.8:
            st.caption("市場より値動きが大きい傾向です。固定的な投資評価ではありません。")
        elif float(beta) < 0.5:
            st.caption("市場感応度が低い傾向です。固定的な投資評価ではありません。")


def _render_stock_drivers(detail: dict[str, object]) -> None:
    st.markdown("##### Macro Drivers")
    for row in detail["primary_drivers"]:
        with st.container(border=True):
            st.markdown(f"**{row['driver']}**")
            if _missing(row.get("proxy")):
                st.caption("実データProxy：未設定。このDriverは現在、定量的なMacro Sensitivity分析の対象外です。")
            else:
                st.caption(f"Proxy: {row['proxy']}")
            if row.get("status") != "Available":
                st.write(f"Unavailable｜{row.get('reason', 'データ不足')}")
                continue
            st.metric("120D Residual correlation", _correlation(row.get("correlation_120d")))
            st.write(f"60D {_correlation(row.get('correlation_60d'))}　/　20D {_correlation(row.get('correlation_20d'))}")
            st.caption(f"Stability: {row.get('stability')}｜{row.get('reason')}")
    explanation = detail["explainability"]
    st.markdown("##### Macro Explainability")
    st.markdown(f"### {explanation.get('classification', 'Unavailable')}")
    st.caption(str(explanation.get("reason", "")))


def _render_stock_anchors(detail: dict[str, object]) -> None:
    st.markdown("##### Core20 Anchors / Relative Behavior")
    anchors = detail["anchors"]
    if not anchors:
        st.info("Strong Anchor not available：比較する意味が十分に強いCore20参照銘柄がありません。")
        return
    for anchor in anchors:
        with st.container(border=True):
            st.markdown(f"**{anchor['name']}（{anchor['code']}）**")
            st.caption("｜".join(anchor["anchor_reasons"]))
            if anchor["status"] != "Available":
                st.write("Unavailable：価格品質または取得状況を確認してください。")
                continue
            metrics = st.columns(2)
            metrics[0].metric("Anchor 1M", _percent(anchor.get("return_1m")))
            metrics[1].metric("Anchor 3M", _percent(anchor.get("return_3m")))
            st.write(
                f"対象との差: 1M {_point(anchor.get('return_gap_1m'))} / "
                f"3M {_point(anchor.get('return_gap_3m'))}｜"
                f"Anchor β {_number(anchor.get('market_beta_252d'))}"
            )
            st.caption(
                f"Anchor TOPIX Relative: 1M {_point(anchor.get('relative_1m'))} / "
                f"3M {_point(anchor.get('relative_3m'))}"
            )
            if anchor.get("shared_driver_sensitivities"):
                st.caption("共通Driverの120D感応度: " + "｜".join(anchor["shared_driver_sensitivities"]))
            if anchor.get("return_gap_3m") is not None and abs(float(anchor["return_gap_3m"])) >= 10:
                st.caption("同じテーマのAnchorと比較して、最近の3か月リターンに大きな差があります。")


def _render_stock_specific_move(detail: dict[str, object]) -> None:
    st.markdown("##### Stock-specific / Unexplained Move")
    residual = detail["residual_periods"]
    metrics = st.columns(3)
    metrics[0].metric("Residual 5D", _percent(residual.get("residual_5d")))
    metrics[1].metric("Residual 1M", _percent(residual.get("residual_1m")))
    metrics[2].metric("Residual 3M", _percent(residual.get("residual_3m")))
    st.caption("日次Residual Returnを複利累積した近似値です。Alphaや企業固有要因を断定するものではありません。")
    movement = detail["movement"]
    st.markdown(f"### {movement['classification']}")
    st.caption(movement["reason"])
    st.markdown("##### Interpretation")
    st.info(detail["interpretation"])
    st.markdown("##### Next Analysis")
    st.caption(detail["next_analysis"])


def _render_stock_diagnostics(detail: dict[str, object]) -> None:
    with st.expander("Detailed Diagnosticsを見る"):
        st.caption("Observed / Ex post correlationsはデータ観測後の相関であり、因果関係や先行性を意味しません。")
        observed = detail["observed_correlations"]
        if not observed.empty:
            display = observed.copy()
            for source, label in (("correlation_120d", "120D"), ("correlation_60d", "60D"), ("correlation_20d", "20D")):
                display[label] = display[source].map(_correlation)
            st.dataframe(display[["macro", "120D", "60D", "20D", "observations"]].rename(columns={"macro": "系列", "observations": "共通観測数"}), hide_index=True, width="stretch")
        regression = detail["regression"]
        if regression.get("status") == "Available":
            st.write(f"Adjusted R²: Market only {_number(regression.get('market_adjusted_r2'))} → Market + Drivers {_number(regression.get('driver_adjusted_r2'))}")
            st.caption(f"改善 {_number(regression.get('adjusted_r2_improvement'))}｜観測数 {int(regression.get('observations', 0))}｜係数 {regression.get('coefficients', {})}")
        st.caption("株価・指数・FX・商品は日次リターン、金利は日次変化幅。米国市場系列との取引時間差は補正していません。")


def _format_aggregate(frame: pd.DataFrame, key: str, label: str) -> pd.DataFrame:
    result = frame.copy()
    result["銘柄数"] = result["stock_count"].astype(int)
    result["取得数"] = result["available_count"].astype(int)
    result["1日平均"] = result["return_1d"].map(_percent)
    result["1か月平均"] = result["return_1m"].map(_percent)
    result["3か月平均"] = result["return_3m"].map(_percent)
    return result[[key, "銘柄数", "取得数", "1日平均", "1か月平均", "3か月平均"]].rename(columns={key: label})


def _percent(value: object) -> str:
    return "—" if value is None or pd.isna(value) else f"{float(value):+.1f}%"


def _point(value: object) -> str:
    return "—" if value is None or pd.isna(value) else f"{float(value):+.1f}pt"


def _price(value: object) -> str:
    return "—" if value is None or pd.isna(value) else f"{float(value):,.1f}円"


def _correlation(value: object) -> str:
    return "—" if value is None or pd.isna(value) else f"{float(value):+.2f}"


def _number(value: object) -> str:
    return "—" if value is None or pd.isna(value) else f"{float(value):.2f}"


def _missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
