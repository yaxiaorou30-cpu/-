import json
import sys
import types
import unittest
from unittest import mock
from pathlib import Path

from src.crawler import NewsCrawler as ProductionNewsCrawler
from src.external_content_adapters import (
    AiotiebaThreadAdapter,
    BridgeCommandResult,
    EnrichmentOutcome,
    Newspaper4kArticleAdapter,
    ScraplingArticleAdapter,
)
from src.external_readonly_bridge import (
    _setup_public_only_routes,
    _validate_public_url,
    fetch_scrapling_article,
)
from tests.helpers import AllowAllSourcePolicy


class NewsCrawler(ProductionNewsCrawler):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("source_policy", AllowAllSourcePolicy())
        super().__init__(*args, **kwargs)


class FakeBridgeRunner:
    def __init__(self, response, returncode=0):
        self.result = BridgeCommandResult(
            returncode=returncode,
            stdout=json.dumps(response, ensure_ascii=False),
            stderr="",
        )
        self.calls = []

    def run(self, command, payload, cwd, timeout):
        self.calls.append({
            "command": list(command),
            "payload": dict(payload),
            "cwd": Path(cwd),
            "timeout": timeout,
        })
        return self.result


def build_available_adapter(adapter_class, response):
    runner = FakeBridgeRunner(response)
    adapter = adapter_class(Path("fake-candidate"), bridge_script=Path("fake-bridge.py"), runner=runner)
    adapter.is_available = lambda: True
    return adapter, runner


