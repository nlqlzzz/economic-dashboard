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
        series = _load_fred(ticker, start_date)
    elif source == "yfinance":
        series = _load_yfinance(ticker, start_date)
    elif source == "mof_jgb":
        series = _load_mof_jgb(ticker, start_date)
    elif source == "us_jp_yield_spread":
        series = _load_us_jp_yield_spread(ticker, start_date)
    else:
        raise ValueError(f"未対応のデータソースです: {source}")
    series.attrs["fetched_at"] = pd.Timestamp.now(tz="Asia/Tokyo")
    return series


def load_indicator_data(info: dict[str, object], start_date: str) -> pd.Series:
    """一次ティッカーを取得し、失敗時は設定済みの代替候補を順に試す。"""
    candidates = [
        {
            "source": info["source"],
            "ticker": info["ticker"],
            "label": None,
            "unit": info["unit"],
        },
        *info.get("fallbacks", []),
    ]
    errors = []
    for index, candidate in enumerate(candidates):
        try:
            series = load_data(
                str(candidate["source"]), str(candidate["ticker"]), start_date
            )
            series.attrs.update(
                {
                    "source": candidate["source"],
                    "ticker": candidate["ticker"],
                    "unit": candidate.get("unit", info["unit"]),
                    "is_fallback": index > 0,
                    "fallback_label": candidate.get("label"),
                }
            )
            return series
        except Exception as error:
            errors.append(f"{candidate['source']}:{candidate['ticker']} ({error})")
    raise ValueError(" / ".join(errors))


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


def _load_mof_jgb(maturity: str, start_date: str) -> pd.Series:
    """財務省の国債金利情報から指定年限の利回りを取得する。"""
    url = "https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv"
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    # CSVはShift_JIS系の文字コードで、1行目はタイトル、2行目が見出し。
    text = response.content.decode("cp932")
    frame = pd.read_csv(StringIO(text), header=1)
    frame.columns = frame.columns.str.strip()
    date_column = frame.columns[0]
    if maturity not in frame.columns:
        raise ValueError(f"財務省データに{maturity}の利回りがありません")

    dates = frame[date_column].map(_parse_japanese_era_date)
    series = pd.Series(pd.to_numeric(frame[maturity], errors="coerce").to_numpy(), index=dates)
    series = series[series.index.notna()].dropna()
    series.name = maturity
    return series.loc[pd.Timestamp(start_date) :]


def _load_us_jp_yield_spread(maturity: str, start_date: str) -> pd.Series:
    """同年限の米国債利回りから日本国債利回りを引いた金利差を返す。"""
    maturity_map = {
        "2Y": ("DGS2", "2年"),
        "10Y": ("DGS10", "10年"),
        "30Y": ("DGS30", "30年"),
    }
    if maturity not in maturity_map:
        raise ValueError(f"未対応の日米金利差です: {maturity}")

    ust_ticker, jgb_maturity = maturity_map[maturity]
    ust = _load_fred(ust_ticker, start_date).rename("US")
    jgb = _load_mof_jgb(jgb_maturity, start_date).rename("JP")

    # 日米の休場日が異なるため、両系列を時系列順に並べて過去の最新値で補完する。
    aligned = pd.concat([ust, jgb], axis=1).sort_index().ffill().dropna()
    spread = aligned["US"] - aligned["JP"]
    spread.name = f"US-JP {maturity}"
    return spread.loc[pd.Timestamp(start_date) :]


def _parse_japanese_era_date(value: object) -> pd.Timestamp | pd.NaT:
    """例: S49.9.24 / H1.1.8 / R6.1.4 を西暦の日付に変換する。"""
    try:
        era_year, month, day = str(value).strip().split(".")
        era_offsets = {"S": 1925, "H": 1988, "R": 2018}
        return pd.Timestamp(
            year=era_offsets[era_year[0]] + int(era_year[1:]),
            month=int(month),
            day=int(day),
        )
    except (KeyError, TypeError, ValueError):
        return pd.NaT
