from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from streamlit_local_storage import LocalStorage

from data_loader import load_data, load_indicator_data, load_meti_semiconductor_iip
from data_status import build_data_status_frame
from economic_calendar import (
    OFFICIAL_SCHEDULE_URLS,
    build_us_economic_events,
    calendar_display_frame,
    latest_event_results,
)
from event_analysis import (
    EVENT_ASSET_DEFINITIONS,
    EVENT_HISTORY,
    EVENT_SOURCE_URLS,
    analyze_event_reactions,
)
from indicators import DATA_SOURCE_LABELS, INDICATORS
from japan_semiconductor_cycle import (
    semiconductor_iip_trends,
    summarize_semiconductor_iip,
)
from macro_regime import (
    assess_us_macro_regime,
    build_macro_focus_guide,
    build_us_macro_assessment_history,
    build_us_macro_trends,
)
from market_alerts import detect_market_moves
from market_hypotheses import build_market_factor_hypotheses
from market_stress import (
    STRESS_INPUT_INDICATORS,
    calculate_market_stress,
)
from market_summary import build_market_summary
from theme_view import (
    THEME_DEFINITIONS,
    build_theme_snapshot,
    relative_strength,
    upcoming_theme_events,
)
from regime_returns import (
    REGIME_ASSET_DEFINITIONS,
    analyze_regime_forward_performance,
    current_regime_labels,
)
from similar_periods import (
    SIMILAR_ASSET_DEFINITIONS,
    SIMILAR_FEATURE_DEFINITIONS,
    build_point_in_time_features,
    find_similar_periods,
)
from correlation_analysis import (
    build_correlation_frame,
    build_daily_change_frame,
    correlation_change_alerts,
    correlation_change_summary,
    correlation_pairs,
    linear_regression_summary,
    rolling_correlation,
)

from utils import change_from_previous, calc_yoy, latest_value, normalize, percent_change_since
from watchlist_storage import dump_watchlists, load_watchlists


def load_market_stress_context(start_date: str) -> dict[str, object]:
    """Market Stress Scoreと要因仮説で共有する系列・診断結果を取得する。"""
    series: dict[str, pd.Series] = {}
    load_errors: list[str] = []
    fallbacks: list[str] = []
    for indicator_name in STRESS_INPUT_INDICATORS:
        try:
            indicator_series = load_indicator_data(
                INDICATORS[indicator_name], start_date
            )
            series[indicator_name] = indicator_series
            if indicator_series.attrs.get("is_fallback"):
                fallbacks.append(
                    f"{indicator_name}: {indicator_series.attrs['fallback_label']}"
                    f"（{indicator_series.attrs['ticker']}）"
                )
        except Exception as error:
            load_errors.append(f"{indicator_name}: {error}")
    return {
        "series": series,
        "load_errors": load_errors,
        "fallbacks": fallbacks,
        "result": calculate_market_stress(series),
    }


