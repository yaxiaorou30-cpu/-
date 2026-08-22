import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import web_app

from src.ai_confirmation import OneShotAiConfirmationStore
from src.deepseek_report import build_ai_report_disclosure


class AiReportExportScopeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("data") / f"_test_ai_export_scope_{uuid.uuid4().hex}"
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root, True)
        self.data_file = self.root / "latest_news.json"
        self.meta_file = self.root / "latest_news_meta.json"
        self.output_dir = self.root / "output"
        self.record = {
            "title": "生成 AI 草稿时的证据",
            "content": "生成草稿时，S1 对应这一条已审核正文。",
            "url": "https://example.com/original",
            "source": "原始来源",
            "platform": "新闻网站",
            "source_type": "media",
            "content_category": "社会事件",
            "sentiment_label": "中性",
            "human_review": {"reviewed_at": "2026-08-14T10:00:00"},
        }
        self.meta = {
            "topic": "测试事件",
            "keywords": ["测试事件"],
            "review": {
                "reviewed_at": "2026-08-14T10:00:00",
                "kept_total": 1,
                "labels_confirmed": True,
            },
        }
        self.preview = {
            "template_id": "event_report",
            "sections": [],
            "analysis": {"task_topic": "测试事件"},
            "key_samples": [{
                "reference_id": "S1",
                "title": self.record["title"],
                "url": self.record["url"],
            }],
        }

    class DummyHandler:
        def __init__(self, payload, session_token="test-session-token"):
            self.payload = payload
            self.session_token = session_token
            self.response = None
            self.status = None

        def read_body_json(self, *, max_bytes=None):
            return self.payload

        def cookie_value(self, name):
            return self.session_token

        def send_json(self, payload, status=200):
            self.response = payload
            self.status = status

    def write_workspace(self, records):
        self.data_file.write_text(
            json.dumps(records, ensure_ascii=False),
            encoding="utf-8",
        )
        self.meta_file.write_text(
            json.dumps(self.meta, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_ai_draft_returns_server_generated_report_export_scope_token(self):
        self.write_workspace([self.record])
        ai_scope_token = build_ai_report_disclosure(
            [self.record],
            self.preview,
            configured=True,
        )["scope_token"]
        confirmations = OneShotAiConfirmationStore()
        confirmation_id = confirmations.issue(ai_scope_token, "test-session-token")
        handler = self.DummyHandler({
            "template_id": "event_report",
            "confirmed_external_send": True,
            "confirmed_scope_token": ai_scope_token,
            "confirmation_id": confirmation_id,
            "report_filter": {},
        })

        class FakeClient:
            def generate(self, records, preview, *, template_id):
                return {
                    "scope": {"scope_token": ai_scope_token},
                    "sections": {"summary": "已生成。[S1]"},
                }

        with (
            patch.object(web_app, "DATA_FILE", self.data_file),
            patch.object(web_app, "META_FILE", self.meta_file),
            patch.object(web_app, "AI_CONFIRMATION_STORE", confirmations),
            patch.object(web_app, "DeepSeekReportClient", return_value=FakeClient()),
            patch("src.orchestrator.build_report_preview", return_value=self.preview),
            patch.object(
                web_app,
                "deepseek_configuration_status",
                return_value={
                    "configured": True,
                    "model": "deepseek-v4-pro",
                    "configuration_error": "",
                },
            ),
        ):
            web_app.WebUIHandler.handle_ai_report_draft(handler)

        self.assertEqual(handler.status, 200)
        expected = web_app.build_ai_report_export_scope_token(
            [self.record],
            self.meta,
            "event_report",
        )
        self.assertEqual(
            handler.response["draft"]["report_export_scope_token"],
            expected,
        )

    def test_word_export_rejects_ai_draft_after_same_count_evidence_replacement(self):
        original_token = web_app.build_ai_report_export_scope_token(
            [self.record],
            self.meta,
            "event_report",
        )
        replacement = {
            **self.record,
            "title": "导出前被替换的新证据",
            "content": "记录数量仍为一条，但 S1 已经对应另一段正文。",
            "url": "https://example.com/replacement",
        }
        self.write_workspace([replacement])
        handler = self.DummyHandler({
            "template_id": "event_report",
            "section_overrides": {"summary": "旧 AI 草稿仍然引用 [S1]。"},
            "report_filter": {},
            "ai_report_scope_token": original_token,
        })

        with (
            patch.object(web_app, "DATA_FILE", self.data_file),
            patch.object(web_app, "META_FILE", self.meta_file),
            patch.object(web_app, "OUTPUT_DIR", self.output_dir),
            patch.object(web_app, "update_current_history_archive", return_value="task-1"),
            patch(
                "src.orchestrator.generate_report",
                side_effect=AssertionError("范围失效时不应开始生成 Word"),
            ) as generate_report,
        ):
            web_app.WebUIHandler.handle_report(handler)

        self.assertEqual(handler.status, 409)
        self.assertIn("证据范围已变化", handler.response["message"])
        generate_report.assert_not_called()

    def test_empty_ai_scope_keeps_non_ai_manual_report_compatible(self):
        web_app.validate_ai_report_export_scope(
            [self.record],
            self.meta,
            "event_report",
            "",
        )

    def test_scope_hash_binds_evidence_but_excludes_credentials(self):
        record_with_secret = {
            **self.record,
            "password": "first-password-must-not-affect-browser-token",
            "cookie_header": "first-cookie-must-not-affect-browser-token",
        }
        original = web_app.build_ai_report_export_scope_token(
            [record_with_secret],
            self.meta,
            "event_report",
        )
        credentials_rotated = web_app.build_ai_report_export_scope_token(
            [{
                **record_with_secret,
                "password": "second-password-must-not-affect-browser-token",
                "cookie_header": "second-cookie-must-not-affect-browser-token",
            }],
            self.meta,
            "event_report",
        )
        evidence_changed = web_app.build_ai_report_export_scope_token(
            [{**record_with_secret, "content": "证据正文已经变化。"}],
            self.meta,
            "event_report",
        )

        self.assertEqual(original, credentials_rotated)
        self.assertNotEqual(original, evidence_changed)

    def test_frontend_only_sends_scope_after_ai_draft_is_applied(self):
        javascript = (web_app.WEB_DIR / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn("appliedAiReportScopeToken", javascript)
        self.assertIn("state.aiDraft.report_export_scope_token", javascript)
        self.assertIn(
            "ai_report_scope_token: state.appliedAiReportScopeToken",
            javascript,
        )


if __name__ == "__main__":
    unittest.main()
