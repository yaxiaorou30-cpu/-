import os
import unittest
from unittest.mock import patch

from src.baidu_web_search import BaiduWebSearchAdapter


OFFICIAL_ENDPOINT = "https://qianfan.baidubce.com/v2/ai_search/web_search"
TEST_API_KEY = "qianfan-test-key-not-real"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(str(self.payload))


class FakeSession:
    def __init__(self, payload, status_code=200):
        self.response = FakeResponse(payload, status_code)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.response


class BaiduWebSearchAdapterTests(unittest.TestCase):
    @patch.dict(os.environ, {"BAIDU_QIANFAN_API_KEY": TEST_API_KEY}, clear=True)
    def test_reads_api_key_from_environment_and_posts_official_request(self):
        session = FakeSession({"references": []})

        outcome = BaiduWebSearchAdapter(session=session).search("跨来源公开网页", top_k=3)

        self.assertTrue(outcome.available)
        self.assertFalse(outcome.error)
        self.assertEqual(len(session.calls), 1)
        call = session.calls[0]
        self.assertEqual(call["url"], OFFICIAL_ENDPOINT)
        self.assertEqual(call["headers"]["Authorization"], f"Bearer {TEST_API_KEY}")
        self.assertEqual(call["headers"]["Content-Type"], "application/json")
        self.assertEqual(call["json"]["messages"], [{"role": "user", "content": "跨来源公开网页"}])
        self.assertEqual(call["json"]["search_source"], "baidu_search_v2")
        self.assertEqual(call["json"]["resource_type_filter"], [{"type": "web", "top_k": 3}])
        self.assertEqual(call["json"]["edition"], "standard")

    @patch.dict(os.environ, {"BAIDU_QIANFAN_API_KEY": TEST_API_KEY}, clear=True)
    def test_top_k_is_clamped_to_official_web_search_bounds(self):
        for requested, expected in ((0, 1), (999, 50)):
            with self.subTest(requested=requested):
                session = FakeSession({"references": []})

                BaiduWebSearchAdapter(session=session).search("测试", top_k=requested)

                resource = session.calls[0]["json"]["resource_type_filter"][0]
                self.assertEqual(resource, {"type": "web", "top_k": expected})

    @patch.dict(os.environ, {"BAIDU_QIANFAN_API_KEY": TEST_API_KEY}, clear=True)
    def test_maps_official_references_to_crawler_records(self):
        session = FakeSession({
            "request_id": "request-1",
            "references": [{
                "id": 1,
                "type": "web",
                "title": "国务院公开信息",
                "url": "https://www.gov.cn/example/1",
                "website": "中国政府网",
                "web_anchor": "中国政府网首页",
                "snippet": "搜索摘要",
                "content": "与检索关键词相关的公开网页内容片段。",
                "date": "2026-08-25 10:30:00",
            }],
        })

        outcome = BaiduWebSearchAdapter(session=session).search("公开信息", top_k=5)

        self.assertFalse(outcome.error)
        self.assertEqual(len(outcome.items), 1)
        record = outcome.items[0]
        self.assertEqual(record["title"], "国务院公开信息")
        self.assertEqual(record["url"], "https://www.gov.cn/example/1")
        self.assertEqual(record["source"], "中国政府网")
        self.assertEqual(record["content"], "与检索关键词相关的公开网页内容片段。")
        self.assertEqual(record["pub_time"], "2026-08-25 10:30:00")
        self.assertEqual(record["search_origin"], "baidu_qianfan_web_search")
        self.assertEqual(record["keyword"], "公开信息")

    @patch.dict(os.environ, {"BAIDU_QIANFAN_API_KEY": TEST_API_KEY}, clear=True)
    def test_bearer_secret_is_not_exposed_in_outcome_or_error(self):
        success = BaiduWebSearchAdapter(
            session=FakeSession({"references": []}),
        ).search("测试", top_k=1)
        failed = BaiduWebSearchAdapter(
            session=FakeSession(
                {"code": "AccessDenied", "message": f"invalid Bearer {TEST_API_KEY}"},
                status_code=401,
            ),
        ).search("测试", top_k=1)

        self.assertNotIn(TEST_API_KEY, repr(success))
        self.assertTrue(failed.error)
        self.assertEqual(failed.items, [])
        self.assertNotIn(TEST_API_KEY, failed.error)
        self.assertNotIn(TEST_API_KEY, repr(failed))

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_environment_key_does_not_attempt_network(self):
        session = FakeSession({"references": []})

        outcome = BaiduWebSearchAdapter(session=session).search("测试", top_k=1)

        self.assertFalse(outcome.available)
        self.assertFalse(outcome.attempted)
        self.assertIn("BAIDU_QIANFAN_API_KEY", outcome.error)
        self.assertEqual(session.calls, [])

    @patch.dict(os.environ, {"BAIDU_QIANFAN_API_KEY": TEST_API_KEY}, clear=True)
    def test_query_over_official_72_unit_limit_does_not_attempt_network(self):
        session = FakeSession({"references": []})

        outcome = BaiduWebSearchAdapter(session=session).search("中" * 37, top_k=1)

        self.assertTrue(outcome.available)
        self.assertFalse(outcome.attempted)
        self.assertIn("72", outcome.error)
        self.assertEqual(session.calls, [])


if __name__ == "__main__":
    unittest.main()
