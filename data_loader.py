from __future__ import annotations

from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from io import StringIO
from io import BytesIO
import time
from typing import Callable, TypeVar

import pandas as pd
import requests
import streamlit as st
import yfinance as yf


MAX_FETCH_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 0.5
METI_IIP_SOURCE_URL = "https://www.meti.go.jp/statistics/tyo/iip/b2020_result-2.html"
METI_IIP_SEASONAL_URL = (
    "https://www.meti.go.jp/statistics/tyo/iip/xls/b2020_gsm1j.xlsx"
)
METI_IIP_ORIGINAL_URL = (
    "https://www.meti.go.jp/statistics/tyo/iip/xls/b2020_gom1j.xlsx"
)
METI_IIP_SEMICONDUCTOR_CODE = "1105000000"
METI_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; economic-dashboard/1.0; "
        "+https://github.com/nlqlzzz/economic-dashboard)"
    )
}
METI_IIP_SHEETS = {
    "生産": "生産",
    "出荷": "出荷",
    "在庫": "在庫",
    "在庫率": "在庫率",
}
LoadResult = TypeVar("LoadResult")


@dataclass(frozen=True)
class LoadFailure:
    source: str
    ticker: str
    error_type: str
    detail: str
    attempts: int


class SourceLoadError(ValueError):
    """単一のデータ元・ティッカーで取得に失敗したことを表す。"""

    def __init__(self, failure: LoadFailure):
        self.failure = failure
        super().__init__(_format_failure(failure))


class IndicatorDataError(ValueError):
    """一次・代替を含む全候補で取得に失敗したことを表す。"""

    def __init__(self, failures: list[LoadFailure]):
        self.failures = failures
        detail = " / ".join(_format_failure(failure) for failure in failures)
        super().__init__(f"全候補の取得に失敗しました: {detail}")


class DataUnavailableError(ValueError):
    """取得先が有効な時系列を返さなかったことを表す。"""


class RetryFailure(Exception):
    """再試行後の元例外と実際の試行回数を保持する。"""

    def __init__(self, error: Exception, attempts: int):
        self.error = error
        self.attempts = attempts
        super().__init__(str(error))


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def load_data(source: str, ticker: str, start_date: str) -> pd.Series:
    """設定されたデータソースから時系列を取得して返す。"""
    loaders: dict[str, Callable[[], pd.Series]] = {
        "fred": lambda: _load_fred(ticker, start_date),
        "yfinance": lambda: _load_yfinance(ticker, start_date),
        "mof_jgb": lambda: _load_mof_jgb(ticker, start_date),
        "us_jp_yield_spread": lambda: _load_us_jp_yield_spread(ticker, start_date),
    }
    if source not in loaders:
        raise ValueError(f"未対応のデータソースです: {source}")

    started_at = time.perf_counter()
    try:
        series, attempts = _load_with_retry(loaders[source])
    except RetryFailure as retry_failure:
        error = retry_failure.error
        raise SourceLoadError(
            LoadFailure(
                source=source,
                ticker=ticker,
                error_type=_classify_error(error),
                detail=str(error),
                attempts=retry_failure.attempts,
            )
        ) from error
    series.attrs.update(
        {
            "fetched_at": pd.Timestamp.now(tz="Asia/Tokyo"),
            "fetch_attempts": attempts,
            "fetch_duration_seconds": time.perf_counter() - started_at,
        }
    )
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
    failures: list[LoadFailure] = []
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
        except SourceLoadError as error:
            failures.append(error.failure)
        except Exception as error:
            failures.append(
                LoadFailure(
                    source=str(candidate["source"]),
                    ticker=str(candidate["ticker"]),
                    error_type=_classify_error(error),
                    detail=str(error),
                    attempts=int(getattr(error, "fetch_attempts", 1)),
                )
            )
    raise IndicatorDataError(failures)


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def load_meti_semiconductor_iip() -> pd.DataFrame:
    """METIの2020年基準IIPから電子部品・デバイス工業の4指数を返す。"""
    started_at = time.perf_counter()
    try:
        (frame, file_updated_at), attempts = _load_with_retry(
            _download_meti_semiconductor_iip
        )
    except RetryFailure as retry_failure:
        error = retry_failure.error
        raise SourceLoadError(
            LoadFailure(
                source="meti_iip",
                ticker=METI_IIP_SEMICONDUCTOR_CODE,
                error_type=_classify_error(error),
                detail=str(error),
                attempts=retry_failure.attempts,
            )
        ) from error
    frame.attrs.update(
        {
            "source": "経済産業省 鉱工業指数（2020年基準）",
            "source_url": METI_IIP_SOURCE_URL,
            "industry_code": METI_IIP_SEMICONDUCTOR_CODE,
            "fetched_at": pd.Timestamp.now(tz="Asia/Tokyo"),
            "file_updated_at": file_updated_at,
            "fetch_attempts": attempts,
            "fetch_duration_seconds": time.perf_counter() - started_at,
        }
    )
    return frame


