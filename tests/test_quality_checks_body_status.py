import unittest

from src.quality_checks import build_collection_assessment


class BodyFetchQualityCheckTests(unittest.TestCase):
    @staticmethod
    def _content_check(assessment):
        return next(
            item for item in assessment["checks"] if item["id"] == "content_complete"
        )

    def test_failed_body_is_unavailable_even_when_search_summary_exists(self):
        assessment = build_collection_assessment(
            [{
                "title": "搜索结果标题",
                "content": "搜索接口返回的摘要不能代替网页正文。",
                "body_fetch_status": "failed",
                "url": "https://example.com/article",
                "pub_time": "2026-08-25",
                "time_basis": "published_date",
                "platform": "Bing 新闻",
                "source_group": "public_news",
                "data_type": "real",
            }],
            {"min_real_results": 1},
        )

        self.assertEqual(assessment["statistics"]["empty_content_count"], 1)
        check = self._content_check(assessment)
        self.assertEqual(check["status"], "fail")
        self.assertEqual(check["value"], "0/1 条有内容")
        self.assertIn("正文获取失败", check["detail"])

    def test_successful_body_remains_available(self):
        assessment = build_collection_assessment(
            [{
                "title": "网页标题",
                "content": "已经成功提取的网页正文。",
                "body_fetch_status": "success",
                "url": "https://example.com/article",
                "pub_time": "2026-08-25",
                "time_basis": "published_date",
                "platform": "Bing 新闻",
                "source_group": "public_news",
                "data_type": "real",
            }],
            {"min_real_results": 1},
        )

        self.assertEqual(assessment["statistics"]["empty_content_count"], 0)
        self.assertEqual(self._content_check(assessment)["status"], "pass")


if __name__ == "__main__":
    unittest.main()
