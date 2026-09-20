import unittest
from pathlib import Path
from unittest.mock import patch

import web_app
from src.crawler import NewsCrawler
from tests.helpers import AllowAllSourcePolicy


ROOT = Path(__file__).resolve().parents[1]


class CrawlCancellationTests(unittest.TestCase):
    def tearDown(self):
        web_app.TASKS.pop("cancel-test", None)

    def test_running_task_accepts_one_cancellation_request(self):
        web_app.TASKS["cancel-test"] = {
            "task_id": "cancel-test",
            "status": "running",
            "message": "采集中",
            "cancel_requested": False,
        }

        task = web_app.request_crawl_cancel("cancel-test")

        self.assertTrue(task["cancel_requested"])
        self.assertEqual(task["status"], "running")
        self.assertIn("当前请求完成后停止", task["message"])
        with self.assertRaisesRegex(ValueError, "已经申请中止"):
            web_app.request_crawl_cancel("cancel-test")

    def test_crawler_stops_before_next_source_and_keeps_collected_records(self):
        crawler = NewsCrawler(
            source_policy=AllowAllSourcePolicy(),
            use_external_social_adapters=False,
        )
        cancelled = {"value": False}
        calls = []

        crawler._build_public_news_source_requests = lambda **_kwargs: [
            {
                "channel": "来源一",
                "platform": "平台一",
                "source_group": "public_news",
                "parser": "generic",
                "url": "https://example.com/one",
                "timeout": 10,
            },
            {
                "channel": "来源二",
                "platform": "平台二",
                "source_group": "public_news",
                "parser": "generic",
                "url": "https://example.com/two",
                "timeout": 10,
            },
        ]

        def fake_collect(**kwargs):
            request = kwargs["source_requests"][0]
            calls.append(request["channel"])
            cancelled["value"] = True
            return ([{
                "title": "已取得的线索",
                "content": "这条数据应在中止后保留。",
                "url": "https://example.com/result",
                "source": "来源一",
                "platform": "平台一",
                "source_group": "public_news",
                "source_type": "media",
                "data_type": "real",
                "pub_time": "2026-09-20T10:00:00",
            }], [])

        crawler._collect_source_requests_safely = fake_collect
        with patch("src.crawler.CRAWLER_AVAILABLE", True):
            records = crawler.crawl(
                ["测试"],
                max_results=10,
                min_real_results=10,
                source_strategy="public_news",
                cancel_callback=lambda: cancelled["value"],
            )

        self.assertEqual(calls, ["来源一"])
        self.assertEqual([item["title"] for item in records], ["已取得的线索"])
        self.assertTrue(crawler.last_meta["cancelled"])

    def test_ui_exposes_cancel_button_and_cancelled_terminal_state(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")
        backend = (ROOT / "web_app.py").read_text(encoding="utf-8")

        self.assertIn('id="cancelCrawlBtn"', html)
        self.assertIn("中止采集", html)
        self.assertIn('requestJson("/api/crawl/cancel"', javascript)
        self.assertIn('cancelled: "已中止"', javascript)
        self.assertIn('"done", "blocked", "not_met", "cancelled", "error"', javascript)
        self.assertIn('parsed.path == "/api/crawl/cancel"', backend)


if __name__ == "__main__":
    unittest.main()
