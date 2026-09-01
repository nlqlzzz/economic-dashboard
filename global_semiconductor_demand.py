from __future__ import annotations

from html import unescape
from io import BytesIO
import re
import unicodedata

import pandas as pd


SEMICONDUCTOR_DATA_COLUMNS = (
    "region",
    "series_id",
    "series_name",
    "reference_period",
    "release_date",
    "value",
    "unit",
    "yoy",
    "frequency",
    "source_name",
    "source_url",
    "publication_stage",
    "is_partial_period",
    "period_start",
    "period_end",
    "working_days",
    "fetched_at",
    "currency",
    "is_derived",
    "data_vintage",
    "yoy_is_derived",
)

TAIWAN_SERIES = {
    "電子產品": ("taiwan_electronic_export_orders", "台湾 電子製品輸出受注"),
    "資訊與通信產品": (
        "taiwan_information_communication_export_orders",
        "台湾 情報通信製品輸出受注",
    ),
}


def empty_semiconductor_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=SEMICONDUCTOR_DATA_COLUMNS)


def parse_taiwan_export_orders_csv(
    content: bytes,
    source_url: str,
    fetched_at: pd.Timestamp,
) -> pd.DataFrame:
    """台湾経済部の外銷訂單CSVを共通形式へ変換する。"""
    try:
        raw = pd.read_csv(BytesIO(content), encoding="utf-8-sig")
    except Exception as error:
        raise ValueError("台湾輸出受注CSVを読み取れません。") from error
    required = {"統計項目", "貨品別", "資料期(民國年)", "統計值(金額)", "計量單位"}
    if not required.issubset(raw.columns):
        raise ValueError("台湾輸出受注CSVの列構造が想定と一致しません。")

    raw = raw[raw["統計項目"].astype(str).str.contains("外銷訂單金額_美元", na=False)]
    rows: list[dict[str, object]] = []
    for _, item in raw.iterrows():
        product = str(item["貨品別"]).strip()
        if product not in TAIWAN_SERIES:
            continue
        period = _parse_taiwan_period(item["資料期(民國年)"])
        value = pd.to_numeric(item["統計值(金額)"], errors="coerce")
        if period is None or pd.isna(value):
            continue
        series_id, series_name = TAIWAN_SERIES[product]
        rows.append(
            {
                "region": "Taiwan",
                "series_id": series_id,
                "series_name": series_name,
                "reference_period": period,
                "release_date": pd.NaT,
                "value": float(value),
                "unit": "million USD",
                "yoy": None,
                "frequency": "monthly",
                "source_name": "台湾経済部 統計処 外銷訂單統計",
                "source_url": source_url,
                "publication_stage": "official_monthly",
                "is_partial_period": False,
                "period_start": period,
                "period_end": period + pd.offsets.MonthEnd(0),
                "working_days": None,
                "fetched_at": fetched_at,
                "currency": "USD",
                "is_derived": False,
                "data_vintage": None,
                "yoy_is_derived": True,
            }
        )
    frame = pd.DataFrame(rows, columns=SEMICONDUCTOR_DATA_COLUMNS)
    if frame.empty:
        raise ValueError("台湾輸出受注CSVに対象系列がありません。")
    frame = frame.sort_values(["series_id", "reference_period"]).reset_index(drop=True)
    frame["yoy"] = frame.groupby("series_id", sort=False)["value"].pct_change(
        12, fill_method=None
    ) * 100
    return frame


def parse_korea_customs_release(
    html: str,
    source_url: str,
    fetched_at: pd.Timestamp,
) -> pd.DataFrame:
    """韓国関税庁の公式発表から半導体輸出を抽出する。"""
    text = _html_to_text(html)
    period = _parse_korea_period(text)
    amount_match = re.search(
        r"반도체(?:\s*수출)?\s*\(\s*([0-9]+(?:\.[0-9]+)?)\s*억\s*달러\s*\)",
        text,
    )
    yoy_matches = re.findall(
        r"반도체\s*\(\s*([△▲+\-−]?\s*[0-9]+(?:\.[0-9]+)?)\s*%\s*\)", text
    )
    if period is None or amount_match is None:
        raise ValueError("韓国関税庁発表から半導体輸出を特定できません。")

    release_match = re.search(r"등록일\s*(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    release_date = (
        pd.Timestamp(*map(int, release_match.groups())) if release_match else pd.NaT
    )
    # 半導体単独の前年比は画像だけで提供される月がある。本文にない値は推測しない。
    yoy = _parse_signed_number(yoy_matches[0]) if yoy_matches else None
    amount_million_usd = float(amount_match.group(1)) * 100
    stage = _korea_publication_stage(text, period[2])
    current_days, previous_days = _parse_working_days(text)
    period_start, period_end, partial_kind = period
    primary = {
        "region": "Korea",
        "series_id": f"korea_semiconductor_exports_{partial_kind}",
        "series_name": f"韓国 半導体輸出（{_period_label(partial_kind)}）",
        "reference_period": period_start.to_period("M").to_timestamp(),
        "release_date": release_date,
        "value": amount_million_usd,
        "unit": "million USD",
        "yoy": yoy,
        "frequency": "monthly",
        "source_name": "韓国関税庁 輸出入現況",
        "source_url": source_url,
        "publication_stage": stage,
        "is_partial_period": partial_kind != "monthly",
        "period_start": period_start,
        "period_end": period_end,
        "working_days": current_days,
        "fetched_at": fetched_at,
        "currency": "USD",
        "is_derived": False,
        "data_vintage": stage,
        "yoy_is_derived": False,
    }
    rows = [primary]
    if (
        yoy is not None
        and current_days
        and previous_days
        and current_days > 0
        and previous_days > 0
    ):
        adjusted_yoy = ((1 + yoy / 100) * previous_days / current_days - 1) * 100
        rows.append(
            {
                **primary,
                "series_id": f"korea_semiconductor_exports_{partial_kind}_per_working_day",
                "series_name": f"韓国 半導体輸出 1営業日当たり（{_period_label(partial_kind)}）",
                "value": amount_million_usd / current_days,
                "unit": "million USD per working day",
                "yoy": adjusted_yoy,
                "is_derived": True,
                "yoy_is_derived": True,
            }
        )
    return pd.DataFrame(rows, columns=SEMICONDUCTOR_DATA_COLUMNS)


