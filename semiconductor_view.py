from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from global_semiconductor_demand import (
    assess_regional_pulse,
    build_japan_pulse_inputs,
    classify_demand_direction,
    combine_global_pulse,
    summarize_global_demand,
)
from semiconductor_validation import (
    add_global_condition_signals,
    analyze_release_aware_correlation,
    analyze_release_aware_returns,
    build_overseas_validation_signals,
    calculate_market_momentum,
    classify_price_vs_fundamentals,
)
from theme_view import build_theme_snapshot


def render_semiconductor_snapshot(
    theme_series: dict[str, pd.Series],
    indicator_metadata: dict[str, dict[str, object]],
    taiwan_data: pd.DataFrame,
    korea_data: pd.DataFrame,
    japan_assessment: str | None,
) -> None:
    """市場と地域別実需を5項目に限定して表示する。"""
    summaries = summarize_global_demand(pd.concat([taiwan_data, korea_data], ignore_index=True))
    taiwan = classify_demand_direction(summaries, "Taiwan")
    korea = classify_demand_direction(summaries, "Korea")
    market_snapshot = build_theme_snapshot(theme_series, indicator_metadata)
    sox = _market_direction(market_snapshot, "SOX指数")
    japan = {
        "direction": "→",
        "status": "Mixed" if japan_assessment else "Unavailable",
        "evidence": [japan_assessment] if japan_assessment else [],
    }
    items = [
        ("SOX", sox),
        ("Taiwan Orders", taiwan),
        ("Korea Exports", korea),
        ("Japan Cycle", japan),
    ]
    st.markdown("#### Semiconductor Snapshot")
    columns = st.columns(2)
    for index, (label, result) in enumerate(items):
        with columns[index % 2]:
            st.metric(label, f"{result['direction']} {result['status']}")
            evidence = result.get("evidence", [])
            st.caption(evidence[0] if evidence else "判定に必要なデータがありません。")
    with st.expander("Snapshotの判定根拠を見る"):
        for label, result in items:
            evidence = result.get("evidence", [])
            st.markdown(f"**{label}: {result['status']}**")
            st.caption(" / ".join(evidence) if evidence else "利用可能な根拠なし")
    st.caption("方向判定は利用可能な系列の前年比と3か月トレンドによる説明用表示で、総合スコアや投資助言ではありません。")


def render_semiconductor_market_compact(
    theme_series: dict[str, pd.Series],
    indicator_metadata: dict[str, dict[str, object]],
) -> None:
    st.markdown("#### Market")
    names = [
        "SOX指数",
        "NASDAQ総合指数",
        "東京エレクトロン（8035）",
        "アドバンテスト（6857）",
        "ディスコ（6146）",
        "キオクシア（285A）",
        "UST 10Y",
        "VIX指数",
    ]
    selected = {name: theme_series[name] for name in names if name in theme_series}
    snapshot = build_theme_snapshot(selected, indicator_metadata)
    if snapshot.empty:
        st.warning("半導体市場データを表示できません。")
        return
    display = snapshot[["指標", "1か月変化", "変化単位", "データ日"]].copy()
    display["1か月変化"] = display.apply(
        lambda row: "—" if pd.isna(row["1か月変化"]) else f"{row['1か月変化']:+.1f}{row['変化単位']}",
        axis=1,
    )
    display["データ日"] = display["データ日"].dt.strftime("%Y-%m-%d")
    st.dataframe(display.drop(columns="変化単位"), hide_index=True, width="stretch")


def build_current_global_pulse(
    taiwan_data: pd.DataFrame,
    korea_data: pd.DataFrame,
    japan_iip_summary: pd.DataFrame,
    machinery_summary: dict[str, object] | None,
) -> dict[str, object]:
    summary = summarize_global_demand(pd.concat([taiwan_data, korea_data], ignore_index=True))
    regions = {
        "Taiwan": assess_regional_pulse(summary, "Taiwan"),
        "Korea": assess_regional_pulse(summary, "Korea"),
        "Japan": assess_regional_pulse(
            summary,
            "Japan",
            build_japan_pulse_inputs(japan_iip_summary, machinery_summary),
        ),
    }
    return combine_global_pulse(regions)


