from __future__ import annotations

import pandas as pd
import streamlit as st

from japan_equity import CORE_20, build_core_snapshot, expected_proxy_names, top_observed_correlations


def render_japan_core_equity(
    market_map: pd.DataFrame,
    sector_summary: pd.DataFrame,
    theme_summary: pd.DataFrame,
    sensitivity: dict[str, pd.DataFrame],
    stock_failures: list[str] | None = None,
    macro_failures: list[str] | None = None,
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
                st.caption(f"Proxy: {row.get('proxy') or 'Proxy not available'}")
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
