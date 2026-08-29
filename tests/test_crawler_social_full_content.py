import unittest
from types import SimpleNamespace
from unittest import mock

from src.crawler import NewsCrawler
from src.external_content_adapters import EnrichmentOutcome


class SocialFullContentTests(unittest.TestCase):
    def setUp(self):
        self.full_content = "完整社交正文" * 700

    def test_browser_article_enrichment_preserves_complete_content(self):
        for platform, extractor in (
            ("知乎", "src.crawler.extract_article_from_html"),
            ("百度贴吧", "src.crawler.extract_tieba_detail_from_html"),
        ):
            with self.subTest(platform=platform):
                crawler = NewsCrawler()
                crawler.account_manager.get_account = lambda _platform: {
                    "session_mode": "browser_session",
                    "browser_session": "{}",
                }
                crawler._request_browser_html = lambda **kwargs: (
                    "<html></html>",
                    kwargs["url"],
                    None,
                )
                record = {
                    "title": "搜索标题",
                    "content": "搜索摘要",
                    "url": "https://example.com/detail/1",
                }

                with mock.patch(
                    extractor,
                    return_value={
                        "title": "详情标题",
                        "content": self.full_content,
                        "discussion_samples": [],
                    },
                ):
                    crawler._enrich_with_browser_article_content(record, platform)

                self.assertEqual(record["content"], self.full_content)

    def test_weibo_detail_enrichment_preserves_complete_content(self):
        crawler = NewsCrawler()
        crawler.account_manager.get_account = lambda _platform: {
            "session_mode": "browser_session",
            "browser_session": "{}",
        }
        crawler._request_browser_json = lambda *args, **kwargs: (
            {"idstr": "1234567890"},
            200,
            args[1],
            None,
        )
        record = {
            "title": "搜索标题",
            "content": "搜索摘要",
            "url": "https://weibo.com/998877/AbCdEf123",
        }

        with mock.patch(
            "src.crawler.extract_weibo_detail_from_payload",
            return_value={"title": "微博详情", "content": self.full_content},
        ):
            crawler._enrich_with_weibo_detail(record)

        self.assertEqual(record["content"], self.full_content)

    def test_tieba_thread_enrichment_preserves_complete_content(self):
        tieba = mock.Mock()
        tieba.fetch.return_value = EnrichmentOutcome(
            adapter_name="aiotieba",
            available=True,
            attempted=True,
            data={
                "title": "贴吧详情",
                "content": self.full_content,
                "posts": [],
            },
        )
        crawler = NewsCrawler(
            external_content_adapters=SimpleNamespace(tieba=tieba)
        )
        crawler.account_manager.get_account = lambda _platform: {}
        record = {
            "title": "搜索标题",
            "content": "搜索摘要",
            "url": "https://tieba.baidu.com/p/9876543210",
        }

        crawler._enrich_with_tieba_thread(record)

        self.assertEqual(record["content"], self.full_content)

    def test_xiaohongshu_detail_enrichment_preserves_complete_content(self):
        crawler = NewsCrawler()
        crawler.account_manager.get_account = lambda _platform: {
            "session_mode": "browser_session",
            "browser_session": "{}",
        }
        crawler._request_browser_html = lambda **kwargs: (
            "<html></html>",
            kwargs["url"],
            None,
        )
        record = {
            "title": "搜索标题",
            "content": "搜索摘要",
            "url": "https://www.xiaohongshu.com/explore/1234567890abcdef",
        }

        with mock.patch(
            "src.crawler.extract_xiaohongshu_detail_from_html",
            return_value={"title": "小红书详情", "content": self.full_content},
        ):
            crawler._enrich_with_xiaohongshu_detail_content(record)

        self.assertEqual(record["content"], self.full_content)


if __name__ == "__main__":
    unittest.main()
