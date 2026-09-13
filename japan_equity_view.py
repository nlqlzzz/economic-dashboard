from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from japan_equity import CORE_20, build_core_snapshot, expected_proxy_names, top_observed_correlations
from stock_detail import build_stock_detail_analysis
from fundamentals import (build_annual_forecast_series, build_fundamentals_cards,
    build_fundamentals_summary, chart_axis_ticks, format_eps, format_financial_value,
    format_jpy, format_yoy)
from jquants_loader import JQuantsConfigurationError, fetch_financial_summaries, normalize_financial_summaries


JAPAN_SELECTED_TICKER_KEY = "japan_selected_ticker"
JAPAN_STOCK_SECTION_ORDER = ("業績", "評価水準", "価格の反応", "リスク・確認事項", "補助分析")


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
    st.markdown("## 日本株分析")
    st.caption(
        "Core20から銘柄を一つ選び、業績 → 評価水準 → 価格の反応 → リスクの順に確認します。"
        "市場・マクロ・残差・同業比較は補助分析としてまとめています。"
    )
    ticker = _render_stock_selector()
    detail_tab, list_tab = st.tabs(["銘柄分析", "Core20一覧"])
    with detail_tab:
        _render_stock_detail(
            ticker, market_map, sensitivity, prices, macro_series, topix_quality
        )
    with list_tab:
        st.caption("一覧は銘柄選びと市場内比較のための補助表示です。個別分析の銘柄は上の選択欄で変更します。")
        if market_map.empty:
            st.info("Core20の価格一覧は取得できません。個別銘柄の決算情報は銘柄分析で確認できます。")
        else:
            _render_snapshot(market_map)
            _render_market_map(market_map)
            _render_aggregates(sector_summary, theme_summary)

    failures = [*(stock_failures or []), *(macro_failures or [])]
    if failures:
        with st.expander("取得できなかった系列を見る"):
            for failure in failures:
                st.warning(failure)


def core20_stock_options() -> list[dict[str, str]]:
    """Return stable selector options, including stocks whose price is unavailable."""
    return [
        {
            "ticker": str(stock["ticker"]),
            "label": f"{stock['name']}（{stock['code']}）",
        }
        for stock in CORE_20
    ]


def _render_stock_selector() -> str:
    options = core20_stock_options()
    tickers = [option["ticker"] for option in options]
    labels = {option["ticker"]: option["label"] for option in options}
    if st.session_state.get(JAPAN_SELECTED_TICKER_KEY) not in tickers:
        st.session_state[JAPAN_SELECTED_TICKER_KEY] = tickers[0]
    return st.selectbox(
        "分析する銘柄",
        tickers,
        format_func=lambda value: labels[value],
        key=JAPAN_SELECTED_TICKER_KEY,
        help="この選択は業績・価格・リスク・補助分析で共通です。画面を移動しても維持されます。",
    )


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
        status_counts = market_map.loc[~market_map["status"].eq("Available"), "status"].value_counts()
        detail = " / ".join(f"{name} {count}社" for name, count in status_counts.items())
        st.caption(f"分析可能 {snapshot['available']}/20社｜除外 {snapshot['unavailable']}社（{detail}）")
    quality_rows = market_map[market_map.get("quality_status", pd.Series(index=market_map.index, dtype=str)).isin(["cleaned", "blocked"])]
    if not quality_rows.empty:
        with st.expander("価格品質の処理を見る"):
            for _, row in quality_rows.iterrows():
                st.caption(f"{row['name']}: {row.get('quality_reason') or row.get('quality_status')}")


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


