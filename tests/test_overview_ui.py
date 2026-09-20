import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OverviewUiTests(unittest.TestCase):
    def test_running_overview_does_not_render_heat_index_card(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web" / "static" / "styles.css").read_text(encoding="utf-8")

        self.assertNotIn("热度指数", html)
        self.assertNotIn('id="heatIndex"', html)
        self.assertNotIn("heat-readout", html)
        self.assertNotIn('getElementById("heatIndex")', javascript)
        self.assertNotIn("els.heatIndex", javascript)
        self.assertNotIn(".heat-readout", styles)


if __name__ == "__main__":
    unittest.main()
