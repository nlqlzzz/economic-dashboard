"""Shared Plotly interaction policy for desktop and mobile views."""
from __future__ import annotations

from typing import Any


STATIC_CHART_CONFIG: dict[str, object] = {
    "displayModeBar": False,
    "scrollZoom": False,
}

EXPLORABLE_CHART_CONFIG: dict[str, object] = {
    "displayModeBar": True,
    "displaylogo": False,
    "scrollZoom": False,
    "doubleClick": "reset",
    "modeBarButtonsToRemove": ["select2d", "lasso2d"],
}


def make_chart_static(figure: Any) -> dict[str, object]:
    """Lock Cartesian axes while preserving hover information."""
    figure.update_xaxes(fixedrange=True)
    figure.update_yaxes(fixedrange=True)
    return dict(STATIC_CHART_CONFIG)


def exploratory_chart_config() -> dict[str, object]:
    """Keep deliberate zoom with a visible reset path; disable scroll zoom."""
    return {
        **EXPLORABLE_CHART_CONFIG,
        "modeBarButtonsToRemove": list(EXPLORABLE_CHART_CONFIG["modeBarButtonsToRemove"]),
    }
