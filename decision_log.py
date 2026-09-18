"""Decision Log domain, snapshot, forward evaluation, and Supabase storage."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import math
from typing import Any, Mapping, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd

from forecast_updates import build_company_forecast_updates, forecast_update_snapshot
from price_quality import inspect_price_series


TOKYO = ZoneInfo("Asia/Tokyo")
TABLE_NAME = "investment_decisions"
SCHEMA_VERSION = 1
SNAPSHOT_SCHEMA_VERSION = 2
BENCHMARK_TICKER = "1306.T"
DECISION_ACTIONS = ("買う", "見送る", "保有継続", "売却")
DECISION_MODES = ("実判断", "仮想判断")
DEFAULT_DECISION_MODE = "仮想判断"
DECISION_SOURCE = "Human"
HORIZON_LABELS = {20: "1か月", 60: "3か月", 120: "6か月"}
REASON_TAGS = (
    "業績", "会社予想", "評価水準", "株価・モメンタム", "TOPIX比",
    "市場感応度", "マクロ環境", "テーマ・業界", "リスク", "その他",
)
MAX_REFERENCE_STALENESS_DAYS = 7
MAX_OBSERVATION_GAP_DAYS = 7


class DecisionValidationError(ValueError):
    """Raised for user-correctable Decision Log input errors."""


class DecisionLogStorageError(RuntimeError):
    """Raised without exposing provider responses or credentials."""


class DecisionStore(Protocol):
    def insert(self, record: Mapping[str, object]) -> dict[str, object]: ...

    def list(self, ticker: str | None = None, limit: int = 100) -> list[dict[str, object]]: ...


@dataclass(frozen=True)
class ReferencePrices:
    status: str
    price: float | None = None
    price_date: str | None = None
    benchmark_price: float | None = None
    benchmark_price_date: str | None = None
    reason: str = ""
    stock_quality_status: str = "ok"
    benchmark_quality_status: str = "ok"


@dataclass(frozen=True)
class ForwardCheckpoint:
    trading_days: int
    label: str
    status: str
    end_date: str | None
    stock_return: float | None
    benchmark_return: float | None
    excess_return: float | None
    direction_alignment: str | None
    reason: str
    stock_reference_change_pct: float | None = None
    benchmark_reference_change_pct: float | None = None


def validate_decision_input(
    decision_action: str,
    horizon_trading_days: int,
    reason_tags: list[str] | tuple[str, ...],
    decision_mode: str,
) -> None:
    if decision_action not in DECISION_ACTIONS:
        raise DecisionValidationError("判断区分が不正です。")
    if horizon_trading_days not in HORIZON_LABELS:
        raise DecisionValidationError("想定投資期間が不正です。")
    if decision_mode not in DECISION_MODES:
        raise DecisionValidationError("判断モードが不正です。")
    if not 1 <= len(reason_tags) <= 3:
        raise DecisionValidationError("主な理由は1〜3個選択してください。")
    if len(set(reason_tags)) != len(reason_tags) or any(tag not in REASON_TAGS for tag in reason_tags):
        raise DecisionValidationError("主な理由に不正な値があります。")


def prepare_reference_prices(
    stock_prices: pd.Series,
    benchmark_prices: pd.Series,
    *,
    as_of: object | None = None,
) -> ReferencePrices:
    """Select the latest quality-checked common daily close available at decision time."""
    stock_quality = inspect_price_series(_clean_prices(stock_prices, as_of))
    benchmark_quality = inspect_price_series(_clean_prices(benchmark_prices, as_of))
    if not stock_quality.usable or not benchmark_quality.usable:
        return ReferencePrices(
            "quality_blocked",
            reason="個別株またはTOPIX連動ETFの価格品質に問題があるため参考価格を確定できません。",
            stock_quality_status=stock_quality.status,
            benchmark_quality_status=benchmark_quality.status,
        )
    common = pd.concat(
        {"stock": stock_quality.series, "benchmark": benchmark_quality.series},
        axis=1,
        join="inner",
    ).dropna().sort_index()
    if common.empty:
        return ReferencePrices(
            "unavailable",
            reason="個別株とTOPIX連動ETFに共通する価格基準日がありません。",
            stock_quality_status=stock_quality.status,
            benchmark_quality_status=benchmark_quality.status,
        )
    reference_date = pd.Timestamp(common.index[-1]).tz_localize(None).normalize()
    cutoff = _normalize_date(as_of) if as_of is not None else pd.Timestamp.now(tz=TOKYO).tz_localize(None).normalize()
    if (cutoff - reference_date).days > MAX_REFERENCE_STALENESS_DAYS:
        return ReferencePrices(
            "stale",
            reason="共通する最新価格が古いため参考価格を確定できません。",
            stock_quality_status=stock_quality.status,
            benchmark_quality_status=benchmark_quality.status,
        )
    return ReferencePrices(
        "available",
        float(common.iloc[-1]["stock"]),
        reference_date.date().isoformat(),
        float(common.iloc[-1]["benchmark"]),
        reference_date.date().isoformat(),
        stock_quality_status=stock_quality.status,
        benchmark_quality_status=benchmark_quality.status,
    )


def build_decision_snapshot(
    detail: Mapping[str, object],
    reference: ReferencePrices,
    risk_items: Mapping[str, object],
    *,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    """Create a small immutable, JSON-safe copy of the information shown at decision time."""
    captured = captured_at or datetime.now(TOKYO)
    performance = _mapping(detail.get("performance"))
    fundamentals = _mapping(detail.get("fundamentals"))
    latest = _mapping(fundamentals.get("latest_period"))
    exposure = _mapping(detail.get("market_exposure"))
    forecasts = _forecast_snapshot(fundamentals.get("forecast"))
    update_records = fundamentals.get("forecast_update_records")
    if isinstance(update_records, pd.DataFrame):
        forecast_updates = build_company_forecast_updates(
            update_records, as_of=captured
        )
    else:
        forecast_updates = fundamentals.get("forecast_updates")
    drivers: list[dict[str, object]] = []
    for row in list(detail.get("primary_drivers") or []):
        item = _mapping(row)
        drivers.append({
            key: _json_value(item.get(key))
            for key in ("driver", "proxy", "status", "correlation_120d", "stability", "reason")
        })
    snapshot = {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "captured_at": captured.astimezone(TOKYO).isoformat(),
        "price": {
            "ticker": _mapping(detail.get("stock")).get("ticker"),
            "value": reference.price,
            "date": reference.price_date,
            "basis": "Yahoo Finance auto_adjust=True の品質処理済み日次終値",
            "quality_status": reference.stock_quality_status,
        },
        "returns": {
            "one_month": _json_value(performance.get("return_1m")),
            "three_month": _json_value(performance.get("return_3m")),
            "topix_relative_one_month": _json_value(performance.get("relative_1m")),
            "topix_relative_three_month": _json_value(performance.get("relative_3m")),
        },
        "fundamentals": {
            "status": fundamentals.get("status", "Unavailable"),
            "fiscal_year": latest.get("fiscal_year"),
            "fiscal_quarter": latest.get("fiscal_quarter"),
            "disclosure_date": _date_or_value(latest.get("disclosure_date")),
            "momentum": fundamentals.get("momentum", "Unavailable"),
            "forecast": forecasts,
        },
        "company_forecast_update": forecast_update_snapshot(
            forecast_updates
        ),
        "valuation": {"status": "unavailable", "reason": "比較条件を満たす評価指標は未実装"},
        "risk": {
            "investment_checks": list(risk_items.get("investment_checks") or []),
            "data_limits": list(risk_items.get("data_limits") or []),
        },
        "market_exposure": {
            "status": exposure.get("status", "Unavailable"),
            "market_beta_252d": _json_value(exposure.get("market_beta_252d")),
        },
        "primary_drivers": drivers,
    }
    return to_jsonable(snapshot)


def build_decision_record(
    stock: Mapping[str, object],
    decision_action: str,
    horizon_trading_days: int,
    reason_tags: list[str],
    comment: str,
    review_condition: str,
    decision_mode: str,
    reference: ReferencePrices,
    snapshot: Mapping[str, object],
    *,
    decision_at: datetime | None = None,
    decision_id: str | None = None,
    supersedes_decision_id: str | None = None,
) -> dict[str, object]:
    validate_decision_input(decision_action, horizon_trading_days, reason_tags, decision_mode)
    if reference.status != "available":
        raise DecisionValidationError("判断時参考価格を確定できません。")
    decided = (decision_at or datetime.now(TOKYO)).astimezone(TOKYO)
    record_id = decision_id or str(uuid4())
    return {
        "id": record_id,
        "created_at": decided.isoformat(),
        "decision_at": decided.isoformat(),
        "ticker": str(stock["ticker"]),
        "security_code": str(stock["code"]),
        "company_name": str(stock["name"]),
        "decision_action": decision_action,
        "horizon_trading_days": int(horizon_trading_days),
        "reason_tags": list(reason_tags),
        "comment": comment.strip() or None,
        "review_condition": review_condition.strip() or None,
        "decision_mode": decision_mode,
        "decision_source": DECISION_SOURCE,
        "reference_price": float(reference.price),
        "reference_price_date": reference.price_date,
        "benchmark_ticker": BENCHMARK_TICKER,
        "benchmark_price": float(reference.benchmark_price),
        "benchmark_price_date": reference.benchmark_price_date,
        "data_snapshot": to_jsonable(snapshot),
        "schema_version": SCHEMA_VERSION,
        "supersedes_decision_id": supersedes_decision_id,
    }


def evaluate_forward_checkpoints(
    decision: Mapping[str, object],
    stock_prices: pd.Series,
    benchmark_prices: pd.Series,
    *,
    as_of: object | None = None,
) -> list[ForwardCheckpoint]:
    return [
        evaluate_forward_checkpoint(
            decision, stock_prices, benchmark_prices, trading_days, as_of=as_of
        )
        for trading_days in HORIZON_LABELS
    ]


def evaluate_forward_checkpoint(
    decision: Mapping[str, object],
    stock_prices: pd.Series,
    benchmark_prices: pd.Series,
    trading_days: int,
    *,
    as_of: object | None = None,
) -> ForwardCheckpoint:
    if trading_days not in HORIZON_LABELS:
        raise DecisionValidationError("評価期間が不正です。")
    try:
        if not decision.get("reference_price_date") or not decision.get("benchmark_price_date"):
            raise ValueError("missing date")
        reference_date = _normalize_date(decision.get("reference_price_date"))
        benchmark_reference_date = _normalize_date(decision.get("benchmark_price_date"))
    except (TypeError, ValueError):
        return _checkpoint(trading_days, "unavailable", None, reason="判断時の価格基準日がありません。")
    if reference_date != benchmark_reference_date:
        return _checkpoint(trading_days, "unavailable", None, reason="判断時の個別株とTOPIXの基準日が一致しません。")
    try:
        stock_base = float(decision["reference_price"])
        benchmark_base = float(decision["benchmark_price"])
    except (KeyError, TypeError, ValueError):
        return _checkpoint(trading_days, "unavailable", None, reason="判断時参考価格がありません。")
    if stock_base <= 0 or benchmark_base <= 0:
        return _checkpoint(trading_days, "unavailable", None, reason="判断時参考価格が不正です。")

    stock_quality = inspect_price_series(_clean_prices(stock_prices, as_of))
    benchmark_quality = inspect_price_series(_clean_prices(benchmark_prices, as_of))
    if not stock_quality.usable or not benchmark_quality.usable:
        return _checkpoint(trading_days, "unavailable", None, reason="価格品質の問題により評価できません。")
    if reference_date not in stock_quality.series.index or reference_date not in benchmark_quality.series.index:
        return _checkpoint(trading_days, "unavailable", None, reason="現在の価格系列で判断時の共通基準日を確認できません。")
    current_stock_base = float(stock_quality.series.loc[reference_date])
    current_benchmark_base = float(benchmark_quality.series.loc[reference_date])
    stock_reference_change = (current_stock_base / stock_base - 1) * 100
    benchmark_reference_change = (current_benchmark_base / benchmark_base - 1) * 100
    benchmark_after = benchmark_quality.series.loc[benchmark_quality.series.index > reference_date]
    if len(benchmark_after) < trading_days:
        if _series_is_stale(benchmark_quality.series, as_of):
            return _checkpoint(trading_days, "unavailable", None, reason="TOPIX価格の更新が古く、評価期間を確認できません。")
        return _checkpoint(trading_days, "pending", None, reason="標準チェックポイントの取引日数に未到達です。")
    target_date = pd.Timestamp(benchmark_after.index[trading_days - 1]).tz_localize(None).normalize()
    evaluation_window = benchmark_quality.series.loc[
        (benchmark_quality.series.index > reference_date)
        & (benchmark_quality.series.index <= target_date)
    ]
    if _has_long_gap(reference_date, evaluation_window.index):
        return _checkpoint(trading_days, "unavailable", target_date, reason="TOPIX価格に長期欠損があり、評価期間を延長しません。")
    if target_date not in stock_quality.series.index:
        return _checkpoint(trading_days, "unavailable", target_date, reason="共通評価日の個別株価格がありません。後日の価格では代用しません。")
    stock_end = float(stock_quality.series.loc[target_date])
    benchmark_end = float(benchmark_quality.series.loc[target_date])
    # Saved prices are an immutable audit snapshot. Forward returns must use the
    # reference and end prices from the same currently retrieved adjusted series.
    stock_return = (stock_end / current_stock_base - 1) * 100
    benchmark_return = (benchmark_end / current_benchmark_base - 1) * 100
    excess = stock_return - benchmark_return
    alignment = direction_alignment(str(decision.get("decision_action")), excess)
    return _checkpoint(
        trading_days,
        "evaluated",
        target_date,
        stock_return=stock_return,
        benchmark_return=benchmark_return,
        excess_return=excess,
        alignment=alignment,
        reason="判断時参考価格から同一評価日までの事後リターンです。",
        stock_reference_change_pct=stock_reference_change,
        benchmark_reference_change_pct=benchmark_reference_change,
    )


def direction_alignment(decision_action: str, excess_return: float | None) -> str | None:
    if excess_return is None or decision_action not in DECISION_ACTIONS:
        return None
    aligned = excess_return > 0 if decision_action in {"買う", "保有継続"} else excess_return < 0
    if excess_return == 0:
        return "中立"
    return "整合" if aligned else "非整合"


class SupabaseDecisionStore:
    """Append/read-only application wrapper; no update/delete methods are exposed."""

    def __init__(self, client: object):
        self._client = client

    def insert(self, record: Mapping[str, object]) -> dict[str, object]:
        try:
            result = self._client.table(TABLE_NAME).insert(dict(record)).execute()
            rows = list(getattr(result, "data", None) or [])
            return dict(rows[0]) if rows else dict(record)
        except Exception as error:
            raise DecisionLogStorageError("判断履歴を保存できませんでした。") from error

    def list(self, ticker: str | None = None, limit: int = 100) -> list[dict[str, object]]:
        try:
            query = self._client.table(TABLE_NAME).select("*")
            if ticker:
                query = query.eq("ticker", ticker)
            result = query.order("decision_at", desc=True).limit(limit).execute()
            return [dict(row) for row in (getattr(result, "data", None) or [])]
        except Exception as error:
            raise DecisionLogStorageError("判断履歴を取得できませんでした。") from error


def create_supabase_store(url: str, secret_key: str) -> SupabaseDecisionStore:
    try:
        from supabase import create_client

        return SupabaseDecisionStore(create_client(url, secret_key))
    except Exception as error:
        raise DecisionLogStorageError("Decision Logの保存先を初期化できませんでした。") from error


def to_jsonable(value: object) -> Any:
    if value is pd.NA or value is pd.NaT:
        return None
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return None if not math.isfinite(value) else value
    if isinstance(value, (datetime, pd.Timestamp)):
        stamp = pd.Timestamp(value)
        if pd.isna(stamp):
            return None
        return stamp.isoformat()
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, pd.DataFrame):
        return [to_jsonable(row) for row in value.to_dict("records")]
    if isinstance(value, pd.Series):
        return [to_jsonable(item) for item in value.tolist()]
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return to_jsonable(value.item())
    return str(value)


def assert_json_serializable(value: object) -> None:
    json.dumps(value, ensure_ascii=False, allow_nan=False)


def _forecast_snapshot(value: object) -> list[dict[str, object]]:
    if not isinstance(value, pd.DataFrame) or value.empty:
        return []
    rows: list[dict[str, object]] = []
    for row in value.to_dict("records"):
        rows.append({
            key: _json_value(row.get(key))
            for key in ("metric", "value", "unit", "currency", "fiscal_year", "disclosure_date")
        })
    return rows


def _clean_prices(series: pd.Series, as_of: object | None) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index().copy()
    clean.index = pd.DatetimeIndex(clean.index).tz_localize(None).normalize()
    clean = clean[~clean.index.duplicated(keep="last")]
    if as_of is not None:
        clean = clean.loc[clean.index <= _normalize_date(as_of)]
    return clean


def _normalize_date(value: object) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert(TOKYO).tz_localize(None)
    return stamp.normalize()


def _series_is_stale(series: pd.Series, as_of: object | None) -> bool:
    if series.empty:
        return True
    cutoff = _normalize_date(as_of) if as_of is not None else pd.Timestamp.now(tz=TOKYO).tz_localize(None).normalize()
    return (cutoff - pd.Timestamp(series.index[-1])).days > MAX_REFERENCE_STALENESS_DAYS


def _has_long_gap(reference_date: pd.Timestamp, dates: pd.DatetimeIndex) -> bool:
    points = pd.DatetimeIndex([reference_date, *list(dates)])
    return len(points) > 1 and bool((points[1:] - points[:-1]).days.max() > MAX_OBSERVATION_GAP_DAYS)


def _checkpoint(
    trading_days: int,
    status: str,
    end_date: object | None,
    *,
    stock_return: float | None = None,
    benchmark_return: float | None = None,
    excess_return: float | None = None,
    alignment: str | None = None,
    reason: str,
    stock_reference_change_pct: float | None = None,
    benchmark_reference_change_pct: float | None = None,
) -> ForwardCheckpoint:
    return ForwardCheckpoint(
        trading_days,
        HORIZON_LABELS[trading_days],
        status,
        None if end_date is None else _normalize_date(end_date).date().isoformat(),
        stock_return,
        benchmark_return,
        excess_return,
        alignment,
        reason,
        stock_reference_change_pct,
        benchmark_reference_change_pct,
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _json_value(value: object) -> object:
    return to_jsonable(value)


def _date_or_value(value: object) -> object:
    if value is None or (not isinstance(value, (str, datetime, pd.Timestamp)) and pd.isna(value)):
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return to_jsonable(value)
    return str(value)