def render_global_semiconductor_pulse(pulse: dict[str, object]) -> None:
    st.markdown("#### Global Semiconductor Demand Pulse")
    state = str(pulse.get("state", "Unavailable"))
    label = "Unavailable / Limited Data" if state == "Unavailable" else state
    st.metric("Global Semiconductor Demand", f"{pulse.get('direction', '→')} {label}")
    st.caption(str(pulse.get("coverage_label", "Limited Data")))
    columns = st.columns(3)
    for column, region in zip(columns, ("Taiwan", "Korea", "Japan")):
        result = pulse.get("regions", {}).get(region, {"state": "Unavailable", "direction": "→"})
        column.metric(region, f"{result.get('direction', '→')} {result.get('state', 'Unavailable')}")
    st.write(str(pulse.get("reason", "判定に必要なデータがありません。")))
    with st.expander("Global Pulseの判定根拠を見る"):
        for region in ("Taiwan", "Korea", "Japan"):
            result = pulse.get("regions", {}).get(region, {})
            st.markdown(f"**{region}: {result.get('state', 'Unavailable')}**")
            positives = result.get("contributors_positive", [])
            negatives = result.get("contributors_negative", [])
            missing = result.get("contributors_missing", [])
            st.caption(
                f"改善: {', '.join(positives) or 'なし'}｜悪化: {', '.join(negatives) or 'なし'}｜欠損: {', '.join(missing) or 'なし'}"
            )
    st.caption("0〜100の総合スコアではありません。利用できた地域と系列の方向を説明可能なルールで統合しています。")


def render_price_vs_fundamentals(
    sox_prices: pd.Series | None,
    pulse: dict[str, object],
) -> dict[str, object]:
    market = calculate_market_momentum(
        pd.Series(dtype=float) if sox_prices is None else sox_prices
    )
    result = classify_price_vs_fundamentals(market, pulse)
    st.markdown("#### Price vs Fundamentals")
    st.metric("SOX × Global Demand", str(result["state"]))
    st.write(str(result["message"]))
    returns = market.get("returns", {})
    columns = st.columns(3)
    for column, months in zip(columns, (1, 3, 6)):
        value = returns.get(months)
        column.metric(f"SOX {months}か月", "—" if value is None else f"{value:+.1f}%")
    with st.expander("株価と実需の根拠を見る"):
        for region, region_result in pulse.get("regions", {}).items():
            observations = region_result.get("observations_used", [])
            st.markdown(f"**{region}: {region_result.get('state', 'Unavailable')}**")
            for observation in observations:
                value = observation.get("value")
                value_text = "—" if value is None else f"{float(value):+.1f}%"
                st.caption(f"{observation.get('label')}: {value_text}（{observation.get('basis', '前年比')}）")
    st.caption("同方向・乖離を整理する説明表示で、割安・バブル・売買判断を示しません。")
    return result


def render_overseas_historical_validation(
    overseas_data: pd.DataFrame,
    asset_prices: dict[str, pd.Series],
) -> None:
    st.markdown("##### 海外統計の公表日基準検証")
    strict = build_overseas_validation_signals(overseas_data, strict=True)
    provisional = build_overseas_validation_signals(overseas_data, strict=False)
    if not strict.empty and asset_prices:
        st.markdown("###### 厳密検証（実際のrelease_dateのみ）")
        _render_validation_controls(strict, asset_prices, "strict")
    else:
        st.info("厳密検証に利用できる公表日付き月次履歴が不足しています。速報は長期検証へ使用しません。")
    with st.expander("暫定検証を見る（推定利用可能日・改定後データ）"):
        st.warning("暫定検証：公表日不明の観測には対象月の2か月後月初を利用可能日として付与しています。公式公表日ではなく、厳密検証と混在させていません。")
        if provisional.empty or not asset_prices:
            st.caption("暫定検証に利用できる履歴がありません。")
        else:
            _render_validation_controls(provisional, asset_prices, "provisional")