def _render_macro_sensitivity(ticker: str, sensitivity: dict[str, pd.DataFrame]) -> None:
    st.markdown("#### Macro Sensitivity")
    st.caption(
        "Market Exposureと、市場共通要因を除いたPrimary Driverとの同時点の関係を分けて確認します。"
        "米国市場と日本株の同日終値は、日本市場の判断時点では利用できない事後的な連動性です。"
        "先行性・因果関係・予測力・売買成績を示すものではありません。"
    )
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
    ticker: str,
    market_map: pd.DataFrame,
    sensitivity: dict[str, pd.DataFrame],
    prices: pd.DataFrame | None,
    macro_series: dict[str, pd.Series] | None,
    topix_quality: object | None,
) -> None:
    stock = next(item for item in CORE_20 if item["ticker"] == ticker)
    price_frame = prices if prices is not None else pd.DataFrame()
    selected_prices = (
        price_frame[ticker] if ticker in price_frame else pd.Series(dtype=float)
    )
    effective_topix_quality = topix_quality or inspect_price_series(pd.Series(dtype=float))
    detail = build_stock_detail_analysis(
        stock,
        selected_prices,
        effective_topix_quality,
        macro_series or {},
        CORE_20,
        price_frame,
        shared_macro_analysis=sensitivity,
        fundamentals=_load_fundamentals(str(stock["code"]), str(stock["ticker"]), str(stock["name"]), str(stock["sector"])),
    )
    market_row = _selected_row(market_map, ticker)
    _render_stock_header(detail, market_row, selected_prices)

    st.divider()
    _render_fundamentals(detail)

    st.divider()
    _render_valuation()

    st.divider()
    _render_price_reaction(detail)

    st.divider()
    _render_risks(detail, market_row)

    st.divider()
    st.markdown("#### 補助分析")
    st.caption("市場感応度・マクロ要因・市場調整後リターン・Core20内の比較を、必要なときに確認します。")
    with st.expander("補助分析を見る", expanded=False):
        _render_stock_market_exposure(detail)
        _render_stock_drivers(detail)
        _render_stock_anchors(detail)
        _render_stock_specific_move(detail)
        _render_stock_diagnostics(detail, inline=True)


def _render_stock_header(
    detail: dict[str, object],
    market_row: dict[str, object] | None,
    prices: pd.Series,
) -> None:
    stock = detail["stock"]
    clean_prices = pd.to_numeric(prices, errors="coerce").dropna().sort_index()
    price_date = clean_prices.index[-1].strftime("%Y-%m-%d") if not clean_prices.empty else "—"
    fundamentals = detail["fundamentals"]
    latest = fundamentals.get("latest_period", {}) if fundamentals.get("status") == "Available" else {}
    st.markdown(f"### {stock['name']}（{stock['code']}）")
    st.caption(f"{stock['sector']} ｜ 価格基準日 {price_date} ｜ Yahoo Finance 調整後終値")
    status_items = build_stock_status_items(detail, market_row)
    st.markdown("　｜　".join(f"**{label}:** {value}" for label, value in status_items))
    if latest:
        st.caption(
            f"最新決算 {latest.get('fiscal_year')} {latest.get('fiscal_quarter')} ｜ "
            f"開示日 {latest.get('disclosure_date')}"
        )


def build_stock_status_items(
    detail: dict[str, object], market_row: dict[str, object] | None
) -> list[tuple[str, str]]:
    fundamentals = detail.get("fundamentals", {})
    price_status = str((market_row or {}).get("status") or "Unavailable")
    return [
        ("株価", _ui_state(price_status)),
        ("決算", "利用可" if fundamentals.get("status") == "Available" else "利用不可"),
        ("現在値", _price(detail.get("performance", {}).get("current"))),
    ]


def _render_valuation() -> None:
    st.markdown("#### ② 評価水準")
    st.info(
        "評価水準は未評価です。対象期・株式数・株式分割の整合を確認できるPER/PBR等がないため、"
        "株価上昇率やTOPIX比で割安・割高を代用しません。"
    )


def build_price_reaction_rows(detail: dict[str, object]) -> list[dict[str, str]]:
    performance = detail.get("performance", {})
    quality = detail.get("quality")
    prices = quality.series if quality is not None and quality.usable else pd.Series(dtype=float)
    rows: list[dict[str, str]] = []
    for months, label in ((1, "1か月"), (3, "3か月"), (6, "6か月")):
        absolute_start, absolute_end = _calendar_period_dates(prices, months)
        rows.append({
            "期間": label,
            "絶対リターン": _percent(performance.get(f"return_{months}m")),
            "TOPIX比": _point(performance.get(f"relative_{months}m")),
            "絶対開始日": _date_text(absolute_start),
            "絶対終了日": _date_text(absolute_end),
            "相対開始日": _date_text(performance.get(f"relative_{months}m_start")),
            "相対終了日": _date_text(performance.get(f"relative_{months}m_end")),
        })
    return rows


