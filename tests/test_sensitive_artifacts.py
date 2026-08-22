import json
import shutil
import unittest
from pathlib import Path

from src.sensitive_artifacts import DiagnosticSnapshotStore, safe_remove_tree
from src.social_browser import BrowserSessionManager


class SensitiveArtifactTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("data") / "_test_sensitive_artifacts"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True)
        self.private_root = self.root / "private"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_diagnostics_are_off_by_default(self):
        store = DiagnosticSnapshotStore(
            self.root,
            sensitive_root=self.private_root,
            enforce_acl=False,
        )
        result = store.write(
            platform="微博",
            channel="微博搜索",
            url="https://weibo.com/search?q=secret",
            html_text="<html>raw secret</html>",
        )

        self.assertEqual(result, "")
        self.assertFalse(store.diagnostic_root.exists())

    def test_diagnostic_contains_only_bounded_sanitized_summary(self):
        store = DiagnosticSnapshotStore(
            self.root,
            sensitive_root=self.private_root,
            enabled=True,
            enforce_acl=False,
        )
        reference = store.write(
            platform="微博",
            channel="微博搜索",
            url="https://weibo.com/search/private-user?q=top-secret",
            html_text="<html><form>验证码 raw-secret-body</form><script></script></html>",
        )
        files = list(store.diagnostic_root.glob("*.diagnostic.json"))
        text = files[0].read_text(encoding="utf-8")
        payload = json.loads(text)

        self.assertTrue(reference.startswith("private-diagnostics/"))
        self.assertEqual(len(files), 1)
        self.assertNotIn("top-secret", text)
        self.assertNotIn("private-user", text)
        self.assertNotIn("raw-secret-body", text)
        self.assertEqual(payload["path_category"], "/search/…")
        self.assertTrue(payload["html_summary"]["has_verification_prompt"])

    def test_platform_clear_is_scoped_and_removes_legacy_snapshot(self):
        store = DiagnosticSnapshotStore(
            self.root,
            sensitive_root=self.private_root,
            enabled=True,
            enforce_acl=False,
        )
        store.write(
            platform="微博",
            channel="微博搜索",
            url="https://weibo.com/search",
            html_text="<html>weibo</html>",
        )
        store.write(
            platform="B站",
            channel="B站搜索",
            url="https://bilibili.com/all",
            html_text="<html>bilibili</html>",
        )
        legacy = self.root / "data" / "debug"
        legacy.mkdir(parents=True)
        (legacy / "latest_weibo_search.html").write_text("legacy secret", encoding="utf-8")

        removed = store.clear_platform("微博")

        self.assertEqual(removed, 2)
        self.assertFalse(list(store.diagnostic_root.glob("weibo_*.diagnostic.json")))
        self.assertEqual(len(list(store.diagnostic_root.glob("bilibili_*.diagnostic.json"))), 1)
        self.assertFalse((legacy / "latest_weibo_search.html").exists())

    def test_browser_profile_clear_removes_only_selected_platform(self):
        manager = BrowserSessionManager(
            self.root,
            sensitive_root=self.private_root,
            enforce_acl=False,
        )
        for base in (manager.profile_root, manager.legacy_profile_root):
            for slug in ("weibo", "bilibili"):
                path = base / slug
                path.mkdir(parents=True)
                (path / "state.bin").write_text("secret", encoding="utf-8")

        result = manager.clear_platform_data("微博")

        self.assertEqual(result["profile_trees_removed"], 2)
        self.assertFalse((manager.profile_root / "weibo").exists())
        self.assertFalse((manager.legacy_profile_root / "weibo").exists())
        self.assertTrue((manager.profile_root / "bilibili").exists())
        self.assertTrue((manager.legacy_profile_root / "bilibili").exists())

    def test_safe_remove_refuses_entire_root(self):
        self.private_root.mkdir(parents=True)
        with self.assertRaises(ValueError):
            safe_remove_tree(self.private_root, self.private_root)


if __name__ == "__main__":
    unittest.main()
