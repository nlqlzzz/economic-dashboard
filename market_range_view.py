from __future__ import annotations

import pandas as pd
import streamlit as st

from market_range import MARKET_RANGE_LABELS, MARKET_RANGE_PRESETS


MARKET_RANGE_MOBILE_CSS = """
<style>
@media (max-width: 768px) {
    .st-key-market_range_preset [data-testid="stRadio"] [role="radiogroup"] {
        flex-wrap: nowrap;
        overflow-x: auto;
        scrollbar-width: thin;
        padding-bottom: 0.25rem;
    }
    .st-key-market_range_preset [data-testid="stRadio"] label {
        flex: 0 0 auto;
    }
}
</style>
"""


def render_market_range_selector(
    active_preset: str,
    range_start: object,
    range_end: object,
    latest_data_date: object | None,
) -> None:
    """Render one horizontally scrollable preset row below the overview chart."""
    st.radio(
        "表示期間",
        MARKET_RANGE_PRESETS,
        horizontal=True,
        key="market_range_preset",
        format_func=lambda value: MARKET_RANGE_LABELS[value],
        label_visibility="collapsed",
    )
    latest = pd.to_datetime(latest_data_date, errors="coerce")
    latest_basis = (
        f"｜最新データ日基準: {latest:%Y-%m-%d}"
        if active_preset != "Custom" and not pd.isna(latest)
        else ""
    )
    st.caption(
        f"選択中: {MARKET_RANGE_LABELS[active_preset]}｜"
        f"表示範囲: {pd.Timestamp(range_start):%Y-%m-%d}〜{pd.Timestamp(range_end):%Y-%m-%d}"
        f"{latest_basis}。任意期間はサイドバーの開始日・終了日で指定します。"
    )
