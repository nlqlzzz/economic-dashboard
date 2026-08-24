from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from streamlit_local_storage import LocalStorage

from data_loader import load_data
from economic_calendar import (
    OFFICIAL_SCHEDULE_URLS,
    build_us_economic_events,
    calendar_display_frame,
    latest_event_results,
)
from indicators import DATA_SOURCE_LABELS, INDICATORS
from macro_regime import (
    assess_us_macro_regime,
    build_macro_focus_guide,
    build_us_macro_assessment_history,
    build_us_macro_trends,
)
from market_alerts import detect_market_moves
from market_summary import build_market_summary
from correlation_analysis import (
    build_correlation_frame,
    correlation_pairs,
    linear_regression_summary,
    rolling_correlation,
)

from utils import change_from_previous, calc_yoy, latest_value, normalize, percent_change_since
from watchlist_storage import dump_watchlists, load_watchlists


st.set_page_config(page_title="市場ダッシュボード", layout="wide")
st.markdown(
    """
    <style>
    @media (max-width: 768px) {
        [data-testid="stAppViewContainer"] h1 {
            font-size: 2rem;
            line-height: 1.25;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("市場ダッシュボード")
st.caption("FRED と Yahoo Finance の公開データを表示します。")

WATCHLISTS: dict[str, set[str]] = {
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
    "注目銘柄": {
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
    for watchlist_name, watchlist_indicators in WATCHLISTS.items():
        if st.button(watchlist_name, use_container_width=True, key=f"watchlist_{watchlist_name}"):
            for name in INDICATORS:
                st.session_state[f"show_{name}_default_v2"] = name in watchlist_indicators

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

    category_order = ["米国経済指標", "マーケット", "米国セクター", "注目銘柄", "為替", "金利"]
    available_categories = dict.fromkeys(info["category"] for info in INDICATORS.values())
    categories = [category for category in category_order if category in available_categories]
    categories.extend(category for category in available_categories if category not in categories)
    for category in categories:
        with st.expander(category, expanded=category == "マーケット"):
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
            series = load_data(info["source"], info["ticker"], str(start_date))
            if info.get("yoy", False):
                series = calc_yoy(series)
            if normalize_values:
                series = normalize(series)
            series_to_plot[name] = series
        except Exception as error:
            errors.append(f"{name}: {error}")

for error in errors:
    st.warning(error)

if not series_to_plot:
    st.error("データを表示できませんでした。ネットワーク接続とティッカーを確認してください。")
    st.stop()

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
    label = f"{name}（前年比 %）" if info.get("yoy") else f"{name}（{info['unit']}）"
    if normalize_values:
        label = f"{name}（開始日=100）"
    return label


def chart_axis_title(name: str) -> str:
    if normalize_values:
        return "100基準"
    info = INDICATORS[name]
    return "前年比 %" if info.get("yoy") else info["unit"]


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
    suffix = "（前年比 %）" if info.get("yoy") else info["unit"]
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
    source_label = DATA_SOURCE_LABELS.get(info["source"], info["source"])
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

with st.expander("データ一覧"):
    table = pd.concat(series_to_plot, axis=1)
    st.dataframe(table.sort_index(ascending=False), use_container_width=True)

st.divider()
st.header("参考情報")

st.subheader("米国経済イベントカレンダー（参考）")
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

st.subheader("相関分析（参考）")
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
                series = load_data(info["source"], info["ticker"], str(correlation_start_date))
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

st.subheader("米国マクロ局面（参考）")
try:
    regime_start_date = (pd.Timestamp.today().normalize() - pd.DateOffset(months=48)).date()
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
                x=macro_assessment_scores.index,
                y=list(macro_assessment_scores.columns),
                z=macro_assessment_scores.T.to_numpy(),
                customdata=macro_assessment_labels.T.to_numpy(),
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
    st.caption("CPI前年比・失業率・FF金利の直近3か月変化と、米国債10年−2年の利回り差による参考判定です。投資判断や将来の市場動向を保証するものではありません。")
except Exception as error:
    st.warning(f"米国マクロ局面を判定できませんでした: {error}")
