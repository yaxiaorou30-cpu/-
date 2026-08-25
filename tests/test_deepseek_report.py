import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
import web_app
import src.deepseek_report as deepseek_report_module

from src.ai_confirmation import OneShotAiConfirmationStore
from src.deepseek_report import (
    AI_EXTERNAL_FIELDS,
    DeepSeekReportClient,
    DeepSeekReportError,
    build_ai_report_disclosure,
    build_deepseek_request,
    deepseek_configuration_status,
    validate_ai_report_output,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class DeepSeekReportTests(unittest.TestCase):
    def setUp(self):
        self.public_record = {
            "title": "警方通报事件处置进展",
            "content": "警方公布处置进展，相关调查仍在进行，公众关注后续权威信息发布。",
            "url": "https://public.example.com/a",
            "pub_time": "2026-08-14T09:30:00",
            "source": "平安示例",
            "platform": "官方公开网页",
            "source_type": "official",
            "source_group": "stable",
            "source_access_type": "A0",
            "content_category": "政务与法治",
            "sentiment_label": "中性",
            "auth_mode": "guest",
            "session_mode": "guest",
            "human_review": {
                "reviewed_at": "2026-08-14T10:00:00",
                "reviewed_by": "民警甲",
                "note": "内部审核备注不得外发",
            },
            "password": "record-password-secret",
            "cookie": "record-cookie-secret",
            "browser_session": "record-session-secret",
        }
        self.login_record = {
            **self.public_record,
            "title": "登录后页面内容",
            "content": "这是通过人工登录会话读取并完成人工审核的页面内容，允许发送给第三方 AI。",
            "url": "https://user:sentinel-url-password@private.example.com/b?xsec_token=sentinel-url-token",
            "source": "授权站点",
            "platform": "辅助登录浏览器",
            "auth_mode": "authorized_session",
            "session_mode": "browser_session",
            "login_confirmed": True,
            "source_access_type": "A1",
            "username": "sentinel-username",
            "account": "sentinel-account",
            "password_enc": "sentinel-password-enc",
            "cookie_header": "sentinel-cookie-header",
            "cookie_enc": "sentinel-cookie-enc",
            "browser_cookie": "sentinel-browser-cookie",
            "browser_cookie_enc": "sentinel-browser-cookie-enc",
            "browser_session_enc": "sentinel-browser-session-enc",
            "storage_state": "sentinel-storage-state",
            "authorization": "sentinel-authorization",
            "access_token": "sentinel-access-token",
            "refresh_token": "sentinel-refresh-token",
            "api_key": "sentinel-api-key",
            "token": "sentinel-token",
            "xsec_token": "sentinel-xsec-token",
            "BDUSS": "sentinel-bduss",
            "STOKEN": "sentinel-stoken",
            "sharetoken": "sentinel-sharetoken",
            "verification_code": "sentinel-verification-code",
        }
        self.unreviewed_record = {
            **self.public_record,
            "title": "尚未审核的页面内容",
            "content": "这条记录尚未完成人工审核，不得发送给第三方 AI。",
            "url": "https://public.example.com/unreviewed",
            "human_review": {},
        }
        self.preview = {
            "analysis": {
                "task_topic": "测试事件",
                "total_posts": 2,
                "platform_dist": {"官方公开网页": 1, "辅助登录浏览器": 1},
                "sentiment_ratio": {"正面": 0.0, "中性": 1.0, "负面": 0.0},
                "content_category_dist": {"政务与法治": 2},
                "data_limitations": [],
            },
            "key_samples": [
                {
                    "reference_id": "S1",
                    "title": self.public_record["title"],
                    "url": self.public_record["url"],
                },
                {
                    "reference_id": "S2",
                    "title": self.login_record["title"],
                    "url": self.login_record["url"],
                },
            ],
        }

    @staticmethod
    def valid_sections():
        return {
            "summary": "公开材料显示事件仍在处置中，后续信息以权威发布为准。[S1]",
            "analysis": "当前讨论主要围绕处置进展和信息公开展开。[S1]",
            "risks": "若权威信息更新不及时，可能出现重复传播或误读。[S1]",
            "recommendations": "建议持续核对权威来源，并由人工确认后使用。[S1]",
        }

    @staticmethod
    def valid_sections_with_two_evidence():
        sections = DeepSeekReportTests.valid_sections()
        sections["analysis"] = "登录后材料补充了处置进展，需与公开信息交叉核对。[S2]"
        return sections

    def valid_api_payload(self):
        return {
            "id": "chatcmpl-test",
            "model": "deepseek-v4-pro",
            "system_fingerprint": "fp-test",
            "choices": [{
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {"sections": self.valid_sections_with_two_evidence()},
                        ensure_ascii=False,
                    ),
                },
            }],
            "usage": {
                "prompt_tokens": 300,
                "prompt_cache_hit_tokens": 20,
                "prompt_cache_miss_tokens": 280,
                "completion_tokens": 120,
                "total_tokens": 420,
            },
        }

    @staticmethod
    def reviewed_records(count, content_factory=None):
        records = []
        for index in range(1, count + 1):
            content = (
                content_factory(index)
                if content_factory
                else f"第 {index} 条已审核证据，内容短小且可以完整进入默认输入预算。"
            )
            records.append({
                "title": f"预算证据 {index:02d}",
                "content": content,
                "url": f"https://evidence.example.com/{index}",
                "pub_time": f"2026-08-14T{index % 24:02d}:00:00",
                "source": f"来源 {index:02d}",
                "platform": f"平台 {(index - 1) % 3 + 1}",
                "source_type": "media",
                "content_category": "社会事件",
                "sentiment_label": "中性",
                "human_review": {"reviewed_at": "2026-08-14T16:00:00"},
            })
        return records

    @staticmethod
    def evidence_preview(records, *, query_keywords=None):
        catalog = [
            {
                "reference_id": f"S{index}",
                "title": record["title"],
                "url": record["url"],
            }
            for index, record in enumerate(records, start=1)
        ]
        return {
            "analysis": {"query_keywords": list(query_keywords or [])},
            "key_samples": catalog[:8],
            "evidence_catalog": catalog,
        }

    @staticmethod
    def sent_evidence(payload):
        return json.loads(
            payload["messages"][1]["content"].split("证据数据如下：\n", 1)[1]
        )["evidence"]

    def test_request_includes_reviewed_login_evidence_but_excludes_secrets(self):
        payload, scope = build_deepseek_request(
            [self.public_record, self.login_record],
            self.preview,
            model="deepseek-v4-flash",
        )

        serialized = json.dumps(payload, ensure_ascii=False)
        evidence_payload = json.loads(
            payload["messages"][1]["content"].split("证据数据如下：\n", 1)[1]
        )
        self.assertEqual(scope["reviewed_record_count"], 2)
        self.assertEqual(scope["eligible_record_count"], 2)
        self.assertEqual(scope["public_record_count"], 1)
        self.assertEqual(scope["login_record_count"], 1)
        self.assertEqual(scope["excluded_nonpublic_count"], 0)
        self.assertEqual(scope["evidence_ids"], ["S1", "S2"])
        self.assertEqual(scope["fields"], list(AI_EXTERNAL_FIELDS))
        self.assertIn(self.public_record["content"], serialized)
        self.assertIn(self.login_record["content"], serialized)
        self.assertNotIn("record-password-secret", serialized)
        self.assertNotIn("record-cookie-secret", serialized)
        self.assertNotIn("record-session-secret", serialized)
        self.assertNotIn("内部审核备注不得外发", serialized)
        self.assertNotIn('"auth_mode"', serialized)
        self.assertNotIn('"session_mode"', serialized)
        self.assertNotIn('"login_confirmed"', serialized)
        self.assertNotIn('"human_review"', serialized)
        for evidence in evidence_payload["evidence"]:
            self.assertEqual(tuple(evidence), AI_EXTERNAL_FIELDS)
        for secret_value in (
            "sentinel-url-password",
            "sentinel-url-token",
            "sentinel-username",
            "sentinel-account",
            "sentinel-password-enc",
            "sentinel-cookie-header",
            "sentinel-cookie-enc",
            "sentinel-browser-cookie",
            "sentinel-browser-cookie-enc",
            "sentinel-browser-session-enc",
            "sentinel-storage-state",
            "sentinel-authorization",
            "sentinel-access-token",
            "sentinel-refresh-token",
            "sentinel-api-key",
            "sentinel-token",
            "sentinel-xsec-token",
            "sentinel-bduss",
            "sentinel-stoken",
            "sentinel-sharetoken",
            "sentinel-verification-code",
            "民警甲",
        ):
            self.assertNotIn(secret_value, serialized)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["thinking"], {"type": "enabled"})
        self.assertEqual(payload["reasoning_effort"], "max")
        self.assertNotIn("temperature", payload)
        self.assertFalse(payload["stream"])

    def test_default_budget_loads_all_twelve_catalog_evidence_and_discloses_estimate(self):
        records = self.reviewed_records(12)
        payload, scope = build_deepseek_request(
            records,
            self.evidence_preview(records),
        )

        evidence = self.sent_evidence(payload)
        expected_ids = [f"S{index}" for index in range(1, 13)]
        self.assertEqual([item["reference_id"] for item in evidence], expected_ids)
        self.assertIn("S9", scope["evidence_ids"])
        self.assertIn("S12", scope["evidence_ids"])
        self.assertEqual(scope["input_budget_tokens"], 128_000)
        self.assertLessEqual(scope["estimated_input_tokens"], 128_000)
        self.assertEqual(
            scope["token_estimator_version"],
            "deepseek-utf8-byte-upper-bound-v2",
        )
        self.assertEqual(scope["selection_version"], "ranked-budget-v1")
        for item in evidence:
            self.assertEqual(tuple(item), AI_EXTERNAL_FIELDS)

    def test_small_budget_preserves_head_keyword_context_and_tail_with_truncation_disclosure(self):
        content = (
            "开头事实标记。"
            + "甲" * 18_000
            + "核心命中词附近的关键事实标记。"
            + "乙" * 18_000
            + "结尾事实标记。"
        )
        records = self.reviewed_records(1, lambda _index: content)
        payload, scope = build_deepseek_request(
            records,
            self.evidence_preview(records, query_keywords=["核心命中词"]),
            input_budget_tokens=4_096,
        )

        evidence = self.sent_evidence(payload)
        self.assertEqual(len(evidence), 1)
        sent_content = evidence[0]["content"]
        self.assertLess(len(sent_content), len(content))
        self.assertIn("开头事实标记", sent_content)
        self.assertIn("核心命中词附近的关键事实标记", sent_content)
        self.assertIn("结尾事实标记", sent_content)
        self.assertIn("中间省略", sent_content)
        self.assertEqual(scope["truncated_evidence_count"], 1)
        self.assertEqual(scope["truncated_evidence_ids"], ["S1"])
        self.assertEqual(scope["original_content_chars"], len(content))
        self.assertEqual(scope["sent_content_chars"], len(sent_content))
        self.assertLessEqual(scope["estimated_input_tokens"], 4_096)
        self.assertEqual(tuple(evidence[0]), AI_EXTERNAL_FIELDS)

    def test_small_budget_omits_long_evidence_and_scope_token_tracks_effective_scope(self):
        records = self.reviewed_records(
            12,
            lambda index: (
                f"第 {index} 条开头事实。"
                + "长" * 6_000
                + "预算关键词附近事实。"
                + "文" * 6_000
                + f"第 {index} 条结尾事实。"
            ),
        )
        preview = self.evidence_preview(records, query_keywords=["预算关键词"])

        small_payload, small_scope = build_deepseek_request(
            records,
            preview,
            input_budget_tokens=2_048,
        )
        large_payload, large_scope = build_deepseek_request(
            records,
            preview,
            input_budget_tokens=128_000,
        )

        small_evidence = self.sent_evidence(small_payload)
        large_evidence = self.sent_evidence(large_payload)
        small_ids = [item["reference_id"] for item in small_evidence]
        self.assertGreater(small_scope["omitted_due_input_budget_count"], 0)
        self.assertEqual(
            small_scope["omitted_due_input_budget_count"],
            len(records) - len(small_evidence),
        )
        self.assertEqual(small_scope["evidence_count"], len(small_evidence))
        self.assertEqual(small_scope["evidence_ids"], small_ids)
        self.assertLessEqual(small_scope["estimated_input_tokens"], 2_048)
        self.assertNotEqual(small_evidence, large_evidence)
        self.assertNotEqual(small_scope["scope_token"], large_scope["scope_token"])

    def test_input_budget_accepts_supported_boundaries_and_rejects_invalid_numbers(self):
        records = self.reviewed_records(1)
        preview = self.evidence_preview(records)

        _, maximum_scope = build_deepseek_request(
            records,
            preview,
            input_budget_tokens=512_000,
        )
        self.assertEqual(maximum_scope["input_budget_tokens"], 512_000)

        for invalid_budget in (True, 128_000.0, 0, -1, 512_001):
            with self.subTest(input_budget_tokens=invalid_budget):
                with self.assertRaises(DeepSeekReportError):
                    build_deepseek_request(
                        records,
                        preview,
                        input_budget_tokens=invalid_budget,
                    )

        with self.assertRaisesRegex(DeepSeekReportError, "上下文|总预算|1000000"):
            build_deepseek_request(
                records,
                preview,
                input_budget_tokens=512_000,
                max_tokens=400_001,
            )

    def test_catalog_identity_uses_title_and_excerpt_when_url_is_duplicated(self):
        duplicate_url = "https://evidence.example.com/shared"
        wrong_record = {
            **self.public_record,
            "url": duplicate_url,
            "title": "同链接的旧版本标题",
            "content": "错误的旧版本正文不得绑定到 S1。",
        }
        expected_record = {
            **self.public_record,
            "url": duplicate_url,
            "title": "同链接的正确版本标题",
            "content": "正确版本正文应当精确绑定到 S1。",
        }
        preview = {
            "evidence_catalog": [{
                "reference_id": "S1",
                "url": duplicate_url,
                "title": expected_record["title"],
                "content_excerpt": expected_record["content"],
            }],
            "analysis": {"query_keywords": ["正确版本"]},
        }

        payload, scope = build_deepseek_request(
            [wrong_record, expected_record],
            preview,
        )

        evidence = self.sent_evidence(payload)
        self.assertEqual(scope["evidence_ids"], ["S1"])
        self.assertEqual(evidence[0]["title"], expected_record["title"])
        self.assertIn("正确版本正文", evidence[0]["content"])
        self.assertNotIn("错误的旧版本正文", evidence[0]["content"])

    def test_catalog_identity_fails_closed_when_duplicate_is_ambiguous_or_excerpt_mismatches(self):
        duplicate_url = "https://evidence.example.com/ambiguous"
        records = [
            {
                **self.public_record,
                "url": duplicate_url,
                "title": "完全相同的目录标题",
                "content": content,
            }
            for content in ("第一个不同正文。", "第二个不同正文。")
        ]
        ambiguous_preview = {
            "evidence_catalog": [{
                "reference_id": "S1",
                "url": duplicate_url,
                "title": "完全相同的目录标题",
            }],
        }
        mismatched_preview = {
            "evidence_catalog": [{
                "reference_id": "S1",
                "url": duplicate_url,
                "title": "完全相同的目录标题",
                "content_excerpt": "目录中不存在的正文摘要",
            }],
        }

        for preview in (ambiguous_preview, mismatched_preview):
            with self.subTest(preview=preview):
                with self.assertRaisesRegex(DeepSeekReportError, "没有可发送|重点证据"):
                    build_deepseek_request(records, preview)

    def test_estimated_input_tokens_is_utf8_byte_upper_bound_for_mixed_text(self):
        contents = (
            "ASCII-only evidence with punctuation 12345 and repeated words. " * 8,
            "中文证据包含时间、地点和多字节字符。" * 16,
            "https://example.com/search?q=token%20budget&lang=zh-CN#result-1 " * 8,
        )
        for content in contents:
            with self.subTest(content=content[:24]):
                records = self.reviewed_records(1, lambda _index: content)
                payload, scope = build_deepseek_request(
                    records,
                    self.evidence_preview(records),
                )
                serialized_bytes = len(json.dumps(
                    payload["messages"],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8"))

                self.assertGreaterEqual(scope["estimated_input_tokens"], serialized_bytes)
                self.assertLessEqual(
                    scope["estimated_input_tokens"] + payload["max_tokens"] + 100_000,
                    1_000_000,
                )

    def test_minimum_budget_selection_respects_utf8_byte_upper_bound(self):
        records = self.reviewed_records(
            20,
            lambda index: (
                f"第 {index} 条中文与 ASCII / URL 混合证据："
                + "汉字ABC123https://example.com/path?q=预算" * 400
            ),
        )
        payload, scope = build_deepseek_request(
            records,
            self.evidence_preview(records, query_keywords=["预算"]),
            input_budget_tokens=2_048,
        )
        serialized_bytes = len(json.dumps(
            payload["messages"],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8"))

        self.assertGreater(scope["evidence_count"], 0)
        self.assertLessEqual(serialized_bytes, scope["estimated_input_tokens"])
        self.assertLessEqual(scope["estimated_input_tokens"], 2_048)

    def test_small_budget_does_not_eagerly_normalize_all_256_full_text_candidates(self):
        shared_long_content = (
            "开头 MIXED Budget Keyword。" + "长文本AbC123" * 5_000 + "结尾。"
        )
        records = self.reviewed_records(256, lambda _index: shared_long_content)
        preview = self.evidence_preview(records, query_keywords=["budget keyword"])
        normalized_input_lengths = []
        original_normalizer = deepseek_report_module._normalized_source_content

        def tracking_normalizer(value):
            normalized_input_lengths.append(len(str(value or "")))
            return original_normalizer(value)

        with patch.object(
            deepseek_report_module,
            "_normalized_source_content",
            side_effect=tracking_normalizer,
        ):
            _, scope = build_deepseek_request(
                records,
                preview,
                input_budget_tokens=2_048,
            )

        self.assertLess(scope["evidence_count"], 256)
        self.assertLess(len(normalized_input_lengths), 128)
        self.assertLessEqual(max(normalized_input_lengths, default=0), 12_000)

    def test_quality_defaults_use_pro_model_and_32768_output_budget(self):
        payload, _ = build_deepseek_request(
            [self.public_record, self.login_record],
            self.preview,
        )
        status = deepseek_configuration_status({"DEEPSEEK_API_KEY": "configured"})

        self.assertEqual(payload["model"], "deepseek-v4-pro")
        self.assertEqual(payload["max_tokens"], 32768)
        self.assertEqual(status["model"], "deepseek-v4-pro")

    def test_output_budget_allows_quality_ranges_up_to_provider_limit(self):
        for max_tokens in (8192, 32768, 384000):
            with self.subTest(max_tokens=max_tokens):
                payload, _ = build_deepseek_request(
                    [self.public_record, self.login_record],
                    self.preview,
                    max_tokens=max_tokens,
                )
                self.assertEqual(payload["max_tokens"], max_tokens)

        with self.assertRaisesRegex(DeepSeekReportError, "384000"):
            build_deepseek_request(
                [self.public_record, self.login_record],
                self.preview,
                max_tokens=384001,
            )

    def test_scope_confirmation_token_binds_the_output_budget(self):
        _, default_scope = build_deepseek_request(
            [self.public_record, self.login_record],
            self.preview,
        )
        _, larger_scope = build_deepseek_request(
            [self.public_record, self.login_record],
            self.preview,
            max_tokens=65536,
        )
        disclosure = build_ai_report_disclosure(
            [self.public_record, self.login_record],
            self.preview,
            configured=True,
        )

        self.assertEqual(disclosure["scope_token"], default_scope["scope_token"])
        self.assertNotEqual(default_scope["scope_token"], larger_scope["scope_token"])

    def test_unreviewed_evidence_remains_excluded_after_scope_is_relaxed(self):
        preview = {
            "key_samples": [
                self.preview["key_samples"][0],
                {
                    "reference_id": "S3",
                    "title": self.unreviewed_record["title"],
                    "url": self.unreviewed_record["url"],
                },
            ]
        }

        payload, scope = build_deepseek_request(
            [self.public_record, self.unreviewed_record],
            preview,
        )

        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(scope["evidence_ids"], ["S1"])
        self.assertEqual(scope["excluded_unreviewed_count"], 1)
        self.assertNotIn(self.unreviewed_record["content"], serialized)

    def test_pending_body_review_is_excluded_even_after_label_review(self):
        pending_record = {
            **self.public_record,
            "title": "正文获取失败但分类情感已经审核",
            "content": "这只是搜索来源返回的摘要，不得作为 DeepSeek 正文证据。",
            "url": "https://public.example.com/pending-body-review",
            "body_fetch_status": "failed",
        }
        preview = {
            "key_samples": [
                self.preview["key_samples"][0],
                {
                    "reference_id": "S3",
                    "title": pending_record["title"],
                    "url": pending_record["url"],
                },
            ]
        }

        payload, scope = build_deepseek_request(
            [self.public_record, pending_record],
            preview,
        )

        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(scope["reviewed_record_count"], 2)
        self.assertEqual(scope["eligible_record_count"], 1)
        self.assertEqual(scope["excluded_unreviewed_count"], 0)
        self.assertEqual(scope["evidence_ids"], ["S1"])
        self.assertNotIn(pending_record["content"], serialized)

    def test_disclosure_never_contains_evidence_text_or_api_key(self):
        disclosure = build_ai_report_disclosure(
            [self.public_record, self.login_record],
            self.preview,
            configured=True,
            model="deepseek-v4-flash",
        )

        serialized = json.dumps(disclosure, ensure_ascii=False)
        self.assertTrue(disclosure["configured"])
        self.assertEqual(disclosure["provider"], "DeepSeek")
        self.assertEqual(disclosure["evidence_count"], 2)
        self.assertEqual(disclosure["eligible_record_count"], 2)
        self.assertEqual(disclosure["login_record_count"], 1)
        self.assertEqual(disclosure["quality_mode"], "quality_first")
        self.assertTrue(disclosure["thinking_enabled"])
        self.assertEqual(disclosure["reasoning_effort"], "max")
        self.assertEqual(disclosure["max_output_tokens"], 32768)
        self.assertEqual(len(disclosure["scope_token"]), 64)
        int(disclosure["scope_token"], 16)
        self.assertNotIn(self.public_record["content"], serialized)
        self.assertNotIn("record-cookie-secret", serialized)

    def test_configuration_status_exposes_presence_but_never_key_value(self):
        status = deepseek_configuration_status(
            {
                "DEEPSEEK_API_KEY": "deepseek-key-must-stay-server-side",
                "DEEPSEEK_MODEL": "deepseek-v4-flash",
            }
        )

        self.assertTrue(status["configured"])
        self.assertEqual(status["model"], "deepseek-v4-flash")
        self.assertNotIn("deepseek-key-must-stay-server-side", json.dumps(status))

    def test_reviewed_login_only_scope_can_generate(self):
        disclosure = build_ai_report_disclosure(
            [self.login_record],
            {"key_samples": [self.preview["key_samples"][1]]},
            configured=True,
        )

        self.assertEqual(disclosure["eligible_record_count"], 1)
        self.assertEqual(disclosure["public_record_count"], 0)
        self.assertEqual(disclosure["login_record_count"], 1)
        self.assertEqual(disclosure["evidence_count"], 1)
        self.assertTrue(disclosure["can_generate"])

    def test_single_confirmation_makes_exactly_one_request_and_returns_usage(self):
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(payload=self.valid_api_payload())

        client = DeepSeekReportClient(
            api_key="deepseek-key-secret",
            request_post=fake_post,
        )
        result = client.generate([self.public_record, self.login_record], self.preview)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "https://api.deepseek.com/chat/completions")
        self.assertEqual(calls[0][1]["timeout"], (5, 120))
        self.assertEqual(result["usage"]["total_tokens"], 420)
        self.assertEqual(result["scope"]["evidence_ids"], ["S1", "S2"])
        self.assertEqual(result["sections"], self.valid_sections_with_two_evidence())
        self.assertIn("风险提示", result["section_overrides"]["analysis"])
        self.assertNotIn("deepseek-key-secret", json.dumps(result, ensure_ascii=False))

    def test_missing_key_stops_before_network_request(self):
        calls = []
        client = DeepSeekReportClient(
            api_key="",
            request_post=lambda *args, **kwargs: calls.append((args, kwargs)),
        )

        with self.assertRaisesRegex(DeepSeekReportError, "未配置 DEEPSEEK_API_KEY"):
            client.generate([self.public_record], self.preview)
        self.assertEqual(calls, [])

    def test_timeout_is_not_retried_and_error_does_not_expose_key(self):
        calls = []

        def timeout_post(*args, **kwargs):
            calls.append((args, kwargs))
            raise requests.Timeout("request included deepseek-key-secret")

        client = DeepSeekReportClient(
            api_key="deepseek-key-secret",
            request_post=timeout_post,
        )
        with self.assertRaises(DeepSeekReportError) as caught:
            client.generate([self.public_record], self.preview)

        self.assertEqual(len(calls), 1)
        self.assertIn("未自动重试", str(caught.exception))
        self.assertNotIn("deepseek-key-secret", str(caught.exception))

    def test_http_errors_are_translated_without_echoing_response_body(self):
        expectations = {
            401: "密钥无效",
            402: "余额不足",
            429: "请求过于频繁",
            500: "服务暂时异常",
            503: "服务繁忙",
        }
        for status, message in expectations.items():
            with self.subTest(status=status):
                client = DeepSeekReportClient(
                    api_key="deepseek-key-secret",
                    request_post=lambda *args, _status=status, **kwargs: FakeResponse(
                        status_code=_status,
                        payload={"error": "server echoed deepseek-key-secret"},
                    ),
                )
                with self.assertRaises(DeepSeekReportError) as caught:
                    client.generate([self.public_record], self.preview)
                self.assertIn(message, str(caught.exception))
                self.assertNotIn("deepseek-key-secret", str(caught.exception))

    def test_invalid_json_unknown_reference_and_missing_reference_are_rejected(self):
        with self.assertRaisesRegex(DeepSeekReportError, "不是有效 JSON"):
            validate_ai_report_output("not-json", {"S1"})

        unknown = self.valid_sections()
        unknown["analysis"] = "错误引用。[S999]"
        with self.assertRaisesRegex(DeepSeekReportError, "未知证据编号"):
            validate_ai_report_output(
                json.dumps({"sections": unknown}, ensure_ascii=False),
                {"S1"},
            )

        missing = self.valid_sections()
        missing["risks"] = "这一段没有证据引用。"
        with self.assertRaisesRegex(DeepSeekReportError, "缺少有效证据引用"):
            validate_ai_report_output(
                json.dumps({"sections": missing}, ensure_ascii=False),
                {"S1"},
            )

    def test_section_over_4000_chars_is_not_rejected_when_quality_rules_pass(self):
        long_sections = self.valid_sections()
        long_sections["summary"] = "完整证据内容" * 900 + "[S1]"

        validated = validate_ai_report_output(
            json.dumps({"sections": long_sections}, ensure_ascii=False),
            {"S1"},
        )

        self.assertEqual(validated["summary"], long_sections["summary"])

    def test_every_nonempty_paragraph_or_list_line_requires_a_valid_reference(self):
        invalid_lines = (
            "第一段已有引用。[S1]\n\n第二段没有引用。",
            "- 风险一已有引用。[S1]\n- 风险二没有引用。",
        )
        for invalid_value in invalid_lines:
            with self.subTest(invalid_value=invalid_value):
                sections = self.valid_sections()
                sections["risks"] = invalid_value
                with self.assertRaisesRegex(DeepSeekReportError, "非空.*有效证据引用"):
                    validate_ai_report_output(
                        json.dumps({"sections": sections}, ensure_ascii=False),
                        {"S1"},
                    )

    def test_section_with_only_reference_and_punctuation_is_rejected(self):
        sections = self.valid_sections()
        sections["summary"] = "……[S1]"

        with self.assertRaisesRegex(DeepSeekReportError, "缺少实质内容"):
            validate_ai_report_output(
                json.dumps({"sections": sections}, ensure_ascii=False),
                {"S1"},
            )

    def test_report_uses_at_least_two_distinct_references_when_available(self):
        with self.assertRaisesRegex(DeepSeekReportError, "至少引用 2 个不同证据"):
            validate_ai_report_output(
                json.dumps({"sections": self.valid_sections()}, ensure_ascii=False),
                {"S1", "S2"},
            )

    def test_all_four_sections_cannot_repeat_after_references_and_whitespace_are_removed(self):
        repeated_sections = {
            "summary": "完全相同的报告内容。[S1]",
            "analysis": " 完全相同的报告内容。 [S2]",
            "risks": "完全相同的报告内容。   [S1]",
            "recommendations": "完全相同的报告内容。[S2]",
        }

        with self.assertRaisesRegex(DeepSeekReportError, "四个章节.*重复"):
            validate_ai_report_output(
                json.dumps({"sections": repeated_sections}, ensure_ascii=False),
                {"S1", "S2"},
            )

    def test_any_two_sections_cannot_repeat_after_references_and_whitespace_are_removed(self):
        repeated_sections = self.valid_sections_with_two_evidence()
        repeated_sections["risks"] = "公开材料显示事件仍在处置中，后续信息以权威发布为准。 [S2]"

        with self.assertRaisesRegex(DeepSeekReportError, "章节.*重复"):
            validate_ai_report_output(
                json.dumps({"sections": repeated_sections}, ensure_ascii=False),
                {"S1", "S2"},
            )

    def test_truncated_or_empty_model_response_is_rejected(self):
        for finish_reason, content, message in (
            ("length", json.dumps({"sections": self.valid_sections()}), "达到输出长度上限"),
            ("stop", "", "返回了空内容"),
        ):
            with self.subTest(finish_reason=finish_reason, content=content):
                response = self.valid_api_payload()
                response["choices"][0]["finish_reason"] = finish_reason
                response["choices"][0]["message"]["content"] = content
                client = DeepSeekReportClient(
                    api_key="deepseek-key-secret",
                    request_post=lambda *args, _response=response, **kwargs: FakeResponse(
                        payload=_response
                    ),
                )
                with self.assertRaisesRegex(DeepSeekReportError, message):
                    client.generate([self.public_record], self.preview)


class WebDeepSeekHandlerTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("data") / "_test_deepseek_handler"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True)
        self.data_file = self.root / "latest_news.json"
        self.meta_file = self.root / "latest_news_meta.json"
        self.record = {
            "title": "已审核公开线索",
            "content": "公开材料显示事件处置工作正在进行。",
            "url": "https://public.example.com/a",
            "pub_time": "2026-08-14T09:30:00",
            "time_basis": "published_time",
            "source": "公开来源",
            "platform": "官方公开网页",
            "source_type": "official",
            "source_group": "stable",
            "source_access_type": "A0",
            "content_category": "政务与法治",
            "sentiment_label": "中性",
            "auth_mode": "guest",
            "session_mode": "guest",
            "human_review": {
                "reviewed_at": "2026-08-14T10:00:00",
                "reviewed_by": "民警甲",
            },
        }
        self.data_file.write_text(
            json.dumps([self.record], ensure_ascii=False),
            encoding="utf-8",
        )
        self.meta_file.write_text(
            json.dumps({
                "topic": "测试事件",
                "review": {
                    "reviewed_at": "2026-08-14T10:00:00",
                    "kept_total": 1,
                    "labels_confirmed": True,
                },
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        self.preview = {
            "sections": [],
            "analysis": {},
            "key_samples": [{
                "reference_id": "S1",
                "title": self.record["title"],
                "url": self.record["url"],
            }],
        }
        self.confirmation_store = OneShotAiConfirmationStore()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def current_scope_token(self):
        return build_ai_report_disclosure(
            [self.record],
            self.preview,
            configured=True,
            model="deepseek-v4-flash",
        )["scope_token"]

    def issue_confirmation(self):
        return self.confirmation_store.issue(
            self.current_scope_token(),
            "test-session-token",
        )

    class DummyHandler:
        def __init__(self, payload, session_token="test-session-token"):
            self.payload = payload
            self.session_token = session_token
            self.response = None
            self.status = None

        def read_body_json(self, *, max_bytes=None):
            return self.payload

        def current_identity(self, *, touch=True):
            return {"username": "民警甲"}

        def cookie_value(self, name):
            return self.session_token

        def send_json(self, payload, status=200):
            self.response = payload
            self.status = status

    def test_ai_handler_requires_explicit_confirmation_without_network_call(self):
        handler = self.DummyHandler({
            "template_id": "event_report",
            "confirmed_external_send": False,
        })
        calls = []

        class FakeClient:
            def generate(self, *args, **kwargs):
                calls.append((args, kwargs))

        with (
            patch.object(web_app, "DATA_FILE", self.data_file),
            patch.object(web_app, "META_FILE", self.meta_file),
            patch.object(web_app, "DeepSeekReportClient", return_value=FakeClient()),
        ):
            web_app.WebUIHandler.handle_ai_report_draft(handler)

        self.assertEqual(handler.status, 400)
        self.assertFalse(handler.response["ok"])
        self.assertIn("按甲方内部规则确认本次发送范围", handler.response["message"])
        self.assertEqual(calls, [])

    def test_ai_handler_rebuilds_server_preview_and_calls_provider_once(self):
        handler = self.DummyHandler({
            "template_id": "event_report",
            "confirmed_external_send": True,
            "confirmed_scope_token": self.current_scope_token(),
            "confirmation_id": self.issue_confirmation(),
            "report_filter": {},
            "records": [{"content": "前端伪造正文不得使用"}],
            "preview": {"key_samples": [{"reference_id": "S999"}]},
            "fields": ["password", "cookie"],
            "evidence_ids": ["S999"],
            "eligible_record_count": 999,
            "secret": "前端伪造秘密不得使用",
        })
        calls = []
        expected_draft = {
            "provider": "DeepSeek",
            "sections": DeepSeekReportTests.valid_sections(),
            "scope": {"evidence_ids": ["S1"]},
            "usage": {"total_tokens": 10},
        }

        class FakeClient:
            def generate(self, records, preview, *, template_id):
                calls.append((records, preview, template_id))
                return expected_draft

        with (
            patch.object(web_app, "DATA_FILE", self.data_file),
            patch.object(web_app, "META_FILE", self.meta_file),
            patch.object(web_app, "DeepSeekReportClient", return_value=FakeClient()),
            patch.object(web_app, "AI_CONFIRMATION_STORE", self.confirmation_store),
            patch("src.orchestrator.build_report_preview", return_value=self.preview),
            patch.object(
                web_app,
                "deepseek_configuration_status",
                return_value={
                    "provider": "DeepSeek",
                    "configured": True,
                    "model": "deepseek-v4-flash",
                    "configuration_error": "",
                },
            ),
        ):
            web_app.WebUIHandler.handle_ai_report_draft(handler)

        self.assertEqual(handler.status, 200)
        self.assertTrue(handler.response["ok"])
        self.assertEqual(handler.response["draft"], expected_draft)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][0]["content"], self.record["content"])
        self.assertNotEqual(calls[0][0], handler.payload["records"])

    def test_ai_handler_rejects_stale_scope_confirmation_without_provider_call(self):
        handler = self.DummyHandler({
            "template_id": "event_report",
            "confirmed_external_send": True,
            "confirmed_scope_token": "0" * 64,
            "confirmation_id": self.issue_confirmation(),
            "report_filter": {},
        })
        calls = []

        class FakeClient:
            def generate(self, *args, **kwargs):
                calls.append((args, kwargs))

        with (
            patch.object(web_app, "DATA_FILE", self.data_file),
            patch.object(web_app, "META_FILE", self.meta_file),
            patch.object(web_app, "DeepSeekReportClient", return_value=FakeClient()),
            patch.object(web_app, "AI_CONFIRMATION_STORE", self.confirmation_store),
            patch("src.orchestrator.build_report_preview", return_value=self.preview),
            patch.object(
                web_app,
                "deepseek_configuration_status",
                return_value={
                    "provider": "DeepSeek",
                    "configured": True,
                    "model": "deepseek-v4-flash",
                    "configuration_error": "",
                },
            ),
        ):
            web_app.WebUIHandler.handle_ai_report_draft(handler)

        self.assertEqual(handler.status, 400)
        self.assertIn("范围已变化", handler.response["message"])
        self.assertEqual(calls, [])

    def test_ai_confirmation_is_consumed_once_and_replay_never_calls_provider(self):
        confirmation_id = self.issue_confirmation()
        payload = {
            "template_id": "event_report",
            "confirmed_external_send": True,
            "confirmed_scope_token": self.current_scope_token(),
            "confirmation_id": confirmation_id,
            "report_filter": {},
        }
        handlers = [self.DummyHandler(dict(payload)), self.DummyHandler(dict(payload))]
        calls = []

        class FakeClient:
            def generate(self, records, preview, *, template_id):
                calls.append((records, preview, template_id))
                return {"sections": DeepSeekReportTests.valid_sections()}

        with (
            patch.object(web_app, "DATA_FILE", self.data_file),
            patch.object(web_app, "META_FILE", self.meta_file),
            patch.object(web_app, "DeepSeekReportClient", return_value=FakeClient()),
            patch.object(web_app, "AI_CONFIRMATION_STORE", self.confirmation_store),
            patch("src.orchestrator.build_report_preview", return_value=self.preview),
            patch.object(
                web_app,
                "deepseek_configuration_status",
                return_value={
                    "provider": "DeepSeek",
                    "configured": True,
                    "model": "deepseek-v4-flash",
                    "configuration_error": "",
                },
            ),
        ):
            for handler in handlers:
                web_app.WebUIHandler.handle_ai_report_draft(handler)

        self.assertEqual(handlers[0].status, 200)
        self.assertEqual(handlers[1].status, 409)
        self.assertIn("已使用", handlers[1].response["message"])
        self.assertEqual(len(calls), 1)

    def test_failed_provider_attempt_also_consumes_confirmation(self):
        confirmation_id = self.issue_confirmation()
        payload = {
            "template_id": "event_report",
            "confirmed_external_send": True,
            "confirmed_scope_token": self.current_scope_token(),
            "confirmation_id": confirmation_id,
            "report_filter": {},
        }
        handlers = [self.DummyHandler(dict(payload)), self.DummyHandler(dict(payload))]
        calls = []

        class FailingClient:
            def generate(self, *args, **kwargs):
                calls.append((args, kwargs))
                raise DeepSeekReportError("服务商调用失败")

        with (
            patch.object(web_app, "DATA_FILE", self.data_file),
            patch.object(web_app, "META_FILE", self.meta_file),
            patch.object(web_app, "DeepSeekReportClient", return_value=FailingClient()),
            patch.object(web_app, "AI_CONFIRMATION_STORE", self.confirmation_store),
            patch("src.orchestrator.build_report_preview", return_value=self.preview),
            patch.object(
                web_app,
                "deepseek_configuration_status",
                return_value={
                    "provider": "DeepSeek",
                    "configured": True,
                    "model": "deepseek-v4-flash",
                    "configuration_error": "",
                },
            ),
        ):
            for handler in handlers:
                web_app.WebUIHandler.handle_ai_report_draft(handler)

        self.assertEqual(handlers[0].status, 502)
        self.assertEqual(handlers[1].status, 409)
        self.assertEqual(len(calls), 1)

    def test_rule_preview_adds_disclosure_without_calling_deepseek(self):
        handler = self.DummyHandler({
            "template_id": "event_report",
            "report_filter": {},
        })

        class ExplodingClient:
            def __init__(self, *args, **kwargs):
                raise AssertionError("普通规则预览不得创建 DeepSeek 客户端")

        with (
            patch.object(web_app, "DATA_FILE", self.data_file),
            patch.object(web_app, "META_FILE", self.meta_file),
            patch.object(web_app, "DeepSeekReportClient", ExplodingClient),
            patch.object(web_app, "AI_CONFIRMATION_STORE", self.confirmation_store),
            patch("src.orchestrator.build_report_preview", return_value=dict(self.preview)),
            patch.object(
                web_app,
                "deepseek_configuration_status",
                return_value={
                    "provider": "DeepSeek",
                    "configured": True,
                    "model": "deepseek-v4-flash",
                    "configuration_error": "",
                },
            ),
        ):
            web_app.WebUIHandler.handle_report_preview(handler)

        self.assertEqual(handler.status, 200)
        disclosure = handler.response["preview"]["ai_assistance"]
        self.assertTrue(disclosure["configured"])
        self.assertFalse(disclosure["automatic_call"])
        self.assertEqual(disclosure["evidence_ids"], ["S1"])
        self.assertTrue(disclosure["confirmation_id"])
        self.assertNotIn("test-session-token", json.dumps(disclosure))


class DeepSeekReportUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (web_app.WEB_DIR / "index.html").read_text(encoding="utf-8")
        cls.javascript = (web_app.WEB_DIR / "static" / "app.js").read_text(
            encoding="utf-8"
        )

    def test_report_page_has_disclosure_confirmation_and_separate_draft_panel(self):
        self.assertIn('id="aiReportPanel"', self.html)
        self.assertIn('id="aiExternalSendConfirm"', self.html)
        self.assertIn('id="aiGenerateBtn"', self.html)
        self.assertIn('id="aiApplyBtn"', self.html)
        self.assertIn('id="aiDraftStatus"', self.html)
        self.assertIn('aria-live="polite"', self.html)
        self.assertIn("系统仅按甲方审核结果和本次人工确认执行发送", self.html)
        self.assertIn("哪些内容允许发送由甲方决定", self.html)
        self.assertIn("系统不作合法性、授权充分性或保密属性判断", self.html)
        self.assertIn(
            "系统不会发送登录配置中的账号、密码、验证码、Cookie、令牌、会话凭据或审核备注",
            self.html,
        )
        self.assertIn("我确认已按甲方内部规则完成本次数据审核并获得授权", self.html)
        self.assertNotIn("已审核正文可以发送", self.html)
        self.assertNotIn("只发送标记为 A0 的匿名公开记录", self.html)

    def test_ai_scope_copy_includes_reviewed_login_records(self):
        self.assertIn("disclosure.eligible_record_count", self.javascript)
        self.assertIn("disclosure.login_record_count", self.javascript)
        self.assertIn("已审核候选", self.javascript)
        self.assertNotIn("已审核可发送", self.javascript)
        self.assertNotIn("排除登录/非公开", self.javascript)
        self.assertIn("未审核数据不会发送", self.javascript)
        self.assertIn("用户已按甲方规则确认本次发送范围", self.javascript)
        self.assertIn("confirmed_scope_token: state.aiDisclosure.scope_token", self.javascript)

    def test_ai_panel_discloses_quality_mode_and_output_budget(self):
        self.assertIn("质量优先", self.javascript)
        self.assertIn("深度思考", self.javascript)
        self.assertIn("disclosure.reasoning_effort", self.javascript)
        self.assertIn("disclosure.max_output_tokens", self.javascript)
        self.assertIn("disclosure.input_budget_tokens", self.javascript)
        self.assertIn("disclosure.estimated_input_tokens", self.javascript)
        self.assertIn("disclosure.candidate_evidence_count", self.javascript)
        self.assertIn("disclosure.omitted_due_input_budget_count", self.javascript)
        self.assertIn("disclosure.truncated_evidence_count", self.javascript)
        self.assertIn("实际发送", self.javascript)
        self.assertIn("因预算省略", self.javascript)
        self.assertIn("正文截取", self.javascript)

    def test_ai_endpoint_is_only_called_by_explicit_generate_action(self):
        self.assertEqual(self.javascript.count('requestJson("/api/report-ai-draft"'), 1)
        self.assertIn("async function generateAiReportDraft()", self.javascript)
        self.assertIn("function applyAiDraftToPreview()", self.javascript)
        self.assertIn("confirmed_external_send: true", self.javascript)
        self.assertIn("confirmation_id: confirmationId", self.javascript)
        self.assertIn("state.aiRequestPending", self.javascript)
        self.assertIn("delete state.aiDisclosure.confirmation_id", self.javascript)
        self.assertIn("els.aiExternalSendConfirm.checked", self.javascript)
        self.assertIn('els.aiGenerateBtn.addEventListener("click", generateAiReportDraft)', self.javascript)
        self.assertIn('els.aiApplyBtn.addEventListener("click", applyAiDraftToPreview)', self.javascript)

    def test_ai_draft_does_not_directly_replace_rule_preview_on_generation(self):
        generate_start = self.javascript.index("async function generateAiReportDraft()")
        apply_start = self.javascript.index("function applyAiDraftToPreview()")
        generate_body = self.javascript[generate_start:apply_start]
        self.assertNotIn(".report-section-editor", generate_body)
        self.assertIn(".report-section-editor", self.javascript[apply_start:])


if __name__ == "__main__":
    unittest.main()
