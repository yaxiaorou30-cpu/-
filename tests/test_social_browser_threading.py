import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from src.social_browser import BrowserSessionManager


class FakePage:
    def __init__(self, calls):
        self.calls = calls
        self.url = "about:blank"

    def goto(self, *args, **kwargs):
        self.calls.append(("goto", threading.get_ident()))
        self.url = args[0]

    def is_closed(self):
        return False

    def bring_to_front(self):
        self.calls.append(("bring_to_front", threading.get_ident()))

    def wait_for_load_state(self, *args, **kwargs):
        self.calls.append(("wait_for_load_state", threading.get_ident()))

    def wait_for_selector(self, *args, **kwargs):
        self.calls.append(("wait_for_selector", threading.get_ident()))

    def evaluate(self, script, *args):
        self.calls.append(("evaluate", threading.get_ident()))
        if args:
            return {"state": True, "kind": "account_control"}
        return False

    def wait_for_timeout(self, timeout):
        self.calls.append(("wait_for_timeout", threading.get_ident()))

    def locator(self, selector):
        page = self

        class Locator:
            def inner_text(self, **kwargs):
                page.calls.append(("inner_text", threading.get_ident()))
                return "警方通报 视频结果"

        return Locator()

    def content(self):
        self.calls.append(("content", threading.get_ident()))
        return (
            "<html><body><div data-e2e='search-card'>"
            "<a href='https://www.douyin.com/video/1234567890'>警方通报 视频结果</a>"
            "</div></body></html>"
        )


class FakeContext:
    def __init__(self, calls):
        self.calls = calls
        self.pages = [FakePage(calls)]

    def new_page(self):
        return self.pages[0]

    def storage_state(self):
        self.calls.append(("storage_state", threading.get_ident()))
        return {
            "cookies": [
                {
                    "name": "sessionid",
                    "value": "test-secret",
                    "domain": ".douyin.com",
                    "path": "/",
                }
            ],
            "origins": [],
        }

    def close(self):
        self.calls.append(("context.close", threading.get_ident()))


class FakeChromium:
    def __init__(self, calls):
        self.calls = calls

    def launch_persistent_context(self, **kwargs):
        self.calls.append(("launch", threading.get_ident()))
        return FakeContext(self.calls)


class FakePlaywright:
    def __init__(self, calls):
        self.calls = calls
        self.chromium = FakeChromium(calls)

    def stop(self):
        self.calls.append(("playwright.stop", threading.get_ident()))


class FakePlaywrightStarter:
    def __init__(self, calls):
        self.calls = calls

    def start(self):
        self.calls.append(("playwright.start", threading.get_ident()))
        return FakePlaywright(self.calls)


def call_in_new_thread(callback):
    result = {}

    def invoke():
        result["caller_thread"] = threading.get_ident()
        try:
            result["value"] = callback()
        except BaseException as exc:
            result["error"] = exc

    thread = threading.Thread(target=invoke)
    thread.start()
    thread.join(timeout=5)
    if thread.is_alive():
        raise AssertionError("browser session operation did not finish")
    if "error" in result:
        raise result["error"]
    return result


class BrowserSessionThreadingTests(unittest.TestCase):
    def test_open_save_and_close_use_one_dedicated_thread(self):
        calls = []
        root = Path.cwd()
        manager = BrowserSessionManager(
            root,
            sensitive_root=root / ".thread-test-private",
            enforce_acl=False,
        )

        def fake_sync_playwright():
            return FakePlaywrightStarter(calls)

        with (
            patch(
                "src.social_browser.load_playwright",
                return_value=(fake_sync_playwright, TimeoutError),
            ),
            patch(
                "src.social_browser.ensure_private_directory",
                side_effect=lambda path, **kwargs: Path(path),
            ),
        ):
            try:
                opened = call_in_new_thread(lambda: manager.start_login("抖音"))
                xhs_opened = call_in_new_thread(lambda: manager.start_login("小红书"))
                saved = call_in_new_thread(lambda: manager.save_session("抖音"))
                probed = call_in_new_thread(lambda: manager.probe_login_controls("抖音"))
                read = call_in_new_thread(
                    lambda: manager.read_page(
                        "抖音",
                        "https://www.douyin.com/search/警方通报",
                    )
                )
                closed = call_in_new_thread(lambda: manager.close_session("抖音"))
                xhs_closed = call_in_new_thread(lambda: manager.close_session("小红书"))
            finally:
                manager.shutdown()

        backend_thread_ids = {thread_id for _, thread_id in calls}
        self.assertEqual(len(backend_thread_ids), 1)
        self.assertNotIn(opened["caller_thread"], backend_thread_ids)
        self.assertNotIn(xhs_opened["caller_thread"], backend_thread_ids)
        self.assertNotIn(saved["caller_thread"], backend_thread_ids)
        self.assertNotIn(probed["caller_thread"], backend_thread_ids)
        self.assertNotIn(read["caller_thread"], backend_thread_ids)
        self.assertNotIn(closed["caller_thread"], backend_thread_ids)
        self.assertNotIn(xhs_closed["caller_thread"], backend_thread_ids)
        self.assertEqual(saved["value"]["cookie_count"], 1)
        self.assertTrue(probed["value"]["login_confirmed"])
        self.assertIsNone(read["value"][2])
        self.assertIn("/video/1234567890", read["value"][0])
        self.assertEqual(
            sum(1 for name, _ in calls if name == "playwright.start"),
            1,
        )
        self.assertEqual(
            sum(1 for name, _ in calls if name == "playwright.stop"),
            1,
        )
        self.assertTrue({"launch", "storage_state", "context.close", "playwright.stop"}.issubset(
            {name for name, _ in calls}
        ))


if __name__ == "__main__":
    unittest.main()
