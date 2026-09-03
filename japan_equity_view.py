from __future__ import annotations

import pandas as pd
import streamlit as st

from japan_equity import CORE_20, build_core_snapshot, expected_proxy_names, top_macro_sensitivities


def render_japan_core_equity(
    market_map: pd.DataFrame,
    sector_summary: pd.DataFrame,
    theme_summary: pd.DataFrame,
    sensitivity: pd.DataFrame,
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


def _render_macro_sensitivity(market_map: pd.DataFrame, sensitivity: pd.DataFrame) -> None:
    st.markdown("#### Macro Sensitivity")
    st.caption(
        "相関は日次の株価騰落率と市場系列の騰落率（金利は変化幅）から計算します。"
        "因果関係や恒常的な感応度を示すものではありません。"
    )
    available = market_map[market_map["status"].eq("Available")]
    options = {f"{row['name']}（{row['code']}）": row["ticker"] for _, row in available.iterrows()}
    label = st.selectbox("確認する銘柄", list(options), key="japan_core_sensitivity_stock")
    ticker = options[label]
    stock = next(item for item in CORE_20 if item["ticker"] == ticker)
    expected = expected_proxy_names(stock)
    st.write(f"**想定ドライバー:** {' / '.join(stock['primary_drivers'])}")
    st.caption(
        "実データProxy: " + (" / ".join(expected) if expected else "設定なし（概念タグのみ）")
    )
    top = top_macro_sensitivities(sensitivity, ticker)
    if top.empty:
        st.info("共通観測数が不足しているため、直近相関を表示できません。")
        return
    display = top.copy()
    display["60日相関"] = display["correlation_60d"].map(_correlation)
    display["20日相関"] = display["correlation_20d"].map(_correlation)
    display["想定Proxy"] = display["is_expected_driver"].map(lambda value: "該当" if value else "—")
    st.markdown("##### 直近60日で相関が強い系列")
    st.dataframe(display[["macro", "60日相関", "20日相関", "想定Proxy"]].rename(columns={"macro": "系列"}), hide_index=True, width="stretch")
    with st.expander("全系列と相関変化を見る"):
        detail = sensitivity[sensitivity["ticker"].eq(ticker)].copy()
        detail["20日相関"] = detail["correlation_20d"].map(_correlation)
        detail["60日相関"] = detail["correlation_60d"].map(_correlation)
        detail["1か月前比"] = detail["change_21d"].map(_correlation)
        detail["3か月前比"] = detail["change_63d"].map(_correlation)
        detail["分布位置"] = detail["percentile_60d"].map(lambda value: "—" if pd.isna(value) else f"{value:.0f}%ile")
        st.dataframe(detail[["macro", "20日相関", "60日相関", "1か月前比", "3か月前比", "分布位置", "observations"]].rename(columns={"macro": "系列", "observations": "共通観測数"}), hide_index=True, width="stretch")


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
