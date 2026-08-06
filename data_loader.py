from __future__ import annotations

from io import StringIO

import pandas as pd
import requests
import streamlit as st
import yfinance as yf


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def load_data(source: str, ticker: str, start_date: str) -> pd.Series:
    """設定されたデータソースから時系列を取得して返す。"""
    if source == "fred":
        return _load_fred(ticker, start_date)
    if source == "yfinance":
        return _load_yfinance(ticker, start_date)
    raise ValueError(f"未対応のデータソースです: {source}")


def _load_fred(ticker: str, start_date: str) -> pd.Series:
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv"
    response = requests.get(
        url,
        params={"id": ticker, "cos": "Close", "coed": "2026-12-31"},
        timeout=30,
    )
    response.raise_for_status()

    frame = pd.read_csv(StringIO(response.text), parse_dates=["observation_date"])
    series = frame.set_index("observation_date")[ticker]
    series = pd.to_numeric(series, errors="coerce").dropna()
    series.name = ticker
    return series.loc[pd.Timestamp(start_date) :]


def _load_yfinance(ticker: str, start_date: str) -> pd.Series:
    frame = yf.download(
        ticker,
        start=start_date,
        auto_adjust=True,
        progress=False,
    )
    if frame.empty:
        raise ValueError(f"Yahoo Financeから「{ticker}」のデータを取得できませんでした。")

    # yfinanceのバージョンにより、列がMultiIndexになる場合がある。
    close = frame["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close.index = pd.to_datetime(close.index).tz_localize(None)
    close.name = ticker
    return close.dropna()
