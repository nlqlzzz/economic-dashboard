from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data_loader import load_data
from indicators import INDICATORS

from utils import calc_yoy, latest_value, normalize


st.set_page_config(page_title="経済指標ダッシュボード", layout="wide")
st.title("経済指標ダッシュボード")
st.caption("FRED と Yahoo Finance の公開データを表示します。")

with st.sidebar:
    st.header("表示設定")
    start_date = st.date_input("開始日", value=date(2020, 1, 1), max_value=date.today())
    normalize_values = st.checkbox("100を基準に比較する", value=False)
    st.divider()

    selected_names: list[str] = []
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
    height=520,
    hovermode="x unified",
    legend_title_text="指標",
    margin=dict(l=20, r=20, t=30, b=20),
)
figure.update_yaxes(title="100基準" if normalize_values else "値")
st.plotly_chart(figure, use_container_width=True)

st.subheader("最新値")
cards = st.columns(len(series_to_plot))
for column, (name, series) in zip(cards, series_to_plot.items()):
    observed_at, value = latest_value(series)
    info = INDICATORS[name]
    suffix = "（前年比 %）" if info.get("yoy") else info["unit"]
    if normalize_values:
        suffix = "（開始日=100）"
    column.metric(name, f"{value:,.2f} {suffix}", help=f"観測日: {observed_at:%Y-%m-%d}")

with st.expander("データ一覧"):
    table = pd.concat(series_to_plot, axis=1)
    st.dataframe(table.sort_index(ascending=False), use_container_width=True)