def _render_price_reaction(detail: dict[str, object]) -> None:
    st.markdown("#### ③ 価格の反応")
    st.caption("絶対リターンとTOPIX連動ETF（1306）比を分けて表示します。業績との因果関係や織り込みを示すものではありません。")
    quality = detail["quality"]
    if not quality.usable:
        st.warning(f"価格分析を表示できません：{quality.reason or '価格品質を確認できません。'}")
        return
    clean = pd.to_numeric(quality.series, errors="coerce").dropna().sort_index()
    if not clean.empty:
        chart = clean.loc[clean.index >= clean.index[-1] - pd.DateOffset(years=1)]
        figure = go.Figure(go.Scatter(x=chart.index, y=chart, mode="lines", name="調整後終値"))
        figure.update_layout(
            height=260, margin={"l": 15, "r": 10, "t": 15, "b": 25},
            yaxis_title="円", xaxis_title=None, showlegend=False,
        )
        st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
    rows = build_price_reaction_rows(detail)
    for row in rows[:2]:
        st.markdown(f"**{row['期間']}**　{row['絶対リターン']}　｜　TOPIX比 {row['TOPIX比']}")
        st.caption(
            f"絶対: {row['絶対開始日']} → {row['絶対終了日']} ｜ "
            f"TOPIX比の共通期間: {row['相対開始日']} → {row['相対終了日']}"
        )
    with st.expander("6か月・短期騰落率を見る"):
        row = rows[2]
        st.markdown(f"**{row['期間']}**　{row['絶対リターン']}　｜　TOPIX比 {row['TOPIX比']}")
        st.caption(
            f"絶対: {row['絶対開始日']} → {row['絶対終了日']} ｜ "
            f"TOPIX比の共通期間: {row['相対開始日']} → {row['相対終了日']}"
        )
        performance = detail["performance"]
        st.write(f"1日 {_percent(performance.get('return_1d'))}　｜　5日 {_percent(performance.get('return_5d'))}　｜　1年 {_percent(performance.get('return_1y'))}")


def build_risk_items(
    detail: dict[str, object], market_row: dict[str, object] | None
) -> dict[str, list[str]]:
    data_limits: list[str] = []
    investment_checks: list[str] = []
    quality = detail.get("quality")
    if quality is not None and quality.status != "ok":
        data_limits.append(f"価格品質: {quality.reason or quality.status}")
    market_status = str((market_row or {}).get("status") or "Unavailable")
    if market_status != "Available":
        data_limits.append(f"価格分析の状態: {_ui_state(market_status)}")
    fundamentals = detail.get("fundamentals", {})
    if fundamentals.get("status") != "Available":
        data_limits.append("決算情報を取得できないため、業績リスクは未評価です。")
    else:
        momentum = str(fundamentals.get("momentum", "Unavailable"))
        if momentum == "Weakening":
            investment_checks.append("比較可能な最新決算では業績の弱含みが確認されています。")
        elif momentum in {"Mixed", "Unavailable"}:
            data_limits.append("業績の方向は混在または比較不能で、単一方向に評価できません。")
        forecast = fundamentals.get("forecast")
        if not isinstance(forecast, pd.DataFrame) or forecast.empty:
            data_limits.append("比較可能な会社予想を取得できません。")
    exposure = detail.get("market_exposure", {})
    beta = exposure.get("market_beta_252d") if exposure.get("status") == "Available" else None
    if beta is None:
        data_limits.append("市場感応度は履歴または比較条件不足のため未評価です。")
    elif float(beta) >= 1.8:
        investment_checks.append("市場より値動きが大きい傾向が確認されています。")
    if not investment_checks:
        investment_checks.append("現在の取得データだけで低リスクとは判断できません。")
    return {"data_limits": data_limits, "investment_checks": investment_checks}


def _render_risks(detail: dict[str, object], market_row: dict[str, object] | None) -> None:
    st.markdown("#### ④ リスク・確認事項")
    items = build_risk_items(detail, market_row)
    st.markdown("**投資判断上の確認事項**")
    for item in items["investment_checks"]:
        st.write(f"・{item}")
    if items["data_limits"]:
        st.markdown("**データ上の制約**")
        for item in items["data_limits"]:
            st.write(f"・{item}")
    st.caption("データ不足は低リスクを意味しません。表示は売買判断や株価予測ではありません。")