def _load_with_retry(
    loader: Callable[[], LoadResult],
    maximum_attempts: int = MAX_FETCH_ATTEMPTS,
    retry_delay_seconds: float = RETRY_DELAY_SECONDS,
) -> tuple[LoadResult, int]:
    """一時障害だけを短く再試行し、成功した系列と試行回数を返す。"""
    if maximum_attempts < 1:
        raise ValueError("最大試行回数は1以上にしてください。")
    for attempt in range(1, maximum_attempts + 1):
        try:
            return loader(), attempt
        except Exception as error:
            if attempt == maximum_attempts or not _is_transient_error(error):
                raise RetryFailure(error, attempt) from error
            time.sleep(retry_delay_seconds)
    raise RuntimeError("データ取得の再試行が予期せず終了しました。")


def _download_meti_semiconductor_iip() -> tuple[pd.DataFrame, pd.Timestamp | None]:
    responses = {}
    for adjustment, url in {
        "季節調整済": METI_IIP_SEASONAL_URL,
        "原指数": METI_IIP_ORIGINAL_URL,
    }.items():
        response = requests.get(url, headers=METI_REQUEST_HEADERS, timeout=30)
        response.raise_for_status()
        if not response.content.startswith(b"PK"):
            content_type = response.headers.get("Content-Type", "unknown")
            raise requests.RequestException(
                f"METI returned a non-Excel response (Content-Type={content_type})."
            )
        responses[adjustment] = response

    series_by_column: dict[str, pd.Series] = {}
    for adjustment, response in responses.items():
        parsed = _parse_meti_iip_workbook(response.content)
        for indicator_name, series in parsed.items():
            series_by_column[f"{indicator_name}_{adjustment}"] = series
    frame = pd.concat(series_by_column, axis=1).sort_index()
    if frame.empty:
        raise DataUnavailableError("METIの電デバ鉱工業指数が空です。")

    updated_values = [
        _parse_http_datetime(response.headers.get("Last-Modified"))
        for response in responses.values()
    ]
    updated_values = [value for value in updated_values if value is not None]
    return frame, max(updated_values) if updated_values else None


def _parse_meti_iip_workbook(content: bytes) -> dict[str, pd.Series]:
    parsed: dict[str, pd.Series] = {}
    for indicator_name, sheet_name in METI_IIP_SHEETS.items():
        try:
            sheet = pd.read_excel(BytesIO(content), sheet_name=sheet_name, header=None)
        except Exception as error:
            raise DataUnavailableError(
                f"METI Excelの「{sheet_name}」シートを読み込めません: {error}"
            ) from error
        if len(sheet) < 4 or sheet.shape[1] < 4:
            raise DataUnavailableError(f"METI Excelの「{sheet_name}」シート形式が不正です。")

        codes = sheet.iloc[:, 0].map(_normalize_meti_code)
        matches = sheet.loc[codes == METI_IIP_SEMICONDUCTOR_CODE]
        if len(matches) != 1:
            raise DataUnavailableError(
                f"METI Excelで分類コード{METI_IIP_SEMICONDUCTOR_CODE}を一意に特定できません。"
            )
        dates = pd.to_datetime(
            sheet.iloc[2, 3:].map(_normalize_meti_code),
            format="%Y%m",
            errors="coerce",
        )
        values = pd.to_numeric(matches.iloc[0, 3:], errors="coerce")
        valid = dates.notna() & values.notna().to_numpy()
        series = pd.Series(
            values.to_numpy()[valid],
            index=pd.DatetimeIndex(dates[valid]),
            name=indicator_name,
            dtype=float,
        )
        parsed[indicator_name] = series[~series.index.duplicated(keep="last")]
    return parsed


def _normalize_meti_code(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def _parse_http_datetime(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    try:
        return pd.Timestamp(parsedate_to_datetime(value)).tz_convert("Asia/Tokyo")
    except (TypeError, ValueError):
        return None


def _is_transient_error(error: Exception) -> bool:
    if isinstance(
        error,
        (requests.Timeout, requests.ConnectionError, TimeoutError, ConnectionError),
    ):
        return True
    if isinstance(error, DataUnavailableError):
        return True
    if isinstance(error, requests.HTTPError):
        status_code = getattr(error.response, "status_code", None)
        return status_code in {408, 429} or (
            status_code is not None and 500 <= status_code < 600
        )
    message = str(error).lower()
    return any(
        marker in message
        for marker in ("timed out", "timeout", "temporarily unavailable", "rate limit")
    )


def _classify_error(error: Exception) -> str:
    if isinstance(error, (requests.Timeout, TimeoutError)):
        return "タイムアウト"
    if isinstance(error, (requests.ConnectionError, ConnectionError)):
        return "接続エラー"
    if isinstance(error, requests.HTTPError):
        status_code = getattr(error.response, "status_code", None)
        return f"HTTP {status_code}" if status_code is not None else "HTTPエラー"
    if isinstance(error, (KeyError, UnicodeError, pd.errors.ParserError)):
        return "データ形式エラー"
    if isinstance(error, DataUnavailableError):
        return "データなし"
    if isinstance(error, ValueError):
        return "データなし・設定エラー"
    return type(error).__name__


def _format_failure(failure: LoadFailure) -> str:
    return (
        f"データ元={failure.source}, ティッカー={failure.ticker}, "
        f"種別={failure.error_type}, 試行={failure.attempts}回, 詳細={failure.detail}"
    )


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
        raise DataUnavailableError(
            f"Yahoo Financeから「{ticker}」のデータを取得できませんでした。"
        )

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
