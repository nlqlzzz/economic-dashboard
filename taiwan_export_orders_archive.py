from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
import json
import re
import time
import unicodedata
from urllib.parse import urljoin

import pandas as pd
import requests

from global_semiconductor_demand import (
    SEMICONDUCTOR_DATA_COLUMNS,
    TAIWAN_SERIES,
    empty_semiconductor_frame,
)


TAIWAN_EXPORT_ORDERS_ARCHIVE_URL = (
    "https://www.moea.gov.tw/Mns/dos/content/ContentLink.aspx?menu_id=9423"
)
TAIWAN_EXPORT_ORDERS_NEWS_ARCHIVE_URL = (
    "https://www.moea.gov.tw/MNS/populace/news/News.aspx"
    "?kind=1&menu_id=40&history=y"
)
TAIWAN_ARCHIVE_DEFAULT_START = pd.Timestamp("2021-01-01")
TAIWAN_ARCHIVE_MIN_REQUEST_INTERVAL_SECONDS = 3.0
TAIWAN_ARCHIVE_429_BACKOFF_SECONDS = (5.0, 15.0, 30.0)
TAIWAN_ARCHIVE_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; economic-dashboard/1.0; "
        "+https://github.com/nlqlzzz/economic-dashboard)"
    )
}
# 公式news historyのローリング範囲外だが、PR84で公式新聞稿をlive確認済み。
# 一般公表ルールから推定せず、確認済みの日付だけをlegacy manifestに置く。
TAIWAN_ARCHIVE_VERIFIED_LEGACY_RELEASE_DATES = {
    pd.Timestamp("2021-01-01"): pd.Timestamp("2021-02-24"),
}
TAIWAN_ARCHIVE_SNAPSHOT_PATH = Path(__file__).resolve().parent / "data" / "taiwan_export_orders_archive.csv"
TAIWAN_ARCHIVE_MANIFEST_PATH = Path(__file__).resolve().parent / "data" / "taiwan_export_orders_archive_manifest.json"
TAIWAN_ARCHIVE_SERIES_IDS = {series_id for series_id, _ in TAIWAN_SERIES.values()}


@dataclass(frozen=True)
class TaiwanArchiveRelease:
    reference_period: pd.Timestamp
    article_url: str
    title: str


