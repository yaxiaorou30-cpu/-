import json
import unittest

from src.deepseek_report import (
    AI_BATCH_FIELDS,
    DeepSeekReportClient,
    build_ai_report_disclosure,
    build_deepseek_batch_requests,
)


class FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


class DeepSeekBatchingTests(unittest.TestCase):
    @staticmethod
    def reviewed_record(index: int, content: str) -> dict:
        return {
            "title": f"记录 {index}",
            "content": content,
            "source": "测试来源",
            "platform": "测试平台",
            "source_type": "media",
            "pub_time": "2026-09-20T10:00:00",
            "content_category": "社会事件",
            "sentiment_label": "中性",
            "human_review": {
                "reviewed_at": "2026-09-20T11:00:00",
                "note": "保密审核备注不得外发",
            },
            "url": "https://user:secret@example.com/item?token=secret-token",
            "password": "secret-password",
            "cookie": "secret-cookie",
        }

    @staticmethod
    def batch_evidence(payload: dict) -> list[dict]:
        user_prompt = payload["messages"][1]["content"]
        raw = user_prompt.split("本批原始数据如下：\n", 1)[1]
        return json.loads(raw)["evidence"]

    def test_all_reviewed_content_is_split_into_batches_without_omission_or_truncation(self):
        records = [
            self.reviewed_record(index, f"第{index}条开头\n" + "完整正文 " * 500 + f"第{index}条结尾")
            for index in range(1, 7)
        ]

        payloads, scope = build_deepseek_batch_requests(
            records,
            {},
            input_budget_tokens=4_096,
        )

        self.assertGreater(len(payloads), 1)
        sent_by_record = {}
        for payload, estimate in zip(payloads, scope["batch_estimated_input_tokens"]):
            self.assertLessEqual(estimate, 4_096)
            serialized = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("secret-password", serialized)
            self.assertNotIn("secret-cookie", serialized)
            self.assertNotIn("secret-token", serialized)
            self.assertNotIn("保密审核备注不得外发", serialized)
            for item in self.batch_evidence(payload):
                self.assertEqual(tuple(item), AI_BATCH_FIELDS)
                sent_by_record.setdefault(item["reference_id"], []).append(item)

        self.assertEqual(len(sent_by_record), len(records))
        for index, record in enumerate(records, start=1):
            chunks = sorted(sent_by_record[f"R{index}"], key=lambda item: item["chunk_index"])
            self.assertEqual("".join(item["content"] for item in chunks), record["content"])
            self.assertEqual([item["chunk_index"] for item in chunks], list(range(1, len(chunks) + 1)))
            self.assertTrue(all(item["chunk_total"] == len(chunks) for item in chunks))

        self.assertEqual(scope["record_count"], len(records))
        self.assertEqual(scope["sent_record_count"], len(records))
        self.assertEqual(scope["batch_count"], len(payloads))
        self.assertEqual(scope["omitted_due_input_budget_count"], 0)
        self.assertEqual(scope["truncated_evidence_count"], 0)
        self.assertEqual(scope["original_content_chars"], scope["sent_content_chars"])

    def test_batch_prompt_is_open_ended_and_final_prompt_keeps_four_section_interface(self):
        record = self.reviewed_record(1, "完整正文")
        calls = []
        progress_events = []

        def fake_post(_url, *, json: dict, **_kwargs):
            calls.append(json)
            if json.get("response_format") == {"type": "json_object"}:
                content = {
                    "sections": {
                        "summary": "模型摘要",
                        "analysis": "模型分析",
                        "risks": "模型风险判断",
                        "recommendations": "模型建议",
                    }
                }
            else:
                content = "模型自行形成的批次分析"
            return FakeResponse({
                "id": f"response-{len(calls)}",
                "model": "deepseek-v4-pro",
                "system_fingerprint": "fp-test",
                "choices": [{
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": (
                        json_module.dumps(content, ensure_ascii=False)
                        if isinstance(content, dict)
                        else content
                    )},
                }],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            })

        # Avoid shadowing the imported json module in the request_post signature.
        json_module = json
        client = DeepSeekReportClient(
            api_key="deepseek-key-secret",
            request_post=fake_post,
            input_budget_tokens=4_096,
            progress_callback=progress_events.append,
        )

        result = client.generate([record], {}, template_id="event_report")

        self.assertEqual(len(calls), 2)
        batch_prompt = "\n".join(item["content"] for item in calls[0]["messages"])
        self.assertIn("自行判断其中有价值的信息", batch_prompt)
        self.assertIn("不得补充输入中不存在的事实", batch_prompt)
        self.assertNotIn("必须输出以下 JSON 结构", batch_prompt)
        final_prompt = "\n".join(item["content"] for item in calls[-1]["messages"])
        self.assertIn("必须使用以下 JSON 结构", final_prompt)
        self.assertEqual(result["sections"]["summary"], "模型摘要")
        self.assertEqual(result["scope"]["sent_record_count"], 1)
        self.assertEqual(result["scope"]["provider_call_count"], 2)
        self.assertEqual(result["usage"]["total_tokens"], 30)
        self.assertEqual(
            [event["type"] for event in progress_events],
            [
                "ai_plan",
                "ai_batch_start",
                "ai_batch_complete",
                "ai_final_start",
                "ai_complete",
            ],
        )
        self.assertEqual(progress_events[0]["batch_total"], 1)

    def test_disclosure_reports_complete_multi_batch_scope(self):
        records = [
            self.reviewed_record(index, "完整材料 " * 600)
            for index in range(1, 5)
        ]

        disclosure = build_ai_report_disclosure(
            records,
            {},
            configured=True,
            input_budget_tokens=4_096,
        )

        self.assertEqual(disclosure["eligible_record_count"], 4)
        self.assertEqual(disclosure["sent_record_count"], 4)
        self.assertGreater(disclosure["batch_count"], 1)
        self.assertEqual(disclosure["omitted_due_input_budget_count"], 0)
        self.assertEqual(disclosure["truncated_evidence_count"], 0)
        self.assertEqual(disclosure["selection_version"], "complete-reviewed-batches-v1")
        self.assertTrue(disclosure["can_generate"])

    def test_oversized_batch_analyses_are_merged_by_deepseek_before_final_generation(self):
        records = [
            self.reviewed_record(index, "原始材料 " * 500)
            for index in range(1, 4)
        ]
        prompts = []
        progress_events = []

        def fake_post(_url, *, json: dict, **_kwargs):
            prompt = json["messages"][1]["content"]
            prompts.append(prompt)
            if json.get("response_format") == {"type": "json_object"}:
                content = json_module.dumps({
                    "sections": {
                        "summary": "最终摘要",
                        "analysis": "最终分析",
                        "risks": "最终风险",
                        "recommendations": "最终建议",
                    }
                }, ensure_ascii=False)
            elif "待合并的分析材料如下" in prompt:
                content = "DeepSeek 自行形成的合并分析"
            else:
                content = "批次分析" * 900
            return FakeResponse({
                "id": f"response-{len(prompts)}",
                "model": "deepseek-v4-pro",
                "system_fingerprint": "fp-test",
                "choices": [{
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": content},
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            })

        json_module = json
        client = DeepSeekReportClient(
            api_key="deepseek-key-secret",
            request_post=fake_post,
            input_budget_tokens=4_096,
            progress_callback=progress_events.append,
        )

        result = client.generate(records, {})

        self.assertTrue(any("待合并的分析材料如下" in prompt for prompt in prompts))
        self.assertIn("全部批次分析材料如下", prompts[-1])
        self.assertEqual(result["sections"]["summary"], "最终摘要")
        self.assertEqual(result["scope"]["provider_call_count"], len(prompts))
        self.assertIn("ai_merge_start", [event["type"] for event in progress_events])


if __name__ == "__main__":
    unittest.main()
