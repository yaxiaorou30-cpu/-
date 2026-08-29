import json
import unittest

from src.social_browser import (
    extract_article_from_html,
    extract_tieba_detail_from_html,
    extract_weibo_detail_from_payload,
    extract_xiaohongshu_detail_from_html,
)


class SocialFullContentTests(unittest.TestCase):
    def test_weibo_detail_preserves_complete_long_text(self):
        full_content = "微博完整正文。" * 700

        detail = extract_weibo_detail_from_payload({
            "longText": {"longTextContent": full_content},
        })

        self.assertGreater(len(full_content), 4000)
        self.assertEqual(detail["content"], full_content)

    def test_xiaohongshu_extracted_json_preserves_complete_long_text(self):
        full_content = "小红书完整正文。" * 600
        payload = json.dumps(
            {"title": "长笔记", "content": full_content},
            ensure_ascii=False,
        )
        html = (
            '<script id="codex-extracted-xhs-detail" type="application/json">'
            f"{payload}</script>"
        )

        detail = extract_xiaohongshu_detail_from_html(html)

        self.assertGreater(len(full_content), 4000)
        self.assertEqual(detail["content"], full_content)

    def test_xiaohongshu_dom_preserves_complete_long_text(self):
        full_content = "小红书页面正文。" * 600
        html = (
            '<main id="noteContainer">'
            '<div id="detail-title">长笔记</div>'
            f'<div id="detail-desc">{full_content}</div>'
            "</main>"
        )

        detail = extract_xiaohongshu_detail_from_html(html)

        self.assertGreater(len(full_content), 4000)
        self.assertEqual(detail["content"], full_content)

    def test_article_parser_preserves_complete_long_text(self):
        full_content = "通用网页完整正文。" * 600
        html = f"<html><body><article>{full_content}</article></body></html>"

        detail = extract_article_from_html(html)

        self.assertGreater(len(full_content), 4000)
        self.assertEqual(detail["content"], full_content)

    def test_tieba_detail_preserves_complete_main_post(self):
        full_content = "贴吧主贴完整正文。" * 600
        html = f'<div class="pb-content-wrap">{full_content}</div>'

        detail = extract_tieba_detail_from_html(html)

        self.assertGreater(len(full_content), 4000)
        self.assertEqual(detail["content"], full_content)
        self.assertEqual(detail["discussion_samples"][0]["content"], full_content)

    def test_tieba_discussion_samples_preserve_complete_posts_and_comments(self):
        full_post = "贴吧帖子完整内容。" * 600
        full_comment = "贴吧评论完整内容。" * 600
        html = (
            f'<div class="pb-content-wrap">{full_post}</div>'
            '<div class="pb-lzl-item">'
            f'<div class="comment-content">{full_comment}</div>'
            "</div>"
        )

        detail = extract_tieba_detail_from_html(html)

        self.assertGreater(len(full_post), 4000)
        self.assertGreater(len(full_comment), 4000)
        self.assertEqual(detail["discussion_samples"][0]["content"], full_post)
        self.assertEqual(detail["discussion_samples"][1]["content"], full_comment)

    def test_tieba_discussion_sample_limit_remains_ten(self):
        posts = [f"第{index}条帖子内容足够长用于解析" for index in range(12)]
        html = "".join(
            f'<div class="pb-content-wrap">{content}</div>' for content in posts
        )

        detail = extract_tieba_detail_from_html(html)

        self.assertEqual(len(detail["discussion_samples"]), 10)
        self.assertEqual(
            [item["content"] for item in detail["discussion_samples"]],
            posts[:10],
        )


if __name__ == "__main__":
    unittest.main()
