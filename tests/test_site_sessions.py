import hashlib
import shutil
import socket
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from src import social_browser


PUBLIC_DNS = [
    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700:4700::1111", 443, 0, 0)),
]

CLASH_FAKE_IP_DNS = [
    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.89", 443)),
]


class FakeFrame:
    def __init__(self, parent_frame=None):
        self.parent_frame = parent_frame


class FakePage:
    def __init__(self):
        self.url = "about:blank"
        self.main_frame = FakeFrame()
        self.closed = False
        self.brought_to_front = 0

    def goto(self, url, **_kwargs):
        self.url = url

    def is_closed(self):
        return self.closed

    def bring_to_front(self):
        self.brought_to_front += 1


class FakeContext:
    def __init__(self, storage_state=None):
        self.pages = [FakePage()]
        self.closed = False
        self.state = storage_state or {"cookies": [], "origins": []}
        self.routes = []
        self.websocket_routes = []

    def new_page(self):
        return self.pages[0]

    def storage_state(self):
        return self.state

    def route(self, pattern, handler):
        self.routes.append((pattern, handler))

    def route_web_socket(self, pattern, handler):
        self.websocket_routes.append((pattern, handler))

    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self):
        self.persistent_launches = []
        self.browser_launches = []

    def launch_persistent_context(self, **kwargs):
        context = FakeContext()
        self.persistent_launches.append((kwargs, context))
        return context

    def launch(self, **kwargs):
        browser = FakeBrowser()
        self.browser_launches.append((kwargs, browser))
        return browser

    def latest_site_context(self):
        if self.browser_launches:
            return self.browser_launches[-1][1].contexts[-1][1]
        return self.persistent_launches[-1][1]

    def latest_site_browser(self):
        return self.browser_launches[-1][1] if self.browser_launches else None


class FakeBrowser:
    def __init__(self):
        self.contexts = []
        self.closed = False

    def new_context(self, **kwargs):
        context = FakeContext()
        self.contexts.append((kwargs, context))
        return context

    def close(self):
        self.closed = True


class FakePlaywright:
    def __init__(self):
        self.chromium = FakeChromium()
        self.stopped = False

    def stop(self):
        self.stopped = True


class FakePlaywrightStarter:
    def __init__(self, playwright):
        self.playwright = playwright

    def start(self):
        return self.playwright


class FakeRoute:
    def __init__(self):
        self.action = ""

    def abort(self, *_args):
        self.action = "abort"

    def continue_(self):
        self.action = "continue"


class FakeRequest:
    def __init__(self, url, *, navigation=False, frame=None):
        self.url = url
        self.frame = frame
        self.navigation = navigation

    def is_navigation_request(self):
        return self.navigation


class FakeWebSocketRoute:
    def __init__(self, url):
        self.url = url
        self.action = ""

    def connect_to_server(self):
        self.action = "connect"

    def close(self, **_kwargs):
        self.action = "close"


