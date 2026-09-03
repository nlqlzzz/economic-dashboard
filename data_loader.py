from __future__ import annotations

from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO
from io import BytesIO
import os
import re
import time
from typing import Callable, TypeVar

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from global_semiconductor_demand import (
    parse_korea_customs_release,
    parse_korea_ict_monthly_release,
    parse_korea_monthly_trade_release,
    parse_taiwan_export_orders_csv,
)


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
ESTAT_API_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"
ESTAT_MACHINERY_ORDERS_TABLE_ID = "0003355226"
ESTAT_MACHINERY_ORDERS_SOURCE_URL = (
    "https://www.e-stat.go.jp/dbview?sid=0003355226"
)
ESTAT_MACHINERY_ORDERS_CLASS_NAME = "電子・通信機械_電子計算機等"
TAIWAN_EXPORT_ORDER_URLS = {
    "electronic": (
        "https://service.moea.gov.tw/EE520/opendata/"
        "%E7%B6%93%E6%BF%9F%E9%83%A8%E7%B5%B1%E8%A8%88%E8%99%95_"
        "%E5%A4%96%E9%8A%B7%E8%A8%82%E5%96%AE_"
        "%E9%9B%BB%E5%AD%90%E7%94%A2%E5%93%81.csv"
    ),
    "information_communication": (
        "https://service.moea.gov.tw/EE520/opendata/"
        "%E7%B6%93%E6%BF%9F%E9%83%A8%E7%B5%B1%E8%A8%88%E8%99%95_"
        "%E5%A4%96%E9%8A%B7%E8%A8%82%E5%96%AE_"
        "%E8%B3%87%E8%A8%8A%E9%80%9A%E8%A8%8A%E7%94%A2%E5%93%81.csv"
    ),
}
KOREA_CUSTOMS_LIST_URL = (
    "https://www.customs.go.kr/kcs/na/ntt/selectNttList.do?mi=2891&bbsId=1362"
)
KOREA_CUSTOMS_RSS_URL = (
    "https://www.customs.go.kr/kcs/selectBoardRss.do?mi=15265&bbsId=1362"
)
KOREA_CUSTOMS_BASE_URL = "https://www.customs.go.kr"
KOREA_MOTIR_PRESS_URL = "https://www.motir.go.kr/"
KOREA_MOTIR_PRESS_LIST_URL = (
    "https://www.motir.go.kr/kor/article/ATCL3f49a5a8c"
)
KOREA_MONTHLY_HISTORY_START = "2021-01-01"
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


