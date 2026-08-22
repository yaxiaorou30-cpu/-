import json
import shutil
import threading
import time
import unittest
import uuid
from pathlib import Path

from src.monitoring import MonitorManager, normalize_original_url, record_fingerprint


TEST_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"


def monitor_payload(**overrides):
    payload = {
        "topic": "天津测试事件",
        "keywords": ["测试事件"],
        "region": "天津",
        "source_strategy": "social",
        "collect_level": "最小采集",
        "time_range": "近一周",
        "stable_sources": [],
        "social_platforms": ["微博"],
        "accounts": {
            "微博": {
                "username": "secret-user",
                "password": "secret-password",
                "cookie": "secret-cookie",
            }
        },
    }
    payload.update(overrides)
    return payload


def record(title, url, pub_time="2026-08-02T10:00:00"):
    return {
        "title": title,
        "content": f"{title}的正文内容",
        "url": url,
        "pub_time": pub_time,
        "platform": "微博",
        "source": "测试账号",
        "author": "测试账号",
        "keyword": "测试事件",
    }


class SequenceRunner:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def __call__(self, _plan_id, _payload, _output_path, _meta_path):
        index = min(self.calls, len(self.results) - 1)
        self.calls += 1
        result = self.results[index]
        if isinstance(result, Exception):
            raise result
        return result