def parse_korea_monthly_trade_release(
    html: str,
    source_url: str,
    fetched_at: pd.Timestamp,
) -> pd.DataFrame:
    """産業通商部の月次輸出入動向から半導体輸出額と前年比を抽出する。"""
    text = _html_to_text(html)
    period_match = re.search(
        r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*수출입\s*동향", text
    )
    # 見出しの整数丸め値より、本文の括弧付き詳細値を優先する。
    amount_match = re.search(
        r"반도체\s*수출(?:은|이)?\s*\(\s*"
        r"([0-9]+(?:\.[0-9]+)?)\s*억\s*(?:달러|불)",
        text,
    ) or re.search(
        r"반도체\s*수출(?:은|이)?\s*"
        r"([0-9]+(?:\.[0-9]+)?)\s*억\s*(?:달러|불)",
        text,
    )
    yoy_match = re.search(
        r"반도체\s*수출(?:은|이)?\s*"
        r"(?:\([^)]*?[,，]\s*)?([△▲+\-−]?\s*[0-9]+(?:\.[0-9]+)?)\s*%",
        text,
    )
    if period_match is None or amount_match is None:
        raise ValueError("韓国産業通商部発表から月次半導体輸出を特定できません。")

    year, month = map(int, period_match.groups())
    period_start = pd.Timestamp(year=year, month=month, day=1)
    release_match = re.search(
        r"등록일\s*(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", text
    )
    release_date = (
        pd.Timestamp(*map(int, release_match.groups())) if release_match else pd.NaT
    )
    row = {
        "region": "Korea",
        "series_id": "korea_semiconductor_exports_monthly",
        "series_name": "韓国 半導体輸出（月次）",
        "reference_period": period_start,
        "release_date": release_date,
        "value": float(amount_match.group(1)) * 100,
        "unit": "million USD",
        "yoy": _parse_signed_number(yoy_match.group(1)) if yoy_match else None,
        "frequency": "monthly",
        "source_name": "韓国産業通商部 輸出入動向",
        "source_url": source_url,
        "publication_stage": "preliminary_monthly",
        "is_partial_period": False,
        "period_start": period_start,
        "period_end": period_start + pd.offsets.MonthEnd(0),
        "working_days": None,
        "fetched_at": fetched_at,
        "currency": "USD",
        "is_derived": False,
        "data_vintage": "preliminary_monthly",
        "yoy_is_derived": False,
    }
    return pd.DataFrame([row], columns=SEMICONDUCTOR_DATA_COLUMNS)


def summarize_global_demand(frame: pd.DataFrame) -> pd.DataFrame:
    """各系列の最新値、前年比、平滑化トレンドを返す。"""
    rows: list[dict[str, object]] = []
    if frame.empty:
        return pd.DataFrame()
    official = frame[~frame["is_derived"].fillna(False)].copy()
    for series_id, group in official.groupby("series_id", sort=False):
        group = group.sort_values(["reference_period", "release_date"], na_position="first")
        latest = group.iloc[-1]
        values = pd.to_numeric(group["value"], errors="coerce")
        yoy_values = pd.to_numeric(group["yoy"], errors="coerce")
        rows.append(
            {
                "series_id": series_id,
                "series_name": latest["series_name"],
                "region": latest["region"],
                "value": latest["value"],
                "unit": latest["unit"],
                "yoy": latest["yoy"],
                "three_month_average": (
                    float(values.tail(3).mean()) if len(values.dropna()) >= 3 else None
                ),
                "three_month_average_yoy": (
                    float(yoy_values.tail(3).mean())
                    if len(yoy_values.dropna()) >= 3
                    else None
                ),
                "six_month_momentum": _six_month_momentum(values),
                "reference_period": latest["reference_period"],
                "release_date": latest["release_date"],
                "fetched_at": latest["fetched_at"],
                "publication_stage": latest["publication_stage"],
                "is_partial_period": latest["is_partial_period"],
                "period_start": latest["period_start"],
                "period_end": latest["period_end"],
                "working_days": latest["working_days"],
                "source_url": latest["source_url"],
            }
        )
    return pd.DataFrame(rows)