class DataSchemaError(DataUnavailableError):
    """取得先の分類・構造が想定と一致しないことを表す。"""


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
def load_yfinance_batch(tickers: tuple[str, ...], start_date: str) -> pd.DataFrame:
    """複数の価格系列を一括取得し、取得できた銘柄だけを返す。"""
    if not tickers:
        return pd.DataFrame()
    unique_tickers = tuple(dict.fromkeys(tickers))
    started_at = time.perf_counter()
    try:
        frame, attempts = _load_with_retry(
            lambda: yf.download(
                list(unique_tickers),
                start=start_date,
                auto_adjust=True,
                progress=False,
                group_by="column",
                threads=True,
            )
        )
    except RetryFailure as retry_failure:
        error = retry_failure.error
        raise SourceLoadError(
            LoadFailure(
                source="yfinance_batch",
                ticker=",".join(unique_tickers),
                error_type=_classify_error(error),
                detail=str(error),
                attempts=retry_failure.attempts,
            )
        ) from error
    if frame.empty:
        raise DataUnavailableError("Yahoo Financeの一括価格データが空です。")

    close = frame["Close"] if "Close" in frame else pd.DataFrame()
    if isinstance(close, pd.Series):
        close = close.to_frame(name=unique_tickers[0])
    if not isinstance(close, pd.DataFrame):
        close = pd.DataFrame(close)
    close.index = pd.to_datetime(close.index).tz_localize(None)
    close = close.apply(pd.to_numeric, errors="coerce").sort_index()
    available = [ticker for ticker in unique_tickers if ticker in close and close[ticker].notna().any()]
    result = close.reindex(columns=available).dropna(how="all")
    result.attrs.update(
        {
            "source": "yfinance",
            "fetched_at": pd.Timestamp.now(tz="Asia/Tokyo"),
            "fetch_attempts": attempts,
            "fetch_duration_seconds": time.perf_counter() - started_at,
            "requested_tickers": list(unique_tickers),
            "missing_tickers": [ticker for ticker in unique_tickers if ticker not in available],
        }
    )
    return result


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


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def load_electronic_computer_orders() -> pd.Series:
    """e-Statから半導体製造装置を含む電子計算機等受注を返す。"""
    app_id = _get_estat_app_id()
    started_at = time.perf_counter()
    try:
        (series, released_at), attempts = _load_with_retry(
            lambda: _download_estat_electronic_computer_orders(app_id)
        )
    except RetryFailure as retry_failure:
        error = retry_failure.error
        raise SourceLoadError(
            LoadFailure(
                source="e-stat",
                ticker=ESTAT_MACHINERY_ORDERS_TABLE_ID,
                error_type=_classify_error(error),
                detail=str(error),
                attempts=retry_failure.attempts,
            )
        ) from error
    series.attrs.update(
        {
            "source": "e-Stat 機械受注統計調査（内閣府）",
            "source_url": ESTAT_MACHINERY_ORDERS_SOURCE_URL,
            "table_id": ESTAT_MACHINERY_ORDERS_TABLE_ID,
            "unit": "百万円",
            "seasonal_adjustment": "原系列",
            "official_series_name": ESTAT_MACHINERY_ORDERS_CLASS_NAME,
            "includes_semiconductor_equipment": True,
            "is_direct_semiconductor_series": False,
            "fetched_at": pd.Timestamp.now(tz="Asia/Tokyo"),
            "released_at": released_at,
            "fetch_attempts": attempts,
            "fetch_duration_seconds": time.perf_counter() - started_at,
        }
    )
    return series


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def load_taiwan_semiconductor_orders() -> pd.DataFrame:
    """台湾経済部の電子製品・情報通信製品輸出受注を返す。"""
    started_at = time.perf_counter()
    frames: list[pd.DataFrame] = []
    total_attempts = 0
    fetched_at = pd.Timestamp.now(tz="Asia/Tokyo")
    for series_key, url in TAIWAN_EXPORT_ORDER_URLS.items():
        try:
            response, attempts = _load_with_retry(lambda target=url: _download_bytes(target))
        except RetryFailure as retry_failure:
            error = retry_failure.error
            raise SourceLoadError(
                LoadFailure(
                    source="taiwan_moea",
                    ticker=series_key,
                    error_type=_classify_error(error),
                    detail=str(error),
                    attempts=retry_failure.attempts,
                )
            ) from error
        total_attempts += attempts
        try:
            frames.append(parse_taiwan_export_orders_csv(response, url, fetched_at))
        except ValueError as error:
            raise DataSchemaError(str(error)) from error
    result = pd.concat(frames, ignore_index=True)
    result.attrs.update(
        {
            "source": "台湾経済部 統計処 外銷訂單統計",
            "source_url": "https://data.gov.tw/dataset/16362",
            "fetched_at": fetched_at,
            "fetch_attempts": total_attempts,
            "fetch_duration_seconds": time.perf_counter() - started_at,
        }
    )
    return result


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def load_korea_semiconductor_exports() -> pd.DataFrame:
    """韓国公式発表から最新の1–10日、1–20日、月次半導体輸出を返す。"""
    started_at = time.perf_counter()
    fetched_at = pd.Timestamp.now(tz="Asia/Tokyo")
    found: dict[str, pd.DataFrame] = {}
    failures: list[str] = []
    article_attempts = 0
    try:
        article_links, discovery_attempts = _load_with_retry(_discover_korea_release_links)
    except RetryFailure as retry_failure:
        error = retry_failure.error
        article_links = []
        discovery_attempts = retry_failure.attempts
        failures.append(
            "韓国関税庁 速報探索: "
            f"{_classify_error(error)}（{retry_failure.attempts}回）: {error}"
        )
    for candidate in article_links:
        if len(found) == 3:
            break
        title, url, embedded_html = (
            (*candidate, None) if len(candidate) == 2 else candidate
        )
        try:
            parsed = None
            if embedded_html:
                try:
                    parsed = parse_korea_customs_release(
                        f"<h1>{title}</h1>{embedded_html}", url, fetched_at
                    )
                except (ValueError, DataSchemaError):
                    # RSS本文が要約だけの場合は、公式記事ページを取得して再試行する。
                    pass
            if parsed is None:
                html, attempts = _load_with_retry(
                    lambda target=url: _download_text(target)
                )
                article_attempts += attempts
                parsed = parse_korea_customs_release(html, url, fetched_at)
        except Exception as error:
            failures.append(f"{title}: {error}")
            continue
        primary = parsed[~parsed["is_derived"]].iloc[0]
        kind = str(primary["series_id"]).removeprefix("korea_semiconductor_exports_")
        if kind in {"1_10", "1_20", "monthly"} and kind not in found:
            found[kind] = parsed
    partial_reference_periods = [
        frame.loc[~frame["is_derived"], "reference_period"].max()
        for kind, frame in found.items()
        if kind in {"1_10", "1_20"}
    ]
    monthly_reference_period = (
        found["monthly"].loc[
            ~found["monthly"]["is_derived"], "reference_period"
        ].max()
        if "monthly" in found
        else pd.NaT
    )
    latest_partial_period = (
        max(partial_reference_periods) if partial_reference_periods else pd.NaT
    )
    monthly_primary = (
        found["monthly"].loc[~found["monthly"]["is_derived"]].iloc[-1]
        if "monthly" in found
        else None
    )
    monthly_is_missing_or_stale = "monthly" not in found or (
        pd.notna(latest_partial_period)
        and pd.notna(monthly_reference_period)
        and monthly_reference_period < latest_partial_period
    )
    monthly_needs_enrichment = monthly_is_missing_or_stale or (
        monthly_primary is not None and pd.isna(monthly_primary.get("yoy"))
    )
    if monthly_needs_enrichment:
        try:
            monthly_url, discovery_attempts_extra = _load_with_retry(
                _discover_korea_monthly_trade_release
            )
            discovery_attempts += discovery_attempts_extra
            monthly_html, attempts = _load_with_retry(
                lambda: _download_text(monthly_url)
            )
            article_attempts += attempts
            motir_monthly = parse_korea_monthly_trade_release(
                monthly_html, monthly_url, fetched_at
            )
            motir_period = motir_monthly.loc[
                ~motir_monthly["is_derived"], "reference_period"
            ].max()
            if (
                "monthly" not in found
                or pd.isna(monthly_reference_period)
                or motir_period >= monthly_reference_period
            ):
                found["monthly"] = motir_monthly
        except Exception as error:
            failures.append(f"韓国産業通商部 月次輸出入動向: {error}")
    missing = [kind for kind in ("1_10", "1_20", "monthly") if kind not in found]
    if not found:
        detail = " / ".join(failures[:3])
        raise DataUnavailableError(
            "韓国半導体輸出を1件も取得できません。"
            + (f"（{detail}）" if detail else "")
        )
    result = pd.concat(
        [found[kind] for kind in ("1_10", "1_20", "monthly") if kind in found],
        ignore_index=True,
    )
    result.attrs.update(
        {
            "source": "韓国関税庁 輸出入現況",
            "source_url": KOREA_CUSTOMS_LIST_URL,
            "fetched_at": fetched_at,
            "fetch_attempts": discovery_attempts + article_attempts,
            "fetch_duration_seconds": time.perf_counter() - started_at,
            "missing_periods": missing,
            "load_warnings": failures,
        }
    )
    return result


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def load_korea_semiconductor_monthly_history(
    start_date: str = KOREA_MONTHLY_HISTORY_START,
) -> pd.DataFrame:
    """産業通商部の月次公表履歴を実公表日付きで返す。"""
    started_at = time.perf_counter()
    fetched_at = pd.Timestamp.now(tz="Asia/Tokyo")
    try:
        links, discovery_attempts = _load_with_retry(
            lambda: _discover_korea_monthly_trade_releases(start_date)
        )
    except RetryFailure as retry_failure:
        error = retry_failure.error
        raise SourceLoadError(
            LoadFailure(
                source="korea_motir_monthly_history",
                ticker="semiconductor_exports",
                error_type=_classify_error(error),
                detail=str(error),
                attempts=retry_failure.attempts,
            )
        ) from error

    # ICT月次発表は半導体の金額・前年比を本文に持つ。一般の輸出入動向は
    # 添付資料だけの月が多いため、ICT発表が見つかった場合は不要な大量取得を避ける。
    ict_links = [
        link
        for link in links
        if "ICT" in link[0].upper() or "정보통신" in link[0]
    ]
    release_links = ict_links or links

    frames: list[pd.DataFrame] = []
    failures: list[str] = []

    def load_release(candidate: tuple[str, str]) -> pd.DataFrame:
        title, url = candidate
        html, _ = _load_with_retry(lambda: _download_text(url))
        try:
            parser = (
                parse_korea_ict_monthly_release
                if "ICT" in title.upper() or "정보통신" in title
                else parse_korea_monthly_trade_release
            )
            return parser(html, url, fetched_at)
        except ValueError as error:
            raise DataSchemaError(f"{title}: {error}") from error

    # 公式サイトへの同時接続を抑えつつ、初回の約5年分取得を現実的な時間に収める。
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(load_release, link): link for link in release_links
        }
        for future in as_completed(futures):
            title, _ = futures[future]
            try:
                frames.append(future.result())
            except Exception as error:
                failures.append(f"{title}: {error}")

    if not frames:
        detail = " / ".join(failures[:3])
        raise DataUnavailableError(
            "韓国産業通商部の月次半導体輸出履歴を取得できません。"
            + (f"（{detail}）" if detail else "")
        )
    result = pd.concat(frames, ignore_index=True)
    result["yoy"] = pd.to_numeric(result["yoy"], errors="coerce")
    result = result.dropna(subset=["yoy", "release_date"])
    if result.empty:
        raise DataUnavailableError(
            "韓国月次履歴に公式前年比と実公表日がそろった観測がありません。"
        )
    result = (
        result.sort_values(["reference_period", "release_date"], na_position="first")
        .drop_duplicates(["series_id", "reference_period"], keep="first")
        .reset_index(drop=True)
    )
    result.attrs.update(
        {
            "source": "韓国産業通商部 輸出入動向",
            "source_url": KOREA_MOTIR_PRESS_LIST_URL,
            "fetched_at": fetched_at,
            "fetch_attempts": discovery_attempts,
            "fetch_duration_seconds": time.perf_counter() - started_at,
            "discovered_release_count": len(links),
            "requested_release_count": len(release_links),
            "loaded_release_count": len(result),
            "load_warnings": failures,
        }
    )
    return result


