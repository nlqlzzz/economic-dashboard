"""Point-in-time-safe valuation readiness checks for Japan Core20."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass

import pandas as pd

from price_quality import inspect_price_series


EPS_UNITS = {"JPY", "JPY/share", "yen/share"}
FINANCIAL_SECTORS = {"銀行", "保険"}
REVISION_IDENTITY = (
    "ticker", "fiscal_year", "reference_period", "accounting_standard",
    "consolidated_flag", "currency", "unit"
)
COMPARABLE_REVISION_DIRECTIONS = {
    "up", "down", "unchanged", "turned_positive", "turned_non_positive"
}


@dataclass(frozen=True)
class ForwardPERAssessment:
    calculable: bool
    status: str
    reason: str
    current_price: float | None = None
    price_date: str | None = None
    forecast_eps: float | None = None
    forecast_fiscal_year: str | None = None
    forecast_period_end: str | None = None
    forecast_disclosure_date: str | None = None
    forward_per: float | None = None
    accounting_standard: str | None = None
    consolidated_flag: bool | None = None
    currency: str | None = None
    unit: str | None = None
    split_basis_status: str = "unknown"
    price_quality_status: str = "missing"


def assess_current_forward_per(
    records: pd.DataFrame,
    prices: pd.Series,
    *,
    split_basis_status: str = "unknown",
) -> ForwardPERAssessment:
    """Assess rather than guess whether current price / company FEPS is safe."""
    quality = inspect_price_series(prices)
    if not quality.usable or quality.series.empty:
        return ForwardPERAssessment(
            False, "NO-GO", "価格品質停止または価格欠損", split_basis_status=split_basis_status,
            price_quality_status=quality.status,
        )
    price_date = _date_text(quality.series.index[-1])
    current_price = _number(quality.series.iloc[-1])
    if current_price is None or current_price <= 0:
        return ForwardPERAssessment(
            False, "NO-GO", "最新価格が正の数値ではない", current_price=current_price,
            price_date=price_date, split_basis_status=split_basis_status,
            price_quality_status=quality.status,
        )

    forecasts = _forecast_rows(records)
    if forecasts.empty:
        return _assessment_with_price(
            quality.status, current_price, price_date, split_basis_status, "forecast EPS欠損"
        )
    forecasts = forecasts[pd.to_datetime(forecasts["disclosure_date"], errors="coerce") <= pd.Timestamp(price_date)]
    if forecasts.empty:
        return _assessment_with_price(
            quality.status, current_price, price_date, split_basis_status,
            "株価基準日までに公表済みのforecast EPSがない",
        )
    row = forecasts.sort_values("disclosure_date").iloc[-1]
    common = _row_fields(row)
    eps = _number(row.get("value"))
    fiscal_year = _text(row.get("fiscal_year"))
    period_end = _date_text(row.get("reference_period"))
    disclosure_date = _date_text(row.get("disclosure_date"))
    blockers: list[str] = []
    if eps is None:
        blockers.append("forecast EPS欠損")
    elif eps <= 0:
        blockers.append("forecast EPSが0以下（N/M候補）")
    if not fiscal_year:
        blockers.append("対象Fiscal Year不明")
    if not period_end:
        blockers.append("Forecast対象期末不明")
    elif pd.Timestamp(period_end) < pd.Timestamp(price_date):
        blockers.append("Forecast対象期が株価基準日前に終了")
    if not disclosure_date:
        blockers.append("開示日不明")
    if common["currency"] != "JPY" or common["unit"] not in EPS_UNITS:
        blockers.append("単位または通貨不整合")
    if not common["accounting_standard"] or common["consolidated_flag"] is None:
        blockers.append("会計基準または連結区分不明")
    if split_basis_status != "basis_verified":
        blockers.append("価格とEPSのper-share basis未確認")
    calculable = not blockers
    return ForwardPERAssessment(
        calculable,
        "GO" if calculable else "NO-GO",
        "算出条件を確認済み" if calculable else " / ".join(blockers),
        current_price=current_price,
        price_date=price_date,
        forecast_eps=eps,
        forecast_fiscal_year=fiscal_year,
        forecast_period_end=period_end,
        forecast_disclosure_date=disclosure_date,
        forward_per=(current_price / eps if calculable and eps else None),
        split_basis_status=split_basis_status,
        price_quality_status=quality.status,
        **common,
    )


def build_forecast_eps_revisions(
    records: pd.DataFrame,
    *,
    adjustment_bars: pd.DataFrame | None = None,
    basis_directly_verified: bool = False,
) -> pd.DataFrame:
    """Compare FEPS only inside an identical fiscal-year/definition cohort."""
    forecasts = _forecast_rows(records)
    columns = list(forecasts.columns) + [
        "previous_forecast_eps", "change", "change_pct", "basis_status",
        "revision_direction"
    ]
    if forecasts.empty:
        return pd.DataFrame(columns=columns)
    work = forecasts.copy()
    work["_disclosure"] = pd.to_datetime(work["disclosure_date"], errors="coerce")
    work = work[work["_disclosure"].notna()].sort_values([*REVISION_IDENTITY, "_disclosure"])
    work = work.drop_duplicates([*REVISION_IDENTITY, "_disclosure"], keep="last")
    rows: list[dict[str, object]] = []
    for _, group in work.groupby(list(REVISION_IDENTITY), dropna=False, sort=False):
        cohort_valid = all(
            _text(group.iloc[0].get(field)) is not None
            for field in ("ticker", "fiscal_year", "reference_period", "accounting_standard", "currency", "unit")
        ) and not pd.isna(group.iloc[0].get("consolidated_flag"))
        previous: float | None = None
        previous_disclosure: object | None = None
        for _, row in group.sort_values("_disclosure").iterrows():
            current = _number(row.get("value"))
            change = current - previous if current is not None and previous is not None else None
            change_pct = (change / previous * 100) if change is not None and previous > 0 else None
            basis_status = _revision_basis_status(
                adjustment_bars, previous_disclosure, row.get("disclosure_date"),
                basis_directly_verified,
            )
            direction = _revision_direction(previous, current)
            if previous is not None and basis_status == "basis_changed":
                direction = "basis_changed"
                change_pct = None
            elif previous is not None and basis_status != "basis_verified":
                direction = "basis_unverified"
                change_pct = None
            payload = row.drop(labels=["_disclosure"]).to_dict()
            rows.append({
                **payload,
                "previous_forecast_eps": previous,
                "change": change,
                "change_pct": change_pct,
                "basis_status": basis_status,
                "revision_direction": direction,
            })
            if current is not None and cohort_valid:
                previous = current
                previous_disclosure = row.get("disclosure_date")
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["ticker", "disclosure_date"], na_position="last"
    ).reset_index(drop=True)


def forecast_available_on(records: pd.DataFrame, price_date: object) -> Mapping[str, object] | None:
    """Return the last FEPS disclosed before a price date (next-session rule)."""
    forecasts = _forecast_rows(records)
    if forecasts.empty:
        return None
    cutoff = pd.Timestamp(price_date).tz_localize(None).normalize()
    disclosed = pd.to_datetime(forecasts["disclosure_date"], errors="coerce")
    eligible = forecasts[disclosed < cutoff].copy()
    eligible = eligible[
        eligible.apply(lambda row: _valid_forecast_for_price(row, cutoff), axis=1)
    ]
    if eligible.empty:
        return None
    eligible["_disclosure"] = pd.to_datetime(eligible["disclosure_date"], errors="coerce")
    return eligible.sort_values("_disclosure").iloc[-1].drop(labels=["_disclosure"]).to_dict()


def build_historical_forward_per(
    records: pd.DataFrame,
    prices: pd.Series,
    *,
    split_basis_status: str = "unknown",
) -> pd.DataFrame:
    """Build a diagnostic series without same-day disclosure look-ahead."""
    columns = [
        "price_date", "price", "forecast_eps", "forecast_fiscal_year",
        "forecast_disclosure_date", "accounting_standard", "consolidated_flag",
        "currency", "unit", "forward_per",
    ]
    if split_basis_status != "basis_verified":
        return pd.DataFrame(columns=columns)
    quality = inspect_price_series(prices)
    if not quality.usable:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, object]] = []
    for price_date, price_value in quality.series.items():
        forecast = forecast_available_on(records, price_date)
        price = _number(price_value)
        eps = _number(forecast.get("value")) if forecast else None
        if forecast is None or price is None or price <= 0 or eps is None or eps <= 0:
            continue
        if forecast.get("currency") != "JPY" or forecast.get("unit") not in EPS_UNITS:
            continue
        rows.append({
            "price_date": _date_text(price_date), "price": price, "forecast_eps": eps,
            "forecast_fiscal_year": _text(forecast.get("fiscal_year")),
            "forecast_disclosure_date": _date_text(forecast.get("disclosure_date")),
            "accounting_standard": _text(forecast.get("accounting_standard")),
            "consolidated_flag": forecast.get("consolidated_flag"),
            "currency": _text(forecast.get("currency")),
            "unit": _text(forecast.get("unit")),
            "forward_per": price / eps,
        })
    return pd.DataFrame(rows, columns=columns)


def historical_feasibility(records: pd.DataFrame, split_basis_status: str = "unknown") -> dict[str, object]:
    forecasts = _forecast_rows(records)
    disclosed = pd.to_datetime(forecasts.get("disclosure_date"), errors="coerce")
    valid = forecasts[disclosed.notna()].copy() if not forecasts.empty else forecasts
    observations, years = 0, 0
    if not valid.empty:
        definition = ["accounting_standard", "consolidated_flag", "currency", "unit"]
        candidates: list[tuple[int, int]] = []
        for _, group in valid.groupby(definition, dropna=False):
            candidates.append((
                len(group.drop_duplicates(["fiscal_year", "disclosure_date"])),
                int(group["fiscal_year"].dropna().nunique()),
            ))
        observations, years = max(candidates, default=(0, 0))
    if split_basis_status != "basis_verified":
        status, reason = "NO-GO", "時系列のper-share basis未確認"
    elif observations >= 3 and years >= 2:
        status, reason = "GO", "複数年度・複数開示の履歴候補あり"
    elif observations:
        status, reason = "CONDITIONAL", "履歴観測数またはFiscal Year数が限定的"
    else:
        status, reason = "NO-GO", "forecast EPS履歴なし"
    return {
        "distinct_forecast_observations": observations,
        "fiscal_year_count": years,
        "oldest_disclosure_date": _date_text(disclosed.min()) if disclosed.notna().any() else None,
        "latest_disclosure_date": _date_text(disclosed.max()) if disclosed.notna().any() else None,
        "status": status,
        "reason": reason,
    }


def sector_valuation_caution(sector: str) -> str:
    if sector == "銀行":
        return "銀行は金利・信用コスト・資本規制の影響が大きく、PER単独で割安・割高を判定しない。"
    if sector == "保険":
        return "保険は運用損益・自然災害・資本政策の影響が大きく、PER単独で割安・割高を判定しない。"
    if sector in {"商社", "投資・テクノロジー"}:
        return "保有資産価値や投資損益の影響が大きく、PER単独評価には注意が必要。"
    return "同業・自社履歴との比較条件をそろえ、PER単独で割安・割高を判定しない。"


def normalized_pbr_readiness(records: pd.DataFrame) -> dict[str, object]:
    metrics = set(records.get("metric", pd.Series(dtype=str)).dropna().astype(str))
    present = sorted(metrics & {"bps", "book_equity", "net_assets", "shares_outstanding"})
    required = {"bps"} if "bps" in present else {"book_equity", "shares_outstanding"}
    calculable = required.issubset(present)
    return {
        "status": "CONDITIONAL" if calculable else "NO-GO",
        "available_metrics": present,
        "reason": "株価とのper-share basis確認が別途必要" if calculable else "現行正規化schemaにPBR構築項目がない",
    }


def split_basis_status_from_daily_bars(
    bars: pd.DataFrame,
    forecast_disclosure_date: object,
    price_date: object,
    *,
    coverage_tolerance_days: int = 7,
) -> str:
    """Use official adjustment factors as evidence; never infer a factor."""
    if bars.empty or not {"Date", "AdjFactor"}.issubset(bars.columns):
        return "unknown"
    disclosure = pd.to_datetime(forecast_disclosure_date, errors="coerce")
    end = pd.to_datetime(price_date, errors="coerce")
    dates = pd.to_datetime(bars["Date"], errors="coerce")
    factors = pd.to_numeric(bars["AdjFactor"], errors="coerce")
    valid = pd.DataFrame({"date": dates, "factor": factors}).dropna().sort_values("date")
    if pd.isna(disclosure) or pd.isna(end) or valid.empty:
        return "unknown"
    window = valid[(valid["date"] > disclosure) & (valid["date"] <= end)]
    if window.empty:
        return "unknown"
    if (window.iloc[0]["date"] - disclosure).days > coverage_tolerance_days:
        return "unknown"
    if (end - window.iloc[-1]["date"]).days > coverage_tolerance_days:
        return "unknown"
    if ((window["factor"] - 1.0).abs() > 1e-12).any():
        return "corporate_action_detected"
    return "no_effective_action_detected"


def _revision_basis_status(
    bars: pd.DataFrame | None,
    previous_disclosure: object | None,
    current_disclosure: object,
    directly_verified: bool,
) -> str:
    if previous_disclosure is None:
        return "comparison_unavailable"
    observed = split_basis_status_from_daily_bars(
        bars if bars is not None else pd.DataFrame(),
        previous_disclosure,
        current_disclosure,
    )
    if observed == "corporate_action_detected":
        return "basis_changed"
    return "basis_verified" if directly_verified else "basis_unverified"


def _valid_forecast_for_price(row: Mapping[str, object], price_date: pd.Timestamp) -> bool:
    period_end = pd.to_datetime(row.get("reference_period"), errors="coerce")
    fiscal_year = _text(row.get("fiscal_year"))
    standard = _text(row.get("accounting_standard"))
    currency = _text(row.get("currency"))
    unit = _text(row.get("unit"))
    consolidated = row.get("consolidated_flag")
    return bool(
        fiscal_year
        and pd.notna(period_end)
        and period_end >= price_date
        and standard
        and consolidated is not None
        and not pd.isna(consolidated)
        and currency == "JPY"
        and unit in EPS_UNITS
    )


def assessment_dict(value: ForwardPERAssessment) -> dict[str, object]:
    return asdict(value)


def _forecast_rows(records: pd.DataFrame) -> pd.DataFrame:
    if records.empty or "metric" not in records:
        return pd.DataFrame(columns=[*REVISION_IDENTITY, "disclosure_date", "value"])
    return records[records["metric"].eq("forecast_eps")].copy()


def _assessment_with_price(
    quality_status: str, price: float, price_date: str | None, split_status: str, reason: str
) -> ForwardPERAssessment:
    return ForwardPERAssessment(
        False, "NO-GO", reason, current_price=price, price_date=price_date,
        split_basis_status=split_status, price_quality_status=quality_status,
    )


def _row_fields(row: Mapping[str, object]) -> dict[str, object]:
    consolidated = row.get("consolidated_flag")
    return {
        "accounting_standard": _text(row.get("accounting_standard")),
        "consolidated_flag": None if pd.isna(consolidated) else bool(consolidated),
        "currency": _text(row.get("currency")),
        "unit": _text(row.get("unit")),
    }


def _revision_direction(previous: float | None, current: float | None) -> str:
    if previous is None or current is None:
        return "comparison_unavailable"
    if current == previous:
        return "unchanged"
    if previous <= 0 < current:
        return "turned_positive"
    if previous > 0 >= current:
        return "turned_non_positive"
    return "up" if current > previous else "down"


def _number(value: object) -> float | None:
    try:
        number = float(value)
        return number if pd.notna(number) else None
    except (TypeError, ValueError):
        return None


def _text(value: object) -> str | None:
    return None if value is None or pd.isna(value) or not str(value).strip() else str(value).strip()


def _date_text(value: object) -> str | None:
    try:
        stamp = pd.Timestamp(value)
        return None if pd.isna(stamp) else stamp.strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return None