class MonitoringTests(unittest.TestCase):
    def setUp(self):
        self.root = TEST_DATA_ROOT / f".test-monitor-{uuid.uuid4().hex}"
        self.state_file = self.root / "monitor_state.json"
        self.data_root = self.root / "runs"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def manager(self, runner):
        return MonitorManager(
            self.state_file,
            self.data_root,
            runner,
            crawl_lock=threading.Lock(),
        )

    def test_plan_persists_conditions_without_credentials(self):
        manager = self.manager(SequenceRunner([]))
        plan = manager.create_plan(monitor_payload(), 15)

        self.assertEqual(plan["payload"]["social_platforms"], ["微博"])
        raw = self.state_file.read_text(encoding="utf-8")
        self.assertNotIn("secret-user", raw)
        self.assertNotIn("secret-password", raw)
        self.assertNotIn("secret-cookie", raw)
        self.assertNotIn('"accounts"', raw)

    def test_first_run_builds_baseline_and_second_run_only_adds_new_clue(self):
        first = record("第一条", "https://weibo.com/1/AAA?utm_source=test")
        second = record("第二条", "https://weibo.com/1/BBB")
        runner = SequenceRunner([
            {
                "records": [first],
                "meta": {"summary": {"real_count": 1}, "failures": []},
            },
            {
                "records": [first, second],
                "meta": {"summary": {"real_count": 2}, "failures": []},
            },
        ])
        manager = self.manager(runner)
        plan_id = manager.create_plan(monitor_payload(), 15)["id"]

        manager.run_plan(plan_id)
        baseline = manager.get_plan(plan_id)
        self.assertTrue(baseline["baseline_ready"])
        self.assertEqual(baseline["latest_new_count"], 0)
        self.assertEqual(baseline["runs"][0]["status"], "baseline")

        manager.run_plan(plan_id)
        updated = manager.get_plan(plan_id)
        self.assertEqual(updated["latest_new_count"], 1)
        self.assertEqual(updated["total_new"], 1)
        self.assertEqual(len(updated["new_items"]), 1)
        self.assertEqual(updated["new_items"][0]["title"], "第二条")

    def test_fingerprint_prefers_normalized_original_url(self):
        first = record("标题甲", "https://WEIBO.com/1/AAA/?utm_source=x&refer_flag=1")
        second = record("完全不同的标题", "https://weibo.com/1/AAA")

        self.assertEqual(normalize_original_url(first["url"]), "https://weibo.com/1/AAA")
        self.assertEqual(record_fingerprint(first), record_fingerprint(second))

    def test_three_consecutive_failures_require_human_attention_and_success_resets(self):
        runner = SequenceRunner([
            RuntimeError("network down"),
            RuntimeError("network down"),
            RuntimeError("network down"),
            {
                "records": [],
                "meta": {"summary": {"real_count": 0}, "failures": []},
            },
        ])
        manager = self.manager(runner)
        plan_id = manager.create_plan(monitor_payload(), 30)["id"]

        manager.run_plan(plan_id)
        manager.run_plan(plan_id)
        manager.run_plan(plan_id)
        failed = manager.get_plan(plan_id)
        self.assertEqual(failed["consecutive_failures"], 3)
        self.assertEqual(failed["runtime_status"], "needs_attention")

        manager.run_plan(plan_id)
        recovered = manager.get_plan(plan_id)
        self.assertEqual(recovered["consecutive_failures"], 0)
        self.assertEqual(recovered["runtime_status"], "normal")

    def test_restart_keeps_baseline_and_does_not_reannounce_duplicate(self):
        original = record("第一条", "https://example.gov.cn/notices/1")
        first_runner = SequenceRunner([
            {
                "records": [original],
                "meta": {"summary": {"real_count": 1}, "failures": []},
            }
        ])
        first_manager = self.manager(first_runner)
        plan_id = first_manager.create_plan(monitor_payload(), 60)["id"]
        first_manager.run_plan(plan_id)

        second_runner = SequenceRunner([
            {
                "records": [original],
                "meta": {"summary": {"real_count": 1}, "failures": []},
            }
        ])
        restored_manager = self.manager(second_runner)
        restored_manager.run_plan(plan_id)
        restored = restored_manager.get_plan(plan_id)

        self.assertTrue(restored["baseline_ready"])
        self.assertEqual(restored["latest_new_count"], 0)
        self.assertEqual(restored["total_new"], 0)

    def test_at_most_five_plans_can_run_at_the_same_time(self):
        manager = self.manager(SequenceRunner([]))
        for index in range(5):
            manager.create_plan(monitor_payload(topic=f"主题 {index}"), 15)

        with self.assertRaisesRegex(ValueError, "最多同时运行 5 个"):
            manager.create_plan(monitor_payload(topic="第六个主题"), 15)

        first = manager.list_plans()[-1]
        manager.action(first["id"], "pause")
        sixth = manager.create_plan(monitor_payload(topic="替补主题"), 15)
        self.assertEqual(sixth["status"], "active")

    def test_plan_requires_real_search_keywords_and_matching_source_strategy(self):
        manager = self.manager(SequenceRunner([]))
        with self.assertRaisesRegex(ValueError, "至少一个监测关键词"):
            manager.create_plan(monitor_payload(keywords=[]), 15)
        with self.assertRaisesRegex(ValueError, "至少选择一个政府官网"):
            manager.create_plan(
                monitor_payload(
                    source_strategy="stable",
                    stable_sources=[],
                    social_platforms=["微博"],
                ),
                15,
            )

        default_plan = manager.create_plan(
            monitor_payload(
                source_strategy="all",
                stable_sources=[],
                social_platforms=[],
            ),
            15,
        )
        self.assertEqual(default_plan["payload"]["source_strategy"], "all")

    def test_scheduler_runs_new_plan_immediately_and_restores_active_job(self):
        event = threading.Event()

        def runner(_plan_id, _payload, _output_path, _meta_path):
            event.set()
            return {
                "records": [],
                "meta": {"summary": {"real_count": 0}, "failures": []},
            }

        manager = self.manager(runner)
        manager.start()
        try:
            plan_id = manager.create_plan(monitor_payload(), 15)["id"]
            self.assertTrue(event.wait(2), "新计划没有被调度器立即执行")
            deadline = time.monotonic() + 2
            while manager.get_plan(plan_id)["runtime_status"] == "running":
                if time.monotonic() >= deadline:
                    self.fail("新计划执行后没有结束")
                time.sleep(0.01)
        finally:
            manager.shutdown()

        restored = self.manager(runner)
        restored.start()
        try:
            self.assertIsNotNone(restored._scheduler.get_job(f"monitor:{plan_id}"))
        finally:
            restored.shutdown()

    def test_state_file_is_valid_json(self):
        manager = self.manager(SequenceRunner([]))
        manager.create_plan(monitor_payload(), 15)
        stored = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(stored["version"], 1)
        self.assertEqual(len(stored["plans"]), 1)


if __name__ == "__main__":
    unittest.main()