class TaiwanArchiveHttpClient:
    """台湾archiveだけを低速取得し、429をbounded retryする。"""

    def __init__(
        self,
        *,
        minimum_interval_seconds: float = TAIWAN_ARCHIVE_MIN_REQUEST_INTERVAL_SECONDS,
        backoff_seconds: tuple[float, ...] = TAIWAN_ARCHIVE_429_BACKOFF_SECONDS,
        session: requests.Session | None = None,
        sleeper=time.sleep,
        clock=time.monotonic,
    ) -> None:
        self.minimum_interval_seconds = minimum_interval_seconds
        self.backoff_seconds = backoff_seconds
        self.session = session or requests.Session()
        self.sleeper = sleeper
        self.clock = clock
        self._last_request_at: float | None = None

    def get_text(self, url: str) -> str:
        response = self._request(url)
        try:
            text = response.content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = response.text
        if not text.strip():
            raise ValueError(f"台湾archive公式ページが空です: {url}")
        return text

    def get_attachment(self, url: str) -> tuple[bytes, str]:
        response = self._request(url)
        content = response.content
        content_type = response.headers.get("Content-Type", "unknown")
        if not (content.startswith(b"%PDF") or content.startswith(b"PK")):
            raise ValueError(
                "台湾archive添付がPDF/XLSXではありません"
                f"（Content-Type={content_type}）。"
            )
        return content, content_type

    def post_text(self, url: str, data: dict[str, str]) -> str:
        response = self._request(url, data=data)
        try:
            text = response.content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = response.text
        if not text.strip():
            raise ValueError(f"台湾archive公式検索結果が空です: {url}")
        return text

    def _request(
        self, url: str, *, data: dict[str, str] | None = None
    ) -> requests.Response:
        maximum_attempts = 1 + len(self.backoff_seconds)
        for attempt in range(maximum_attempts):
            self._wait_for_request_slot()
            headers = dict(TAIWAN_ARCHIVE_REQUEST_HEADERS)
            if data is None:
                response = self.session.get(url, headers=headers, timeout=30)
            else:
                headers.update({"Referer": url, "Origin": "https://www.moea.gov.tw"})
                response = self.session.post(
                    url, data=data, headers=headers, timeout=30
                )
            self._last_request_at = self.clock()
            if response.status_code != 429:
                response.raise_for_status()
                return response
            if attempt == maximum_attempts - 1:
                response.raise_for_status()
            retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
            self.sleeper(
                retry_after
                if retry_after is not None
                else self.backoff_seconds[attempt]
            )
        raise RuntimeError("台湾archiveの429 retryが予期せず終了しました。")

    def _wait_for_request_slot(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = self.clock() - self._last_request_at
        remaining = self.minimum_interval_seconds - elapsed
        if remaining > 0:
            self.sleeper(remaining)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current: dict[str, str] | None = None
        self.parts: list[str] = []
        self.links: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered == "img" and self.current is not None:
            image_attrs = {key.lower(): value or "" for key, value in attrs}
            if image_attrs.get("alt"):
                self.parts.append(image_attrs["alt"])
            return
        if lowered != "a":
            return
        self.current = {key.lower(): value or "" for key, value in attrs}
        self.parts = []

    def handle_data(self, data: str) -> None:
        if self.current is not None:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self.current is not None:
            self.links.append((" ".join(self.parts), self.current))
            self.current = None
            self.parts = []


class _HiddenInputParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "input":
            return
        attributes = {key.lower(): value or "" for key, value in attrs}
        if attributes.get("type", "").lower() != "hidden" or not attributes.get("name"):
            return
        self.values[attributes["name"]] = attributes.get("value", "")


def discover_taiwan_export_order_releases(
    html: str,
    source_url: str = TAIWAN_EXPORT_ORDERS_ARCHIVE_URL,
    start_period: str | pd.Timestamp = TAIWAN_ARCHIVE_DEFAULT_START,
    end_period: str | pd.Timestamp | None = None,
) -> list[TaiwanArchiveRelease]:
    """公式archive HTMLに実在する月次リンクだけを返す。"""
    start = pd.Timestamp(start_period).to_period("M").to_timestamp()
    end = (
        pd.Timestamp(end_period).to_period("M").to_timestamp()
        if end_period is not None
        else pd.Timestamp.max.to_period("M").to_timestamp()
    )
    if start < TAIWAN_ARCHIVE_DEFAULT_START:
        raise ValueError("台湾archive loaderの対応開始月は2021-01です。")
    if end < start:
        raise ValueError("end_periodはstart_period以降を指定してください。")

    parser = _LinkParser()
    parser.feed(html)
    releases: dict[pd.Timestamp, tuple[int, TaiwanArchiveRelease]] = {}
    for raw_title, attrs in parser.links:
        title = _compact_text(raw_title or attrs.get("title", ""))
        period = _parse_roc_month(title)
        if period is None or not (start <= period <= end):
            continue
        href = attrs.get("href", "").strip()
        if not href or href.lower().startswith("javascript:") or href == "#":
            # data-url等が公式HTMLに明示される場合だけ採用する。数値IDは生成しない。
            href = next(
                (
                    attrs[key].strip()
                    for key in ("data-url", "data-href")
                    if attrs.get(key, "").strip()
                ),
                "",
            )
        if not href:
            continue
        article_url = urljoin(source_url, unescape(href))
        if article_url.lower().startswith(("http://", "https://")):
            candidate = TaiwanArchiveRelease(period, article_url, title)
            priority = _archive_link_priority(article_url)
            current = releases.get(period)
            if current is None or priority < current[0]:
                releases[period] = (priority, candidate)
    return [releases[period][1] for period in sorted(releases)]


def _archive_link_priority(url: str) -> int:
    """同月の公式リンクでは記事を表・旧file handlerより優先する。"""
    lowered = url.lower()
    if "news.aspx" in lowered:
        return 0
    if "whandnews_file.ashx" in lowered:
        return 1
    if "whandpublish_file.ashx" in lowered:
        return 2
    if "whandmenufile.ashx" in lowered:
        return 3
    return 4


def build_taiwan_news_archive_search_form(
    html: str, reference_period: pd.Timestamp
) -> dict[str, str]:
    """公式news archiveのhidden stateを保ち、対象月の完全な記事名で検索する。"""
    parser = _HiddenInputParser()
    parser.feed(html)
    if "__VIEWSTATE" not in parser.values:
        raise ValueError("台湾公式news archiveの検索form schemaが変わりました。")
    roc_year = reference_period.year - 1911
    query = f"{roc_year}年{reference_period.month}月外銷訂單統計"
    parser.values.update(
        {
            "ctl00$holderContent$txtQ_Title": query,
            "ctl00$holderContent$uctlQ_PageSize$ddlQ_PageSize": "30",
            "ctl00$holderContent$btnQuery": "查詢",
        }
    )
    return parser.values


def parse_taiwan_news_archive_search_result(
    html: str, reference_period: pd.Timestamp, source_url: str
) -> str:
    """公式検索結果に明示された対象月の記事URLだけを返す。"""
    parser = _LinkParser()
    parser.feed(html)
    expected = f"{reference_period.year - 1911}年{reference_period.month}月外銷訂單統計"
    for raw_title, attrs in parser.links:
        title = _compact_text(raw_title or attrs.get("title", ""))
        href = attrs.get("href", "").strip()
        if title != expected or "news.aspx" not in href.lower() or "news_id=" not in href.lower():
            continue
        return urljoin(source_url, unescape(href))
    raise ValueError(f"台湾公式news archiveで{reference_period:%Y-%m}の記事を発見できません。")


def parse_taiwan_archive_article(
    html: str,
    article_url: str,
) -> tuple[pd.Timestamp, pd.Timestamp, str]:
    """記事ページから対象月、公表日時、公式添付URLを得る。"""
    text = _html_to_text(html)
    period = _parse_roc_month(text)
    if period is None:
        raise ValueError("台湾archive記事から対象月を特定できません。")
    release_date = _parse_release_timestamp(text)
    if release_date is None:
        raise ValueError("台湾archive記事から実公表日を確認できません。")

    parser = _LinkParser()
    parser.feed(html)
    candidates: list[tuple[int, str]] = []
    for raw_label, attrs in parser.links:
        href = attrs.get("href", "").strip()
        label = _compact_text(raw_label + " " + attrs.get("title", ""))
        if not href or "whandnews_file.ashx" not in href.lower():
            continue
        lowered = label.lower()
        # 商品別の文章形式が2021年以降で安定している「新聞稿」PDFを優先する。
        # 全表XLSXは年によってsheet配置が異なるため、安全な構造検知後のfallbackとする。
        if "新聞稿" in label and "全部附表" not in label and "pdf" in lowered:
            priority = 0
        elif "xlsx" in lowered or href.lower().endswith(".xlsx"):
            priority = 1
        elif "ods" in lowered or href.lower().endswith(".ods"):
            priority = 2
        elif "pdf" in lowered:
            priority = 3
        else:
            continue
        candidates.append((priority, urljoin(article_url, unescape(href))))
    if not candidates:
        raise ValueError("台湾archive記事から公式添付を特定できません。")
    return period, release_date, sorted(candidates)[0][1]


def parse_taiwan_export_orders_archive_text(
    text: str,
    source_url: str,
    fetched_at: pd.Timestamp,
    *,
    reference_period: pd.Timestamp | None = None,
    release_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """当時の公式ニュースリリース本文をpoint-in-time行へ変換する。"""
    normalized = _compact_text(text)
    period = reference_period or _parse_roc_month(normalized)
    released = release_date or _parse_release_timestamp(normalized)
    if period is None:
        raise ValueError("台湾archive資料から対象月を特定できません。")
    if released is None:
        raise ValueError("台湾archive資料に実公表日がありません。")

    rows: list[dict[str, object]] = []
    for product, (series_id, series_name) in TAIWAN_SERIES.items():
        product_pattern = (
            r"資訊(?:與|及)?通信(?:產品)?" if product == "資訊與通信產品" else r"電子產品"
        )
        heading = re.search(
            product_pattern + r"\s*[：:]\s*",
            normalized,
        )
        if heading is None:
            raise ValueError(f"台湾archive資料から{product}の金額・前年比を抽出できません。")
        # Older releases may place several explanatory sentences between the amount and
        # official YoY.  Search only within this product's numbered paragraph so a
        # cumulative or another product's YoY can never be captured accidentally.
        tail = normalized[heading.end():]
        next_heading = re.search(
            r"(?:^|\s)\d+[\.、]\s*(?:資訊(?:與|及)?通信(?:產品)?|電子產品|光學器材|基本金屬|機械)",
            tail,
        )
        section = tail[: next_heading.start()] if next_heading else tail[:1200]
        amount = re.search(r"([0-9,]+(?:\.[0-9]+)?)\s*億\s*美元", section)
        official_yoy = re.search(
            r"較\s*上\s*年\s*同\s*月\s*(增|減)\s*([0-9]+(?:\.[0-9]+)?)\s*%",
            section,
        )
        if amount is None or official_yoy is None:
            raise ValueError(f"台湾archive資料から{product}の金額・前年比を抽出できません。")
        amount_hundred_million = float(amount.group(1).replace(",", ""))
        yoy = float(official_yoy.group(2)) * (1 if official_yoy.group(1) == "增" else -1)
        rows.append(
            {
                "region": "Taiwan",
                "series_id": series_id,
                "series_name": series_name,
                "reference_period": period,
                "release_date": released,
                "value": round(amount_hundred_million * 100, 6),
                "unit": "million USD",
                "yoy": yoy,
                "frequency": "monthly",
                "source_name": "台湾経済部 統計処 外銷訂單統計速報",
                "source_url": source_url,
                "publication_stage": "official_monthly_release",
                "is_partial_period": False,
                "period_start": period,
                "period_end": period + pd.offsets.MonthEnd(0),
                "working_days": None,
                "fetched_at": fetched_at,
                "currency": "USD",
                "is_derived": False,
                "data_vintage": "as_published_monthly_release",
                "yoy_is_derived": False,
            }
        )
    return pd.DataFrame(rows, columns=SEMICONDUCTOR_DATA_COLUMNS)


def parse_taiwan_export_orders_archive_attachment(
    content: bytes,
    source_url: str,
    fetched_at: pd.Timestamp,
    *,
    reference_period: pd.Timestamp,
    release_date: pd.Timestamp | None,
) -> pd.DataFrame:
    """XLSXまたはテキストPDFから当時値を抽出する。OCRは行わない。"""
    if content.startswith(b"PK"):
        text = _spreadsheet_to_text(content)
    elif content.startswith(b"%PDF"):
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise ValueError("PDF解析にはpypdfが必要です。") from error
        reader = PdfReader(BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if not text.strip():
            raise ValueError("台湾archive PDFに抽出可能なテキストがありません。")
    else:
        raise ValueError("台湾archive添付がXLSX/PDFではありません。")
    frame = parse_taiwan_export_orders_archive_text(
        text,
        source_url,
        fetched_at,
        reference_period=reference_period,
        release_date=release_date,
    )
    frame.attrs["attachment_sha256"] = sha256(content).hexdigest()
    return frame


def empty_taiwan_archive_frame() -> pd.DataFrame:
    frame = empty_semiconductor_frame()
    frame.attrs.update({"failures": [], "attachment_hashes": {}})
    return frame


def load_taiwan_archive_snapshot(
    path: str | Path = TAIWAN_ARCHIVE_SNAPSHOT_PATH,
) -> pd.DataFrame:
    """Read the committed point-in-time snapshot without network access."""
    source = Path(path)
    if not source.exists():
        raise ValueError(f"台湾archive snapshotがありません: {source}")
    frame = pd.read_csv(source)
    if tuple(frame.columns) != SEMICONDUCTOR_DATA_COLUMNS:
        raise ValueError("台湾archive snapshotの列構造が想定と一致しません。")
    for column in ("reference_period", "release_date", "period_start", "period_end", "fetched_at"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    for column in ("value", "yoy", "working_days"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ("is_partial_period", "is_derived", "yoy_is_derived"):
        frame[column] = frame[column].map(_parse_snapshot_boolean)
    validate_taiwan_archive_snapshot(frame)
    return frame.sort_values(["reference_period", "series_id"]).reset_index(drop=True)


def validate_taiwan_archive_snapshot(frame: pd.DataFrame) -> None:
    """Fail closed when a committed strict snapshot loses PIT provenance."""
    if tuple(frame.columns) != SEMICONDUCTOR_DATA_COLUMNS:
        raise ValueError("台湾archive snapshotのschemaが不正です。")
    if frame.empty:
        raise ValueError("台湾archive snapshotが空です。")
    if set(frame["series_id"]) != TAIWAN_ARCHIVE_SERIES_IDS or set(frame["region"]) != {"Taiwan"}:
        raise ValueError("台湾archive snapshotに対象外系列があります。")
    required = ["reference_period", "release_date", "value", "yoy", "source_url"]
    if frame[required].isna().any().any() or frame["source_url"].astype(str).str.strip().eq("").any():
        raise ValueError("台湾archive snapshotにstrict必須値の欠損があります。")
    if not frame["publication_stage"].eq("official_monthly_release").all():
        raise ValueError("台湾archive snapshotのpublication_stageが不正です。")
    if not frame["data_vintage"].eq("as_published_monthly_release").all():
        raise ValueError("台湾archive snapshotのdata_vintageが不正です。")
    if frame["is_derived"].any() or frame["is_partial_period"].any() or frame["yoy_is_derived"].any():
        raise ValueError("台湾archive snapshotに派生値または部分期間があります。")
    if frame.duplicated(["reference_period", "series_id"]).any():
        raise ValueError("台湾archive snapshotに対象月・系列の重複があります。")
    per_month = frame.groupby("reference_period")["series_id"].agg(lambda values: set(values))
    if not per_month.map(lambda values: values == TAIWAN_ARCHIVE_SERIES_IDS).all():
        raise ValueError("台湾archive snapshotに2系列が揃わない月があります。")


def load_taiwan_archive_manifest(
    path: str | Path = TAIWAN_ARCHIVE_MANIFEST_PATH,
) -> dict[str, object]:
    source = Path(path)
    if not source.exists():
        raise ValueError(f"台湾archive manifestがありません: {source}")
    return json.loads(source.read_text(encoding="utf-8"))


def _parse_snapshot_boolean(value: object) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    raise ValueError(f"台湾archive snapshotのboolean値が不正です: {value}")


def _spreadsheet_to_text(content: bytes) -> str:
    try:
        sheets = pd.read_excel(BytesIO(content), sheet_name=None, header=None)
    except Exception as error:
        raise ValueError("台湾archive XLSXを読み取れません。") from error
    if not sheets:
        raise ValueError("台湾archive XLSXにsheetがありません。")
    return "\n".join(
        " ".join(str(value) for value in row if pd.notna(value))
        for frame in sheets.values()
        for row in frame.itertuples(index=False, name=None)
    )


def _parse_roc_month(text: str) -> pd.Timestamp | None:
    match = re.search(r"(?<!\d)(1\d{2})\s*年\s*(1[0-2]|0?[1-9])\s*月", text)
    if match is None:
        return None
    return pd.Timestamp(year=int(match.group(1)) + 1911, month=int(match.group(2)), day=1)


def _parse_release_timestamp(text: str) -> pd.Timestamp | None:
    western = re.search(
        r"(?<!\d)(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})"
        r"(?:\s+(\d{1,2}):(\d{2}))?",
        text,
    )
    if western:
        year, month, day = map(int, western.group(1, 2, 3))
        hour = int(western.group(4)) if western.group(4) is not None else 0
        minute = int(western.group(5)) if western.group(5) is not None else 0
        return pd.Timestamp(year=year, month=month, day=day, hour=hour, minute=minute)
    roc = re.search(
        r"(?:DATE\s*)?(1\d{2})[年.]\s*(\d{1,2})[月.]\s*(\d{1,2})(?:\s*日)?"
        r"(?:\s*(?:下午)?\s*(\d{1,2}):(\d{2}))?",
        text,
        flags=re.I,
    )
    if roc:
        year = int(roc.group(1)) + 1911
        hour = int(roc.group(4)) if roc.group(4) is not None else 0
        if "下午" in roc.group(0) and hour < 12:
            hour += 12
        minute = int(roc.group(5)) if roc.group(5) is not None else 0
        return pd.Timestamp(year, int(roc.group(2)), int(roc.group(3)), hour, minute)
    return None


def _html_to_text(html: str) -> str:
    return _compact_text(re.sub(r"<[^>]+>", " ", unescape(html)))


def _compact_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", unescape(str(value)))
    return re.sub(r"\s+", " ", normalized).strip()


def _retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    return max(0.0, seconds)
