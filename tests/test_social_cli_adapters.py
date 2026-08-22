import unittest
import json
from pathlib import Path

from src.crawler import NewsCrawler as ProductionNewsCrawler
from src.external_content_adapters import BridgeCommandResult
from src.social_cli_adapters import (
    AdapterSearchOutcome,
    BilibiliCliAdapter,
    CommandResult,
    WeiboCliAdapter,
    XiaohongshuCliAdapter,
    decode_json_output,
    parse_count,
)
from tests.helpers import AllowAllSourcePolicy


class NewsCrawler(ProductionNewsCrawler):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("source_policy", AllowAllSourcePolicy())
        kwargs.setdefault("use_external_social_adapters", False)
        super().__init__(*args, **kwargs)


class FakeRunner:
    def __init__(self, payload: str, returncode: int = 0, stderr: str = ""):
        self.result = CommandResult(returncode=returncode, stdout=payload, stderr=stderr)
        self.commands = []

    def run(self, command, cwd, timeout):
        self.commands.append({"command": list(command), "cwd": Path(cwd), "timeout": timeout})
        return self.result


class FakeBridgeRunner:
    def __init__(self, data):
        self.result = BridgeCommandResult(
            returncode=0,
            stdout=json.dumps({"ok": True, "data": data}, ensure_ascii=False),
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


def build_adapter(adapter_class, payload):
    runner = FakeRunner(payload)
    adapter = adapter_class(Path("fake-candidate-repo"), runner=runner)
    adapter.is_available = lambda: True
    return adapter, runner


class SocialCliAdapterTests(unittest.TestCase):
    def test_decode_json_output_skips_leading_warning(self):
        payload = decode_json_output('warning: optional dependency missing\n[{"id": 1}]\n')
        self.assertEqual(payload, [{"id": 1}])

    def test_parse_count_understands_chinese_units(self):
        self.assertEqual(parse_count("1.2万"), 12000)
        self.assertEqual(parse_count("2亿"), 200000000)
        self.assertEqual(parse_count(None), 0)

    def test_xiaohongshu_search_is_read_only_and_normalized(self):
        payload = """[
          {
            "id": "6a40acc2000000000f0151b2",
            "xsec_token": "AB-token=",
            "note_card": {
              "display_title": "警方发布情况通报",
              "desc": "警方发布情况通报正文",
              "user": {"user_id": "u1", "nickname": "发布者"},
              "interact_info": {"liked_count": "1.2万", "comment_count": "35"}
            }
          }
        ]"""
        adapter, runner = build_adapter(XiaohongshuCliAdapter, payload)

        outcome = adapter.search("情况通报", limit=5)

        self.assertFalse(outcome.error)
        self.assertEqual(len(outcome.items), 1)
        self.assertIn("xsec_source=pc_search", outcome.items[0]["url"])
        self.assertEqual(outcome.items[0]["like_count"], 12000)
        self.assertEqual(runner.commands[0]["command"][1:], ["search", "情况通报", "--json"])

    def test_bilibili_search_forces_video_json_mode(self):
        payload = '[{"id":"BV1Ab411c7mD","bvid":"BV1Ab411c7mD","title":"<em>通报</em>视频","author":"警方账号","play":321,"duration":"01:20"}]'
        adapter, runner = build_adapter(BilibiliCliAdapter, payload)

        outcome = adapter.search("通报", limit=3)

        self.assertEqual(outcome.items[0]["url"], "https://www.bilibili.com/video/BV1Ab411c7mD")
        self.assertEqual(outcome.items[0]["title"], "通报 视频")
        args = runner.commands[0]["command"][1:]
        self.assertEqual(args, ["search", "通报", "--type", "video", "--max", "3", "--json"])

    def test_weibo_search_normalizes_nested_mobile_cards(self):
        payload = """{
          "data": {"cards": [{"card_type": 9, "mblog": {
            "id": 5123456789012345,
            "bid": "P0AbCdEf1",
            "text": "<p>警方发布<strong>情况通报</strong></p>",
            "created_at": "2026-07-23 10:30",
            "user": {"id": 123456, "screen_name": "平安测试"},
            "reposts_count": 4,
            "comments_count": 5,
            "attitudes_count": 6
          }}]}
        }"""
        adapter, runner = build_adapter(WeiboCliAdapter, payload)

        outcome = adapter.search("情况通报", limit=10)

        record = outcome.items[0]
        self.assertEqual(record["url"], "https://weibo.com/123456/P0AbCdEf1")
        self.assertEqual(record["content"], "警方发布 情况通报")
        self.assertEqual(record["comment_count"], 5)
        self.assertEqual(
            runner.commands[0]["command"][1:],
            ["search", "情况通报", "--count", "10", "--page", "1", "--json"],
        )

    def test_authorized_cookie_is_sent_only_through_bridge_stdin(self):
        bridge = FakeBridgeRunner({"items": [{
            "bvid": "BV1Ab411c7mD",
            "title": "情况通报",
            "author": "警方账号",
        }]})
        adapter = BilibiliCliAdapter(
            Path("fake-candidate-repo"),
            bridge_runner=bridge,
            bridge_script=Path("external_readonly_bridge.py"),
        )
        adapter.bridge_is_available = lambda: True
        secret = "authorized-session-secret"

        outcome = adapter.search(
            "情况通报",
            limit=1,
            auth_payload={"cookies": {"SESSDATA": secret}},
        )

        self.assertFalse(outcome.error)
        self.assertEqual(outcome.items[0]["adapter_backend"], "external_bridge")
        self.assertEqual(bridge.calls[0]["payload"]["cookies"]["SESSDATA"], secret)
        self.assertNotIn(secret, " ".join(bridge.calls[0]["command"]))


class FakeRegistry:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def supports(self, platform):
        return platform in {"微博", "B站", "小红书"}

    def search(self, platform, keyword, limit, timeout, auth_payload=None):
        self.calls.append((platform, keyword, limit, timeout))
        return self.outcome

    def status(self):
        return [{"platform": "微博", "adapter_name": "weibo-cli", "available": True}]


class CrawlerExternalAdapterIntegrationTests(unittest.TestCase):
    def test_external_adapter_result_enters_existing_record_contract(self):
        item = {
            "title": "情况通报",
            "content": "警方发布情况通报，现将有关事实和处置进展向社会公开。" * 4,
            "url": "https://weibo.com/123456/P0AbCdEf1",
            "source": "微博",
            "platform": "微博",
            "author": "平安测试",
            "like_count": 6,
            "adapter_backend": "external_cli",
            "adapter_name": "weibo-cli",
        }
        registry = FakeRegistry(AdapterSearchOutcome(
            platform="微博",
            adapter_name="weibo-cli",
            available=True,
            attempted=True,
            items=[item],
        ))
        crawler = NewsCrawler(external_social_registry=registry)
        crawler.anti_crawl.delay = lambda *args, **kwargs: None
        crawler._request_source_html = lambda *args, **kwargs: self.fail("不应调用浏览器回退")

        records, failures = crawler._collect_from_source_requests(
            source_requests=crawler._build_social_source_requests("微博", "情况通报", None, None),
            keyword="情况通报",
            region="全国",
            collect_level="最小采集",
            start_time=None,
            end_time=None,
            remaining=5,
        )

        self.assertFalse(failures)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["adapter_backend"], "external_cli")
        self.assertEqual(records[0]["auth_mode"], "external_cli")
        self.assertEqual(records[0]["source_rule_id"], "SRC-TEST")
        self.assertEqual(records[0]["source_support_level"], "TEST")

    def test_adapter_failure_falls_back_to_existing_html_path(self):
        registry = FakeRegistry(AdapterSearchOutcome(
            platform="微博",
            adapter_name="weibo-cli",
            available=True,
            attempted=True,
            error="login required",
        ))
        crawler = NewsCrawler(external_social_registry=registry)
        crawler.anti_crawl.delay = lambda *args, **kwargs: None
        crawler._request_source_html = lambda **kwargs: ("<html></html>", kwargs["url"], None)
        crawler._parse_results = lambda *args, **kwargs: [{
            "title": "浏览器回退结果",
            "content": "浏览器回退后得到的公开微博正文。" * 8,
            "url": "https://weibo.com/123456/P0Fallback1",
            "source": "微博",
            "platform": "微博",
        }]
        events = []

        records, failures = crawler._collect_from_source_requests(
            source_requests=crawler._build_social_source_requests("微博", "情况通报", None, None),
            keyword="情况通报",
            region="全国",
            collect_level="最小采集",
            start_time=None,
            end_time=None,
            remaining=5,
            progress_callback=events.append,
        )

        self.assertFalse(failures)
        self.assertEqual(len(records), 1)
        self.assertNotIn("adapter_backend", records[0])
        self.assertTrue(any(event.get("type") == "adapter_fallback" for event in events))


if __name__ == "__main__":
    unittest.main()