def merge_korea_semiconductor_exports(
    latest: pd.DataFrame,
    monthly_history: pd.DataFrame,
) -> pd.DataFrame:
    """速報と月次履歴を結合し、同じ対象月は実公表日が新しい行を残す。"""
    available = [frame for frame in (monthly_history, latest) if not frame.empty]
    if not available:
        return pd.DataFrame()
    result = pd.concat(available, ignore_index=True)
    monthly_mask = result["series_id"].eq("korea_semiconductor_exports_monthly")
    valid_monthly_mask = monthly_mask & pd.to_numeric(
        result["yoy"], errors="coerce"
    ).notna()
    excluded_incomplete_monthly = 0
    if valid_monthly_mask.any():
        incomplete_monthly = monthly_mask & ~valid_monthly_mask
        excluded_incomplete_monthly = int(incomplete_monthly.sum())
        result = result.loc[~incomplete_monthly].copy()
    result = (
        result.sort_values(
            ["series_id", "reference_period", "release_date"],
            na_position="first",
        )
        .drop_duplicates(
            ["series_id", "reference_period", "is_derived"], keep="last"
        )
        .reset_index(drop=True)
    )
    history_warnings = monthly_history.attrs.get("load_warnings", [])
    latest_warnings = latest.attrs.get("load_warnings", [])
    result.attrs.update(latest.attrs)
    result.attrs.update(
        {
            "monthly_history_start": (
                result.loc[
                    result["series_id"].eq("korea_semiconductor_exports_monthly"),
                    "reference_period",
                ].min()
            ),
            "monthly_history_count": int(
                result["series_id"].eq("korea_semiconductor_exports_monthly").sum()
            ),
            "load_warnings": [*history_warnings, *latest_warnings],
            "excluded_incomplete_monthly": excluded_incomplete_monthly,
        }
    )
    return result