def classify_demand_direction(summary: pd.DataFrame, region: str) -> dict[str, object]:
    """表示から独立した説明可能な地域別方向判定を返す。"""
    selected = summary[summary["region"] == region] if not summary.empty else summary
    evidence: list[str] = []
    improving = 0
    weakening = 0
    for _, row in selected.iterrows():
        yoy = pd.to_numeric(row.get("yoy"), errors="coerce")
        trend = pd.to_numeric(row.get("three_month_average_yoy"), errors="coerce")
        if pd.isna(yoy):
            continue
        name = str(row["series_name"])
        if yoy > 0:
            improving += 1
            evidence.append(f"{name}の前年比がプラス")
        elif yoy < 0:
            weakening += 1
            evidence.append(f"{name}の前年比がマイナス")
        if pd.notna(trend):
            if yoy > trend:
                improving += 1
                evidence.append(f"{name}が3か月平均前年比を上回る")
            elif yoy < trend:
                weakening += 1
                evidence.append(f"{name}が3か月平均前年比を下回る")
    if not evidence:
        return {"status": "Unavailable", "direction": "→", "evidence": []}
    if improving >= 2 and weakening == 0:
        status = "Strong"
        direction = "↑"
    elif improving > weakening:
        status = "Improving"
        direction = "↑"
    elif weakening > improving:
        status = "Weakening"
        direction = "↓"
    else:
        status = "Mixed"
        direction = "→"
    return {"status": status, "direction": direction, "evidence": evidence}


def _parse_taiwan_period(value: object) -> pd.Timestamp | None:
    digits = re.sub(r"\D", "", str(value)).zfill(5)
    if len(digits) != 5:
        return None
    year = int(digits[:3]) + 1911
    month = int(digits[3:])
    if month < 1 or month > 12:
        return None
    return pd.Timestamp(year=year, month=month, day=1)


def _html_to_text(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(unicodedata.normalize("NFKC", unescape(value)).split())


def _parse_korea_period(text: str) -> tuple[pd.Timestamp, pd.Timestamp, str] | None:
    partial = re.search(
        r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*1\s*일\s*[~∼\-]\s*"
        r"(?:\d{1,2}\s*월\s*)?(10|20)\s*일",
        text,
    )
    if partial:
        year, month, end_day = map(int, partial.groups())
        start = pd.Timestamp(year=year, month=month, day=1)
        return start, pd.Timestamp(year=year, month=month, day=end_day), f"1_{end_day}"
    monthly = re.search(r"(20\d{2})\s*년\s*(\d{1,2})\s*월(?:\s*월간)?\s*수출입\s*현황", text)
    if monthly:
        year, month = map(int, monthly.groups())
        start = pd.Timestamp(year=year, month=month, day=1)
        return start, start + pd.offsets.MonthEnd(0), "monthly"
    return None


def _parse_working_days(text: str) -> tuple[float | None, float | None]:
    match = re.search(
        r"조업일수\s*\[\s*\([^)]*\)\s*([0-9]+(?:\.[0-9]+)?)\s*일\s*,"
        r"\s*\([^)]*\)\s*([0-9]+(?:\.[0-9]+)?)\s*일\s*\]",
        text,
    )
    if not match:
        return None, None
    previous, current = map(float, match.groups())
    return current, previous


def _parse_signed_number(value: str) -> float:
    normalized = value.replace(" ", "").replace("−", "-")
    negative = normalized.startswith(("△", "-"))
    number = float(re.sub(r"[^0-9.]", "", normalized))
    return -number if negative else number


def _korea_publication_stage(text: str, partial_kind: str) -> str:
    if partial_kind != "monthly":
        return "preliminary_partial"
    if "확정치" in text:
        return "final_monthly"
    return "preliminary_monthly"


def _period_label(partial_kind: str) -> str:
    return {"1_10": "1–10日速報", "1_20": "1–20日速報", "monthly": "月次"}[partial_kind]


def _six_month_momentum(values: pd.Series) -> float | None:
    clean = values.dropna()
    if len(clean) < 7:
        return None
    base = float(clean.iloc[-7:-4].mean())
    current = float(clean.iloc[-3:].mean())
    return None if base == 0 else (current / base - 1) * 100
