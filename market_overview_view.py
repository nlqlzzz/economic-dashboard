from __future__ import annotations

from collections.abc import Mapping
from html import escape
import unicodedata

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
LATEST_VALUE_WIDTH_LIMITS = {
    "指標名": (110, 220),
    "最新の値": (90, 160),
    "直前の値との比": (125, 190),
    "重要度": (72, 90),
    "データ日": (105, 120),
    "データ元": (100, 190),
}
CHANGE_RATE_COLUMNS = ["指標", "直前値比", "1週間", "1か月", "年初来", "表示期間"]
CHANGE_RATE_WIDTH_LIMITS = {
    "指標": (110, 220),
    "直前値比": (90, 120),
    "1週間": (76, 100),
    "1か月": (76, 100),
    "年初来": (76, 100),
    "表示期間": (90, 110),
}
MARKET_CHART_PLOT_HEIGHT = 360
MARKET_CHART_TOP_MARGIN = 30
MARKET_CHART_LEGEND_ROW_HEIGHT = 27
MARKET_CHART_LEGEND_GAP = 52


def _display_character_width(value: object) -> int:
    return sum(
        2 if unicodedata.east_asian_width(character) in {"W", "F", "A"} else 1
        for character in str(value)
    )


def _bounded_column_widths(
    table: pd.DataFrame,
    columns: list[str],
    limits: Mapping[str, tuple[int, int]],
) -> dict[str, int]:
    widths: dict[str, int] = {}
    for column in columns:
        minimum, maximum = limits[column]
        content_width = max(
            [_display_character_width(column)]
            + [_display_character_width(value) for value in table[column].fillna("")]
        )
        widths[column] = min(maximum, max(minimum, content_width * 8 + 28))
    return widths


def latest_value_column_widths(table: pd.DataFrame) -> dict[str, int]:
    """Size latest-value columns from visible text with bounded widths."""
    return _bounded_column_widths(
        table, LATEST_VALUE_COLUMNS, LATEST_VALUE_WIDTH_LIMITS
    )


def change_rate_column_widths(table: pd.DataFrame) -> dict[str, int]:
    """Size return columns from visible text with bounded widths."""
    return _bounded_column_widths(table, CHANGE_RATE_COLUMNS, CHANGE_RATE_WIDTH_LIMITS)


def _stable_table_html(
    table: pd.DataFrame,
    columns: list[str],
    widths: Mapping[str, int],
    aria_label: str,
) -> str:
    total_width = sum(widths.values())
    colgroup_html = "".join(
        f'<col style="width:{widths[column]}px;max-width:{widths[column]}px">'
        for column in columns
    )
    column_names = list(table.columns)
    headers = "".join(f"<th>{escape(column)}</th>" for column in column_names)
    rows = []
    for _, row in table.iterrows():
        cells = "".join(
            f'<td title="{escape(str(row[column]), quote=True)}">'
            f"{escape(str(row[column]))}</td>"
            for column in column_names
        )
        rows.append(f"<tr>{cells}</tr>")
    return f"""
<style>
.market-latest-values-wrap {{
    width: 100%;
    overflow-x: auto;
    overscroll-behavior-x: contain;
    border: 1px solid rgba(128, 128, 128, 0.28);
    border-radius: 0.5rem;
}}
.market-latest-values {{
    width: {total_width}px;
    table-layout: fixed;
    border-collapse: collapse;
    font-size: 0.9rem;
}}
.market-latest-values th,
.market-latest-values td {{
    padding: 0.55rem 0.65rem;
    border-right: 1px solid rgba(128, 128, 128, 0.22);
    border-bottom: 1px solid rgba(128, 128, 128, 0.22);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    text-align: left;
}}
.market-latest-values th {{
    background: rgba(128, 128, 128, 0.12);
    font-weight: 600;
}}
.market-latest-values th:last-child,
.market-latest-values td:last-child {{ border-right: 0; }}
.market-latest-values tbody tr:last-child td {{ border-bottom: 0; }}
</style>
<div class="market-latest-values-wrap" tabindex="0" aria-label="{escape(aria_label, quote=True)}">
  <table class="market-latest-values">
    <colgroup>{colgroup_html}</colgroup>
    <thead><tr>{headers}</tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>
"""


def latest_values_table_html(table: pd.DataFrame) -> str:
    """Render a stable latest-values table without a stateful viewport."""
    return _stable_table_html(
        table,
        LATEST_VALUE_COLUMNS,
        latest_value_column_widths(table),
        "最新値の表",
    )


def change_rates_table_html(table: pd.DataFrame) -> str:
    """Render stable market returns without preserving a stale scroll offset."""
    return _stable_table_html(
        table,
        CHANGE_RATE_COLUMNS,
        change_rate_column_widths(table),
        "騰落率の表",
    )


def market_chart_dimensions(series_count: int) -> tuple[int, int]:
    """Reserve legend space without reducing the market chart's plot height.

    The legend can wrap to one item per row on a narrow phone, so the sizing is
    intentionally based on that conservative layout. Wider screens may retain
    extra whitespace, but the plot area remains stable as series are added.
    """
    legend_rows = max(1, series_count)
    bottom_margin = max(
        90,
        MARKET_CHART_LEGEND_GAP + legend_rows * MARKET_CHART_LEGEND_ROW_HEIGHT,
    )
    total_height = MARKET_CHART_TOP_MARGIN + MARKET_CHART_PLOT_HEIGHT + bottom_margin
    return total_height, bottom_margin


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