def _render_validation_controls(
    signals: pd.DataFrame,
    asset_prices: dict[str, pd.Series],
    key_suffix: str,
) -> None:
    st.caption(
        f"利用可能日: {signals.index.min():%Y-%m-%d}〜{signals.index.max():%Y-%m-%d}｜"
        f"利用可能日数: {len(signals)}"
    )
    signal_name = st.selectbox("経済指標", list(signals), key=f"overseas_validation_signal_{key_suffix}")
    asset_name = st.selectbox("市場系列", list(asset_prices), key=f"overseas_validation_asset_{key_suffix}")
    signal = pd.to_numeric(signals[signal_name], errors="coerce")
    correlation = analyze_release_aware_correlation(signal, asset_prices[asset_name])
    correlation_display = correlation.copy()
    correlation_display["相関"] = correlation_display["相関"].map(
        lambda value: "—" if pd.isna(value) else f"{float(value):+.2f}"
    )
    st.markdown("**公表後リード・ラグ相関**")
    st.dataframe(correlation_display, hide_index=True, width="stretch")
    conditions = {
        f"{signal_name}: YoY > 0": signal > 0,
        f"{signal_name}: YoYが前回より改善": signal > signal.shift(1),
        f"{signal_name}: YoY > +20%": signal > 20,
    }
    enriched = add_global_condition_signals(signals)
    for condition_name in (
        "Taiwan Improving",
        "Korea Improving",
        "Taiwan AND Korea Improving",
        "Taiwan AND Korea AND Japan Improving",
    ):
        if condition_name in enriched:
            conditions[condition_name] = enriched[condition_name]
    condition_name = st.selectbox("条件", list(conditions), key=f"overseas_validation_condition_{key_suffix}")
    result = analyze_release_aware_returns(conditions[condition_name], asset_prices[asset_name])
    display = result.copy()
    for column in ("平均", "中央値", "上昇確率", "25%点", "75%点", "最悪値", "最良値"):
        display[column] = display[column].map(lambda value: "—" if pd.isna(value) else f"{value:+.1f}%")
    st.dataframe(display[["期間", "平均", "中央値", "上昇確率", "サンプル数", "注意"]], hide_index=True, width="stretch")
    with st.expander("分布の詳細を見る"):
        st.dataframe(display[["期間", "25%点", "75%点", "最悪値", "最良値", "サンプル数"]], hide_index=True, width="stretch")


def render_global_demand(
    taiwan_data: pd.DataFrame,
    korea_data: pd.DataFrame,
    taiwan_error: str | None = None,
    korea_error: str | None = None,
) -> None:
    """台湾の受注と韓国の出荷を、部分障害を許容して表示する。"""
    st.markdown("#### Global Demand")
    st.caption("台湾は海外から台湾企業への『受注』、韓国は通関ベースの『輸出額』です。注文と実際の出荷を同一指標として扱いません。")
    if taiwan_error:
        st.warning(f"Taiwan Orders: 一時取得失敗。韓国・日本・市場データは引き続き表示します: {taiwan_error}")
    else:
        _render_taiwan_orders(taiwan_data)
    if korea_error:
        st.warning(f"Korea Exports: 一時取得失敗。台湾・日本・市場データは引き続き表示します: {korea_error}")
    else:
        _render_korea_exports(korea_data)