st.set_page_config(page_title="市場ダッシュボード", layout="wide")
st.markdown(
    """
    <style>
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.75rem;
            padding-right: 0.75rem;
            padding-top: 1rem;
        }
        [data-testid="stAppViewContainer"] h1 {
            font-size: clamp(1.35rem, 6.2vw, 1.7rem);
            line-height: 1.5;
            padding-top: 1.5rem;
            overflow-wrap: anywhere;
        }
        [data-testid="stAppViewContainer"] h2 {
            font-size: 1.35rem;
        }
        [data-testid="stMetric"] {
            min-width: 0;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.25rem;
        }
        [data-baseweb="tab-list"] {
            gap: 0.25rem;
            overflow-x: auto;
            scrollbar-width: thin;
        }
        [data-baseweb="tab"] {
            flex: 0 0 auto;
            padding-left: 0.65rem;
            padding-right: 0.65rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("市場ダッシュボード")
st.caption("FRED と Yahoo Finance の公開データを表示します。")

DISPLAY_SETS: dict[str, set[str]] = {
    "半導体": {
        "SOX指数",
        "キオクシア（285A）",
        "東京エレクトロン（8035）",
        "レーザーテック（6920）",
        "ディスコ（6146）",
        "アドバンテスト（6857）",
    },
    "日本株": {
        "日経平均株価",
        "日経平均先物",
        "キオクシア（285A）",
        "東京エレクトロン（8035）",
        "レーザーテック（6920）",
        "ディスコ（6146）",
        "アドバンテスト（6857）",
        "三菱商事（8058）",
        "三菱UFJ（8306）",
        "三菱重工（7011）",
        "任天堂（7974）",
    },
    "主要国株価指数": {
        "日経平均株価",
        "S&P 500指数",
        "中国：上海総合指数",
        "インド：NIFTY 50",
        "ベトナム：VN-Index",
        "ドイツ：DAX",
        "スペイン：IBEX 35",
        "ポーランド：NASDAQ Poland",
        "メキシコ：S&P/BMV IPC",
        "オーストラリア：S&P/ASX 200",
    },
    "米国セクター": {
        "情報技術（XLK）",
        "金融（XLF）",
        "ヘルスケア（XLV）",
        "一般消費財（XLY）",
        "生活必需品（XLP）",
        "資本財・サービス（XLI）",
        "エネルギー（XLE）",
        "素材（XLB）",
        "公益事業（XLU）",
        "不動産（XLRE）",
        "コミュニケーション・サービス（XLC）",
    },
    "為替": {
        "USD/JPY",
        "EUR/JPY",
        "AUD/JPY",
        "MXN/JPY",
        "CHF/JPY",
        "AUD/MXN",
        "MXN/CHF",
    },
    "金利": {
        "UST 2Y",
        "UST 10Y",
        "UST 30Y",
        "JGB 2Y",
        "JGB 10Y",
        "JGB 30Y",
        "日米金利差 2Y（米国−日本）",
        "日米金利差 10Y（米国−日本）",
        "日米金利差 30Y（米国−日本）",
    },
}

WATCHLIST_STORAGE_KEY = "economic_dashboard_watchlists_v1"
KEY_MARKET_INDICATORS = {
    "CPI",
    "FF金利",
    "失業率",
    "USD/JPY",
    "日経平均株価",
    "S&P 500指数",
    "VIX指数",
    "UST 10Y",
    "JGB 10Y",
}

with st.sidebar:
    st.header("表示設定")
    today = pd.Timestamp.today().normalize()
    period_starts = {
        "年初来": date(today.year, 1, 1),
        "1か月": (today - pd.DateOffset(months=1)).date(),
        "3か月": (today - pd.DateOffset(months=3)).date(),
        "6か月": (today - pd.DateOffset(months=6)).date(),
        "1年": (today - pd.DateOffset(years=1)).date(),
        "3年": (today - pd.DateOffset(years=3)).date(),
        "任意指定": date(2026, 1, 1),
    }
    selected_period = st.selectbox("表示期間", list(period_starts))
    if st.session_state.get("last_selected_period") != selected_period:
        st.session_state["start_date"] = period_starts[selected_period]
    st.session_state["last_selected_period"] = selected_period
    start_date = st.date_input("開始日", max_value=date.today(), key="start_date")
    st.divider()

    selected_names: list[str] = []
    st.caption("表示セット")
    for display_set_name, display_set_indicators in DISPLAY_SETS.items():
        if st.button(
            display_set_name,
            use_container_width=True,
            key=f"display_set_{display_set_name}",
        ):
            for name in INDICATORS:
                st.session_state[f"show_{name}_default_v2"] = (
                    name in display_set_indicators
                )

    browser_storage = LocalStorage(key="watchlist_browser_storage")
    saved_watchlists = load_watchlists(
        browser_storage.getItem(WATCHLIST_STORAGE_KEY), INDICATORS
    )
    with st.expander("保存したウォッチリスト", expanded=bool(saved_watchlists)):
        if not saved_watchlists:
            st.caption("保存済みのウォッチリストはありません。")
        else:
            saved_watchlist_name = st.selectbox(
                "保存済みリスト", list(saved_watchlists), key="saved_watchlist_name"
            )
            saved_left, saved_right = st.columns(2)
            with saved_left:
                if st.button("呼び出す", use_container_width=True):
                    selected_watchlist = set(saved_watchlists[saved_watchlist_name])
                    for name in INDICATORS:
                        st.session_state[f"show_{name}_default_v2"] = (
                            name in selected_watchlist
                        )
            with saved_right:
                if st.button("削除", use_container_width=True):
                    updated_watchlists = dict(saved_watchlists)
                    del updated_watchlists[saved_watchlist_name]
                    browser_storage.setItem(
                        WATCHLIST_STORAGE_KEY,
                        dump_watchlists(updated_watchlists),
                        key="delete_saved_watchlist",
                    )
                    st.success(f"「{saved_watchlist_name}」を削除しました。")

    if st.button("すべてのチェックを外す", use_container_width=True):
        for name in INDICATORS:
            st.session_state[f"show_{name}_default_v2"] = False

    category_order = ["米国経済指標", "マーケット", "米国セクター", "個別株", "為替", "金利"]
    available_categories = dict.fromkeys(info["category"] for info in INDICATORS.values())
    categories = [category for category in category_order if category in available_categories]
    categories.extend(category for category in available_categories if category not in categories)
    for category in categories:
        with st.expander(category, expanded=category == "マーケット"):
            if category == "個別株":
                st.caption(
                    "銘柄を選択し、下の「現在の選択を保存・更新」から任意のウォッチリストとして保存できます。"
                )
            for name, info in INDICATORS.items():
                is_default = name in {"日経平均株価", "S&P 500指数"}
                if info["category"] == category and st.checkbox(name, value=is_default, key=f"show_{name}_default_v2"):
                    selected_names.append(name)

    with st.expander("現在の選択を保存・更新"):
        st.caption(
            "同じ名前で保存すると内容を更新します。保存先は、このブラウザだけです。"
        )
        new_watchlist_name = st.text_input(
            "ウォッチリスト名", max_chars=40, key="new_watchlist_name"
        ).strip()
        if st.button("現在の選択を保存", use_container_width=True):
            if not new_watchlist_name:
                st.warning("ウォッチリスト名を入力してください。")
            elif not selected_names:
                st.warning("保存する指標を一つ以上選んでください。")
            else:
                updated_watchlists = dict(saved_watchlists)
                updated_watchlists[new_watchlist_name] = selected_names
                browser_storage.setItem(
                    WATCHLIST_STORAGE_KEY,
                    dump_watchlists(updated_watchlists),
                    key="save_current_watchlist",
                )
                st.success(f"「{new_watchlist_name}」をブラウザに保存しました。")

if not selected_names:
    st.info("左のメニューから、表示する指標を一つ以上選んでください。")
    st.stop()

normalize_values = st.session_state.get("normalize_values_v2", True)
series_to_plot: dict[str, pd.Series] = {}
errors: list[str] = []

with st.spinner("データを取得しています…"):
    for name in selected_names:
        info = INDICATORS[name]
        try:
            series = load_indicator_data(info, str(start_date))
            source_metadata = dict(series.attrs)
            if info.get("yoy", False):
                series = calc_yoy(series)
            if normalize_values:
                series = normalize(series)
            series.attrs.update(source_metadata)
            series_to_plot[name] = series
            if series.attrs.get("is_fallback"):
                errors.append(
                    f"{name}: 一次データを取得できないため、"
                    f"{series.attrs['fallback_label']}（{series.attrs['ticker']}）を表示しています。"
                )
        except Exception as error:
            errors.append(f"{name}: {error}")

for error in errors:
    st.warning(error)

if not series_to_plot:
    st.error("データを表示できませんでした。ネットワーク接続とティッカーを確認してください。")
    st.stop()

market_tab, event_tab, analysis_tab, theme_tab = st.tabs(
    ["市場概況", "イベント", "分析", "投資テーマ"]
)

with market_tab:
    graph_display_mode = st.radio(
        "グラフ表示",
        ["重ねて表示", "左右の軸", "個別グラフ"],
        horizontal=True,
        key="graph_display_mode",
    )
    right_axis_names: list[str] = []
    if graph_display_mode == "左右の軸":
        right_axis_names = st.multiselect(
            "右軸に表示する指標",
            options=list(series_to_plot),
            default=list(series_to_plot)[-1:] if len(series_to_plot) > 1 else [],
            help="選ばなかった指標は左軸に表示します。",
        )


    def chart_label(name: str) -> str:
        info = INDICATORS[name]
        unit = series_to_plot[name].attrs.get("unit", info["unit"])
        label = f"{name}（前年比 %）" if info.get("yoy") else f"{name}（{unit}）"
        if normalize_values:
            label = f"{name}（開始日=100）"
        return label


    def chart_axis_title(name: str) -> str:
        if normalize_values:
            return "100基準"
        info = INDICATORS[name]
        return (
            "前年比 %"
            if info.get("yoy")
            else series_to_plot[name].attrs.get("unit", info["unit"])
        )


    if graph_display_mode == "個別グラフ":
        for name, series in series_to_plot.items():
            individual_figure = go.Figure(
                go.Scatter(
                    x=series.index,
                    y=series,
                    mode="lines",
                    name=chart_label(name),
                )
            )
            individual_figure.update_layout(
                height=300,
                title=dict(text=chart_label(name), font=dict(size=16)),
                hovermode="x unified",
                showlegend=False,
                margin=dict(l=20, r=20, t=45, b=35),
            )
            individual_figure.update_yaxes(title=chart_axis_title(name))
            st.plotly_chart(individual_figure, use_container_width=True)
    else:
        if graph_display_mode == "左右の軸":
            figure = make_subplots(specs=[[{"secondary_y": True}]])
        else:
            figure = go.Figure()

        for name, series in series_to_plot.items():
            trace = go.Scatter(x=series.index, y=series, mode="lines", name=chart_label(name))
            if graph_display_mode == "左右の軸":
                figure.add_trace(trace, secondary_y=name in right_axis_names)
            else:
                figure.add_trace(trace)

        figure.update_layout(
            height=420,
            hovermode="x unified",
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.2,
                xanchor="left",
                x=0,
            ),
            margin=dict(l=20, r=20, t=30, b=90),
        )
        if graph_display_mode == "左右の軸":
            figure.update_yaxes(
                title="左軸（100基準）" if normalize_values else "左軸",
                secondary_y=False,
            )
            figure.update_yaxes(
                title="右軸（100基準）" if normalize_values else "右軸",
                secondary_y=True,
            )
        else:
            figure.update_yaxes(title="100基準" if normalize_values else "値")
        st.plotly_chart(figure, use_container_width=True)
    st.checkbox("100を基準に比較する", value=True, key="normalize_values_v2")

    latest_values_note = (
        '<span style="font-size: 0.9rem; font-weight: 400; color: #888;">（開始日=100）</span>'
        if normalize_values
        else ""
    )
    st.markdown(f"### 最新値　{latest_values_note}", unsafe_allow_html=True)
    st.caption("★ 主要は、景気・為替・日米株・市場心理・長期金利の代表指標です。")
    change_rows: list[dict[str, str]] = []
    card_items = list(series_to_plot.items())
    for card_index, (name, series) in enumerate(card_items):
        if card_index % 4 == 0:
            cards = st.columns(4)
        column = cards[card_index % 4]
        card = column.container(border=True)
        observed_at, value = latest_value(series)
        info = INDICATORS[name]
        suffix = (
            "（前年比 %）"
            if info.get("yoy")
            else series.attrs.get("unit", info["unit"])
        )
        display_value = f"{value:,.2f}" if normalize_values else f"{value:,.2f} {suffix}"
        previous_change = change_from_previous(series)
        if previous_change is None:
            delta = None
            previous_rate = None
        else:
            change, previous_rate = previous_change
            delta = f"{change:+,.2f}（{previous_rate:+.2f}%）"
        if previous_rate is None:
            movement_label = "－ 変化データなし"
        elif previous_rate > 0.05:
            movement_label = "↗ 上昇"
        elif previous_rate < -0.05:
            movement_label = "↘ 下落"
        else:
            movement_label = "→ 横ばい"
        importance_label = "★ 主要" if name in KEY_MARKET_INDICATORS else "通常"
        actual_source = series.attrs.get("source", info["source"])
        source_label = DATA_SOURCE_LABELS.get(actual_source, actual_source)
        if series.attrs.get("is_fallback"):
            source_label = f"{source_label}・{series.attrs['ticker']}（代替）"
        card.caption(f"{importance_label}｜{movement_label}")
        card.metric(name, display_value, delta=delta, help=f"観測日: {observed_at:%Y-%m-%d}")
        card.caption(f"データ日: {observed_at:%Y-%m-%d}｜データ元: {source_label}")

        def format_rate(rate: float | None) -> str:
            return "—" if rate is None else f"{rate:+.2f}%"

        change_rows.append(
            {
                "指標": name,
                "直前値比": format_rate(previous_rate),
                "1週間": format_rate(percent_change_since(series, observed_at - pd.Timedelta(days=7))),
                "1か月": format_rate(percent_change_since(series, observed_at - pd.DateOffset(months=1))),
                "年初来": format_rate(percent_change_since(series, pd.Timestamp(year=observed_at.year, month=1, day=1))),
                "表示期間": format_rate(percent_change_since(series, pd.Timestamp(start_date))),
            }
        )

    market_summary = build_market_summary(series_to_plot, INDICATORS)
    st.subheader("今日のマーケット")
    st.info(f"**{market_summary['headline']}**")
    if market_summary["bullets"]:
        for summary_line in market_summary["bullets"]:
            st.markdown(f"- {summary_line}")
    else:
        st.caption("要約できる直前観測値がありません。")
    summary_latest_date = market_summary["latest_date"]
    if summary_latest_date is not None:
        st.caption(
            f"選択中の指標の直前観測値比によるルールベース要約です。最新データ日: "
            f"{summary_latest_date:%Y-%m-%d}。ニュースや将来予測は含みません。"
        )

    st.subheader("騰落率")
    st.caption("直前値比は直前の観測値、その他は指定時点以前で最も新しい観測値を基準に計算します。")
    st.dataframe(pd.DataFrame(change_rows), hide_index=True, use_container_width=True)

    st.subheader("急変検知")
    with st.expander("検知する騰落率を設定"):
        alert_threshold_columns = st.columns(3)
        alert_thresholds = {
            "直前観測値比": alert_threshold_columns[0].number_input(
                "直前観測値比（%）",
                min_value=0.1,
                value=2.0,
                step=0.5,
                key="alert_previous_threshold",
            ),
            "1週間": alert_threshold_columns[1].number_input(
                "1週間（%）",
                min_value=0.1,
                value=5.0,
                step=0.5,
                key="alert_week_threshold",
            ),
            "1か月": alert_threshold_columns[2].number_input(
                "1か月（%）",
                min_value=0.1,
                value=10.0,
                step=0.5,
                key="alert_month_threshold",
            ),
        }

    market_move_alerts = detect_market_moves(series_to_plot, alert_thresholds)
    if market_move_alerts.empty:
        st.success("設定した閾値を超える動きはありません。")
    else:
        st.warning(f"設定した閾値を超えた動きが{len(market_move_alerts)}件あります。")
        alert_display = market_move_alerts.copy()
        alert_display["方向"] = alert_display["方向"].map(
            {"上昇": "🔴 上昇", "下落": "🔵 下落", "横ばい": "横ばい"}
        )
        alert_display["騰落率"] = alert_display["騰落率"].map(lambda rate: f"{rate:+.2f}%")
        alert_display["閾値"] = alert_display["閾値"].map(lambda value: f"±{value:.1f}%")
        alert_display["データ日"] = alert_display["データ日"].dt.strftime("%Y-%m-%d")
        st.dataframe(
            alert_display.drop(columns="重要度"),
            hide_index=True,
            use_container_width=True,
        )
    st.caption(
        "画面内の注意表示です。直前観測値比は指標ごとの直前データと比較します。"
        "外部通知や売買判断を行うものではありません。"
    )

    with st.expander("データ更新状況"):
        data_status_frame = build_data_status_frame(
            series_to_plot, INDICATORS, DATA_SOURCE_LABELS
        )
        stale_data = data_status_frame[data_status_frame["鮮度"] == "⚠ 要確認"]
        if not stale_data.empty:
            st.warning(
                "想定より更新が遅い系列があります: "
                + "、".join(stale_data["指標"].astype(str))
                + "。データ元の公表状況や取得状態を確認してください。"
            )
        st.dataframe(
            data_status_frame,
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            "データ最終日は系列の最新観測日、取得確認日時はキャッシュ内データを取得した日本時間です。"
            "営業日次は週末を除く2営業日、暦日次は2日、月次は通常の公表ラグを含む62日を超えると要確認になります。"
            "単発の休場日では警告しにくい猶予を設けています。取得試行と取得時間は、キャッシュ生成時の値です。"
        )

    with st.expander("データ一覧"):
        table = pd.concat(series_to_plot, axis=1)
        st.dataframe(table.sort_index(ascending=False), use_container_width=True)

with event_tab:
    st.subheader("米国経済イベントカレンダー")
    calendar_months = st.radio(
        "表示期間",
        ["今後3か月", "今後6か月", "収録分すべて"],
        horizontal=True,
        key="economic_calendar_period",
    )
    calendar_end_offsets = {
        "今後3か月": pd.DateOffset(months=3),
        "今後6か月": pd.DateOffset(months=6),
        "収録分すべて": pd.DateOffset(years=2),
    }
    try:
        calendar_today = pd.Timestamp.now(tz="Asia/Tokyo").normalize()
        calendar_data_start = (calendar_today - pd.DateOffset(months=18)).date()
        with st.spinner("経済イベントと直近結果を確認しています…"):
            economic_events = build_us_economic_events()
            event_results = latest_event_results(
                cpi=load_data("fred", "CPIAUCSL", str(calendar_data_start)),
                unemployment=load_data("fred", "UNRATE", str(calendar_data_start)),
                payrolls=load_data("fred", "PAYEMS", str(calendar_data_start)),
                fed_funds=load_data("fred", "DFEDTARU", str(calendar_data_start)),
            )
            calendar_table = calendar_display_frame(
                economic_events,
                event_results,
                start=calendar_today,
                end=calendar_today + calendar_end_offsets[calendar_months],
            )
        if calendar_table.empty:
            st.info("選択期間に収録済みのイベントはありません。")
        else:
            st.dataframe(calendar_table, hide_index=True, use_container_width=True)
        st.caption(
            "日程はBLS（2026年12月まで）とFRB（2027年12月まで）の公表情報を日本時間へ変換。"
            "予想値は公式データにないため表示しません。直近結果・前回値はFREDの最新系列値です。"
        )
        st.markdown(
            f"日程元: [BLS]({OFFICIAL_SCHEDULE_URLS['BLS']}) / "
            f"[FRB]({OFFICIAL_SCHEDULE_URLS['FRB']})"
        )
    except Exception as error:
        st.warning(f"経済イベントカレンダーを表示できませんでした: {error}")

    st.subheader("イベント前後分析")
    st.caption(
        "重要イベントの公表直前の終値を基準に、当日から20営業日後までの市場反応を集計します。"
    )
    selected_event_name = st.selectbox(
        "分析するイベント", list(EVENT_HISTORY), key="event_analysis_name"
    )
    st.caption(
        f"公式実績日: 2024〜2025年｜収録数: {len(EVENT_HISTORY[selected_event_name])}件"
    )
    if st.button(
        "イベント反応を分析",
        key="run_event_reaction_analysis",
        use_container_width=True,
    ):
        st.session_state["show_event_reaction_analysis"] = True
        st.session_state["analyzed_event_name"] = selected_event_name

    if st.session_state.get("show_event_reaction_analysis", False):
        active_event_name = st.session_state.get(
            "analyzed_event_name", selected_event_name
        )
        if active_event_name != selected_event_name:
            st.info("イベントを変更したため、「イベント反応を分析」を押して更新してください。")
        else:
            event_asset_series: dict[str, pd.Series] = {}
            event_asset_methods: dict[str, str] = {}
            event_asset_errors: list[str] = []
            event_data_start = pd.Timestamp(EVENT_HISTORY[active_event_name][0]) - pd.DateOffset(
                days=40
            )
            with st.spinner(f"{active_event_name}前後の市場反応を集計しています…"):
                for display_name, (
                    indicator_name,
                    method,
                ) in EVENT_ASSET_DEFINITIONS.items():
                    try:
                        event_asset_series[display_name] = load_indicator_data(
                            INDICATORS[indicator_name], str(event_data_start.date())
                        )
                        event_asset_methods[display_name] = method
                    except Exception as event_asset_error:
                        event_asset_errors.append(f"{display_name}: {event_asset_error}")

            for event_asset_error in event_asset_errors:
                st.warning(f"イベント前後分析では {event_asset_error}")

            if event_asset_series:
                event_reactions = analyze_event_reactions(
                    event_dates=EVENT_HISTORY[active_event_name],
                    asset_series=event_asset_series,
                    methods_by_asset=event_asset_methods,
                )
                for event_horizon in ["当日", "翌営業日", "5営業日後", "20営業日後"]:
                    with st.expander(event_horizon, expanded=event_horizon in {"当日", "5営業日後"}):
                        event_horizon_table = event_reactions[
                            event_reactions["期間"] == event_horizon
                        ].copy()
                        for event_value_column in ["平均", "中央値"]:
                            event_horizon_table[event_value_column] = event_horizon_table.apply(
                                lambda row: (
                                    "—"
                                    if pd.isna(row[event_value_column])
                                    else f"{row[event_value_column]:+.2f}{row['単位']}"
                                ),
                                axis=1,
                            )
                        event_horizon_table["上昇確率"] = event_horizon_table[
                            "上昇確率"
                        ].map(lambda value: "—" if pd.isna(value) else f"{value:.1f}%")
                        st.dataframe(
                            event_horizon_table.drop(columns=["期間", "単位"]),
                            hide_index=True,
                            use_container_width=True,
                        )
                if (event_reactions["注意"] == "サンプル少").any():
                    st.warning(
                        "サンプル数が12未満の組合せがあります。平均値だけで判断しないでください。"
                    )
                st.caption(
                    "当日は公表日の最初の市場観測値、翌営業日以降はそこから指定観測数後を使い、"
                    "公表日前の最終観測値と比較します。米10年金利は変化幅（bp）で、上昇確率は"
                    "金利が上昇した割合です。日次終値による集計であり、発表直後の値動きではありません。"
                )
                st.caption(
                    "過去の傾向であり、将来予測や投資助言ではありません。"
                    "サプライズ方向別に拡張できる設計ですが、予想値がないため現在は全イベントを集計します。"
                )
                st.markdown(
                    f"日程元: [{active_event_name}]({EVENT_SOURCE_URLS[active_event_name]})"
                )

with analysis_tab:
    st.subheader("Market Stress Score")
    st.caption(
        "VIX、株価変動、株価下落、米10年金利変化、為替変動を過去5年分布と比較し、"
        "市場の不安定さを0〜100で機械的に要約します。"
    )
    if st.button(
        "ストレススコアを計算",
        key="run_market_stress_score",
        width="stretch",
    ):
        st.session_state["show_market_stress_score"] = True

    if st.session_state.get("show_market_stress_score", False):
        stress_history_start = (
            pd.Timestamp.today().normalize()
            - pd.DateOffset(years=5)
            - pd.DateOffset(days=120)
        ).date()
        with st.spinner("市場ストレスの構成項目を確認しています…"):
            stress_context = load_market_stress_context(str(stress_history_start))
            st.session_state["market_stress_context"] = stress_context

        for stress_load_error in stress_context["load_errors"]:
            st.warning(f"Market Stress Scoreでは取得できない系列があります: {stress_load_error}")
        for stress_fallback in stress_context["fallbacks"]:
            st.warning(f"Market Stress Scoreでは代替系列を使用します: {stress_fallback}")

        stress_result = stress_context["result"]
        stress_score = stress_result["score"]
        if stress_score is None:
            st.warning(
                "Market Stress Scoreを算出できません。"
                f"利用可能な構成項目は{stress_result['coverage']}/"
                f"{stress_result['total_components']}です。3項目以上が必要です。"
            )
        else:
            stress_metrics = st.columns(3)
            stress_metrics[0].metric("ストレススコア", f"{stress_score:.0f} / 100")
            stress_metrics[1].metric("状態", stress_result["level"])
            stress_metrics[2].metric(
                "データカバレッジ",
                f"{stress_result['coverage']} / {stress_result['total_components']}",
            )
            st.progress(float(stress_score) / 100)

            stress_components = stress_result["components"].copy()
            stress_components["実測値"] = stress_components.apply(
                lambda row: f"{row['実測値']:.2f}{row['単位']}", axis=1
            )
            stress_components["過去5年percentile"] = stress_components[
                "過去5年percentile"
            ].map(lambda value: f"{value:.1f}%")
            stress_components["ウェイト"] = stress_components["ウェイト"].map(
                lambda value: f"{value:.1f}%"
            )
            stress_components["スコア寄与"] = stress_components["スコア寄与"].map(
                lambda value: f"{value:.1f}pt"
            )
            stress_components["基準日"] = stress_components["基準日"].dt.strftime(
                "%Y-%m-%d"
            )
            st.dataframe(
                stress_components.drop(columns=["単位"]),
                hide_index=True,
                width="stretch",
            )

        if stress_result["unavailable"]:
            with st.expander("利用できなかった構成項目"):
                for unavailable_component in stress_result["unavailable"]:
                    st.write(f"- {unavailable_component}")
        st.caption(
            "各項目の最新値が過去5年分布のどの位置にあるかをpercentile化し、利用可能項目を"
            "等ウェイトで集計します。欠損時はウェイトを再配分します。サンプル数は各項目の"
            "percentile計算に使った過去観測数です。高スコアは市場の不安定さを示す参考値であり、"
            "将来予測、売買シグナル、投資助言ではありません。"
        )

    st.subheader("相関変化検知")
    st.caption(
        "代表的な市場間関係について、現在の20日・60日相関を過去時点と5年間の分布に照らします。"
        "価格は日次騰落率、金利・金利差は日次変化幅を使用します。"
    )
    correlation_change_pairs = {
        "SOX × 米10年金利": ("SOX指数", "UST 10Y"),
        "NASDAQ × 米10年金利": ("NASDAQ総合指数", "UST 10Y"),
        "USD/JPY × 日米10年金利差": ("USD/JPY", "日米金利差 10Y（米国−日本）"),
        "日経平均 × USD/JPY": ("日経平均株価", "USD/JPY"),
    }
    change_pair_label = st.selectbox(
        "変化を確認する組合せ",
        list(correlation_change_pairs),
        key="correlation_change_pair",
    )
    change_left_name, change_right_name = correlation_change_pairs[change_pair_label]
    change_history_start = (
        pd.Timestamp.today().normalize() - pd.DateOffset(years=5) - pd.DateOffset(days=120)
    ).date()
    try:
        with st.spinner("相関変化を確認しています…"):
            change_series = {
                name: load_indicator_data(INDICATORS[name], str(change_history_start))
                for name in (change_left_name, change_right_name)
            }
        change_methods = {
            name: (
                "change"
                if INDICATORS[name]["category"] == "金利"
                or INDICATORS[name]["source"] == "us_jp_yield_spread"
                else "return"
            )
            for name in change_series
        }
        daily_change_frame, daily_change_labels = build_daily_change_frame(
            change_series, change_methods
        )
        five_year_start = pd.Timestamp.today().normalize() - pd.DateOffset(years=5)
        daily_change_frame = daily_change_frame.loc[daily_change_frame.index >= five_year_start]
        change_summary = correlation_change_summary(
            daily_change_frame[change_left_name], daily_change_frame[change_right_name]
        )

        if change_summary.empty:
            st.info("相関変化を計算するための共通データが十分にありません。")
        else:
            alerts = correlation_change_alerts(change_summary)
            if alerts:
                for alert in alerts:
                    st.warning(f"相関変化シグナル: {alert}")
            else:
                st.info("現在、設定した基準に該当する大きな相関変化はありません。")

            change_display = change_summary.copy()
            change_display["現在"] = change_display["現在"].map(lambda value: f"{value:+.2f}")
            for offset, label in ((21, "1か月前"), (63, "3か月前")):
                change_display[label] = change_display[f"{offset}日前"].map(
                    lambda value: "—" if pd.isna(value) else f"{value:+.2f}"
                )
                change_display[f"{label}比"] = change_display[f"{offset}日差"].map(
                    lambda value: "—" if pd.isna(value) else f"{value:+.2f}"
                )
            change_display["過去5年percentile"] = change_display["percentile"].map(
                lambda value: f"{value:.0f}%"
            )
            st.dataframe(
                change_display[
                    [
                        "期間",
                        "現在",
                        "1か月前",
                        "1か月前比",
                        "3か月前",
                        "3か月前比",
                        "過去5年percentile",
                        "共通観測数",
                    ]
                ],
                hide_index=True,
                use_container_width=True,
            )

            change_figure = go.Figure()
            for window, color in ((20, "#1f77b4"), (60, "#ff7f0e")):
                values = rolling_correlation(
                    daily_change_frame[change_left_name],
                    daily_change_frame[change_right_name],
                    window,
                )
                if not values.empty:
                    change_figure.add_trace(
                        go.Scatter(
                            x=values.index,
                            y=values,
                            mode="lines",
                            name=f"{window}日相関",
                            line=dict(color=color, width=2),
                            hovertemplate="日付: %{x|%Y-%m-%d}<br>相関係数: %{y:.2f}<extra></extra>",
                        )
                    )
            change_figure.add_hline(y=0, line_width=1, line_dash="dot", line_color="gray")
            change_figure.update_layout(
                height=340,
                margin=dict(l=20, r=20, t=20, b=40),
                yaxis=dict(title="相関係数", range=[-1.05, 1.05]),
                xaxis_title="日付",
            )
            st.plotly_chart(change_figure, use_container_width=True)
            st.caption(
                f"{change_left_name}（{daily_change_labels[change_left_name]}）× "
                f"{change_right_name}（{daily_change_labels[change_right_name]}）｜"
                "急変は1か月前比±0.25以上、分布シグナルは過去5年の上位・下位10%を目安に表示。"
            )
    except Exception as error:
        st.warning(f"相関変化検知を表示できませんでした: {error}")

    st.caption(
        "相関の変化は市場構造の変化を探す判断材料です。因果関係や将来の値動きを示すものではありません。"
    )

    st.subheader("相関分析")
    st.caption(
        "価格系は騰落率、金利・金利差・マクロ指標はポイント変化で比較します。"
        "マクロ指標を含む場合は月次、それ以外は週次です。初期値は、上で選択している指標です。"
    )

    correlation_period_months = {
        "3か月": 3,
        "6か月": 6,
        "1年": 12,
        "3年": 36,
    }
    correlation_presets = {
        "為替と日本株": ["USD/JPY", "日経平均株価"],
        "米金利と半導体株": ["UST 10Y", "SOX指数"],
        "米金利と米国株": ["UST 10Y", "S&P 500指数"],
        "米物価と政策金利": ["CPI", "FF金利"],
    }
    if "correlation_names" not in st.session_state:
        st.session_state["correlation_names"] = selected_names[:8]

    st.markdown("##### よく使う組合せ")
    st.caption("ボタンを押すと、下の相関分析対象へ2指標が設定されます。")
    preset_columns = st.columns(2)
    for preset_index, (preset_name, preset_indicators) in enumerate(correlation_presets.items()):
        with preset_columns[preset_index % 2]:
            if st.button(
                preset_name,
                key=f"correlation_preset_{preset_index}",
                use_container_width=True,
                help=" × ".join(preset_indicators),
            ):
                st.session_state["correlation_names"] = preset_indicators

    analysis_left, analysis_right = st.columns([1, 2])
    with analysis_left:
        correlation_period_label = st.selectbox(
            "相関を調べる期間", list(correlation_period_months), index=2
        )
    with analysis_right:
        correlation_names = st.multiselect(
            "相関分析の対象（最大8指標）",
            options=list(INDICATORS),
            max_selections=8,
            key="correlation_names",
            help="例：USD/JPYと日経平均株価、UST 10YとSOX指数を選択します。",
        )

    if len(correlation_names) < 2:
        st.info("相関分析の対象を2つ以上選択してください。")
    else:
        correlation_start_date = (
            pd.Timestamp.today().normalize()
            - pd.DateOffset(months=correlation_period_months[correlation_period_label])
            - pd.DateOffset(days=14)
        ).date()
        correlation_series: dict[str, pd.Series] = {}
        correlation_methods: dict[str, str] = {}
        correlation_errors: list[str] = []
        with st.spinner("相関分析用のデータを取得しています…"):
            for name in correlation_names:
                info = INDICATORS[name]
                try:
                    series = load_indicator_data(info, str(correlation_start_date))
                    correlation_series[name] = series
                    if info.get("correlation_method"):
                        correlation_methods[name] = info["correlation_method"]
                    elif info["category"] == "金利":
                        correlation_methods[name] = "weekly_change"
                    else:
                        correlation_methods[name] = "weekly_return"
                except Exception as error:
                    correlation_errors.append(f"{name}: {error}")

        for error in correlation_errors:
            st.warning(f"相関分析では {error}")

        if len(correlation_series) < 2:
            st.warning("相関を計算できる指標が2つ以上ありません。")
        else:
            correlation_frame, correlation_labels, frequency_label = build_correlation_frame(
                correlation_series, correlation_methods
            )
            minimum_observations = 3 if frequency_label == "月次" else 8
            correlation_matrix = correlation_frame.corr(min_periods=minimum_observations)
            pair_table = correlation_pairs(correlation_frame, minimum_observations)

            if pair_table.empty:
                st.info(f"相関を計算するための共通する{frequency_label}データが十分にありません。")
            else:
                pair_table["相関係数"] = pair_table["相関係数"].map(lambda value: f"{value:+.2f}")
                st.markdown("##### 相関係数一覧")
                st.dataframe(pair_table, hide_index=True, use_container_width=True)

                st.markdown("##### 相関マトリクス")
                heatmap = go.Figure(
                    data=go.Heatmap(
                        z=correlation_matrix.values,
                        x=correlation_matrix.columns,
                        y=correlation_matrix.index,
                        zmin=-1,
                        zmax=1,
                        zmid=0,
                        colorscale="RdBu",
                        colorbar=dict(title="相関"),
                        hovertemplate="%{y} × %{x}<br>相関係数: %{z:.2f}<extra></extra>",
                    )
                )
                heatmap.update_layout(height=450, margin=dict(l=20, r=20, t=20, b=100))
                st.plotly_chart(heatmap, use_container_width=True)

                st.markdown("##### 2指標の散布図")
                scatter_left, scatter_right = st.columns(2)
                with scatter_left:
                    scatter_x_name = st.selectbox("横軸", list(correlation_series), key="correlation_x")
                with scatter_right:
                    scatter_y_options = [name for name in correlation_series if name != scatter_x_name]
                    scatter_y_name = st.selectbox("縦軸", scatter_y_options, key="correlation_y")
                scatter_data = correlation_frame[[scatter_x_name, scatter_y_name]].dropna()
                scatter_figure = go.Figure(
                    go.Scatter(
                        x=scatter_data[scatter_x_name],
                        y=scatter_data[scatter_y_name],
                        mode="markers",
                        name="データ",
                        marker=dict(size=8, opacity=0.7),
                        text=[observed.strftime("%Y-%m-%d") for observed in scatter_data.index],
                        hovertemplate=(
                            f"{frequency_label}: %{{text}}<br>"
                            "横軸: %{x:.2f}<br>縦軸: %{y:.2f}<extra></extra>"
                        ),
                    )
                )
                regression = linear_regression_summary(
                    scatter_data[scatter_x_name], scatter_data[scatter_y_name]
                )
                if regression is not None:
                    slope, intercept, scatter_correlation = regression
                    line_x = [
                        float(scatter_data[scatter_x_name].min()),
                        float(scatter_data[scatter_x_name].max()),
                    ]
                    line_y = [slope * value + intercept for value in line_x]
                    scatter_figure.add_trace(
                        go.Scatter(
                            x=line_x,
                            y=line_y,
                            mode="lines",
                            name="回帰線",
                            line=dict(color="#ff7f0e", width=2),
                            hoverinfo="skip",
                        )
                    )
                scatter_figure.update_layout(
                    height=380,
                    margin=dict(l=20, r=20, t=20, b=50),
                    xaxis_title=f"{scatter_x_name}（{correlation_labels[scatter_x_name]}）",
                    yaxis_title=f"{scatter_y_name}（{correlation_labels[scatter_y_name]}）",
                )
                st.plotly_chart(scatter_figure, use_container_width=True)
                if regression is None:
                    st.caption("回帰線と相関係数を計算できる有効なデータが不足しています。")
                else:
                    st.caption(
                        f"相関係数: {scatter_correlation:+.2f}｜"
                        f"回帰式: y = {slope:.3f}x {intercept:+.3f}｜"
                        f"データ数: {len(scatter_data)}"
                    )

                st.markdown("##### ローリング相関")
                if frequency_label == "月次":
                    rolling_windows = {"6か月": 6, "12か月": 12}
                else:
                    rolling_windows = {"13週": 13, "26週": 26}
                rolling_window_label = st.selectbox(
                    "計算期間",
                    list(rolling_windows),
                    key=f"rolling_window_{frequency_label}",
                )
                rolling_values = rolling_correlation(
                    scatter_data[scatter_x_name],
                    scatter_data[scatter_y_name],
                    rolling_windows[rolling_window_label],
                )
                if rolling_values.empty:
                    st.info(
                        f"{rolling_window_label}ローリング相関を計算するためのデータが"
                        "十分にありません。相関を調べる期間を長くしてください。"
                    )
                else:
                    rolling_figure = go.Figure(
                        go.Scatter(
                            x=rolling_values.index,
                            y=rolling_values,
                            mode="lines",
                            name=f"{rolling_window_label}相関",
                            line=dict(width=2),
                            hovertemplate="日付: %{x|%Y-%m-%d}<br>相関係数: %{y:.2f}<extra></extra>",
                        )
                    )
                    rolling_figure.add_hline(y=0, line_width=1, line_dash="dot", line_color="gray")
                    rolling_figure.update_layout(
                        height=340,
                        margin=dict(l=20, r=20, t=20, b=40),
                        yaxis=dict(title="相関係数", range=[-1.05, 1.05]),
                        xaxis_title="日付",
                    )
                    st.plotly_chart(rolling_figure, use_container_width=True)
                    st.caption(
                        f"最新の{rolling_window_label}相関: {rolling_values.iloc[-1]:+.2f}｜"
                        f"{scatter_x_name} × {scatter_y_name}"
                    )

            st.caption("相関係数は-1から+1です。相関は因果関係や将来の値動きを示すものではなく、景気・インフレ・リスク回避など市場環境によって変化します。")

    st.subheader("米国マクロ局面")
    try:
        regime_start_date = (pd.Timestamp.today().normalize() - pd.DateOffset(years=15)).date()
        with st.spinner("マクロ指標を確認しています…"):
            macro_cpi = load_data("fred", "CPIAUCSL", str(regime_start_date))
            macro_unemployment = load_data("fred", "UNRATE", str(regime_start_date))
            macro_fed_funds = load_data("fred", "FEDFUNDS", str(regime_start_date))
            macro_ust_2y = load_data("fred", "DGS2", str(regime_start_date))
            macro_ust_10y = load_data("fred", "DGS10", str(regime_start_date))
            macro_regime = assess_us_macro_regime(
                cpi=macro_cpi,
                unemployment=macro_unemployment,
                fed_funds=macro_fed_funds,
                ust_2y=macro_ust_2y,
                ust_10y=macro_ust_10y,
            )
            macro_trends = build_us_macro_trends(
                cpi=macro_cpi,
                unemployment=macro_unemployment,
                fed_funds=macro_fed_funds,
                ust_2y=macro_ust_2y,
                ust_10y=macro_ust_10y,
            )
            macro_assessment_labels, macro_assessment_scores = (
                build_us_macro_assessment_history(
                    cpi=macro_cpi,
                    unemployment=macro_unemployment,
                    fed_funds=macro_fed_funds,
                    ust_2y=macro_ust_2y,
                    ust_10y=macro_ust_10y,
                )
            )
            macro_focus_guide = build_macro_focus_guide(macro_regime)

        macro_trends = {
            name: series.loc[
                pd.Timestamp.today().normalize() - pd.DateOffset(months=36) :
            ]
            for name, series in macro_trends.items()
        }
        macro_assessment_labels_display = macro_assessment_labels.tail(48)
        macro_assessment_scores_display = macro_assessment_scores.tail(48)

        st.info(f"**{macro_regime['regime']}**  \n{macro_regime['description']}")
        inflation = macro_regime["inflation"]
        labor = macro_regime["labor"]
        policy = macro_regime["policy"]
        curve = macro_regime["curve"]
        macro_columns = st.columns(4)
        macro_columns[0].metric(
            "インフレ（CPI前年比）",
            f"{inflation['value']:.2f}%",
            delta=f"3か月: {inflation['change']:+.2f}pt（{inflation['status']}）",
            help=f"最新値: {inflation['date']:%Y-%m-%d}",
        )
        macro_columns[1].metric(
            "雇用（失業率）",
            f"{labor['value']:.2f}%",
            delta=f"3か月: {labor['change']:+.2f}pt（{labor['status']}）",
            help=f"最新値: {labor['date']:%Y-%m-%d}",
        )
        macro_columns[2].metric(
            "金融政策（FF金利）",
            f"{policy['value']:.2f}%",
            delta=f"3か月: {policy['change']:+.2f}pt（{policy['status']}）",
            help=f"最新値: {policy['date']:%Y-%m-%d}",
        )
        macro_columns[3].metric(
            "長短金利差（10年−2年）",
            f"{curve['spread']:+.2f}pt",
            delta=curve["status"],
            help=f"UST 10Y: {curve['ust_10y']:.2f}% / UST 2Y: {curve['ust_2y']:.2f}%（{curve['date']:%Y-%m-%d}）",
        )
        st.markdown("#### 市場変動の要因仮説")
        st.caption(
            "Market Stress Scoreの構成項目、直近変化、米国マクロ評価から、"
            "現在のデータと整合する要因候補を上位3件に整理します。"
        )
        if st.button(
            "要因仮説を整理",
            key="run_market_factor_hypotheses",
            width="stretch",
        ):
            st.session_state["show_market_factor_hypotheses"] = True

        if st.session_state.get("show_market_factor_hypotheses", False):
            hypothesis_stress_start = (
                pd.Timestamp.today().normalize()
                - pd.DateOffset(years=5)
                - pd.DateOffset(days=120)
            ).date()
            hypothesis_context = st.session_state.get("market_stress_context")
            if hypothesis_context is None:
                with st.spinner("要因仮説に必要な市場データを確認しています…"):
                    hypothesis_context = load_market_stress_context(
                        str(hypothesis_stress_start)
                    )
                    st.session_state["market_stress_context"] = hypothesis_context

            hypothesis_result = build_market_factor_hypotheses(
                stress_result=hypothesis_context["result"],
                series_by_name=hypothesis_context["series"],
                macro_regime=macro_regime,
            )
            for hypothesis_fallback in hypothesis_context["fallbacks"]:
                st.warning(f"要因仮説では代替系列を使用します: {hypothesis_fallback}")
            st.caption(
                f"市場入力カバレッジ: {hypothesis_result['input_coverage']} / "
                f"{hypothesis_result['total_inputs']}"
            )
            for hypothesis_index, hypothesis in enumerate(
                hypothesis_result["hypotheses"]
            ):
                with st.expander(
                    f"{hypothesis_index + 1}. {hypothesis['title']}｜"
                    f"根拠の強さ: {hypothesis['strength']}",
                    expanded=hypothesis_index == 0,
                ):
                    st.write(hypothesis["interpretation"])
                    st.markdown("**整合する観測**")
                    for observation in hypothesis["observations"]:
                        st.write(f"- {observation}")
                    st.caption(
                        f"利用した観測: {hypothesis['observation_count']}件"
                    )
                    if hypothesis["counter_evidence"]:
                        st.markdown("**反対材料・留意点**")
                        for counter_evidence in hypothesis["counter_evidence"]:
                            st.write(f"- {counter_evidence}")

            hypothesis_unavailable = list(hypothesis_context["load_errors"])
            hypothesis_unavailable.extend(hypothesis_result["unavailable"])
            if hypothesis_unavailable:
                with st.expander("利用できなかったデータ"):
                    for unavailable_item in dict.fromkeys(hypothesis_unavailable):
                        st.write(f"- {unavailable_item}")
            observed_at = hypothesis_result["observed_at"]
            observed_at_text = (
                "不明" if observed_at is None else f"{observed_at:%Y-%m-%d}"
            )
            st.caption(
                "ルールベースで観測の整合性を整理したもので、因果関係を特定するものでは"
                "ありません。ニュース、企業固有要因、市場参加者のポジションは含みません。"
                "将来予測、売買シグナル、投資助言ではありません。"
                f" 市場データ基準日: {observed_at_text}。"
            )
        with st.expander("現在の局面で確認したい指標・セクター", expanded=True):
            st.caption("各評価に関連する指標を、確認の観点とともに参考表示します。")
            for focus_index, focus in enumerate(macro_focus_guide):
                if focus_index % 2 == 0:
                    focus_columns = st.columns(2)
                focus_card = focus_columns[focus_index % 2].container(border=True)
                focus_card.markdown(f"**{focus['dimension']}｜{focus['status']}**")
                focus_card.write("・".join(focus["indicators"]))
                focus_card.caption(focus["reason"])
            st.caption(
                "局面判定に関連して値動きを確認しやすい候補であり、上昇・下落の予測や売買推奨ではありません。"
            )
        with st.expander("過去の評価と比較する", expanded=True):
            assessment_figure = go.Figure(
                go.Heatmap(
                    x=macro_assessment_scores_display.index,
                    y=list(macro_assessment_scores_display.columns),
                    z=macro_assessment_scores_display.T.to_numpy(),
                    customdata=macro_assessment_labels_display.T.to_numpy(),
                    zmin=-1,
                    zmax=1,
                    colorscale=[
                        [0.0, "#d9534f"],
                        [0.49, "#d9534f"],
                        [0.5, "#b7b7b7"],
                        [0.51, "#5cb85c"],
                        [1.0, "#5cb85c"],
                    ],
                    showscale=False,
                    xgap=1,
                    ygap=2,
                    hovertemplate="%{y}<br>%{x|%Y年%m月}: %{customdata}<extra></extra>",
                )
            )
            assessment_figure.update_layout(
                height=280,
                margin=dict(l=20, r=20, t=20, b=40),
                xaxis=dict(title="判定月", tickformat="%Y-%m"),
                yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(assessment_figure, use_container_width=True)
            st.caption(
                "緑は改善・鈍化・緩和・順イールド、灰色は横ばい、"
                "赤は悪化・上昇・引き締め・逆イールドです。各月時点の直近3か月変化で再判定します。"
            )
        with st.expander("判定指標の推移を見る"):
            macro_trend_figure = make_subplots(
                rows=2,
                cols=2,
                subplot_titles=list(macro_trends),
                vertical_spacing=0.16,
                horizontal_spacing=0.1,
            )
            for trend_index, (trend_name, trend_series) in enumerate(macro_trends.items()):
                row = trend_index // 2 + 1
                column = trend_index % 2 + 1
                macro_trend_figure.add_trace(
                    go.Scatter(
                        x=trend_series.index,
                        y=trend_series,
                        mode="lines",
                        name=trend_name,
                        hovertemplate="日付: %{x|%Y-%m-%d}<br>値: %{y:.2f}<extra></extra>",
                    ),
                    row=row,
                    col=column,
                )
                macro_trend_figure.update_yaxes(
                    title_text="pt" if trend_name == "10年−2年金利差" else "%",
                    row=row,
                    col=column,
                )
            macro_trend_figure.add_hline(
                y=0,
                line_width=1,
                line_dash="dot",
                line_color="gray",
                row=2,
                col=2,
            )
            macro_trend_figure.update_layout(
                height=650,
                showlegend=False,
                hovermode="x unified",
                margin=dict(l=20, r=20, t=45, b=35),
            )
            st.plotly_chart(macro_trend_figure, use_container_width=True)
            st.caption("表示期間は直近約3年です。判定には各指標の最新値と3か月変化を使います。")
        st.markdown("#### レジーム別リターン分析")
        st.caption(
            "現在と同じ、または近い4つのマクロ評価だった過去の月から、"
            "その後の資産パフォーマンスを集計します。"
        )
        regime_match_mode = st.radio(
            "過去局面の一致条件",
            ["完全一致（4評価すべて）", "近似を含む（4評価中3つ以上）"],
            horizontal=True,
            key="regime_return_match_mode",
        )
        active_regime_labels = current_regime_labels(macro_regime)
        st.caption(
            "現在の評価: "
            + " / ".join(
                f"{dimension}={status}"
                for dimension, status in active_regime_labels.items()
            )
        )
        if st.button(
            "過去リターンを分析",
            key="run_regime_return_analysis",
            use_container_width=True,
        ):
            st.session_state["show_regime_return_analysis"] = True

        if st.session_state.get("show_regime_return_analysis", False):
            regime_asset_series: dict[str, pd.Series] = {}
            regime_asset_methods: dict[str, str] = {}
            regime_asset_errors: list[str] = []
            with st.spinner("過去の各資産リターンを集計しています…"):
                for display_name, (
                    indicator_name,
                    method,
                ) in REGIME_ASSET_DEFINITIONS.items():
                    try:
                        regime_asset_series[display_name] = load_indicator_data(
                            INDICATORS[indicator_name], str(regime_start_date)
                        )
                        regime_asset_methods[display_name] = method
                    except Exception as asset_error:
                        regime_asset_errors.append(f"{display_name}: {asset_error}")

            for asset_error in regime_asset_errors:
                st.warning(f"レジーム別リターン分析では {asset_error}")

            if regime_asset_series:
                minimum_dimensions = 4 if regime_match_mode.startswith("完全一致") else 3
                regime_performance = analyze_regime_forward_performance(
                    regime_history=macro_assessment_labels,
                    current_labels=active_regime_labels,
                    asset_series=regime_asset_series,
                    methods_by_asset=regime_asset_methods,
                    minimum_matching_dimensions=minimum_dimensions,
                )
                for horizon_label in ["1か月後", "3か月後", "6か月後"]:
                    with st.expander(horizon_label, expanded=horizon_label == "3か月後"):
                        horizon_table = regime_performance[
                            regime_performance["期間"] == horizon_label
                        ].copy()
                        for column in ["平均", "中央値"]:
                            horizon_table[column] = horizon_table.apply(
                                lambda row: (
                                    "—"
                                    if pd.isna(row[column])
                                    else f"{row[column]:+.2f}{row['単位']}"
                                ),
                                axis=1,
                            )
                        horizon_table["上昇確率"] = horizon_table["上昇確率"].map(
                            lambda value: "—" if pd.isna(value) else f"{value:.1f}%"
                        )
                        st.dataframe(
                            horizon_table.drop(columns=["期間", "単位"]),
                            hide_index=True,
                            use_container_width=True,
                        )
                low_sample_rows = regime_performance[
                    regime_performance["注意"] == "サンプル少"
                ]
                if not low_sample_rows.empty:
                    st.warning(
                        "サンプル数が12未満の組合せがあります。結果のばらつきが大きいため、"
                        "平均値だけで判断しないでください。"
                    )
                st.caption(
                    "サンプル数は一致した月次観測数です。3か月後・6か月後は計測期間が重なるため、"
                    "互いに独立した標本ではありません。米10年金利はリターンではなく変化幅（bp）、"
                    "TOPIXは1306 ETFによる近似です。過去の傾向であり、将来予測や投資助言ではありません。"
                )
        st.markdown("#### 過去類似局面検索")
        st.caption(
            "現在の日次変化とマクロ評価に近い、互いに20取引日より離れた過去局面を検索します。"
            "対象資産と件数を絞り、その後の実績を参考表示します。"
        )
        similar_control_columns = st.columns(2)
        similar_asset_name = similar_control_columns[0].selectbox(
            "対象資産", list(SIMILAR_ASSET_DEFINITIONS), key="similar_period_asset"
        )
        similar_neighbor_count = similar_control_columns[1].selectbox(
            "検索件数", [5, 10], key="similar_period_count"
        )
        if st.button(
            "類似局面を検索",
            key="run_similar_period_search",
            use_container_width=True,
        ):
            st.session_state["show_similar_period_search"] = True

        if st.session_state.get("show_similar_period_search", False):
            similar_raw_series: dict[str, pd.Series] = {}
            similar_indicator_series: dict[str, pd.Series] = {}
            similar_methods: dict[str, str] = {}
            similar_errors: list[str] = []
            similar_fallbacks: list[str] = []
            with st.spinner("過去の日次特徴量と対象資産を確認しています…"):
                for feature_name, (
                    indicator_name,
                    method,
                ) in SIMILAR_FEATURE_DEFINITIONS.items():
                    try:
                        feature_series = load_indicator_data(
                            INDICATORS[indicator_name], str(regime_start_date)
                        )
                        similar_raw_series[feature_name] = feature_series
                        similar_indicator_series[indicator_name] = feature_series
                        similar_methods[feature_name] = method
                        if feature_series.attrs.get("is_fallback"):
                            similar_fallbacks.append(
                                f"{feature_name}: {feature_series.attrs['fallback_label']}"
                                f"（{feature_series.attrs['ticker']}）"
                            )
                    except Exception as similar_feature_error:
                        similar_errors.append(f"{feature_name}: {similar_feature_error}")

                target_indicator_name, target_method = SIMILAR_ASSET_DEFINITIONS[
                    similar_asset_name
                ]
                target_series = similar_indicator_series.get(target_indicator_name)
                if target_series is None:
                    try:
                        target_series = load_indicator_data(
                            INDICATORS[target_indicator_name], str(regime_start_date)
                        )
                        if target_series.attrs.get("is_fallback"):
                            similar_fallbacks.append(
                                f"{similar_asset_name}: {target_series.attrs['fallback_label']}"
                                f"（{target_series.attrs['ticker']}）"
                            )
                    except Exception as similar_target_error:
                        similar_errors.append(
                            f"対象資産 {similar_asset_name}: {similar_target_error}"
                        )
                        target_series = None

            for similar_error in similar_errors:
                st.warning(f"類似局面検索では取得できない系列があります: {similar_error}")
            for similar_fallback in similar_fallbacks:
                st.warning(f"類似局面検索では代替系列を使用します: {similar_fallback}")

            if len(similar_raw_series) < 3:
                st.warning(
                    "類似度を計算できる数値特徴量が3系列未満です。取得できた系列を確認してください。"
                )
            elif target_series is None:
                st.warning("対象資産を取得できないため、その後の実績を集計できません。")
            else:
                similar_daily_changes, _ = build_daily_change_frame(
                    similar_raw_series, similar_methods
                )
                similar_daily_changes = similar_daily_changes.apply(
                    pd.to_numeric, errors="coerce"
                )
                point_in_time_features, _ = build_point_in_time_features(
                    similar_daily_changes,
                    macro_history=macro_assessment_labels,
                    minimum_history=252,
                )
                matches, similar_summary, feature_contributions = find_similar_periods(
                    point_in_time_features=point_in_time_features,
                    target_series=target_series,
                    target_method=target_method,
                    neighbor_count=similar_neighbor_count,
                    exclusion_sessions=20,
                )
                if matches.empty:
                    st.info("条件を満たす過去局面を検索できませんでした。")
                else:
                    st.caption(
                        f"基準日: {point_in_time_features.index[-1]:%Y-%m-%d}｜"
                        f"数値特徴量: {len(similar_raw_series)}系列｜"
                        f"採用サンプル数: {len(matches)}"
                    )
                    match_display = matches.drop(columns=["距離"]).copy()
                    match_display["類似局面の日付"] = match_display[
                        "類似局面の日付"
                    ].dt.strftime("%Y-%m-%d")
                    match_display["類似度"] = match_display["類似度"].map(
                        lambda value: f"{value:.1f}"
                    )
                    result_unit = "bp" if target_method == "change_bp" else "%"
                    for result_column in ["1営業日後", "5営業日後", "20営業日後"]:
                        match_display[result_column] = match_display[result_column].map(
                            lambda value: f"{value:+.2f}{result_unit}"
                        )
                    st.dataframe(match_display, hide_index=True, use_container_width=True)

                    summary_display = similar_summary.copy()
                    for summary_column in ["平均", "中央値"]:
                        summary_display[summary_column] = summary_display.apply(
                            lambda row: f"{row[summary_column]:+.2f}{row['単位']}", axis=1
                        )
                    summary_display["上昇確率"] = summary_display["上昇確率"].map(
                        lambda value: f"{value:.1f}%"
                    )
                    st.markdown("##### 選ばれた類似局面の集計")
                    st.dataframe(
                        summary_display.drop(columns=["単位"]),
                        hide_index=True,
                        use_container_width=True,
                    )

                    with st.expander("特徴量ごとの距離への寄与を見る"):
                        contribution_display = feature_contributions.copy()
                        contribution_display["類似局面の日付"] = contribution_display[
                            "類似局面の日付"
                        ].dt.strftime("%Y-%m-%d")
                        contribution_display["距離への寄与率"] = contribution_display[
                            "距離への寄与率"
                        ].map(lambda value: f"{value:.1f}%")
                        st.dataframe(
                            contribution_display,
                            hide_index=True,
                            use_container_width=True,
                        )
                    st.caption(
                        "数値特徴量は各時点までの観測だけで標準化し、マクロ評価は月末判定を翌月から利用します。"
                        "公表時刻の完全な再現ではありません。類似度は距離を0〜100へ換算した相対指標です。"
                        "将来リターンは類似度に使用していません。サンプルは近接日を除いた過去の実績であり、"
                        "将来予測や投資助言ではありません。"
                    )
        st.caption("CPI前年比・失業率・FF金利の直近3か月変化と、米国債10年−2年の利回り差による参考判定です。投資判断や将来の市場動向を保証するものではありません。")
    except Exception as error:
        st.warning(f"米国マクロ局面を判定できませんでした: {error}")

with theme_tab:
    st.subheader("投資テーマ別ビュー")
    st.caption(
        "既存の指標・急変検知・相関・マクロ局面・イベントを、投資テーマ単位でまとめ直します。"
    )
    selected_theme_name = st.selectbox(
        "確認するテーマ", list(THEME_DEFINITIONS), key="investment_theme"
    )
    selected_theme = THEME_DEFINITIONS[selected_theme_name]
    st.info(f"**{selected_theme_name}**  \n{selected_theme['description']}")
    theme_history_start = (
        pd.Timestamp.today().normalize() - pd.DateOffset(years=5) - pd.DateOffset(days=120)
    ).date()
    try:
        theme_series: dict[str, pd.Series] = {}
        theme_errors: list[str] = []
        with st.spinner(f"{selected_theme_name}テーマのデータをまとめています…"):
            for theme_indicator_name in selected_theme["indicators"]:
                try:
                    theme_series[theme_indicator_name] = load_indicator_data(
                        INDICATORS[theme_indicator_name], str(theme_history_start)
                    )
                except Exception as theme_error:
                    theme_errors.append(f"{theme_indicator_name}: {theme_error}")
        for theme_error in theme_errors:
            st.warning(f"テーマ別ビューでは {theme_error}")

        if selected_theme_name == "半導体":
            st.markdown("#### Japan Fundamental Cycle")
            st.caption(
                "経済産業省の電子部品・デバイス工業から、生産・出荷・在庫・在庫率を"
                "組み合わせて日本の半導体実体サイクルを確認します。"
            )
            try:
                with st.spinner("電デバの鉱工業指数を確認しています…"):
                    semiconductor_iip = load_meti_semiconductor_iip()
                    semiconductor_iip_result = summarize_semiconductor_iip(
                        semiconductor_iip
                    )
                st.info(semiconductor_iip_result["assessment"])

                iip_summary = semiconductor_iip_result["summary"].copy()
                if iip_summary.empty:
                    st.warning("電デバ4指標の要約に必要なデータがありません。")
                else:
                    iip_summary["最新値"] = iip_summary["最新値"].map(
                        lambda value: f"{value:.1f}"
                    )
                    for change_column in ("前月比", "前年同月比"):
                        iip_summary[change_column] = iip_summary[change_column].map(
                            lambda value: (
                                "—" if pd.isna(value) else f"{value:+.1f}%"
                            )
                        )
                    iip_summary["3か月移動平均"] = iip_summary[
                        "3か月移動平均"
                    ].map(lambda value: "—" if pd.isna(value) else f"{value:.1f}")
                    iip_summary["対象年月"] = iip_summary["対象年月"].dt.strftime(
                        "%Y-%m"
                    )
                    st.dataframe(
                        iip_summary[
                            [
                                "指標",
                                "最新値",
                                "前月比",
                                "前年同月比",
                                "3か月移動平均",
                                "対象年月",
                            ]
                        ],
                        hide_index=True,
                        width="stretch",
                    )

                for unavailable_iip in semiconductor_iip_result["unavailable"]:
                    st.warning(f"Japan Fundamental Cycleでは {unavailable_iip}")

                iip_trends = semiconductor_iip_trends(semiconductor_iip)
                if not iip_trends.empty:
                    with st.expander("生産・出荷・在庫・在庫率の推移を見る"):
                        iip_figure = go.Figure()
                        for iip_name in iip_trends:
                            iip_figure.add_trace(
                                go.Scatter(
                                    x=iip_trends.index,
                                    y=iip_trends[iip_name],
                                    mode="lines",
                                    name=iip_name,
                                    line=dict(width=3 if iip_name == "在庫率" else 2),
                                    hovertemplate=(
                                        f"{iip_name}<br>対象月: %{{x|%Y-%m}}"
                                        "<br>指数: %{y:.1f}<extra></extra>"
                                    ),
                                )
                            )
                        iip_figure.update_layout(
                            height=360,
                            margin=dict(l=20, r=20, t=20, b=40),
                            xaxis_title="対象月",
                            yaxis_title="2020年=100",
                            hovermode="x unified",
                            legend=dict(orientation="h", y=-0.22),
                        )
                        st.plotly_chart(iip_figure, width="stretch")

                source_url = semiconductor_iip.attrs["source_url"]
                file_updated_at = semiconductor_iip.attrs.get("file_updated_at")
                file_updated_text = (
                    "不明"
                    if file_updated_at is None
                    else f"{file_updated_at:%Y-%m-%d %H:%M} JST"
                )
                st.caption(
                    "最新値・前月比・3か月移動平均は季節調整済指数、前年比は原指数です。"
                    "在庫率だけで強弱を判定せず、生産・出荷・在庫と合わせて表示します。"
                    "掲載値は最新ファイルのため、確報・年間補正で過去値が改定されます。"
                    f" ファイル更新日時: {file_updated_text}。"
                )
                st.markdown(f"データ出所: [経済産業省 鉱工業指数（2020年基準）]({source_url})")
            except Exception as iip_error:
                st.warning(
                    "Japan Fundamental Cycleの電デバ統計を取得できませんでした。"
                    f"市場データは引き続き表示します: {iip_error}"
                )

        theme_snapshot = build_theme_snapshot(theme_series, INDICATORS)
        if theme_snapshot.empty:
            st.info("テーマの最新状況を表示できるデータがありません。")
        else:
            theme_snapshot_display = theme_snapshot.copy()
            theme_snapshot_display["最新値"] = theme_snapshot_display.apply(
                lambda row: f"{row['最新値']:,.2f} {row['単位']}", axis=1
            )
            for change_column in ("直前変化", "1か月変化"):
                theme_snapshot_display[change_column] = theme_snapshot_display.apply(
                    lambda row: (
                        "—"
                        if pd.isna(row[change_column])
                        else f"{row[change_column]:+.2f}{row['変化単位']}"
                    ),
                    axis=1,
                )
            theme_snapshot_display["データ日"] = theme_snapshot_display["データ日"].dt.strftime(
                "%Y-%m-%d"
            )
            st.markdown("##### テーマの現在地")
            st.dataframe(
                theme_snapshot_display[
                    ["指標", "最新値", "直前変化", "1か月変化", "データ日"]
                ],
                hide_index=True,
                use_container_width=True,
            )

            price_theme_series = {
                name: series
                for name, series in theme_series.items()
                if INDICATORS[name]["category"] != "金利"
            }
            theme_move_alerts = detect_market_moves(price_theme_series, alert_thresholds)
            if theme_move_alerts.empty:
                st.caption("設定中の急変検知基準を超えるテーマ指標はありません。")
            else:
                strongest_theme_alert = theme_move_alerts.iloc[0]
                st.warning(
                    f"急変: {strongest_theme_alert['指標']}が{strongest_theme_alert['期間']}で"
                    f"{strongest_theme_alert['騰落率']:+.2f}%（{strongest_theme_alert['方向']}）"
                )

            relative_left, relative_right = selected_theme["relative_pair"]
            if relative_left in theme_series and relative_right in theme_series:
                relative_values, relative_month_change = relative_strength(
                    theme_series[relative_left], theme_series[relative_right]
                )
                if not relative_values.empty:
                    relative_values = relative_values.loc[
                        relative_values.index
                        >= pd.Timestamp.today().normalize() - pd.DateOffset(months=6)
                    ]
                    st.markdown("##### 相対強度")
                    relative_figure = go.Figure(
                        go.Scatter(
                            x=relative_values.index,
                            y=relative_values,
                            mode="lines",
                            name=f"{relative_left} / {relative_right}",
                            line=dict(width=2),
                            hovertemplate="日付: %{x|%Y-%m-%d}<br>相対強度: %{y:.2f}<extra></extra>",
                        )
                    )
                    relative_figure.add_hline(
                        y=100, line_width=1, line_dash="dot", line_color="gray"
                    )
                    relative_figure.update_layout(
                        height=280,
                        margin=dict(l=20, r=20, t=20, b=40),
                        yaxis_title="取得開始日=100",
                        xaxis_title="日付",
                    )
                    st.plotly_chart(relative_figure, use_container_width=True)
                    relative_direction = (
                        "優位"
                        if relative_month_change is not None and relative_month_change > 0
                        else "劣位"
                        if relative_month_change is not None and relative_month_change < 0
                        else "横ばい"
                    )
                    st.caption(
                        f"{relative_left}は{relative_right}に対して直近1か月で"
                        f"{relative_direction}"
                        + (
                            ""
                            if relative_month_change is None
                            else f"（相対強度 {relative_month_change:+.2f}%）"
                        )
                    )

            correlation_left, correlation_right = selected_theme["correlation_pair"]
            if correlation_left in theme_series and correlation_right in theme_series:
                theme_correlation_methods = {
                    name: (
                        "change" if INDICATORS[name]["category"] == "金利" else "return"
                    )
                    for name in (correlation_left, correlation_right)
                }
                theme_daily_frame, _ = build_daily_change_frame(
                    {
                        correlation_left: theme_series[correlation_left],
                        correlation_right: theme_series[correlation_right],
                    },
                    theme_correlation_methods,
                )
                theme_correlation_summary = correlation_change_summary(
                    theme_daily_frame[correlation_left], theme_daily_frame[correlation_right]
                )
                if not theme_correlation_summary.empty:
                    st.markdown("##### 市場間関係")
                    correlation_columns = st.columns(len(theme_correlation_summary))
                    for column, (_, correlation_row) in zip(
                        correlation_columns, theme_correlation_summary.iterrows()
                    ):
                        column.metric(
                            f"{correlation_row['期間']}相関",
                            f"{correlation_row['現在']:+.2f}",
                            delta=f"1か月前比 {correlation_row['21日差']:+.2f}",
                            help=(
                                f"{correlation_left} × {correlation_right}｜"
                                f"過去5年percentile {correlation_row['percentile']:.0f}%"
                            ),
                        )
                    for theme_correlation_alert in correlation_change_alerts(
                        theme_correlation_summary
                    ):
                        st.warning(f"相関変化シグナル: {theme_correlation_alert}")

            if "macro_regime" in locals():
                st.markdown("##### マクロ局面")
                st.write(f"**{macro_regime['regime']}** — {macro_regime['description']}")

            theme_events = upcoming_theme_events(
                build_us_economic_events(),
                selected_theme["event_types"],
                pd.Timestamp.today().normalize(),
            )
            st.markdown("##### 関連イベント")
            if theme_events.empty:
                st.caption("収録期間内に今後の関連イベントはありません。")
            else:
                theme_event_display = theme_events.copy()
                theme_event_display["日本時間"] = theme_event_display["datetime"].dt.strftime(
                    "%Y-%m-%d %H:%M"
                )
                st.dataframe(
                    theme_event_display[["日本時間", "event", "importance"]].rename(
                        columns={"event": "イベント", "importance": "重要度"}
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
        st.caption(
            "テーマ別ビューは関連データを一か所に整理する機能です。相対強度・相関・急変は"
            "将来予測や売買推奨ではなく、投資判断の材料として表示しています。"
        )
    except Exception as error:
        st.warning(f"投資テーマ別ビューを表示できませんでした: {error}")