@st.cache_data(ttl=21600, show_spinner=False)
def _load_fundamentals(code: str, ticker: str, name: str, sector: str) -> dict[str, object]:
    try:
        loaded = fetch_financial_summaries([code])
        records = normalize_financial_summaries(loaded.records, ticker_by_code={code: ticker}, company_by_code={code: name}, fetched_at=loaded.fetched_at)
        return build_fundamentals_summary(records, sector)
    except JQuantsConfigurationError:
        return {"status": "Unavailable", "reason": "J-Quants API Keyが未設定です。"}
    except Exception:
        return {"status": "Unavailable", "reason": "Fundamentalsを一時取得できません。"}


def _render_fundamentals(detail: dict[str, object]) -> None:
    data = detail["fundamentals"]
    st.markdown("#### ① 業績")
    st.caption("開示済みの実績と、期間が一致する通期会社予想を分けて確認します。")
    if data.get("status") != "Available":
        st.info("取得不可：" + str(data.get("reason", "業績データを取得できません。")))
        return
    st.markdown("**最新決算**　" + str(data["history_status"]))
    cards = build_fundamentals_cards(data)
    for start in range(0, len(cards), 2):
        columns = st.columns(2)
        for column, card in zip(columns, cards[start:start + 2]):
            with column:
                st.markdown(f"**{card['label']}**")
                st.markdown(f"### {card['value']}")
                st.caption(card["yoy"])
    latest = data["latest_period"]
    st.info(f"**業績モメンタム：{_ui_state(data['momentum'])}**\n\n{data.get('momentum_reason', '')}")
    period_kind = "累計/FY開示" if latest.get("fiscal_quarter") in {"Q2", "Q3", "FY"} else "単独四半期"
    st.caption(f"対象期: {latest.get('fiscal_year')} {latest.get('fiscal_quarter')}（{period_kind}） ｜ 開示日: {latest.get('disclosure_date')} ｜ 出典: {data['source']}")
    tabs = st.tabs(["四半期推移", "会社予想", "詳細データ"])
    with tabs[0]:
        history = data["history"].copy()
        if len(history) < 4:
            st.info("履歴不足：推移は4四半期以上で表示します。")
        else:
            history["期"] = history["fiscal_year"].astype(str) + " " + history["fiscal_quarter"].astype(str)
            for metric, label in (("revenue", "売上高等"), ("net_income", "純利益"), ("eps", "EPS"), ("operating_profit", "営業利益")):
                series = history[history.metric.eq(metric)][["期", "value", "unit"]].dropna(subset=["value"])
                if len(series) >= 4:
                    eps_note = "（開示された累計・通期EPS。単独四半期への差分導出はしません）" if metric == "eps" else "（単独四半期・実績）"
                    st.caption(label + eps_note)
                    _render_actual_chart(series, metric)
                    annual = build_annual_forecast_series(data, metric)
                    if not annual.empty and annual["会社予想"].notna().any():
                        st.caption("通期実績・会社予想（同じFiscal Yearのみ）")
                        _render_annual_forecast_chart(annual, metric)
    with tabs[1]:
        forecast = data["forecast"]
        if forecast.empty:
            st.info("会社予想は取得できません。")
        else:
            labels = {"forecast_revenue": "会社予想 売上高等", "forecast_net_income": "会社予想 純利益", "forecast_eps": "会社予想 EPS", "forecast_operating_profit": "会社予想 営業利益"}
            for _, row in forecast.iterrows():
                value = format_financial_value(row["value"], str(row["metric"]).replace("forecast_", ""), row.get("unit"))
                st.write(f"**{labels.get(row['metric'], row['metric'])}**　{value}")
            st.caption(f"対象年度: {forecast.iloc[0].get('fiscal_year')} ｜ 開示日: {forecast.iloc[0].get('disclosure_date')}。四半期実績の次期値としては扱いません。")
    with tabs[2]:
        with st.expander("詳細データ・出所・導出方法を見る"):
            history = data["history"].copy()
            if not history.empty:
                history["前年比"] = history["yoy"].map(format_yoy)
                history["比較"] = history["comparison"]
                st.dataframe(history[["metric", "fiscal_year", "fiscal_quarter", "value", "比較", "前年比", "is_derived", "disclosure_date"]], hide_index=True, width="stretch")
            st.caption("is_derived=true は売上・利益の累計開示から安全に導出した単独四半期です。EPSは差分導出しません。")


