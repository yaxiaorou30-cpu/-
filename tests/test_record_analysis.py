import json
import unittest
from pathlib import Path

from src.analyzer import Analyzer
from src.orchestrator import build_report_preview
from src.preprocessor import Preprocessor
from src.record_analysis import (
    annotate_record,
    apply_human_review,
    body_review_is_pending,
    classify_content,
)
from web_app import build_reviewed_records, filter_report_records, review_is_complete


class RecordAnalysisTests(unittest.TestCase):
    def _science_record(self):
        return {
            "title": "中国数学家获得菲尔兹奖",
            "content": "高校科研团队介绍数学研究成果，网友表达祝贺。",
            "url": "https://example.com/science",
            "pub_time": "2026-07-31T12:00:00",
            "time_basis": "published_time",
            "source": "科普作者",
            "platform": "微博",
            "source_type": "public",
            "source_group": "social",
            "data_type": "real",
        }

    def test_machine_analysis_is_attached_without_claiming_human_review(self):
        annotated = annotate_record(self._science_record())

        self.assertEqual(annotated["machine_content_category"], "科技与教育")
        self.assertEqual(annotated["content_category"], "科技与教育")
        self.assertEqual(annotated["content_category_source"], "machine")
        self.assertIn(annotated["sentiment_label"], {"正面", "中性", "负面"})
        self.assertEqual(annotated["sentiment_source"], "machine")
        self.assertTrue(annotated["analysis_reference_only"])
        self.assertNotIn("human_review", annotated)

    def test_human_review_preserves_machine_result_and_becomes_effective(self):
        reviewed = apply_human_review(
            self._science_record(),
            content_category="社会民生",
            sentiment_label="负面",
            note="原文主要讨论教育资源争议",
            reviewer="民警甲",
            reviewed_at="2026-07-31T21:00:00",
        )

        self.assertEqual(reviewed["machine_content_category"], "科技与教育")
        self.assertEqual(reviewed["content_category"], "社会民生")
        self.assertEqual(reviewed["sentiment_label"], "负面")
        self.assertEqual(reviewed["content_category_source"], "human_review")
        self.assertEqual(reviewed["sentiment_source"], "human_review")
        self.assertTrue(reviewed["human_review"]["category_changed"])
        self.assertEqual(reviewed["human_review"]["reviewed_by"], "民警甲")

    def test_body_fetch_failure_requires_explicit_original_content_check(self):
        record = {
            **self._science_record(),
            "body_fetch_status": "failed",
        }

        with self.assertRaisesRegex(ValueError, "正文获取失败"):
            apply_human_review(
                record,
                content_category="科技与教育",
                sentiment_label="正面",
                reviewer="民警甲",
                reviewed_at="2026-07-31T21:00:00",
            )

        reviewed = apply_human_review(
            record,
            content_category="科技与教育",
            sentiment_label="正面",
            reviewer="民警甲",
            reviewed_at="2026-07-31T21:00:00",
            body_verified=True,
        )

        self.assertFalse(body_review_is_pending(reviewed))
        self.assertEqual(
            reviewed["body_manual_review"]["reviewed_at"],
            "2026-07-31T21:00:00",
        )
        self.assertEqual(reviewed["body_manual_review"]["reviewed_by"], "民警甲")

    def test_unknown_time_with_successful_body_is_not_pending(self):
        record = {
            **self._science_record(),
            "pub_time": "",
            "time_basis": "unknown",
            "body_fetch_status": "success",
        }

        self.assertFalse(body_review_is_pending(record))

    def test_review_merge_cannot_overwrite_source_evidence_fields(self):
        original = [self._science_record(), {**self._science_record(), "url": "https://example.com/other"}]
        reviewed, summary = build_reviewed_records(
            original,
            [
                {
                    "index": 0,
                    "keep": True,
                    "content_category": "社会民生",
                    "sentiment_label": "中性",
                    "note": "人工确认",
                    "url": "https://attacker.invalid/overwrite",
                },
                {
                    "index": 1,
                    "keep": False,
                    "content_category": "其他",
                    "sentiment_label": "中性",
                },
            ],
            reviewer="民警甲",
            reviewed_at="2026-07-31T21:00:00",
        )

        self.assertEqual(len(reviewed), 1)
        self.assertEqual(reviewed[0]["url"], "https://example.com/science")
        self.assertEqual(reviewed[0]["content_category"], "社会民生")
        self.assertEqual(summary["removed_total"], 1)
        self.assertEqual(summary["category_changed_count"], 1)
        self.assertTrue(summary["labels_confirmed"])

    def test_old_checkbox_only_review_does_not_unlock_report(self):
        data = [self._science_record()]
        self.assertFalse(review_is_complete(data, {
            "review": {"reviewed_at": "2026-07-31T20:00:00", "kept_total": 1},
        }))
        self.assertTrue(review_is_complete(data, {
            "review": {
                "reviewed_at": "2026-07-31T21:00:00",
                "kept_total": 1,
                "labels_confirmed": True,
            },
        }))

    def test_pending_body_review_does_not_unlock_report(self):
        data = [{**self._science_record(), "body_fetch_status": "failed"}]
        meta = {
            "review": {
                "reviewed_at": "2026-07-31T21:00:00",
                "kept_total": 1,
                "labels_confirmed": True,
            }
        }

        self.assertFalse(review_is_complete(data, meta))

    def test_analyzer_and_report_use_human_confirmed_labels(self):
        reviewed = apply_human_review(
            self._science_record(),
            content_category="社会民生",
            sentiment_label="负面",
            note="人工复核后修正",
            reviewer="民警甲",
            reviewed_at="2026-07-31T21:00:00",
        )
        records = Preprocessor().process([reviewed])
        context = Analyzer().analyze(records)
        self.assertEqual(context.content_category_dist, {"社会民生": 1})
        self.assertEqual(context.sentiment_ratio, {"正面": 0.0, "中性": 0.0, "负面": 1.0})
        self.assertEqual(context.human_reviewed_count, 1)

        tmp_path = Path("data") / "_test_reviewed_analysis"
        tmp_path.mkdir(parents=True, exist_ok=True)
        data_path = tmp_path / "latest_news.json"
        meta_path = tmp_path / "latest_news_meta.json"
        data_path.write_text(json.dumps([reviewed], ensure_ascii=False), encoding="utf-8")
        meta_path.write_text(json.dumps({
            "topic": "菲尔兹奖讨论",
            "keywords": ["菲尔兹奖"],
            "social_platforms": ["微博"],
            "review": {"reviewed_at": "2026-07-31T21:00:00", "kept_total": 1, "labels_confirmed": True},
        }, ensure_ascii=False), encoding="utf-8")

        preview = build_report_preview(str(data_path), "event_report")
        section_text = "\n".join(section["content"] for section in preview["sections"])
        self.assertEqual(preview["analysis"]["content_category_dist"], {"社会民生": 1})
        self.assertEqual(preview["analysis"]["sentiment_ratio"]["负面"], 1.0)
        self.assertIn("社会民生1条", section_text)
        self.assertIn("负向100%", section_text)
        self.assertEqual(preview["key_samples"][0]["review_note"], "人工复核后修正")

    def test_content_classifier_has_safe_fallback(self):
        self.assertEqual(classify_content({"title": "无明显主题词"})["category"], "其他")

    def test_report_scope_uses_review_filters_without_mutating_saved_data(self):
        original = [
            apply_human_review(
                self._science_record(),
                content_category="科技与教育",
                sentiment_label="正面",
                reviewed_at="2026-07-31T21:00:00",
            ),
            apply_human_review(
                {
                    **self._science_record(),
                    "title": "教育资源争议引发批评",
                    "url": "https://example.com/negative",
                    "platform": "小红书",
                },
                content_category="社会民生",
                sentiment_label="负面",
                reviewed_at="2026-07-31T21:00:00",
            ),
        ]

        scoped, summary = filter_report_records(original, {
            "source": "小红书",
            "category": "社会民生",
            "sentiment": "负面",
        })

        self.assertEqual(len(scoped), 1)
        self.assertEqual(scoped[0]["url"], "https://example.com/negative")
        self.assertEqual(summary["matched_total"], 1)
        self.assertEqual(summary["original_total"], 2)
        self.assertTrue(summary["active"])
        self.assertEqual(len(original), 2)

    def test_report_scope_rejects_empty_result(self):
        with self.assertRaisesRegex(ValueError, "没有匹配数据"):
            filter_report_records([self._science_record()], {"sentiment": "负面"})

    def test_report_scope_filters_by_completed_body_review_status(self):
        checked = {
            **self._science_record(),
            "url": "https://example.com/checked",
            "body_fetch_status": "failed",
            "body_manual_review": {
                "reviewed_at": "2026-07-31T21:00:00",
                "reviewed_by": "民警甲",
            },
        }
        normal = {
            **self._science_record(),
            "url": "https://example.com/normal",
            "body_fetch_status": "success",
        }

        scoped, summary = filter_report_records(
            [checked, normal],
            {"review_status": "checked"},
        )

        self.assertEqual([record["url"] for record in scoped], [checked["url"]])
        self.assertTrue(summary["active"])
        self.assertEqual(summary["filters"]["review_status"], "checked")


if __name__ == "__main__":
    unittest.main()
