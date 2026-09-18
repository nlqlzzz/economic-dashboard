"""Streamlit UI for the password-gated Decision Log MVP."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hmac
from typing import Mapping

import pandas as pd
import streamlit as st

from fundamentals import format_financial_value
from decision_log import (
    DECISION_ACTIONS,
    DECISION_MODES,
    DEFAULT_DECISION_MODE,
    HORIZON_LABELS,
    REASON_TAGS,
    TOKYO,
    DecisionLogStorageError,
    DecisionValidationError,
    SupabaseDecisionStore,
    build_decision_record,
    build_decision_snapshot,
    create_supabase_store,
    evaluate_forward_checkpoints,
    prepare_reference_prices,
)


AUTHENTICATED_KEY = "decision_log_authenticated"
PASSWORD_INPUT_KEY = "decision_log_password_input"


@dataclass(frozen=True)
class DecisionLogConfiguration:
    available: bool
    url: str = ""
    secret_key: str = ""
    password: str = ""
    reason: str = ""


def load_decision_log_configuration(secrets: Mapping[str, object] | None = None) -> DecisionLogConfiguration:
    source = secrets if secrets is not None else _streamlit_secrets()
    values = {name: _secret_text(source, name) for name in (
        "SUPABASE_URL", "SUPABASE_SECRET_KEY", "DECISION_LOG_PASSWORD"
    )}
    missing = [name for name, value in values.items() if not value]
    if missing:
        return DecisionLogConfiguration(False, reason="Decision Logは未設定です。")
    return DecisionLogConfiguration(
        True,
        values["SUPABASE_URL"],
        values["SUPABASE_SECRET_KEY"],
        values["DECISION_LOG_PASSWORD"],
    )


@st.cache_resource(show_spinner=False)
def _cached_store(url: str, secret_key: str) -> SupabaseDecisionStore:
    return create_supabase_store(url, secret_key)


def render_decision_entry(
    detail: Mapping[str, object],
    stock_prices: pd.Series,
    benchmark_prices: pd.Series,
    risk_items: Mapping[str, object],
) -> None:
    st.markdown("#### ⑤ 判断を記録")
    st.caption("その時点の判断と表示中の分析を保存します。売買注文・約定・損益の記録ではありません。")
    configuration = load_decision_log_configuration()
    if not configuration.available:
        st.info(configuration.reason)
        return
    if not st.session_state.get(AUTHENTICATED_KEY, False):
        st.info("判断履歴タブでロックを解除すると登録できます。")
        return
    reference = prepare_reference_prices(stock_prices, benchmark_prices)
    if reference.status != "available":
        st.warning(reference.reason)
        return
    stock = detail["stock"]
    st.caption(
        f"判断時参考価格: {reference.price:,.1f}円（{reference.price_date}）｜"
        f"TOPIX連動ETF: {reference.benchmark_price:,.1f}円（{reference.benchmark_price_date}）"
    )
    st.caption("品質処理済みの最新日次終値であり、約定価格ではありません。")
    with st.form("decision_log_entry", clear_on_submit=True):
        first, second = st.columns(2)
        decision_action = first.selectbox("判断", DECISION_ACTIONS)
        horizon_label = second.selectbox("想定投資期間", list(HORIZON_LABELS.values()), index=1)
        decision_mode = st.radio(
            "判断モード",
            DECISION_MODES,
            index=DECISION_MODES.index(DEFAULT_DECISION_MODE),
            horizontal=True,
        )
        reason_tags = st.multiselect("主な理由（必須・1〜3個）", REASON_TAGS, max_selections=3)
        comment = st.text_area("コメント（任意）", max_chars=300, height=80)
        review_condition = st.text_area("見直し・反証条件（任意）", max_chars=300, height=80)
        submitted = st.form_submit_button("この判断を記録", type="primary", use_container_width=True)
    if not submitted:
        return
    horizon = next(days for days, label in HORIZON_LABELS.items() if label == horizon_label)
    try:
        # Creating the provider client is deferred until an explicit save. Streamlit
        # evaluates hidden tabs, so merely opening Japan equities must stay local.
        store = _cached_store(configuration.url, configuration.secret_key)
        captured_at = datetime.now(TOKYO)
        snapshot = build_decision_snapshot(detail, reference, risk_items, captured_at=captured_at)
        record = build_decision_record(
            stock,
            decision_action,
            horizon,
            list(reason_tags),
            comment,
            review_condition,
            decision_mode,
            reference,
            snapshot,
            decision_at=captured_at,
        )
        saved = store.insert(record)
        st.success(
            f"{stock['name']}の「{decision_action}」を記録しました。"
            f"（{_datetime_text(saved.get('decision_at'))}）"
        )
    except (DecisionValidationError, DecisionLogStorageError) as error:
        st.warning(str(error))


def render_decision_history(
    selected_ticker: str,
    prices: pd.DataFrame,
    benchmark_prices: pd.Series,
) -> None:
    st.markdown("### 判断履歴")
    st.caption("登録済みの判断を新しい順に表示します。通常画面から過去記録の編集・削除はできません。")
    configuration = load_decision_log_configuration()
    if not configuration.available:
        st.info(configuration.reason)
        return
    if not st.session_state.get(AUTHENTICATED_KEY, False):
        _render_password_gate(configuration.password)
        return
    scope = st.radio(
        "表示範囲", ["現在選択銘柄", "全銘柄"], horizontal=True, key="decision_log_scope"
    )
    if not st.button("判断履歴を読み込む", use_container_width=True, key="load_decision_history"):
        st.caption("必要なときだけ履歴を読み込みます。Streamlit再読み込み後もSupabase上の記録は保持されます。")
        return
    try:
        store = _cached_store(configuration.url, configuration.secret_key)
    except DecisionLogStorageError as error:
        st.warning(str(error))
        return
    ticker_filter = selected_ticker if scope == "現在選択銘柄" else None
    try:
        records = store.list(ticker_filter)
    except DecisionLogStorageError as error:
        st.warning(str(error))
        return
    if not records:
        st.info("保存済みの判断はありません。")
        return
    for record in records:
        ticker = str(record.get("ticker", ""))
        stock_prices = prices[ticker] if ticker in prices else pd.Series(dtype=float)
        checkpoints = evaluate_forward_checkpoints(
            record, stock_prices, benchmark_prices, as_of=pd.Timestamp.now(tz=TOKYO)
        )
        intended = next(
            item for item in checkpoints
            if item.trading_days == int(record.get("horizon_trading_days", 60))
        )
        with st.container(border=True):
            st.markdown(
                f"**{_datetime_text(record.get('decision_at'))}｜{record.get('company_name', ticker)}**"
            )
            st.write(
                f"{record.get('decision_action')}｜{HORIZON_LABELS.get(int(record.get('horizon_trading_days', 0)), '—')}｜"
                f"{record.get('decision_mode')}"
            )
            tags = " / ".join(record.get("reason_tags") or []) or "理由タグなし"
            st.caption(
                f"主理由: {tags}｜判断時参考価格 {_price_text(record.get('reference_price'))} "
                f"（{record.get('reference_price_date', '—')}）"
            )
            st.caption(f"評価状態: {_evaluation_status(intended.status)}｜{intended.reason}")
            with st.expander("判断内容・前向き検証・Snapshotを見る"):
                if record.get("comment"):
                    st.write(f"**コメント:** {record['comment']}")
                if record.get("review_condition"):
                    st.write(f"**見直し・反証条件:** {record['review_condition']}")
                st.caption("参考価格は判断時点の日次終値で、約定価格ではありません。")
                for checkpoint in checkpoints:
                    _render_checkpoint(checkpoint)
                st.caption(
                    "判断方向との整合はTOPIX超過の符号だけを見る参考表示です。"
                    "絶対リターン、リスク、機会費用、手数料を含まず、正解・成功・実損益を意味しません。"
                )
                st.markdown("**判断時点Snapshot**")
                _render_forecast_update_snapshot(record.get("data_snapshot") or {})
                st.json(record.get("data_snapshot") or {})


def _render_forecast_update_snapshot(snapshot: Mapping[str, object]) -> None:
    update = snapshot.get("company_forecast_update")
    if not isinstance(update, Mapping) or update.get("status") != "Available":
        return
    st.markdown("**判断時点の会社予想の変化**")
    st.caption(
        f"対象: {update.get('fiscal_year')}（期末 {update.get('reference_period')}）｜"
        f"{update.get('previous_disclosure_date')} → {update.get('latest_disclosure_date')}"
    )
    labels = {
        "forecast_revenue": "売上高等",
        "forecast_operating_profit": "営業利益",
        "forecast_net_income": "純利益",
    }
    metrics = update.get("metrics")
    if not isinstance(metrics, Mapping):
        return
    for metric, values in metrics.items():
        if not isinstance(values, Mapping):
            continue
        previous = format_financial_value(values.get("previous_value"), str(metric).replace("forecast_", ""), update.get("unit"))
        current = format_financial_value(values.get("current_value"), str(metric).replace("forecast_", ""), update.get("unit"))
        st.write(f"{labels.get(str(metric), str(metric))}: 前回 {previous} → 今回 {current}")


def _render_password_gate(expected_password: str) -> None:
    st.info("Decision Logの閲覧・登録にはパスワードが必要です。")
    with st.form("decision_log_auth"):
        entered = st.text_input("Decision Log Password", type="password", key=PASSWORD_INPUT_KEY)
        submitted = st.form_submit_button("ロックを解除", use_container_width=True)
    if not submitted:
        return
    valid = password_matches(str(entered), expected_password)
    st.session_state.pop(PASSWORD_INPUT_KEY, None)
    if valid:
        st.session_state[AUTHENTICATED_KEY] = True
        st.rerun()
    else:
        st.warning("パスワードを確認してください。")


def password_matches(candidate: str, expected: str) -> bool:
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def _render_checkpoint(checkpoint: object) -> None:
    data = asdict(checkpoint)
    st.markdown(f"**{data['label']}（{data['trading_days']}営業日）:** {_evaluation_status(data['status'])}")
    if data["status"] == "evaluated":
        st.write(
            f"個別株 {_percent(data['stock_return'])}｜TOPIX {_percent(data['benchmark_return'])}｜"
            f"TOPIX比 {_point(data['excess_return'])}"
        )
        st.caption(f"共通評価日: {data['end_date']}｜判断方向との整合（参考）: {data['direction_alignment']}")
        stock_change = data.get("stock_reference_change_pct")
        benchmark_change = data.get("benchmark_reference_change_pct")
        if _material_reference_change(stock_change) or _material_reference_change(benchmark_change):
            st.caption(
                "取得時点による調整後価格の差: "
                f"個別株 {_point(stock_change)}｜TOPIX {_point(benchmark_change)}。"
                "保存参考価格は監査用に維持し、リターンは現在系列内で計算しています。"
            )
    else:
        st.caption(data["reason"])


def _streamlit_secrets() -> Mapping[str, object]:
    try:
        return st.secrets
    except Exception:
        return {}


def _secret_text(secrets: Mapping[str, object], name: str) -> str:
    try:
        value = secrets.get(name, "")
    except Exception:
        return ""
    return str(value).strip() if value is not None else ""


def _datetime_text(value: object) -> str:
    try:
        stamp = pd.Timestamp(value)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        return stamp.tz_convert(TOKYO).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "日時不明"


def _price_text(value: object) -> str:
    try:
        return f"{float(value):,.1f}円"
    except (TypeError, ValueError):
        return "—"


def _percent(value: object) -> str:
    return "—" if value is None else f"{float(value):+.1f}%"


def _point(value: object) -> str:
    return "—" if value is None else f"{float(value):+.1f}pt"


def _evaluation_status(status: str) -> str:
    return {"pending": "評価待ち", "unavailable": "評価不能", "evaluated": "評価済み"}.get(status, status)


def _material_reference_change(value: object) -> bool:
    return value is not None and abs(float(value)) >= 0.1