def _render_stock_snapshot(detail: dict[str, object]) -> None:
    stock = detail["stock"]
    st.markdown("##### 銘柄概要")
    st.markdown(f"### {stock['name']}（{stock['code']}）")
    st.markdown(
        f"{stock['sector']}　｜　**現在値 {_price(detail['performance'].get('current'))}**"
    )
    st.caption("テーマ: " + " / ".join(stock["macro_themes"]))
    st.caption("主なマクロ要因: " + " / ".join(stock["primary_drivers"]))
    quality = detail["quality"]
    if quality.reason:
        st.caption(f"価格品質: {quality.reason}")


def _render_stock_performance(detail: dict[str, object]) -> None:
    performance = detail["performance"]
    st.markdown("##### パフォーマンス")
    st.markdown(
        f"**1M** {_percent(performance.get('return_1m'))}　　"
        f"**3M** {_percent(performance.get('return_3m'))}"
    )
    st.caption(
        f"TOPIX比　1M {_point(performance.get('relative_1m'))}　／　"
        f"3M {_point(performance.get('relative_3m'))}"
    )
    with st.expander("短期・長期パフォーマンスを見る"):
        st.markdown(
            f"**1D** {_percent(performance.get('return_1d'))}　　"
            f"**5D** {_percent(performance.get('return_5d'))}"
        )
        st.markdown(
            f"**6M** {_percent(performance.get('return_6m'))}　　"
            f"**1Y** {_percent(performance.get('return_1y'))}"
        )
        st.caption(f"TOPIX比　6M {_point(performance.get('relative_6m'))}")


def _render_stock_market_exposure(detail: dict[str, object]) -> None:
    exposure = detail["market_exposure"]
    st.markdown("##### 市場感応度")
    st.caption("市場全体との連動度を確認します。マクロ要因の分析とは別レイヤーです。")
    if exposure.get("status") != "Available":
        st.info(f"利用不可：{exposure.get('reason', '市場調整後分析を計算できません。')}")
        return
    metrics = st.columns(2)
    metrics[0].metric("市場ベータ（252日）", _number(exposure.get("market_beta_252d")))
    metrics[1].metric("市場ベータ（120日）", _number(exposure.get("market_beta_120d")))
    metrics = st.columns(2)
    metrics[0].metric("TOPIX相関（252日）", _correlation(exposure.get("topix_correlation_252d")))
    metrics[1].metric("ベータ安定性", _ui_state(exposure.get("beta_stability", "Unavailable")))
    beta = exposure.get("market_beta_252d")
    if beta is not None:
        if float(beta) >= 1.8:
            st.caption("市場より値動きが大きい傾向です。固定的な投資評価ではありません。")
        elif float(beta) < 0.5:
            st.caption("市場感応度が低い傾向です。固定的な投資評価ではありません。")


def _render_stock_drivers(detail: dict[str, object]) -> None:
    st.markdown("##### マクロ要因")
    st.caption("市場調整後リターン（Residual）と、事前定義した要因の同時点の関係です。")
    for row in detail["primary_drivers"]:
        with st.container(border=True):
            st.markdown(f"**{row['driver']}**")
            if _missing(row.get("proxy")):
                st.caption("実データProxy：未設定。このDriverは現在、定量的なMacro Sensitivity分析の対象外です。")
            else:
                st.caption(f"Proxy: {row['proxy']}")
            if row.get("status") != "Available":
                st.write(f"利用不可｜{row.get('reason', 'データ不足')}")
                continue
            st.metric("120日 Residual相関", _correlation(row.get("correlation_120d")))
            st.write(f"60D {_correlation(row.get('correlation_60d'))}　/　20D {_correlation(row.get('correlation_20d'))}")
            st.caption(f"安定性: {_ui_state(row.get('stability'))}｜{row.get('reason')}")
    explanation = detail["explainability"]
    st.markdown("##### マクロ説明力")
    st.markdown(f"### {_ui_state(explanation.get('classification', 'Unavailable'))}")
    st.caption(str(explanation.get("reason", "")))


