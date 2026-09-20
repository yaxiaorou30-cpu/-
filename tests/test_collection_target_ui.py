import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CollectionTargetUiTests(unittest.TestCase):
    def test_task_form_uses_one_custom_target_input(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="targetResultCount"', html)
        self.assertIn('max="5000"', html)
        self.assertIn('min="1"', html)
        self.assertNotIn('id="collectLevel"', html)
        self.assertNotIn('id="minRealResults"', html)
        self.assertIn("max_results: targetResultCount", javascript)
        self.assertIn("min_real_results: targetResultCount", javascript)
        self.assertNotIn("COLLECT_LEVEL_COPY", javascript)
        self.assertNotIn("els.collectLevel", javascript)
        self.assertNotIn("els.minRealResults", javascript)

    def test_backend_normalizes_target_before_starting_task(self):
        backend = (ROOT / "web_app.py").read_text(encoding="utf-8")

        self.assertIn("payload = normalize_collection_target(self.read_body_json())", backend)
        self.assertIn('return "not_met", f"结果不足：实际 {real_count}/{minimum}"', backend)


if __name__ == "__main__":
    unittest.main()
