import shutil
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import web_app
from src.monitoring import MonitorManager


TEST_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"


def sample_payload():
    return {
        "topic": "持续监测测试",
        "keywords": ["测试事件"],
        "region": "全国",
        "source_strategy": "public_news",
        "public_news_sources": ["Bing News RSS"],
        "max_results": 10,
    }


def sample_record():
    return {
        "title": "测试事件出现新进展",
        "content": "测试事件正文内容，包含可供审核和报告生成的完整信息。",
        "url": "https://example.com/news/1",
        "pub_time": "2026-09-24T10:00:00",
        "platform": "Bing News RSS",
        "source": "示例媒体",
    }


class MonitoringWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.root = TEST_DATA_ROOT / f".test-monitor-workflow-{uuid.uuid4().hex}"
        self.calls = 0

        def runner(_plan_id, _payload, _output_path, _meta_path):
            self.calls += 1
            return {
                "records": [sample_record()],
                "meta": {"summary": {"real_count": 1}, "failures": []},
            }

        self.manager = MonitorManager(
            self.root / "monitor_state.json",
            self.root / "monitoring",
            runner,
            crawl_lock=threading.Lock(),
        )
        self.plan_id = self.manager.create_plan(sample_payload(), 15)["id"]
        self.manager.run_plan(self.plan_id)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _review_all(self):
        record = self.manager.get_records(self.plan_id)[0]
        self.manager.save_reviews(self.plan_id, [{
            "record_id": record["monitoring"]["record_id"],
            "keep": True,
            "content_category": "社会民生",
            "sentiment_label": "中性",
            "note": "已核对原文",
        }], reviewer="测试员")

    def test_monitor_review_payload_is_separate_and_annotated(self):
        with patch.object(web_app, "MONITOR_MANAGER", self.manager):
            payload = web_app.build_monitor_review_payload(self.plan_id)

        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["plan"]["id"], self.plan_id)
        self.assertEqual(payload["data"][0]["monitoring"]["review_status"], "pending")
        self.assertEqual(payload["data"][0]["content_category_source"], "machine")
        self.assertIn(self.plan_id, payload["data_path"])

    def test_monitor_preview_uses_and_reloads_frozen_reviewed_snapshot(self):
        self._review_all()
        fake_preview = {
            "sections": [{"id": "summary", "content": "规则预览"}],
            "key_samples": [{"reference_id": "S001"}],
            "quality": {"ready_for_review": True},
        }
        with (
            patch.object(web_app, "MONITOR_MANAGER", self.manager),
            patch("src.orchestrator.build_report_preview", return_value=fake_preview),
        ):
            result = web_app.create_monitor_report_preview(
                self.plan_id,
                cutoff_at="2026-09-24T18:00:00+08:00",
                automatic=True,
            )

        self.assertEqual(result["preview"]["monitoring"]["record_count"], 1)
        self.assertEqual(result["preview"]["monitoring"]["cutoff_at"], "2026-09-24T18:00:00+08:00")
        self.assertTrue(result["summary"]["automatic"])
        stored = self.manager.get_report_preview(
            self.plan_id,
            result["summary"]["snapshot_id"],
        )
        self.assertEqual(stored["preview"]["sections"][0]["content"], "规则预览")
        with patch.object(web_app, "MONITOR_MANAGER", self.manager):
            context = web_app.load_monitor_report_context({
                "monitor_id": self.plan_id,
                "monitor_snapshot_id": result["summary"]["snapshot_id"],
            })
        self.assertEqual(len(context["records"]), 1)
        self.assertEqual(context["scope"]["matched_total"], 1)
        self.assertEqual(context["cutoff_at"], "2026-09-24T18:00:00+08:00")

    def test_review_page_declares_one_time_and_monitoring_modes(self):
        html = (web_app.WEB_DIR / "index.html").read_text(encoding="utf-8")
        javascript = (web_app.WEB_DIR / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="reviewModeOnce"', html)
        self.assertIn('id="reviewModeMonitor"', html)
        self.assertIn('id="monitorReviewPlan"', html)
        self.assertIn("function switchReviewMode", javascript)
        self.assertIn("/api/monitors/review", javascript)


if __name__ == "__main__":
    unittest.main()