def _render_stock_anchors(detail: dict[str, object]) -> None:
    st.markdown("##### Core20 Anchorとの比較")
    st.caption("共通テーマ・共通マクロ要因・セクターをもつ参照銘柄と比較します。")
    anchors = detail["anchors"]
    if not anchors:
        st.info("比較可能なAnchorなし：比較根拠が十分に強いCore20参照銘柄がありません。")
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
    st.markdown("##### 個別要因・説明しきれない値動き")
    residual = detail["residual_periods"]
    metrics = st.columns(3)
    metrics[0].metric("市場調整後 5日", _percent(residual.get("residual_5d")))
    metrics[1].metric("市場調整後 1か月", _percent(residual.get("residual_1m")))
    metrics[2].metric("市場調整後 3か月", _percent(residual.get("residual_3m")))
    st.caption("市場・マクロ等では説明しきれない値動きの大きさを確認します。企業固有要因を断定するものではありません。")
    movement = detail["movement"]
    st.markdown(f"### 判定: {movement['classification']}")
    st.caption(movement["reason"])
    st.markdown("##### 解釈・次に確認すること")
    st.caption(detail["next_analysis"])


def _render_stock_diagnostics(detail: dict[str, object], *, inline: bool = False) -> None:
    if inline:
        st.markdown("##### 観測後相関・回帰の詳細")
        _render_stock_diagnostic_content(detail)
        return
    with st.expander("観測後相関・回帰の詳細を見る"):
        _render_stock_diagnostic_content(detail)


def _render_stock_diagnostic_content(detail: dict[str, object]) -> None:
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


def _render_actual_chart(series: pd.DataFrame, metric: str) -> None:
    unit = series["unit"].iloc[0] if "unit" in series and not series.empty else None
    formatter = lambda value: format_financial_value(value, metric, unit)
    figure = go.Figure(go.Scatter(
        x=series["期"], y=series["value"], name="実績", mode="lines+markers",
        line={"color": "#4da3ff"}, marker={"symbol": "circle", "size": 8},
        customdata=[formatter(value) for value in series["value"]],
        hovertemplate="%{x}<br>実績: %{customdata}<extra></extra>",
    ))
    figure.update_layout(**_chart_layout(series["value"], metric, unit))
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})


def _render_annual_forecast_chart(series: pd.DataFrame, metric: str) -> None:
    unit = series["unit"].dropna().iloc[0] if "unit" in series and series["unit"].notna().any() else None
    formatter = lambda value: format_financial_value(value, metric, unit)
    figure = go.Figure()
    for column, name, dash, symbol, color in (
        ("実績", "実績", "solid", "circle", "#4da3ff"),
        ("会社予想", "会社予想", "dash", "circle-open", "#f0b429"),
    ):
        values = series[column]
        figure.add_trace(go.Scatter(
            x=series["期"], y=values, name=name, mode="lines+markers",
            connectgaps=False, line={"dash": dash, "color": color},
            marker={"symbol": symbol, "size": 9, "line": {"width": 2, "color": color}},
            customdata=[formatter(value) if pd.notna(value) else "—" for value in values],
            hovertemplate=f"%{{x}}<br>{name}: %{{customdata}}<extra></extra>",
        ))
    figure.update_layout(**_chart_layout(pd.concat([series["実績"], series["会社予想"]]), metric, unit))
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})


def _chart_layout(values: pd.Series, metric: str, unit: object = None) -> dict[str, object]:
    ticks = chart_axis_ticks(values, metric, unit)
    return {
        "height": 280, "margin": {"l": 22, "r": 12, "t": 18, "b": 38},
        "legend": {"orientation": "h", "y": -0.22},
        "yaxis": {"tickvals": ticks["tickvals"], "ticktext": ticks["ticktext"], "automargin": True},
        "xaxis": {"title": None, "tickangle": -30},
        "hovermode": "x unified",
    }


def _ui_state(value: object) -> str:
    labels = {
        "Strong": "強い", "Improving": "改善", "Mixed": "まちまち", "Weakening": "弱含み",
        "Unavailable": "利用不可", "Available": "利用可", "High": "高い", "Medium": "中程度",
        "Low": "低い", "Macro-unexplained": "マクロで説明しにくい", "Stable": "安定", "Unstable": "不安定",
        "Quality Blocked": "品質上利用不可", "History Limited": "履歴不足", "Stale": "更新要確認",
    }
    return labels.get(str(value), str(value))


def _date_text(value: object) -> str:
    if value is None or pd.isna(value):
        return "—"
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _calendar_period_dates(
    series: pd.Series, months: int
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    if clean.empty:
        return None, None
    end = pd.Timestamp(clean.index[-1])
    candidates = clean.loc[clean.index <= end - pd.DateOffset(months=months)]
    if candidates.empty:
        return None, end
    return pd.Timestamp(candidates.index[-1]), end


def _missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