class SiteUrlTests(unittest.TestCase):
    def test_loopback_proxy_check_uses_https_then_all_proxy(self):
        cases = (
            ({"http": "http://127.0.0.1:7897"}, False),
            (
                {
                    "https": "http://proxy.example:8080",
                    "all": "http://127.0.0.1:7897",
                },
                False,
            ),
            ({"https": "http://127.0.0.1:7897"}, True),
            ({"all": "socks5://localhost:7897"}, True),
        )

        for proxies, expected in cases:
            with (
                self.subTest(proxies=proxies),
                patch.object(social_browser, "getproxies", return_value=proxies),
            ):
                self.assertEqual(
                    social_browser._has_loopback_system_proxy(),
                    expected,
                )

    def test_normalize_site_url_requires_exact_public_https_host(self):
        with patch.object(social_browser.socket, "getaddrinfo", return_value=PUBLIC_DNS):
            target = social_browser.normalize_site_url(
                " HTTPS://WWW.Example.COM.:443/Login?next=%2F#done "
            )

        self.assertEqual(target["domain"], "www.example.com")
        self.assertEqual(
            target["url"],
            "https://www.example.com/Login?next=%2F",
        )

    def test_normalize_site_url_rejects_more_than_2048_characters(self):
        oversized = "https://example.com/" + ("a" * 2048)

        with self.assertRaises(ValueError):
            social_browser.normalize_site_url(oversized, resolve_dns=False)

    def test_normalize_site_url_rejects_unsafe_url_shapes(self):
        invalid_urls = (
            "http://example.com/login",
            "https://user:pass@example.com/login",
            "https://example.com:444/login",
            "https://localhost/login",
            "https://127.0.0.1/login",
            "https://[::1]/login",
            "https://203.0.113.10/login",
            "https://198.18.0.89/login",
        )

        for url in invalid_urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                social_browser.normalize_site_url(url)

    def test_normalize_site_url_rejects_when_any_dns_address_is_not_public(self):
        mixed_dns = [
            PUBLIC_DNS[0],
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443)),
        ]
        with (
            patch.object(social_browser.socket, "getaddrinfo", return_value=mixed_dns),
            self.assertRaises(ValueError),
        ):
            social_browser.normalize_site_url("https://example.com/login")

    def test_normalize_site_url_allows_clash_fake_ip_only_with_loopback_proxy(self):
        with (
            patch.object(
                social_browser.socket,
                "getaddrinfo",
                return_value=CLASH_FAKE_IP_DNS,
            ),
            self.assertRaisesRegex(ValueError, "Clash Fake-IP"),
        ):
            social_browser.normalize_site_url("https://example.com/login")

        with (
            patch.object(
                social_browser.socket,
                "getaddrinfo",
                return_value=CLASH_FAKE_IP_DNS,
            ),
            patch.object(
                social_browser,
                "_has_loopback_system_proxy",
                return_value=False,
            ),
            self.assertRaisesRegex(ValueError, "Clash Fake-IP"),
        ):
            social_browser.normalize_site_url(
                "https://example.com/login",
                allow_clash_fake_ip=True,
            )

        with (
            patch.object(
                social_browser.socket,
                "getaddrinfo",
                return_value=CLASH_FAKE_IP_DNS,
            ),
            patch.object(
                social_browser,
                "_has_loopback_system_proxy",
                return_value=True,
            ),
        ):
            target = social_browser.normalize_site_url(
                "https://example.com/login",
                allow_clash_fake_ip=True,
            )

        self.assertEqual(target["domain"], "example.com")

    def test_filter_storage_state_keeps_only_data_usable_by_exact_https_host(self):
        state = {
            "cookies": [
                {"name": "parent", "value": "keep-parent", "domain": ".example.com"},
                {"name": "exact", "value": "keep-exact", "domain": ".news.example.com"},
                {"name": "child", "value": "drop-child", "domain": ".private.news.example.com"},
                {"name": "other", "value": "drop-other", "domain": ".evil.example"},
                {
                    "name": "expired",
                    "value": "drop-expired",
                    "domain": ".example.com",
                    "expires": time.time() - 10,
                },
            ],
            "origins": [
                {
                    "origin": "https://news.example.com",
                    "localStorage": [{"name": "token", "value": "keep-storage"}],
                },
                {
                    "origin": "https://sub.news.example.com",
                    "localStorage": [{"name": "token", "value": "drop-subdomain"}],
                },
                {
                    "origin": "http://news.example.com",
                    "localStorage": [{"name": "token", "value": "drop-http"}],
                },
            ],
        }

        filtered = social_browser.filter_storage_state_for_site(state, "news.example.com")

        self.assertEqual(
            [cookie["name"] for cookie in filtered["cookies"]],
            ["parent", "exact"],
        )
        self.assertEqual(
            [cookie["domain"] for cookie in filtered["cookies"]],
            ["news.example.com", "news.example.com"],
        )
        self.assertEqual(
            [origin["origin"] for origin in filtered["origins"]],
            ["https://news.example.com"],
        )
        self.assertNotIn("drop-", str(filtered))


class SiteSessionManagerTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("data") / "_test_site_sessions"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True)
        self.playwright = FakePlaywright()
        self.manager = social_browser.BrowserSessionManager(
            self.root,
            sensitive_root=self.root / "private",
            enforce_acl=False,
        )
        self.playwright_patch = patch.object(
            social_browser,
            "load_playwright",
            return_value=(lambda: FakePlaywrightStarter(self.playwright), TimeoutError),
        )
        self.dns_patch = patch.object(
            social_browser.socket,
            "getaddrinfo",
            return_value=PUBLIC_DNS,
        )
        self.playwright_patch.start()
        self.dns_patch.start()

    def tearDown(self):
        self.manager.shutdown()
        self.dns_patch.stop()
        self.playwright_patch.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_site_login_uses_ephemeral_context_and_only_one_generic_window(self):
        self.manager.start_login("抖音")
        social_context = self.playwright.chromium.persistent_launches[0][1]

        first = self.manager.start_site_login(
            "https://example.com/login?token=do-not-return#ignored"
        )
        first_context = self.playwright.chromium.latest_site_context()
        first_browser = self.playwright.chromium.latest_site_browser()
        second = self.manager.start_site_login("https://other.example/account")
        second_context = self.playwright.chromium.latest_site_context()
        second_browser = self.playwright.chromium.latest_site_browser()

        self.assertEqual(first["domain"], "example.com")
        self.assertNotIn("do-not-return", str(first))
        self.assertEqual(len(self.playwright.chromium.persistent_launches), 1)
        self.assertEqual(len(self.playwright.chromium.browser_launches), 2)
        first_context_kwargs = self.playwright.chromium.browser_launches[0][1].contexts[0][0]
        self.assertEqual(first_context_kwargs["service_workers"], "block")
        self.assertFalse((self.manager.profile_root / "sites").exists())
        self.assertTrue(first_context.closed)
        self.assertTrue(first_browser.closed)
        self.assertFalse(second_context.closed)
        self.assertFalse(social_context.closed)
        self.assertEqual(second["domain"], "other.example")
        self.assertEqual(set(self.manager.status()), {"抖音"})

        self.manager.close_site_session("other.example")
        self.assertTrue(second_context.closed)
        self.assertTrue(second_browser.closed)
        self.assertFalse(social_context.closed)

    def test_site_login_proxy_mode_allows_fake_ip_for_page_assets_and_websockets(self):
        with (
            patch.object(
                social_browser.socket,
                "getaddrinfo",
                return_value=CLASH_FAKE_IP_DNS,
            ),
            patch.object(
                social_browser,
                "_has_loopback_system_proxy",
                return_value=True,
            ),
        ):
            self.manager.start_site_login(
                "https://example.com/login",
                use_system_proxy=True,
            )
            context = self.playwright.chromium.latest_site_context()

            route = FakeRoute()
            context.routes[0][1](
                route,
                FakeRequest("https://cdn.example.com/app.js"),
            )
            websocket = FakeWebSocketRoute("wss://socket.example.com/connect")
            context.websocket_routes[0][1](websocket)

        self.assertEqual(route.action, "continue")
        self.assertEqual(websocket.action, "connect")

    def test_save_site_session_requires_exact_final_host_and_accepts_local_storage(self):
        self.manager.start_site_login("https://example.com/login")
        context = self.playwright.chromium.latest_site_context()
        browser = self.playwright.chromium.latest_site_browser()
        context.state = {
            "cookies": [],
            "origins": [
                {
                    "origin": "https://example.com",
                    "localStorage": [{"name": "session", "value": "top-secret"}],
                },
                {
                    "origin": "https://other.example",
                    "localStorage": [{"name": "session", "value": "other-secret"}],
                },
            ],
        }
        context.pages[0].url = "https://sub.example.com/account"

        with self.assertRaises(RuntimeError):
            self.manager.save_site_session("example.com")

        context.pages[0].url = "https://example.com/account"
        popup = FakePage()
        popup.url = "https://sso.public.example/complete"
        context.pages.append(popup)

        with self.assertRaises(RuntimeError):
            self.manager.save_site_session("example.com")

        popup.url = "https://example.com/complete"
        with patch.object(
            social_browser.socket,
            "getaddrinfo",
            side_effect=OSError("offline"),
        ):
            saved = self.manager.save_site_session("example.com")

        self.assertEqual(saved["cookie_count"], 0)
        self.assertEqual(saved["origin_count"], 1)
        self.assertTrue(saved["has_local_storage"])
        self.assertEqual(
            saved["storage_state"]["origins"][0]["origin"],
            "https://example.com",
        )
        public_status = {key: value for key, value in saved.items() if key != "storage_state"}
        self.assertNotIn("top-secret", str(public_status))
        self.assertNotIn("other-secret", str(saved))
        self.assertTrue(context.closed)
        self.assertTrue(browser.closed)

    def test_site_login_blocks_literal_private_network_subrequests(self):
        self.manager.start_site_login("https://example.com/login")
        context = self.playwright.chromium.latest_site_context()
        self.assertEqual(context.routes[0][0], "**/*")
        guard = context.routes[0][1]

        expected_actions = {
            "http://localhost/admin": "abort",
            "http://cdn.public.example/app.js": "abort",
            "https://127.0.0.1/private": "abort",
            "http://[::1]/private": "abort",
            "https://10.0.0.8/private": "abort",
            "https://203.0.113.10/reserved": "abort",
            "https://cdn.public.example:8443/app.js": "abort",
            "https://sso.public.example/login": "continue",
            "data:text/plain,asset": "continue",
        }
        for url, expected in expected_actions.items():
            with self.subTest(url=url):
                route = FakeRoute()
                guard(route, FakeRequest(url))
                self.assertEqual(route.action, expected)

    def test_site_login_requires_public_https_for_main_frame_navigation(self):
        self.manager.start_site_login("https://example.com/login")
        context = self.playwright.chromium.latest_site_context()
        page = context.pages[0]
        guard = context.routes[0][1]

        def resolve_navigation(host, _port, **_kwargs):
            if host == "private-dns.example":
                return [
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.8", 443)),
                ]
            if host == "mixed-dns.example":
                return [
                    PUBLIC_DNS[0],
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443)),
                ]
            return PUBLIC_DNS

        checks = (
            ("https://sso.public.example/login", True, "continue"),
            ("http://sso.public.example/login", True, "abort"),
            ("https://private-dns.example/login", True, "abort"),
            ("https://private-dns.example/app.js", False, "abort"),
            ("https://mixed-dns.example/app.js", False, "abort"),
            ("https://cdn.public.example/app.js", False, "continue"),
        )
        with patch.object(
            social_browser.socket,
            "getaddrinfo",
            side_effect=resolve_navigation,
        ):
            for url, navigation, expected in checks:
                with self.subTest(url=url, navigation=navigation):
                    route = FakeRoute()
                    guard(
                        route,
                        FakeRequest(
                            url,
                            navigation=navigation,
                            frame=page.main_frame if navigation else None,
                        ),
                    )
                    self.assertEqual(route.action, expected)

    def test_site_login_guards_websocket_targets_before_connecting(self):
        self.manager.start_site_login("https://example.com/login")
        context = self.playwright.chromium.latest_site_context()
        self.assertEqual(context.websocket_routes[0][0], "**")
        guard = context.websocket_routes[0][1]

        expected_actions = {
            "ws://example.com/socket": "close",
            "wss://127.0.0.1/socket": "close",
            "wss://socket.public.example:8443/connect": "close",
            "wss://socket.public.example/connect": "connect",
        }
        for url, expected in expected_actions.items():
            with self.subTest(url=url):
                websocket = FakeWebSocketRoute(url)
                guard(websocket)
                self.assertEqual(websocket.action, expected)

    def test_site_login_blocks_cross_domain_popup_navigation(self):
        self.manager.start_site_login("https://example.com/login")
        context = self.playwright.chromium.latest_site_context()
        page = context.pages[0]
        guard = context.routes[0][1]
        popup_frame = FakeFrame()

        checks = (
            ("https://sso.public.example/login", page.main_frame, "continue"),
            ("https://sso.public.example/login", popup_frame, "abort"),
            ("https://example.com/callback", popup_frame, "continue"),
            ("http://example.com/callback", popup_frame, "abort"),
        )
        for url, frame, expected in checks:
            with self.subTest(url=url, original=frame is page.main_frame):
                route = FakeRoute()
                guard(route, FakeRequest(url, navigation=True, frame=frame))
                self.assertEqual(route.action, expected)

    def test_save_site_session_rejects_empty_filtered_state(self):
        self.manager.start_site_login("https://example.com/login")
        context = self.playwright.chromium.latest_site_context()
        context.state = {
            "cookies": [{"name": "sid", "value": "other-secret", "domain": ".other.example"}],
            "origins": [],
        }

        with self.assertRaises(RuntimeError):
            self.manager.save_site_session("example.com")

    def test_clear_site_data_removes_only_matching_site_profile(self):
        digest = hashlib.sha256(b"example.com").hexdigest()
        site_profile = self.manager.profile_root / "sites" / digest
        social_profile = self.manager.profile_root / "weibo"
        site_profile.mkdir(parents=True)
        social_profile.mkdir(parents=True)
        (site_profile / "state.bin").write_text("site-secret", encoding="utf-8")
        (social_profile / "state.bin").write_text("social-secret", encoding="utf-8")

        with patch.object(
            social_browser.socket,
            "getaddrinfo",
            side_effect=OSError("offline"),
        ):
            result = self.manager.clear_site_data("EXAMPLE.COM.")

        self.assertEqual(result["domain"], "example.com")
        self.assertEqual(result["profile_trees_removed"], 1)
        self.assertFalse(site_profile.exists())
        self.assertTrue(social_profile.exists())


if __name__ == "__main__":
    unittest.main()
