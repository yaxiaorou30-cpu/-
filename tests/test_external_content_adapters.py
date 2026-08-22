import json
import unittest
from pathlib import Path

from src.crawler import NewsCrawler as ProductionNewsCrawler
from src.external_content_adapters import (
    AiotiebaThreadAdapter,
    BridgeCommandResult,
    EnrichmentOutcome,
    Newspaper4kArticleAdapter,
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


class FakeContentAdapters:
    def __init__(self, newspaper_outcome=None, tieba_outcome=None):
        self.newspaper = FakeNewspaperAdapter(newspaper_outcome or EnrichmentOutcome("newspaper4k", True))
        self.tieba = FakeTiebaAdapter(tieba_outcome or EnrichmentOutcome("aiotieba", True))

    def status(self):
        return [
            {"adapter_name": "newspaper4k", "available": True},
            {"adapter_name": "aiotieba", "available": True},
        ]


class CrawlerContentEnrichmentTests(unittest.TestCase):
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

    def test_newspaper4k_is_used_only_for_government_domain(self):
        outcome = EnrichmentOutcome(
            adapter_name="newspaper4k",
            available=True,
            attempted=True,
            data={"title": "政府公告", "content": "外部提取的完整政府公告正文。" * 8, "source": "某政府", "pub_time": "2026-07-23"},
        )
        adapters = FakeContentAdapters(newspaper_outcome=outcome)
        crawler = NewsCrawler(external_content_adapters=adapters)
        html = "<html><head><title>短标题</title></head><body><p>内置解析正文长度足够用于比较。</p></body></html>"

        detail = crawler._extract_article_content(html, "https://www.example.gov.cn/notice/1")
        crawler._extract_article_content(html, "https://news.example.com/notice/1")

        self.assertEqual(detail["detail_source"], "newspaper4k")
        self.assertIn("完整政府公告正文", detail["content"])
        self.assertEqual(len(adapters.newspaper.calls), 1)

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
