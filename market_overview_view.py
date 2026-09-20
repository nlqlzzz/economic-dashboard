from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
import streamlit as st

from utils import change_from_previous, latest_value


LATEST_VALUE_COLUMNS = [
    "指標名",
    "最新の値",
    "直前の値との比",
    "重要度",
    "データ日",
    "データ元",
]


def build_latest_values_table(
    series_by_name: Mapping[str, pd.Series],
    indicators: Mapping[str, Mapping[str, object]],
    key_indicators: set[str],
    source_labels: Mapping[str, str],
    *,
    normalized: bool,
) -> pd.DataFrame:
    """Build a compact latest-values table in the requested mobile-friendly order."""
    rows: list[dict[str, str]] = []
    for name, series in series_by_name.items():
        observed_at, value = latest_value(series)
        info = indicators[name]
        suffix = (
            "（前年比 %）"
            if info.get("yoy")
            else str(series.attrs.get("unit", info["unit"]))
        )
        latest_display = f"{value:,.2f}" if normalized else f"{value:,.2f} {suffix}"
        previous_change = change_from_previous(series)
        if previous_change is None:
            previous_display = "—"
        else:
            change, previous_rate = previous_change
            previous_display = f"{change:+,.2f}（{previous_rate:+.2f}%）"

        actual_source = str(series.attrs.get("source", info["source"]))
        source_label = source_labels.get(actual_source, actual_source)
        if series.attrs.get("is_fallback"):
            source_label = f"{source_label}・{series.attrs['ticker']}（代替）"
        rows.append(
            {
                "指標名": name,
                "最新の値": latest_display,
                "直前の値との比": previous_display,
                "重要度": "主要" if name in key_indicators else "通常",
                "データ日": f"{observed_at:%Y-%m-%d}",
                "データ元": source_label,
            }
        )
    return pd.DataFrame(rows, columns=LATEST_VALUE_COLUMNS)


def _set_category_open(category: str, is_open: bool) -> None:
    st.session_state[f"sidebar_category_open_{category}"] = is_open


def set_sidebar_indicator_selected(name: str, selected: bool) -> None:
    """Keep selection independently of Streamlit removing a hidden checkbox widget."""
    st.session_state[f"sidebar_indicator_selected_{name}"] = selected
    st.session_state[f"show_{name}_default_v2"] = selected


def _sync_sidebar_indicator(name: str) -> None:
    st.session_state[f"sidebar_indicator_selected_{name}"] = bool(
        st.session_state.get(f"show_{name}_default_v2", False)
    )


def render_sidebar_indicator_category(
    category: str,
    indicators: Mapping[str, Mapping[str, object]],
) -> list[str]:
    """Render a sidebar category that can be closed from both its top and bottom."""
    state_key = f"sidebar_category_open_{category}"
    st.session_state.setdefault(state_key, category == "マーケット")
    is_open = bool(st.session_state[state_key])
    selected: list[str] = []
    category_names = [
        name for name, info in indicators.items() if info["category"] == category
    ]
    for name in category_names:
        is_default = name in {"日経平均株価", "S&P 500指数"}
        selection_key = f"sidebar_indicator_selected_{name}"
        widget_key = f"show_{name}_default_v2"
        if widget_key in st.session_state:
            st.session_state[selection_key] = bool(st.session_state[widget_key])
        else:
            st.session_state.setdefault(selection_key, is_default)
    with st.container(border=True):
        st.button(
            f"{'⌄' if is_open else '›'} {category}",
            use_container_width=True,
            key=f"sidebar_category_toggle_{category}",
            on_click=_set_category_open,
            args=(category, not is_open),
        )
        if not is_open:
            for name in category_names:
                if st.session_state[f"sidebar_indicator_selected_{name}"]:
                    selected.append(name)
            return selected
        if category == "個別株":
            st.caption(
                "銘柄を選択し、下の「現在の選択を保存・更新」から任意のウォッチリストとして保存できます。"
            )
        for name in category_names:
            if st.checkbox(
                name,
                value=bool(st.session_state[f"sidebar_indicator_selected_{name}"]),
                key=f"show_{name}_default_v2",
                on_change=_sync_sidebar_indicator,
                args=(name,),
            ):
                selected.append(name)
        st.divider()
        st.button(
            f"⌃ {category}を閉じる",
            use_container_width=True,
            key=f"sidebar_category_close_{category}",
            on_click=_set_category_open,
            args=(category, False),
        )
    return selected
