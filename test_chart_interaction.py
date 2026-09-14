import ast
from pathlib import Path
import unittest

import plotly.graph_objects as go

from chart_interaction import exploratory_chart_config, make_chart_static


class ChartInteractionTest(unittest.TestCase):
    def test_static_chart_locks_both_axes_and_hides_modebar(self) -> None:
        figure = go.Figure(go.Scatter(x=[1, 2], y=[3, 4]))
        config = make_chart_static(figure)

        self.assertTrue(figure.layout.xaxis.fixedrange)
        self.assertTrue(figure.layout.yaxis.fixedrange)
        self.assertFalse(config["displayModeBar"])
        self.assertFalse(config["scrollZoom"])

    def test_explorable_chart_has_visible_reset_without_scroll_zoom(self) -> None:
        config = exploratory_chart_config()

        self.assertTrue(config["displayModeBar"])
        self.assertFalse(config["displaylogo"])
        self.assertFalse(config["scrollZoom"])
        self.assertEqual(config["doubleClick"], "reset")
        self.assertIn("select2d", config["modeBarButtonsToRemove"])
        self.assertIn("lasso2d", config["modeBarButtonsToRemove"])

    def test_config_returns_an_independent_button_list(self) -> None:
        first = exploratory_chart_config()
        second = exploratory_chart_config()
        first["modeBarButtonsToRemove"].append("zoom2d")

        self.assertNotIn("zoom2d", second["modeBarButtonsToRemove"])

    def test_every_plotly_chart_call_declares_an_interaction_policy(self) -> None:
        for filename in ("app.py", "japan_equity_view.py", "semiconductor_view.py"):
            tree = ast.parse(Path(filename).read_text(encoding="utf-8"), filename=filename)
            calls = [
                node for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "plotly_chart"
            ]
            self.assertTrue(calls, filename)
            for call in calls:
                self.assertIn("config", {keyword.arg for keyword in call.keywords}, filename)


if __name__ == "__main__":
    unittest.main()
