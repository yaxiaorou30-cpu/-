import json
import shutil
import unittest
from pathlib import Path

from src.crawler import NewsCrawler
from src.source_policy import (
    AUTHORIZED_SESSION_ACCESS_MODE,
    EXTERNAL_ADAPTER_ACCESS_MODE,
    SOURCE_POLICY_PRODUCT_TOKEN,
    SOURCE_POLICY_USER_AGENT,
    AccessDecision,
    SourceAccessPolicy,
)


class FakeResponse:
    def __init__(self, status_code=200, content=b"", url="", headers=None):
        self.status_code = status_code
        self.content = content
        self.url = url
        self.headers = headers or {}


class SourceAccessPolicyTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("data") / "_test_source_policy"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True)
        self.registry_path = self.root / "rules.json"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write_registry(self, *, sources=None):
        payload = {
            "version": 1,
            "robots_cache_ttl_seconds": 3600,
            "default_rule": {
                "id": "SRC-DEFAULT",
                "name": "测试公开来源",
                "access_type": "A0",
                "support_level": "S2",
                "automation_enabled": True,
                "robots_required": True,
                "external_adapter_allowed": False,
                "platform_rule_status": "test",
                "allowed_paths": [],
                "allowed_path_prefixes": [],
                "denied_path_prefixes": [],
            },
            "sources": sources or [],
        }
        self.registry_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_robots_longest_match_and_cache_are_enforced(self):
        self.write_registry()
        calls = []
        robots = (
            b"User-agent: *\n"
            b"Disallow: /private\n"
            b"Allow: /private/public\n"
        )

        def fetcher(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(200, robots, url)

        policy = SourceAccessPolicy(self.registry_path, fetcher=fetcher)
        public = policy.check("https://example.com/private/public/a?token=secret")
        private = policy.check("https://example.com/private/a")

        self.assertTrue(public.allowed)
        self.assertFalse(private.allowed)
        self.assertEqual(private.code, "robots_disallowed")
        self.assertEqual(len(calls), 1)
        self.assertIn(SOURCE_POLICY_PRODUCT_TOKEN, calls[0][1]["headers"]["User-Agent"])

    def test_ordinary_4xx_allows_but_5xx_and_network_error_block(self):
        self.write_registry()
        unavailable = SourceAccessPolicy(
            self.registry_path,
            fetcher=lambda *args, **kwargs: FakeResponse(404, b"", args[0]),
        )
        unreachable = SourceAccessPolicy(
            self.registry_path,
            fetcher=lambda *args, **kwargs: FakeResponse(503, b"", args[0]),
        )

        def fail_fetch(*args, **kwargs):
            raise OSError("network unavailable")

        network_error = SourceAccessPolicy(self.registry_path, fetcher=fail_fetch)

        self.assertTrue(unavailable.check("https://example.com/public").allowed)
        self.assertEqual(
            unreachable.check("https://example.com/public").code,
            "robots_unreachable",
        )
        self.assertEqual(
            network_error.check("https://example.com/public").code,
            "robots_unreachable",
        )

    def test_robots_redirects_are_never_followed_automatically(self):
        self.write_registry()
        redirect_targets = (
            "http://127.0.0.1/private",
            "https://private.internal/robots.txt",
            "https://other.example/robots.txt",
        )

        for location in redirect_targets:
            with self.subTest(location=location):
                calls = []

                def fetcher(url, **kwargs):
                    calls.append((url, kwargs))
                    return FakeResponse(
                        302,
                        b"",
                        url,
                        {"Location": location},
                    )

                policy = SourceAccessPolicy(self.registry_path, fetcher=fetcher)
                decision = policy.check("https://example.com/public")

                self.assertFalse(decision.allowed)
                self.assertEqual(decision.code, "robots_unreachable")
                self.assertEqual(len(calls), 1)
                self.assertFalse(calls[0][1]["allow_redirects"])

    def test_disabled_platform_and_private_target_stop_before_fetch(self):
        source = {
            "id": "SRC-DOUYIN",
            "name": "抖音",
            "domains": ["douyin.com"],
            "access_type": "A1",
            "support_level": "S0",
            "automation_enabled": False,
            "automation_reason": "安全验证后停止自动路径",
            "robots_required": True,
            "external_adapter_allowed": False,
            "platform_rule_status": "stopped",
        }
        self.write_registry(sources=[source])

        def unexpected_fetch(*args, **kwargs):
            self.fail("策略本地阻断后不应请求 robots.txt")

        policy = SourceAccessPolicy(self.registry_path, fetcher=unexpected_fetch)

        self.assertEqual(
            policy.check("https://www.douyin.com/search/test").code,
            "automation_disabled",
        )
        self.assertEqual(
            policy.check("http://127.0.0.1/private").code,
            "private_network_target",
        )

    def test_authorized_session_and_external_adapter_use_separate_rules(self):
        source = {
            "id": "SRC-SOCIAL",
            "name": "测试社交平台",
            "domains": ["example.com"],
            "access_type": "A1",
            "support_level": "S3目标",
            "automation_enabled": True,
            "robots_required": True,
            "authorized_session_enabled": True,
            "authorized_session_robots_required": False,
            "external_adapter_allowed": True,
            "external_adapter_robots_required": False,
            "platform_rule_status": "test",
            "allowed_path_prefixes": ["/search"],
        }
        self.write_registry(sources=[source])
        calls = []

        def fetcher(url, **kwargs):
            calls.append(url)
            return FakeResponse(200, b"User-agent: *\nDisallow: /\n", url)

        policy = SourceAccessPolicy(self.registry_path, fetcher=fetcher)

        public = policy.check("https://example.com/search?q=test")
        authorized = policy.check(
            "https://example.com/search?q=test",
            access_mode=AUTHORIZED_SESSION_ACCESS_MODE,
        )
        external = policy.check(
            "https://example.com/search?q=test",
            access_mode=EXTERNAL_ADAPTER_ACCESS_MODE,
        )

        self.assertEqual(public.code, "robots_disallowed")
        self.assertTrue(authorized.allowed)
        self.assertEqual(authorized.code, "authorized_session_allowed")
        self.assertTrue(external.allowed)
        self.assertEqual(external.code, "external_adapter_allowed")
        self.assertEqual(len(calls), 1)

    def test_authorized_session_robots_default_follows_source_robots_requirement(self):
        source = {
            "id": "SRC-SAVED-SESSION",
            "name": "已保存网站会话",
            "domains": ["example.com"],
            "access_type": "A1",
            "support_level": "S2",
            "automation_enabled": True,
            "robots_required": True,
            "platform_rule_status": "test",
        }
        self.write_registry(sources=[source])
        calls = []

        def fetcher(url, **kwargs):
            calls.append(url)
            return FakeResponse(200, b"User-agent: *\nDisallow: /\n", url)

        policy = SourceAccessPolicy(self.registry_path, fetcher=fetcher)

        decision = policy.check(
            "https://example.com/member/article",
            access_mode=AUTHORIZED_SESSION_ACCESS_MODE,
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "robots_disallowed")
        self.assertEqual(len(calls), 1)

    def test_authorized_session_explicit_robots_requirement_is_respected(self):
        source = {
            "id": "SRC-ROBOTS-SESSION",
            "name": "显式检查 robots 的授权会话",
            "domains": ["example.com"],
            "access_type": "A1",
            "support_level": "S2",
            "automation_enabled": True,
            "robots_required": False,
            "authorized_session_enabled": True,
            "authorized_session_robots_required": True,
            "platform_rule_status": "test",
        }
        self.write_registry(sources=[source])
        calls = []

        def fetcher(url, **kwargs):
            calls.append(url)
            return FakeResponse(200, b"User-agent: *\nDisallow: /\n", url)

        policy = SourceAccessPolicy(self.registry_path, fetcher=fetcher)
        decision = policy.check(
            "https://example.com/member/article",
            access_mode=AUTHORIZED_SESSION_ACCESS_MODE,
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "robots_disallowed")
        self.assertEqual(len(calls), 1)

    def test_authorized_session_explicit_disable_still_blocks(self):
        source = {
            "id": "SRC-DISABLED-SESSION",
            "name": "禁用授权会话",
            "domains": ["example.com"],
            "access_type": "A1",
            "support_level": "S0",
            "automation_enabled": True,
            "robots_required": False,
            "authorized_session_enabled": False,
            "authorized_session_robots_required": False,
            "platform_rule_status": "stopped",
        }
        self.write_registry(sources=[source])
        policy = SourceAccessPolicy(
            self.registry_path,
            fetcher=lambda *args, **kwargs: self.fail("显式禁用后不应请求 robots.txt"),
        )

        decision = policy.check(
            "https://example.com/member/article",
            access_mode=AUTHORIZED_SESSION_ACCESS_MODE,
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "authorized_session_disabled")

    def test_audit_excludes_query_and_full_path(self):
        self.write_registry()
        audit_path = self.root / "audit.json"
        policy = SourceAccessPolicy(
            self.registry_path,
            audit_path=audit_path,
            fetcher=lambda *args, **kwargs: FakeResponse(404, b"", args[0]),
        )
        policy.check("https://example.com/search/private-id?token=top-secret")
        audit_text = audit_path.read_text(encoding="utf-8")

        self.assertNotIn("top-secret", audit_text)
        self.assertNotIn("private-id", audit_text)
        self.assertIn("/search/…", audit_text)

    def test_crawler_rechecks_policy_before_following_redirect(self):
        class RedirectPolicy:
            def __init__(self):
                self.urls = []

            def check(self, url, channel="", access_mode="public_crawler"):
                self.urls.append(url)
                allowed = url.startswith("https://allowed.example/")
                return AccessDecision(
                    allowed=allowed,
                    code="allowed" if allowed else "redirect_blocked",
                    reason="test redirect boundary",
                    source_rule_id="SRC-TEST",
                    source_name="test",
                    support_level="TEST",
                    access_type="TEST",
                    platform_rule_status="test",
                    external_adapter_allowed=False,
                )

        class RedirectSession:
            def __init__(self):
                self.calls = 0

            def get(self, url, **kwargs):
                self.calls += 1
                return FakeResponse(
                    302,
                    b"",
                    url,
                    {"Location": "https://blocked.example/private"},
                )

        policy = RedirectPolicy()
        crawler = NewsCrawler(source_policy=policy)
        crawler.session = RedirectSession()
        _, final_url, error = crawler._request_html(
            "https://allowed.example/start",
            "test",
        )

        self.assertEqual(crawler.session.calls, 1)
        self.assertEqual(final_url, "https://blocked.example/private")
        self.assertIn("redirect_blocked", error)
        self.assertEqual(
            policy.urls,
            [
                "https://allowed.example/start",
                "https://blocked.example/private",
            ],
        )
        self.assertIn(SOURCE_POLICY_PRODUCT_TOKEN, SOURCE_POLICY_USER_AGENT)

    def test_production_registry_allows_bing_news_rss_search_path(self):
        policy = SourceAccessPolicy(
            Path("config") / "source_access_rules.json",
            fetcher=lambda *args, **kwargs: FakeResponse(
                200,
                b"User-agent: *\nDisallow: /search\n",
                args[0],
            ),
        )

        allowed = policy.check(
            "https://www.bing.com/news/search?q=test&format=RSS",
            "Bing News RSS",
        )
        unrelated = policy.check("https://www.bing.com/account/private", "Bing News RSS")

        self.assertTrue(allowed.allowed)
        self.assertEqual(allowed.source_rule_id, "SRC-PUBLIC-BING-NEWS")
        self.assertEqual(allowed.support_level, "S2")
        self.assertEqual(unrelated.code, "path_not_registered")

    def test_production_registry_allows_baidu_qianfan_search_api(self):
        policy = SourceAccessPolicy(
            Path("config") / "source_access_rules.json",
            fetcher=lambda *args, **kwargs: self.fail("official API must not fetch robots.txt"),
        )

        allowed = policy.check(
            "https://qianfan.baidubce.com/v2/ai_search/web_search",
            "百度网页搜索",
            access_mode=EXTERNAL_ADAPTER_ACCESS_MODE,
        )

        self.assertTrue(allowed.allowed)
        self.assertEqual(allowed.source_rule_id, "SRC-PUBLIC-BAIDU-QIANFAN")
        self.assertEqual(allowed.code, "external_adapter_allowed")

    def test_production_registry_distinguishes_baijiahao_from_baidu_search(self):
        robots_calls = []

        def fetcher(*args, **kwargs):
            robots_calls.append(args[0])
            return FakeResponse(404, b"", args[0])

        policy = SourceAccessPolicy(
            Path("config") / "source_access_rules.json",
            fetcher=fetcher,
        )

        search = policy.check("https://www.baidu.com/s?wd=test", "百度公开搜索")
        article = policy.check(
            "https://baijiahao.baidu.com/s?id=1234567890",
            "百家号文章",
        )

        self.assertFalse(search.allowed)
        self.assertEqual(search.source_rule_id, "SRC-STABLE-BAIDU")
        self.assertEqual(search.code, "automation_disabled")
        self.assertEqual(article.source_rule_id, "SRC-PUBLIC-BAIJIAHAO")
        self.assertTrue(article.allowed)
        self.assertEqual(robots_calls, [])


if __name__ == "__main__":
    unittest.main()
