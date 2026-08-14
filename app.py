from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data_loader import load_data
from indicators import INDICATORS

from utils import change_from_previous, calc_yoy, latest_value, normalize, percent_change_since


st.set_page_config(page_title="経済指標ダッシュボード", layout="wide")
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
st.title("経済指標ダッシュボード")
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
    "為替": {
        "USD/JPY",
        "EUR/JPY",
        "AUD/JPY",
        "MXN/JPY",
    },
    "金利": {
        "UST 2Y",
        "UST 10Y",
        "UST 30Y",
        "JGB 2Y",
        "JGB 10Y",
        "JGB 30Y",
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
    normalize_values = st.checkbox("100を基準に比較する", value=True, key="normalize_values_v2")
    st.divider()

    selected_names: list[str] = []
    st.caption("表示セット")
    for watchlist_name, watchlist_indicators in WATCHLISTS.items():
        if st.button(watchlist_name, use_container_width=True, key=f"watchlist_{watchlist_name}"):
            for name in INDICATORS:
                st.session_state[f"show_{name}_default_v2"] = name in watchlist_indicators

    if st.button("すべてのチェックを外す", use_container_width=True):
        for name in INDICATORS:
            st.session_state[f"show_{name}_default_v2"] = False

    categories = dict.fromkeys(info["category"] for info in INDICATORS.values())
    for category in categories:
        st.subheader(category)
        for name, info in INDICATORS.items():
            is_default = name in {"日経平均株価", "S&P 500指数"}
            if info["category"] == category and st.checkbox(name, value=is_default, key=f"show_{name}_default_v2"):
                selected_names.append(name)

if not selected_names:
    st.info("左のメニューから、表示する指標を一つ以上選んでください。")
    st.stop()

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

figure = go.Figure()
for name, series in series_to_plot.items():
    info = INDICATORS[name]
    label = f"{name}（前年比 %）" if info.get("yoy") else f"{name}（{info['unit']}）"
    if normalize_values:
        label = f"{name}（開始日=100）"
    figure.add_trace(go.Scatter(x=series.index, y=series, mode="lines", name=label))

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
figure.update_yaxes(title="100基準" if normalize_values else "値")
st.plotly_chart(figure, use_container_width=True)

st.subheader("最新値")
cards = st.columns(len(series_to_plot))
change_rows: list[dict[str, str]] = []
for column, (name, series) in zip(cards, series_to_plot.items()):
    observed_at, value = latest_value(series)
    info = INDICATORS[name]
    suffix = "（前年比 %）" if info.get("yoy") else info["unit"]
    if normalize_values:
        suffix = "（開始日=100）"
    previous_change = change_from_previous(series)
    if previous_change is None:
        delta = None
        previous_rate = None
    else:
        change, previous_rate = previous_change
        delta = f"{change:+,.2f}（{previous_rate:+.2f}%）"
    column.metric(name, f"{value:,.2f} {suffix}", delta=delta, help=f"観測日: {observed_at:%Y-%m-%d}")

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

st.subheader("騰落率")
st.caption("直前値比は直前の観測値、その他は指定時点以前で最も新しい観測値を基準に計算します。")
st.dataframe(pd.DataFrame(change_rows), hide_index=True, use_container_width=True)

with st.expander("データ一覧"):
    table = pd.concat(series_to_plot, axis=1)
    st.dataframe(table.sort_index(ascending=False), use_container_width=True)