def _download_bytes(url: str) -> bytes:
    response = requests.get(url, headers=METI_REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    if not response.content:
        raise DataUnavailableError(f"公式データが空です: {url}")
    return response.content


def _download_text(url: str) -> str:
    response = requests.get(url, headers=METI_REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    if not response.text.strip():
        raise DataUnavailableError(f"公式ページが空です: {url}")
    return response.text


def _discover_korea_release_links() -> list[tuple[str, str, str | None]]:
    """関税庁の検索結果から半導体速報・月次発表候補を新しい順に返す。"""
    from html.parser import HTMLParser
    from urllib.parse import urljoin
    import xml.etree.ElementTree as ET

    class ArticleLinkParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.href: str | None = None
            self.parts: list[str] = []
            self.links: list[tuple[str, str]] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag.lower() != "a":
                return
            attributes = dict(attrs)
            article_id = attributes.get("data-id")
            article_token = attributes.get("data-url")
            if article_id and article_token:
                self.href = (
                    "/kcs/na/ntt/selectNttInfo.do?mi=2891&bbsId=1362"
                    f"&nttSn={article_id}&nttSnUrl={article_token}"
                )
                self.parts = []
                return
            href = attributes.get("href")
            if href and "selectNttInfo" in href:
                self.href = href
                self.parts = []
                return
            action = " ".join(
                value or "" for key, value in attrs if key in {"href", "onclick"}
            )
            article_id = re.search(r"(?:nttSn\D+|fnView\s*\(\s*['\"]?)(\d{6,})", action)
            if article_id:
                self.href = (
                    "/kcs/na/ntt/selectNttInfo.do?mi=2891&bbsId=1362&nttSn="
                    f"{article_id.group(1)}"
                )
                self.parts = []

        def handle_data(self, data: str) -> None:
            if self.href is not None:
                self.parts.append(data)

        def handle_endtag(self, tag: str) -> None:
            if tag.lower() == "a" and self.href is not None:
                title = " ".join("".join(self.parts).split())
                self.links.append((title, urljoin(KOREA_CUSTOMS_BASE_URL, self.href)))
                self.href = None
                self.parts = []

    collected: list[tuple[str, str, str | None]] = []
    seen: set[str] = set()
    rss_response = requests.get(
        KOREA_CUSTOMS_RSS_URL, headers=METI_REQUEST_HEADERS, timeout=20
    )
    rss_response.raise_for_status()
    try:
        root = ET.fromstring(rss_response.content)
    except ET.ParseError as error:
        raise DataSchemaError("韓国関税庁RSSの形式が不正です。") from error
    for item in root.findall(".//item"):
        title = " ".join((item.findtext("title") or "").split())
        url = (item.findtext("link") or "").strip()
        description = item.findtext("description") or ""
        if _korea_release_title_kind(title) and url and url not in seen:
            seen.add(url)
            # 新しい記事ではRSSリンクから本文が返らない場合があるため、
            # 公式RSSに埋め込まれた記事本文も候補とともに保持する。
            collected.append((title, url, description))

    if _has_all_korea_release_kinds(collected):
        return collected

    # RSSは最新記事を一定件数しか返さないため、同じ月の1–10日速報が
    # 既にフィード外でも拾えるよう一覧の1ページ目から確認する。
    for page_index in range(1, 4):
        response = requests.get(
            KOREA_CUSTOMS_LIST_URL,
            params={
                "pageIndex": page_index,
                "searchType": "sj",
                "searchValue": "수출입 현황",
            },
            headers=METI_REQUEST_HEADERS,
            timeout=20,
        )
        response.raise_for_status()
        parser = ArticleLinkParser()
        parser.feed(response.text)
        for title, url in parser.links:
            if not _korea_release_title_kind(title) or url in seen:
                continue
            seen.add(url)
            collected.append((title, url, None))
        if _has_all_korea_release_kinds(collected):
            break
    if not collected:
        raise DataUnavailableError("韓国関税庁の輸出入発表一覧を取得できません。")
    return collected


def _discover_korea_monthly_trade_release() -> str:
    """産業通商部の一覧から最新の月次輸出入動向URLを返す。"""
    from html.parser import HTMLParser
    from urllib.parse import urljoin

    class MonthlyLinkParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.href: str | None = None
            self.parts: list[str] = []
            self.links: list[tuple[str, str]] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag.lower() != "a":
                return
            href = dict(attrs).get("href")
            if href and "/kor/article/ATCL3f49a5a8c/" in href and href.endswith("/view"):
                self.href = href
                self.parts = []

        def handle_data(self, data: str) -> None:
            if self.href is not None:
                self.parts.append(data)

        def handle_endtag(self, tag: str) -> None:
            if tag.lower() == "a" and self.href is not None:
                self.links.append((" ".join("".join(self.parts).split()), self.href))
                self.href = None
                self.parts = []

    for page_url in (KOREA_MOTIR_PRESS_URL, KOREA_MOTIR_PRESS_LIST_URL):
        response = requests.get(
            page_url, headers=METI_REQUEST_HEADERS, timeout=20
        )
        response.raise_for_status()
        parser = MonthlyLinkParser()
        parser.feed(response.text)
        for title, href in parser.links:
            if re.search(r"20\d{2}년\s*\d{1,2}월\s*수출입\s*동향", title):
                return urljoin(page_url, href)
    # 現行一覧は詳細URLではなく javascript:article.view(id) を使うため、
    # アーカイブ用Parserを共通のフォールバックとして利用する。
    recent_start = (pd.Timestamp.now(tz="Asia/Tokyo") - pd.DateOffset(months=6))
    for title, url in _discover_korea_monthly_trade_releases(
        recent_start.strftime("%Y-%m-%d")
    ):
        if "ICT" not in title.upper() and "정보통신" not in title:
            return url
    raise DataUnavailableError("韓国産業通商部の最新月次輸出入動向を取得できません。")


def _discover_korea_monthly_trade_releases(
    start_date: str = KOREA_MONTHLY_HISTORY_START,
) -> list[tuple[str, str]]:
    """産業通商部の検索一覧から月次輸出入動向記事を新しい順に返す。"""
    from html import unescape
    from html.parser import HTMLParser
    from urllib.parse import urljoin

    class MonthlyArchiveParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.article_id: str | None = None
            self.parts: list[str] = []
            self.links: list[tuple[str, str]] = []
            self.article_count = 0

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag.lower() != "a":
                return
            action = " ".join(
                value or "" for key, value in attrs if key in {"href", "onclick"}
            )
            match = re.search(r"article\.view\(['\"]?(\d+)['\"]?\)", action)
            if match:
                self.article_count += 1
                self.article_id = match.group(1)
                self.parts = []

        def handle_data(self, data: str) -> None:
            if self.article_id is not None:
                self.parts.append(data)

        def handle_endtag(self, tag: str) -> None:
            if tag.lower() != "a" or self.article_id is None:
                return
            title = " ".join(unescape("".join(self.parts)).split())
            compact = re.sub(r"\s+", "", title)
            if (
                re.search(r"20\d{2}년\d{1,2}월", compact)
                and "수출입동향" in compact
            ):
                url = urljoin(
                    KOREA_MOTIR_PRESS_LIST_URL,
                    f"/kor/article/ATCL3f49a5a8c/{self.article_id}/view",
                )
                self.links.append((title, url))
            self.article_id = None
            self.parts = []

    start = pd.Timestamp(start_date)
    end = pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None).normalize()
    collected: list[tuple[str, str]] = []
    seen: set[str] = set()
    for page_index in range(1, 5):
        response = requests.get(
            KOREA_MOTIR_PRESS_LIST_URL,
            params={
                "pageIndex": page_index,
                "rowPageC": 100,
                "searchCondition": 1,
                "searchKeyword": "수출입 동향",
                "startDtD": start.strftime("%Y-%m-%d"),
                "endDtD": end.strftime("%Y-%m-%d"),
            },
            headers=METI_REQUEST_HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        parser = MonthlyArchiveParser()
        parser.feed(response.text)
        page_new = 0
        for title, url in parser.links:
            if url in seen:
                continue
            seen.add(url)
            collected.append((title, url))
            page_new += 1
        if parser.article_count < 100:
            break
    if not collected:
        raise DataUnavailableError("韓国産業通商部の月次輸出入動向履歴を探索できません。")
    return collected


def _has_all_korea_release_kinds(
    links: list[tuple[str, str] | tuple[str, str, str | None]],
) -> bool:
    return {
        kind
        for candidate in links
        if (kind := _korea_release_title_kind(candidate[0]))
    } == {
        "1_10",
        "1_20",
        "monthly",
    }


def _korea_release_title_kind(title: str) -> str | None:
    """半導体輸出を掲載する通常の速報・月次発表だけを識別する。"""
    compact = re.sub(r"\s+", "", title)
    if any(excluded in compact for excluded in ("기업규모별", "운송비용")):
        return None
    if re.search(r"1일[~∼\-].{0,5}10일수출입현황", compact):
        return "1_10"
    if re.search(r"1일[~∼\-].{0,5}20일수출입현황", compact):
        return "1_20"
    if re.search(r"20\d{2}년\d{1,2}월(?:월간)?수출입현황", compact):
        return "monthly"
    return None


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


def _get_estat_app_id() -> str:
    app_id = os.getenv("ESTAT_APP_ID", "").strip()
    if not app_id:
        try:
            app_id = str(st.secrets.get("ESTAT_APP_ID", "")).strip()
        except Exception:
            app_id = ""
    if not app_id:
        raise DataUnavailableError(
            "e-Stat APIの利用にはStreamlit Secretsまたは環境変数の"
            "ESTAT_APP_ID設定が必要です。"
        )
    return app_id


def _download_estat_electronic_computer_orders(
    app_id: str,
) -> tuple[pd.Series, pd.Timestamp | None]:
    response = requests.get(
        ESTAT_API_URL,
        params={
            "appId": app_id,
            "statsDataId": ESTAT_MACHINERY_ORDERS_TABLE_ID,
            "metaGetFlg": "Y",
            "cntGetFlg": "N",
        },
        timeout=30,
    )
    if response.status_code >= 400:
        raise requests.HTTPError(f"e-Stat API HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as error:
        raise requests.RequestException("e-Stat APIがJSON以外を返しました。") from error
    return _parse_estat_electronic_computer_orders(payload)


def _parse_estat_electronic_computer_orders(
    payload: dict[str, object],
) -> tuple[pd.Series, pd.Timestamp | None]:
    root = payload.get("GET_STATS_DATA", {})
    result = root.get("RESULT", {}) if isinstance(root, dict) else {}
    status = str(result.get("STATUS", "")) if isinstance(result, dict) else ""
    if status != "0":
        raise DataUnavailableError(
            f"e-Stat APIエラー（status={status or 'unknown'}）。"
        )
    statistical_data = root.get("STATISTICAL_DATA", {})
    if not isinstance(statistical_data, dict):
        raise DataUnavailableError("e-Stat APIの統計データ形式が不正です。")

    class_inf = statistical_data.get("CLASS_INF", {})
    class_objects = class_inf.get("CLASS_OBJ", []) if isinstance(class_inf, dict) else []
    if isinstance(class_objects, dict):
        class_objects = [class_objects]
    machine_dimension = _find_estat_dimension(class_objects, "機種分類")
    time_dimension = _find_estat_dimension(class_objects, "時間軸")
    machine_classes = machine_dimension.get("CLASS", [])
    time_classes = time_dimension.get("CLASS", [])
    if isinstance(machine_classes, dict):
        machine_classes = [machine_classes]
    if isinstance(time_classes, dict):
        time_classes = [time_classes]
    machine_matches = [
        item
        for item in machine_classes
        if isinstance(item, dict)
        and str(item.get("@name", "")) == ESTAT_MACHINERY_ORDERS_CLASS_NAME
    ]
    if len(machine_matches) != 1:
        raise DataSchemaError(
            "e-Statで電子計算機等の受注系列を一意に特定できません。"
        )
    machine_code = str(machine_matches[0].get("@code", ""))
    machine_dimension_id = str(machine_dimension.get("@id", ""))
    time_dimension_id = str(time_dimension.get("@id", ""))
    time_names = {
        str(item.get("@code", "")): str(item.get("@name", ""))
        for item in time_classes
        if isinstance(item, dict)
    }

    data_inf = statistical_data.get("DATA_INF", {})
    values = data_inf.get("VALUE", []) if isinstance(data_inf, dict) else []
    if isinstance(values, dict):
        values = [values]
    observations: dict[pd.Timestamp, float] = {}
    for item in values:
        if not isinstance(item, dict) or str(item.get(f"@{machine_dimension_id}")) != machine_code:
            continue
        time_code = str(item.get(f"@{time_dimension_id}", ""))
        target_date = pd.to_datetime(
            time_names.get(time_code, ""), format="%Y年%m月", errors="coerce"
        )
        value = pd.to_numeric(item.get("$"), errors="coerce")
        if pd.notna(target_date) and pd.notna(value):
            observations[pd.Timestamp(target_date)] = float(value)
    if not observations:
        raise DataUnavailableError("e-Statの電子計算機等受注系列が空です。")
    series = pd.Series(
        observations,
        name="電子計算機等受注（半導体製造装置を含む）",
        dtype=float,
    ).sort_index()

    table_inf = statistical_data.get("TABLE_INF", {})
    updated_date = table_inf.get("UPDATED_DATE") if isinstance(table_inf, dict) else None
    released_at = pd.to_datetime(updated_date, errors="coerce")
    return series, None if pd.isna(released_at) else pd.Timestamp(released_at)


def _find_estat_dimension(
    class_objects: list[object], name_fragment: str
) -> dict[str, object]:
    matches = [
        item
        for item in class_objects
        if isinstance(item, dict) and name_fragment in str(item.get("@name", ""))
    ]
    if len(matches) != 1:
        raise DataSchemaError(
            f"e-Statメタ情報の{name_fragment}を一意に特定できません。"
        )
    return matches[0]


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
    if isinstance(error, DataSchemaError):
        return False
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