def _render_taiwan_orders(frame: pd.DataFrame) -> None:
    st.markdown("##### Taiwan Orders")
    if frame.empty:
        st.info("台湾輸出受注データがありません。")
        return
    summary = summarize_global_demand(frame)
    display = summary[["series_name", "value", "yoy", "three_month_average", "three_month_average_yoy", "six_month_momentum", "reference_period"]].copy()
    display.columns = ["系列", "最新受注額", "前年比", "3か月平均", "3か月平均前年比", "3〜6か月モメンタム", "対象月"]
    display["最新受注額"] = display["最新受注額"].map(lambda value: f"{value:,.0f} 百万USD")
    for column in ("前年比", "3か月平均前年比", "3〜6か月モメンタム"):
        display[column] = display[column].map(_format_percent)
    display["3か月平均"] = display["3か月平均"].map(lambda value: "—" if pd.isna(value) else f"{value:,.0f}")
    display["対象月"] = pd.to_datetime(display["対象月"]).dt.strftime("%Y-%m")
    st.dataframe(display, hide_index=True, width="stretch")
    with st.expander("台湾輸出受注の推移を見る"):
        figure = go.Figure()
        for series_id, group in frame.groupby("series_id"):
            group = group.sort_values("reference_period").tail(36)
            figure.add_trace(go.Scatter(x=group["reference_period"], y=group["yoy"], mode="lines", name=str(group.iloc[-1]["series_name"])))
        figure.add_hline(y=0, line_color="gray", line_width=1)
        figure.update_layout(height=340, margin=dict(l=20, r=20, t=20, b=40), yaxis_title="前年比（%）", xaxis_title="対象月", legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(figure, width="stretch")
    latest = frame.sort_values("reference_period").iloc[-1]
    fetched = _format_timestamp(latest["fetched_at"])
    st.caption(f"対象月: {latest['reference_period']:%Y-%m}｜公表日: 公式履歴なし｜取得日時: {fetched}。前年比・移動平均・モメンタムは当アプリ計算値です。外銷訂單は台湾からの実輸出額ではなく、海外生産分を含み得る受注統計です。")
    st.markdown(f"データ出所: [台湾経済部 統計処 外銷訂單統計]({latest['source_url']})")


def _render_korea_exports(frame: pd.DataFrame) -> None:
    st.markdown("##### Korea Exports")
    if frame.empty:
        st.info("韓国半導体輸出データがありません。")
        return
    missing_periods = frame.attrs.get("missing_periods", [])
    if missing_periods:
        labels = {
            "1_10": "1–10日速報",
            "1_20": "1–20日速報",
            "monthly": "月次",
        }
        missing_text = "、".join(labels.get(kind, kind) for kind in missing_periods)
        st.warning(
            f"韓国半導体輸出は {missing_text} を取得できませんでした。"
            "取得済みの公式区分だけを表示します。"
        )
    official = frame[~frame["is_derived"]].copy().sort_values("period_end")
    display = official[["series_name", "value", "yoy", "period_start", "period_end", "release_date", "working_days", "publication_stage"]].copy()
    display.columns = ["区分", "輸出額", "前年比", "期間開始", "期間終了", "公表日", "営業日数", "公表段階"]
    display["輸出額"] = display["輸出額"].map(lambda value: f"{value:,.0f} 百万USD")
    display["前年比"] = display["前年比"].map(_format_percent)
    for column in ("期間開始", "期間終了", "公表日"):
        display[column] = pd.to_datetime(display[column]).dt.strftime("%Y-%m-%d").fillna("不明")
    display["営業日数"] = display["営業日数"].map(lambda value: "—" if pd.isna(value) else f"{value:g}日")
    display["公表段階"] = display["公表段階"].map({"preliminary_partial": "速報", "preliminary_monthly": "月次暫定", "final_monthly": "月次確定"}).fillna(display["公表段階"])
    st.dataframe(display, hide_index=True, width="stretch")
    derived = frame[frame["is_derived"]]
    if not derived.empty:
        with st.expander("営業日調整を見る（Derived / 当アプリ計算値）"):
            derived_display = derived[["series_name", "value", "yoy", "working_days"]].copy()
            derived_display.columns = ["区分", "1営業日当たり輸出", "営業日調整後前年比", "当年営業日数"]
            derived_display["1営業日当たり輸出"] = derived_display["1営業日当たり輸出"].map(lambda value: f"{value:,.1f} 百万USD")
            derived_display["営業日調整後前年比"] = derived_display["営業日調整後前年比"].map(_format_percent)
            st.dataframe(derived_display, hide_index=True, width="stretch")
            st.caption("当年・前年同期の営業日数が公式発表から両方取得できた場合だけ表示します。公式公表値ではなく、公式輸出額・前年比・営業日数からの当アプリ計算値です。")
    else:
        st.caption("営業日調整値なし：前年同期を含む公式営業日数が揃わないため推計していません。")
    latest = official.iloc[-1]
    st.caption(f"最新対象期間: {latest['period_start']:%Y-%m-%d}〜{latest['period_end']:%Y-%m-%d}｜公表日: {_format_date(latest['release_date'])}｜取得日時: {_format_timestamp(latest['fetched_at'])}。輸出金額は数量×価格であり、数量需要だけを示しません。速報値は月次確報ではありません。")
    sources = official[["source_name", "source_url"]].drop_duplicates()
    source_links = " / ".join(
        f"[{row.source_name}]({row.source_url})" for row in sources.itertuples()
    )
    st.markdown(f"データ出所: {source_links}")


def _market_direction(snapshot: pd.DataFrame, name: str) -> dict[str, object]:
    row = snapshot[snapshot["指標"] == name]
    if row.empty or pd.isna(row.iloc[0]["1か月変化"]):
        return {"direction": "→", "status": "Unavailable", "evidence": []}
    change = float(row.iloc[0]["1か月変化"])
    if change >= 5:
        return {"direction": "↑", "status": "Strong", "evidence": [f"1か月変化が{change:+.1f}%"]}
    if change > 0:
        return {"direction": "↑", "status": "Improving", "evidence": [f"1か月変化が{change:+.1f}%"]}
    if change <= -5:
        return {"direction": "↓", "status": "Weakening", "evidence": [f"1か月変化が{change:+.1f}%"]}
    return {"direction": "→", "status": "Mixed", "evidence": [f"1か月変化が{change:+.1f}%"]}


def _format_percent(value: object) -> str:
    return "—" if pd.isna(value) else f"{float(value):+.1f}%"


def _format_date(value: object) -> str:
    timestamp = pd.to_datetime(value, errors="coerce")
    return "不明" if pd.isna(timestamp) else f"{timestamp:%Y-%m-%d}"


def _format_timestamp(value: object) -> str:
    timestamp = pd.to_datetime(value, errors="coerce")
    return "不明" if pd.isna(timestamp) else f"{timestamp:%Y-%m-%d %H:%M}"
