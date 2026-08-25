import unittest

from src.quality_checks import build_collection_assessment


class SourceGroupQualityCheckTests(unittest.TestCase):
    @staticmethod
    def _record(source_group="public_news", platform="Bing 新闻"):
        return {
            "title": "公开网页检索结果",
            "content": "已经成功取得、可以核对的公开网页正文。",
            "body_fetch_status": "success",
            "url": "https://example.com/article",
            "pub_time": "2026-08-25T12:00:00",
            "time_basis": "published_time",
            "platform": platform,
            "source_group": source_group,
            "data_type": "real",
        }

    def test_public_news_ignores_inactive_social_and_stable_selections(self):
        assessment = build_collection_assessment(
            [self._record()],
            {
                "min_real_results": 1,
                "source_strategy": "public_news",
                "active_source_groups": ["public_news"],
                "social_platforms": ["微博", "B站"],
                "stable_sources": ["政府官网"],
            },
        )

        check_ids = {item["id"] for item in assessment["checks"]}
        self.assertNotIn("social_platforms", check_ids)
        self.assertNotIn("government_sources", check_ids)
        self.assertEqual(assessment["status_code"], "ready_for_review")

    def test_all_strategy_keeps_social_and_stable_checks(self):
        assessment = build_collection_assessment(
            [self._record()],
            {
                "min_real_results": 1,
                "source_strategy": "all",
                "active_source_groups": ["stable", "public_news", "social"],
                "social_platforms": ["微博"],
                "stable_sources": ["政府官网"],
            },
        )

        checks = {item["id"]: item for item in assessment["checks"]}
        self.assertEqual(checks["social_platforms"]["status"], "fail")
        self.assertEqual(checks["government_sources"]["status"], "warning")
        self.assertEqual(assessment["status_code"], "collection_failed")

    def test_social_only_keeps_social_check(self):
        assessment = build_collection_assessment(
            [self._record(source_group="social", platform="B站")],
            {
                "min_real_results": 1,
                "source_strategy": "social",
                "active_source_groups": ["social"],
                "social_platforms": ["微博"],
                "stable_sources": ["政府官网"],
            },
        )

        checks = {item["id"]: item for item in assessment["checks"]}
        self.assertEqual(checks["social_platforms"]["status"], "fail")
        self.assertNotIn("government_sources", checks)
        self.assertEqual(assessment["status_code"], "collection_failed")

    def test_stable_only_keeps_government_check(self):
        assessment = build_collection_assessment(
            [self._record(source_group="stable", platform="政府官网")],
            {
                "min_real_results": 1,
                "source_strategy": "stable",
                "active_source_groups": ["stable"],
                "social_platforms": ["微博"],
                "stable_sources": ["政府官网"],
            },
        )

        checks = {item["id"]: item for item in assessment["checks"]}
        self.assertNotIn("social_platforms", checks)
        self.assertEqual(checks["government_sources"]["status"], "pass")

    def test_source_strategy_is_used_when_active_groups_are_missing(self):
        expectations = {
            "public_news": (False, False),
            "stable": (False, True),
            "social": (True, False),
            "all": (True, True),
            "stable_first": (True, True),
            "public": (False, True),
        }
        for strategy, (has_social, has_stable) in expectations.items():
            with self.subTest(strategy=strategy):
                assessment = build_collection_assessment(
                    [self._record()],
                    {
                        "min_real_results": 1,
                        "source_strategy": strategy,
                        "social_platforms": ["微博"],
                        "stable_sources": ["政府官网"],
                    },
                )
                check_ids = {item["id"] for item in assessment["checks"]}
                self.assertEqual("social_platforms" in check_ids, has_social)
                self.assertEqual("government_sources" in check_ids, has_stable)

    def test_invalid_active_groups_fall_back_to_source_strategy(self):
        assessment = build_collection_assessment(
            [self._record()],
            {
                "min_real_results": 1,
                "source_strategy": "all",
                "active_source_groups": ["public_news", "typo"],
                "social_platforms": ["微博"],
                "stable_sources": ["政府官网"],
            },
        )

        check_ids = {item["id"] for item in assessment["checks"]}
        self.assertIn("social_platforms", check_ids)
        self.assertIn("government_sources", check_ids)

    def test_task_payload_strategy_is_used_for_older_metadata(self):
        assessment = build_collection_assessment(
            [self._record()],
            {
                "min_real_results": 1,
                "task_payload": {"source_strategy": "public_news"},
                "social_platforms": ["微博"],
                "stable_sources": ["政府官网"],
            },
        )

        check_ids = {item["id"] for item in assessment["checks"]}
        self.assertNotIn("social_platforms", check_ids)
        self.assertNotIn("government_sources", check_ids)

    def test_valid_active_groups_override_conflicting_strategy(self):
        assessment = build_collection_assessment(
            [self._record()],
            {
                "min_real_results": 1,
                "source_strategy": "all",
                "active_source_groups": ["public_news"],
                "social_platforms": ["微博"],
                "stable_sources": ["政府官网"],
            },
        )

        check_ids = {item["id"] for item in assessment["checks"]}
        self.assertNotIn("social_platforms", check_ids)
        self.assertNotIn("government_sources", check_ids)

    def test_legacy_metadata_without_active_groups_keeps_existing_checks(self):
        assessment = build_collection_assessment(
            [self._record(source_group="social", platform="微博")],
            {
                "min_real_results": 1,
                "social_platforms": ["微博"],
                "stable_sources": ["政府官网"],
            },
        )

        check_ids = {item["id"] for item in assessment["checks"]}
        self.assertIn("social_platforms", check_ids)
        self.assertIn("government_sources", check_ids)


if __name__ == "__main__":
    unittest.main()