class ExternalContentAdapterTests(unittest.TestCase):
    def test_scrapling_bridge_blocks_local_targets(self):
        for url in (
            "http://127.0.0.1/private",
            "http://localhost/private",
            "http://10.0.0.8/private",
            "file:///etc/passwd",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                _validate_public_url(url)

    def test_scrapling_bridge_enables_strong_fetcher_options(self):
        calls = []

        class FakePage:
            html_content = "<html><article>公开正文</article></html>"
            url = "https://news.example.com/article/1"
            status = 200

        class FakeStealthyFetcher:
            @staticmethod
            def fetch(url, **kwargs):
                calls.append((url, kwargs))
                return FakePage()

        package = types.ModuleType("scrapling")
        fetchers = types.ModuleType("scrapling.fetchers")
        fetchers.StealthyFetcher = FakeStealthyFetcher
        with mock.patch.dict(
            sys.modules,
            {"scrapling": package, "scrapling.fetchers": fetchers},
        ):
            result = fetch_scrapling_article({
                "url": "https://news.example.com/article/1",
                "timeout_ms": 20_000,
                "use_system_proxy": False,
            })

        self.assertEqual(result["fetcher"], "stealthy")
        self.assertEqual(result["status"], 200)
        self.assertTrue(calls[0][1]["solve_cloudflare"])
        self.assertTrue(calls[0][1]["network_idle"])
        self.assertTrue(calls[0][1]["block_ads"])
        self.assertFalse(calls[0][1]["disable_resources"])
        self.assertFalse(calls[0][1]["google_search"])
        self.assertIs(calls[0][1]["page_setup"], _setup_public_only_routes)

    def test_scrapling_browser_routes_abort_private_targets_and_preserve_existing_handlers(self):
        handlers = []

        class FakePage:
            def route(self, pattern, handler):
                handlers.append((pattern, handler))

        class FakeRequest:
            def __init__(self, url):
                self.url = url

        class FakeRoute:
            def __init__(self, url):
                self.request = FakeRequest(url)
                self.action = None

            def abort(self):
                self.action = "abort"

            def fallback(self):
                self.action = "fallback"

        _setup_public_only_routes(FakePage())
        self.assertEqual(handlers[0][0], "**/*")

        private_route = FakeRoute("http://127.0.0.1/admin")
        public_route = FakeRoute("https://cdn.example.com/app.js")
        data_route = FakeRoute("data:text/plain,ok")
        handlers[0][1](private_route)
        handlers[0][1](public_route)
        handlers[0][1](data_route)

        self.assertEqual(private_route.action, "abort")
        self.assertEqual(public_route.action, "fallback")
        self.assertEqual(data_route.action, "fallback")

    def test_newspaper_bridge_receives_downloaded_html(self):
        response = {"ok": True, "data": {"title": "政府公告", "content": "完整正文"}}
        adapter, runner = build_available_adapter(Newspaper4kArticleAdapter, response)

        outcome = adapter.extract("<html>正文</html>", "https://example.gov.cn/a")

        self.assertEqual(outcome.data["title"], "政府公告")
        self.assertEqual(runner.calls[0]["command"][-1], "newspaper_extract")
        self.assertEqual(runner.calls[0]["payload"]["html"], "<html>正文</html>")

    def test_tieba_cookie_tokens_are_sent_via_stdin_not_command(self):
        response = {"ok": True, "data": {"tid": "123", "posts": []}}
        adapter, runner = build_available_adapter(AiotiebaThreadAdapter, response)

        outcome = adapter.fetch(123, bduss="secret-bduss", stoken="secret-stoken")

        self.assertFalse(outcome.error)
        command_text = " ".join(runner.calls[0]["command"])
        self.assertNotIn("secret-bduss", command_text)
        self.assertNotIn("secret-stoken", command_text)
        self.assertEqual(runner.calls[0]["payload"]["bduss"], "secret-bduss")

    def test_scrapling_bridge_uses_isolated_runtime_and_stdin_payload(self):
        response = {
            "ok": True,
            "data": {
                "html": "<html><article>完整正文</article></html>",
                "final_url": "https://news.example.com/article/1",
                "status": 200,
                "fetcher": "stealthy",
            },
        }
        runner = FakeBridgeRunner(response)
        adapter = ScraplingArticleAdapter(
            Path("project-root"),
            bridge_script=Path("fake-bridge.py"),
            runner=runner,
        )
        adapter.is_available = lambda: True

        outcome = adapter.fetch(
            "https://news.example.com/article/1",
            use_system_proxy=False,
            timeout=45,
        )

        self.assertEqual(outcome.data["fetcher"], "stealthy")
        self.assertEqual(runner.calls[0]["command"][-1], "scrapling_fetch")
        self.assertNotIn("https://news.example.com", " ".join(runner.calls[0]["command"]))
        self.assertEqual(runner.calls[0]["payload"]["url"], "https://news.example.com/article/1")
        self.assertEqual(runner.calls[0]["payload"]["timeout_ms"], 45_000)
        self.assertEqual(runner.calls[0]["timeout"], 60)
        self.assertEqual(
            adapter.python_path,
            Path("project-root") / ".scrapling-venv" / "Scripts" / "python.exe",
        )

class FakeNewspaperAdapter:
    adapter_name = "newspaper4k"

    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def is_available(self):
        return True

    def extract(self, html, url, language, timeout):
        self.calls.append((html, url, language, timeout))
        return self.outcome


class FakeTiebaAdapter:
    adapter_name = "aiotieba"

    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def is_available(self):
        return True

    def fetch(self, **kwargs):
        self.calls.append(kwargs)
        return self.outcome


class FakeScraplingAdapter:
    adapter_name = "scrapling"

    def __init__(self, outcome=None):
        self.outcome = outcome or EnrichmentOutcome("scrapling", True)
        self.calls = []

    def is_available(self):
        return True

    def fetch(self, **kwargs):
        self.calls.append(kwargs)
        return self.outcome


class FakeContentAdapters:
    def __init__(self, newspaper_outcome=None, tieba_outcome=None, scrapling_outcome=None):
        self.newspaper = FakeNewspaperAdapter(newspaper_outcome or EnrichmentOutcome("newspaper4k", True))
        self.tieba = FakeTiebaAdapter(tieba_outcome or EnrichmentOutcome("aiotieba", True))
        self.scrapling = FakeScraplingAdapter(scrapling_outcome)

    def status(self):
        return [
            {"adapter_name": "newspaper4k", "available": True},
            {"adapter_name": "aiotieba", "available": True},
            {"adapter_name": "scrapling", "available": True},
        ]


class CrawlerContentEnrichmentTests(unittest.TestCase):
    def test_scrapling_stealth_is_default_article_detail_fetcher(self):
        outcome = EnrichmentOutcome(
            adapter_name="scrapling",
            available=True,
            attempted=True,
            data={
                "html": "<html><head><title>完整新闻</title></head><body><article><p>"
                        + ("Scrapling 渲染后的完整公开新闻正文。" * 20)
                        + "</p></article></body></html>",
                "final_url": "https://news.example.com/article/1",
                "status": 200,
                "fetcher": "stealthy",
            },
        )
        adapters = FakeContentAdapters(scrapling_outcome=outcome)
        crawler = NewsCrawler(external_content_adapters=adapters)
        crawler._request_html = lambda *args, **kwargs: self.fail("ordinary fetch must be fallback only")
        record = {
            "title": "短标题",
            "content": "RSS 摘要",
            "url": "https://news.example.com/article/1",
            "platform": "Bing 新闻",
            "source_group": "public_news",
        }

        crawler._enrich_with_article_content(record)

        self.assertIn("Scrapling 渲染后的完整公开新闻正文", record["content"])
        self.assertEqual(record["detail_source"], "scrapling_stealth")
        self.assertTrue(record["detail_enriched"])
        self.assertEqual(adapters.scrapling.calls[0]["url"], record["url"])

    def test_scrapling_failure_falls_back_to_registered_ordinary_fetch(self):
        outcome = EnrichmentOutcome(
            adapter_name="scrapling",
            available=True,
            attempted=True,
            error="browser unavailable",
        )
        adapters = FakeContentAdapters(scrapling_outcome=outcome)
        crawler = NewsCrawler(external_content_adapters=adapters)
        detail_html = "<html><body><article><p>" + ("普通请求回退正文。" * 20) + "</p></article></body></html>"
        crawler._request_html = lambda *args, **kwargs: (
            detail_html,
            "https://news.example.com/article/2",
            None,
        )
        record = {
            "title": "新闻",
            "content": "短摘要",
            "url": "https://news.example.com/article/2",
            "platform": "Bing 新闻",
            "source_group": "public_news",
        }

        crawler._enrich_with_article_content(record)

        self.assertIn("普通请求回退正文", record["content"])
        self.assertEqual(len(adapters.scrapling.calls), 1)

    def test_tieba_prefers_browser_detail_over_aiotieba(self):
        adapters = FakeContentAdapters()
        crawler = NewsCrawler(external_content_adapters=adapters)
        calls = []
        crawler._enrich_with_browser_article_content = lambda record, platform: (
            calls.append("browser"),
            record.update({"detail_enriched": True, "detail_source": "browser_session"}),
        )
        crawler._enrich_with_tieba_thread = lambda record: calls.append("aiotieba")
        record = {"url": "https://tieba.baidu.com/p/123", "content": "摘要"}

        crawler._enrich_tieba_record(record)

        self.assertEqual(calls, ["browser"])
        self.assertEqual(record["detail_source"], "browser_session")

    def test_tieba_uses_aiotieba_only_when_browser_detail_fails(self):
        crawler = NewsCrawler()
        calls = []
        crawler._enrich_with_browser_article_content = lambda record, platform: calls.append("browser")
        crawler._enrich_with_tieba_thread = lambda record: calls.append("aiotieba")

        crawler._enrich_tieba_record({"url": "https://tieba.baidu.com/p/123", "content": "摘要"})

        self.assertEqual(calls, ["browser", "aiotieba"])

    def test_extract_article_content_reads_json_ld_article_body(self):
        article_body = "JSON-LD 中保存的完整公开新闻正文。" * 12
        html = f"""
        <html><head>
          <title>JSON-LD 新闻</title>
          <script type="application/ld+json">
            {json.dumps({"@type": "NewsArticle", "articleBody": article_body}, ensure_ascii=False)}
          </script>
        </head><body></body></html>
        """

        detail = NewsCrawler()._extract_article_content(
            html,
            "https://news.example.com/article/json-ld",
        )

        self.assertEqual(detail["content"], article_body)
        self.assertEqual(detail["body_content_length"], len(article_body))

    def test_baijiahao_extracts_ordered_bjh_paragraphs_without_ssr_noise(self):
        paragraphs = [
            "第一段介绍事件背景和已经确认的公开信息。" * 5,
            "第二段继续说明事件进展和相关主体的公开回应。" * 5,
        ]
        expected = " ".join(paragraphs)
        html = f"""
        <html><head><title>百家号合成文章</title></head><body>
          <div id="ssr-content">
            <div class="share-panel">分享、收藏和相关推荐等非正文噪音。</div>
            <span class="bjh-p">{paragraphs[0]}</span>
            <div class="recommend-panel">推荐阅读以及客户端打开提示。</div>
            <span class="bjh-p">{paragraphs[1]}</span>
          </div>
        </body></html>
        """
        crawler = NewsCrawler()

        detail = crawler._extract_article_content(
            html,
            "https://baijiahao.baidu.com/s?id=123456789",
        )

        self.assertEqual(detail["content"], expected)
        self.assertEqual(detail["body_content_length"], len(expected))
        self.assertEqual(
            detail["body_content_sha256"],
            crawler._body_content_fingerprint(expected),
        )

    def test_baijiahao_falls_back_to_window_json_data_text_sections(self):
        text_sections = [
            "脚本正文第一段包含事件起因和经过等公开事实。" * 5,
            "脚本正文第二段包含后续进展和发布者补充说明。" * 5,
        ]
        ignored_image_text = "图片说明不应进入正文。" * 10
        payload = {
            "bsData": {
                "superlanding": [{
                    "itemData": {
                        "sections": [
                            {
                                "type": "text",
                                "content": f'<span class="bjh-p">{text_sections[0]}</span>',
                            },
                            {
                                "type": "img",
                                "content": f'<span class="bjh-p">{ignored_image_text}</span><img src="image.jpg">',
                            },
                            {
                                "type": "text",
                                "content": f'<span class="bjh-p">{text_sections[1]}</span>',
                            },
                        ]
                    }
                }]
            }
        }
        expected = " ".join(text_sections)
        html = (
            "<html><head><title>百家号脚本合成文章</title>"
            f"<script>window.jsonData = {json.dumps(payload, ensure_ascii=False)};</script>"
            "</head><body><div id=\"ssr-content\">页面骨架和非正文噪音。</div></body></html>"
        )
        crawler = NewsCrawler()

        detail = crawler._extract_article_content(
            html,
            "https://baijiahao.baidu.com/s?id=987654321",
        )

        self.assertEqual(detail["content"], expected)
        self.assertEqual(detail["body_content_length"], len(expected))
        self.assertEqual(
            detail["body_content_sha256"],
            crawler._body_content_fingerprint(expected),
        )

    def test_newspaper4k_skips_non_government_page_when_builtin_body_is_usable(self):
        outcome = EnrichmentOutcome(
            adapter_name="newspaper4k",
            available=True,
            attempted=True,
            data={"title": "政府公告", "content": "外部提取的完整政府公告正文。" * 20, "source": "某政府", "pub_time": "2026-07-23"},
        )
        adapters = FakeContentAdapters(newspaper_outcome=outcome)
        crawler = NewsCrawler(external_content_adapters=adapters)
        html = (
            "<html><head><title>短标题</title></head><body><article><p>"
            + ("内置解析得到的完整新闻正文。" * 12)
            + "</p></article></body></html>"
        )

        detail = crawler._extract_article_content(html, "https://www.example.gov.cn/notice/1")
        crawler._extract_article_content(html, "https://news.example.com/notice/1")

        self.assertEqual(detail["detail_source"], "newspaper4k")
        self.assertIn("完整政府公告正文", detail["content"])
        self.assertEqual(len(adapters.newspaper.calls), 1)

    def test_newspaper4k_falls_back_for_short_non_government_news_body(self):
        full_body = "newspaper4k 提取的完整公开新闻正文。" * 300
        outcome = EnrichmentOutcome(
            adapter_name="newspaper4k",
            available=True,
            attempted=True,
            data={"title": "完整新闻", "content": full_body},
        )
        adapters = FakeContentAdapters(newspaper_outcome=outcome)
        crawler = NewsCrawler(external_content_adapters=adapters)
        html = "<html><head><title>短标题</title></head><body><article>简短说明。</article></body></html>"

        detail = crawler._extract_article_content(
            html,
            "https://news.example.com/article/short-body",
        )

        self.assertEqual(detail["detail_source"], "newspaper4k")
        with self.subTest(field="content"):
            self.assertEqual(detail["content"], full_body)
        with self.subTest(field="body_content_length"):
            self.assertEqual(detail["body_content_length"], len(full_body))
        with self.subTest(field="body_content_sha256"):
            self.assertEqual(
                detail["body_content_sha256"],
                crawler._body_content_fingerprint(full_body),
            )
        self.assertEqual(
            adapters.newspaper.calls[0][1],
            "https://news.example.com/article/short-body",
        )

    def test_official_source_enriches_even_when_search_abstract_is_long(self):
        outcome = EnrichmentOutcome(
            adapter_name="newspaper4k",
            available=True,
            attempted=True,
            data={"title": "正式公告", "content": "newspaper4k 提取的正式公告正文。" * 12},
        )
        adapters = FakeContentAdapters(newspaper_outcome=outcome)
        crawler = NewsCrawler(external_content_adapters=adapters)
        crawler.anti_crawl.delay = lambda *args, **kwargs: None
        search_html = """
        <html><body><div class="result">
          <h3><a href="https://www.example.gov.cn/notice/1">正式公告</a></h3>
          <div class="c-abstract">这是长度已经超过八十字的搜索摘要，用来确认官方公开网页仍然会进入正文增强流程，而不是因为摘要较长就跳过详情页。为了满足长度条件，这里继续补充测试文字。</div>
        </div></body></html>
        """
        detail_html = "<html><head><title>正式公告</title></head><body><article><p>内置详情正文。</p></article></body></html>"

        def fake_request(url, channel, timeout=10):
            if channel == "官方公开网页":
                return search_html, url, None
            if channel == "article-detail":
                return detail_html, "https://www.example.gov.cn/notice/1", None
            return "", url, "unexpected request"

        crawler._request_html = fake_request
        records, failures = crawler._collect_from_source_requests(
            source_requests=[{
                "channel": "官方公开网页",
                "platform": "官方公开网页",
                "source_group": "stable",
                "parser": "baidu",
                "url": "https://www.baidu.com/s?wd=test",
                "timeout": 10,
            }],
            keyword="正式公告",
            region="全国",
            collect_level="最小采集",
            start_time=None,
            end_time=None,
            remaining=1,
        )

        self.assertFalse(failures)
        self.assertEqual(records[0]["detail_source"], "newspaper4k")
        self.assertIn("newspaper4k 提取", records[0]["content"])

    def test_tieba_thread_enrichment_preserves_discussion_samples(self):
        outcome = EnrichmentOutcome(
            adapter_name="aiotieba",
            available=True,
            attempted=True,
            data={
                "tid": "9876543210",
                "title": "贴吧事件讨论",
                "content": "楼主发布的事件经过和后续说明。" * 6,
                "author": "楼主",
                "forum": "本地吧",
                "pub_time": "2026-07-23T10:00:00+08:00",
                "view_count": 500,
                "reply_count": 20,
                "share_count": 2,
                "posts": [{"id": "1", "floor": 1, "content": "第一层回复", "comments": []}],
            },
        )
        adapters = FakeContentAdapters(tieba_outcome=outcome)
        crawler = NewsCrawler(external_content_adapters=adapters)
        crawler.set_account("百度贴吧", cookie="BDUSS=secret-bduss; STOKEN=secret-stoken")
        record = {
            "title": "搜索摘要",
            "content": "短摘要",
            "url": "https://tieba.baidu.com/p/9876543210?pid=1",
            "platform": "百度贴吧",
            "comment_count": 0,
            "repost_count": 0,
        }

        crawler._enrich_with_tieba_thread(record)

        self.assertEqual(record["detail_source"], "aiotieba")
        self.assertEqual(record["comment_count"], 20)
        self.assertEqual(record["discussion_samples"][0]["content"], "第一层回复")
        self.assertEqual(adapters.tieba.calls[0]["bduss"], "secret-bduss")
        self.assertEqual(record["url"], "https://tieba.baidu.com/p/9876543210")

    def test_tieba_tid_parser_accepts_path_and_legacy_query(self):
        self.assertEqual(NewsCrawler._extract_tieba_tid("https://tieba.baidu.com/p/123456"), 123456)
        self.assertEqual(NewsCrawler._extract_tieba_tid("https://tieba.baidu.com/f?kz=654321"), 654321)
        self.assertIsNone(NewsCrawler._extract_tieba_tid("https://tieba.baidu.com/f?kw=test"))


if __name__ == "__main__":
    unittest.main()
