import unittest

from src.summary_builder import build_evidence_summary
from web_app import select_summary_records


class EvidenceSummaryTests(unittest.TestCase):
    def _record(self, *, platform="微博", suffix="1", sentiment="中性"):
        return {
            "title": f"官方公布菲尔兹奖相关结果{suffix}",
            "content": "页面介绍获奖结果和研究背景。多位网友留言表示祝贺。",
            "url": f"https://example.com/{suffix}",
            "pub_time": "2026-07-31T12:00:00",
            "time_basis": "published_time",
            "source": f"示例来源{suffix}",
            "platform": platform,
            "source_type": "public",
            "source_group": "social",
            "data_type": "real",
            "content_category": "科技与教育",
            "sentiment_label": sentiment,
            "human_review": {
                "content_category": "科技与教育",
                "sentiment_label": sentiment,
                "reviewed_at": "2026-07-31T21:00:00",
            },
        }

    def test_single_record_summary_has_clickable_evidence_mapping(self):
        summary = build_evidence_summary(
            [self._record()],
            {"topic": "菲尔兹奖", "keywords": ["菲尔兹奖"]},
            scope_type="record",
            scope_label="单条线索",
        )

        self.assertEqual(summary["scope"]["record_count"], 1)
        self.assertEqual(summary["key_points"][0]["evidence_ids"], ["S1"])
        self.assertEqual(summary["evidence"][0]["url"], "https://example.com/1")
        self.assertTrue(summary["grounding"]["all_citations_valid"])
        self.assertIn("机器生成草稿", summary["notice"])

    def test_collection_summary_only_cites_available_samples(self):
        summary = build_evidence_summary(
            [
                self._record(platform="微博", suffix="1", sentiment="正面"),
                self._record(platform="小红书", suffix="2", sentiment="中性"),
            ],
            {"topic": "菲尔兹奖", "keywords": ["菲尔兹奖"]},
            scope_type="filtered",
            scope_label="当前筛选结果",
        )

        self.assertIn("微博1条", summary["overview"])
        self.assertIn("小红书1条", summary["overview"])
        self.assertTrue(summary["key_points"])
        cited = set(summary["grounding"]["cited_ids"])
        available = set(summary["grounding"]["available_ids"])
        self.assertTrue(cited)
        self.assertTrue(cited <= available)
        self.assertTrue(summary["review"]["labels_confirmed_for_all"])

    def test_source_scope_selects_all_records_from_one_platform(self):
        data = [
            self._record(platform="微博", suffix="1"),
            self._record(platform="微博", suffix="2"),
            self._record(platform="小红书", suffix="3"),
        ]

        selected, scope = select_summary_records(data, {
            "scope_type": "source",
            "source": "微博",
        })

        self.assertEqual(len(selected), 2)
        self.assertEqual(scope["label"], "来源“微博”")
        self.assertEqual(scope["matched_total"], 2)

    def test_record_scope_rejects_stale_index(self):
        with self.assertRaisesRegex(ValueError, "不存在或已经变化"):
            select_summary_records([self._record()], {
                "scope_type": "record",
                "record_index": 3,
            })

    def test_pending_body_review_cannot_be_used_for_summary(self):
        record = {
            **self._record(),
            "body_fetch_status": "failed",
        }

        with self.assertRaisesRegex(ValueError, "正文获取失败"):
            select_summary_records([record], {
                "scope_type": "record",
                "record_index": 0,
            })


if __name__ == "__main__":
    unittest.main()
