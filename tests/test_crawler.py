import json
import inspect
import socket
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from src.analyzer import Analyzer
from src.crawler import (
    NewsCrawler as ProductionNewsCrawler,
    PLATFORM_LIST,
    STABLE_CHANNELS,
    STABLE_SOURCE_REGISTRY,
    crawl_and_save,
)
from src.social_browser import (
    extract_douyin_items_from_api_payload,
    SOCIAL_PLATFORM_ADAPTERS,
    extract_article_from_html,
    extract_search_items_from_html,
    extract_tieba_detail_from_html,
    extract_weibo_detail_from_payload,
    extract_xiaohongshu_detail_from_html,
    extract_xiaohongshu_items_from_api_payload,
)
from src.preprocessor import Preprocessor
from src.source_policy import AUTHORIZED_SESSION_ACCESS_MODE, SourceAccessPolicy
from tests.helpers import AllowAllSourcePolicy


class NewsCrawler(ProductionNewsCrawler):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("source_policy", AllowAllSourcePolicy())
        kwargs.setdefault("use_external_social_adapters", False)
        super().__init__(*args, **kwargs)


class CrawlerParsingTests(unittest.TestCase):
    def setUp(self):
        self.crawler = NewsCrawler()

    @staticmethod
    def _bing_news_rss_fixture():
        return """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0"
             xmlns:News="https://www.bing.com/news/search?q=test&amp;format=RSS">
          <channel>
            <title>Bing News Search</title>
            <link>https://www.bing.com/news/search?q=test</link>
            <item>
              <title>第一条公开新闻</title>
              <link>https://news.example.com/a?id=1&amp;from=rss</link>
              <description><![CDATA[<p>第一条新闻的公开摘要。</p>]]></description>
              <pubDate>Sat, 22 Aug 2026 12:10:11 GMT</pubDate>
              <News:Source>示例日报</News:Source>
            </item>
            <item>
              <title>第二条公开新闻</title>
              <link>https://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;tid=abc&amp;url=https%3A%2F%2Fother.example.org%2Fb%3Fid%3D2&amp;c=1&amp;mkt=zh-cn</link>
              <description><![CDATA[第二条新闻的公开摘要。]]></description>
              <pubDate>Sat, 22 Aug 2026 11:00:00 GMT</pubDate>
              <News:Source>另一家媒体</News:Source>
            </item>
          </channel>
        </rss>"""

    def test_bing_news_rss_request_uses_keyword_region_and_rss_format(self):
        requests = self.crawler._build_public_news_source_requests(
            keyword="跨来源检索",
            province="天津市",
            city=None,
        )

        self.assertEqual(len(requests), 2)
        request = next(item for item in requests if item["parser"] == "bing_news_rss")
        query = parse_qs(urlparse(request["url"]).query)
        self.assertEqual(query["q"], ["跨来源检索 天津市"])
        self.assertEqual(query["qft"], ['sortbydate="1"'])
        self.assertEqual(query["format"], ["RSS"])
        self.assertEqual(request["source_group"], "public_news")
        self.assertEqual(request["parser"], "bing_news_rss")
        self.assertEqual(request["channel"], "Bing News RSS")
        self.assertEqual(request["platform"], "Bing 新闻")
        self.assertNotIn("setlang", query)
        self.assertNotIn("mkt", query)
        self.assertNotIn("cc", query)

        baidu = next(
            item for item in requests if item["parser"] == "baidu_qianfan_web_search"
        )
        self.assertEqual(baidu["channel"], "百度网页搜索")
        self.assertEqual(baidu["platform"], "百度网页")
        self.assertEqual(baidu["source_group"], "public_news")
        self.assertEqual(baidu["query"], "跨来源检索 天津市")

    def test_bing_news_rss_parser_returns_distinct_original_article_urls(self):
        previous_parser = self.crawler._active_parser_hint
        self.crawler._active_parser_hint = "bing_news_rss"
        try:
            items = self.crawler._parse_results(
                "Bing 新闻",
                self._bing_news_rss_fixture(),
                "公开新闻",
                "Bing News RSS",
                "https://www.bing.com/news/search?q=test&format=RSS",
            )
        finally:
            self.crawler._active_parser_hint = previous_parser

        self.assertEqual(len(items), 2)
        self.assertEqual(
            {item["url"] for item in items},
            {
                "https://news.example.com/a?id=1&from=rss",
                "https://other.example.org/b?id=2",
            },
        )
        self.assertTrue(all("bing.com/news/apiclick" not in item["url"] for item in items))
        self.assertEqual(items[0]["source"], "示例日报")
        self.assertEqual(items[0]["content"], "第一条新闻的公开摘要。")
        self.assertEqual(items[0]["pub_time"], "Sat, 22 Aug 2026 12:10:11 GMT")
        self.assertTrue(all(item["search_origin"] == "bing_news_rss" for item in items))

    def test_bing_candidates_with_same_summary_are_enriched_before_body_dedup(self):
        rss = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0"><channel>
          <item><title>候选一</title><link>https://one.example.com/a</link>
            <description>搜索来源返回的相同摘要</description></item>
          <item><title>候选二</title><link>https://two.example.com/b</link>
            <description>搜索来源返回的相同摘要</description></item>
        </channel></rss>"""

        items = self.crawler._parse_bing_news_rss(
            rss,
            keyword="公开信息",
            platform="Bing 新闻",
            channel="Bing News RSS",
        )

        self.assertEqual(len(items), 2)

    def test_bing_news_rss_collection_enriches_each_original_article(self):
        fixture = self._bing_news_rss_fixture().replace(
            "第一条新闻的公开摘要。",
            "这是长度超过八十字的公开新闻摘要，用于确认 RSS 已经提供较长摘要时，系统仍然会调用 Scrapling 获取原始文章详情，而不会因为摘要长度足够就跳过强模式。" * 2,
        )
        self.crawler._request_source_html = lambda **kwargs: (
            fixture,
            kwargs["url"],
            None,
        )

        enriched_urls = []

        def record_detail_enrichment(record):
            enriched_urls.append(record["url"])
            record["detail_enriched"] = True
            record["detail_source"] = "scrapling_stealth"

        self.crawler._enrich_with_article_content = record_detail_enrichment
        public_requests = self.crawler._build_public_news_source_requests(
            keyword="公开新闻",
            province=None,
            city=None,
        )
        bing_request = next(
            item for item in public_requests if item["parser"] == "bing_news_rss"
        )
        records, failures = self.crawler._collect_from_source_requests(
            source_requests=[bing_request],
            keyword="公开新闻",
            region="全国",
            collect_level="最小采集",
            start_time=None,
            end_time=None,
            remaining=10,
        )

        self.assertEqual(failures, [])
        self.assertEqual(len(records), 2)
        self.assertTrue(all(item["source_group"] == "public_news" for item in records))
        self.assertTrue(all(item["data_type"] == "real" for item in records))
        self.assertTrue(all(item["search_origin"] == "bing_news_rss" for item in records))
        self.assertTrue(all(item["time_basis"] == "published_time" for item in records))
        self.assertTrue(all(datetime.fromisoformat(item["pub_time"]) for item in records))
        self.assertEqual(set(enriched_urls), {item["url"] for item in records})
        self.assertTrue(all(item["detail_source"] == "scrapling_stealth" for item in records))

    def test_public_news_attempts_every_keyword_and_discovery_source_before_limiting(self):
        calls = []

        def fake_collect(**kwargs):
            request = kwargs["source_requests"][0]
            keyword = kwargs["keyword"]
            calls.append((keyword, request["parser"]))
            return ([{
                "title": f"{keyword}-{request['parser']}",
                "content": "公开网页候选内容",
                "url": f"https://example.com/{len(calls)}",
                "source_group": "public_news",
                "data_type": "real",
            }], [])

        self.crawler._collect_source_requests_safely = fake_collect

        records = self.crawler.crawl(
            ["关键词一", "关键词二"],
            max_results=1,
            collect_level="最小采集",
            source_strategy="public_news",
            min_real_results=0,
        )

        self.assertEqual(
            calls,
            [
                ("关键词一", "bing_news_rss"),
                ("关键词一", "baidu_qianfan_web_search"),
                ("关键词二", "bing_news_rss"),
                ("关键词二", "baidu_qianfan_web_search"),
            ],
        )
        self.assertEqual(len(records), 1)

    def test_public_news_limit_keeps_bing_and_baidu_coverage(self):
        def fake_collect(**kwargs):
            request = kwargs["source_requests"][0]
            if request["parser"] == "bing_news_rss":
                return ([{
                    "title": f"Bing 结果 {index}",
                    "content": f"Bing 公开新闻内容 {index}",
                    "url": f"https://news.example.com/{index}",
                    "platform": "Bing 新闻",
                    "source_group": "public_news",
                    "data_type": "real",
                } for index in range(2)], [])
            return ([{
                "title": "百度网页结果",
                "content": "百度公开网页内容",
                "url": "https://blog.example.com/public-post",
                "platform": "百度网页",
                "source_group": "public_news",
                "data_type": "real",
            }], [])

        self.crawler._collect_source_requests_safely = fake_collect

        records = self.crawler.crawl(
            ["公开信息"],
            max_results=2,
            collect_level="最小采集",
            source_strategy="public_news",
            min_real_results=0,
        )

        self.assertEqual(len(records), 2)
        self.assertEqual(
            {item["platform"] for item in records},
            {"Bing 新闻", "百度网页"},
        )

    def test_baidu_qianfan_results_use_common_article_enrichment_chain(self):
        calls = []

        class FakeBaiduAdapter:
            def search(self, query, *, top_k, keyword):
                calls.append((query, top_k, keyword))
                return SimpleNamespace(
                    error="",
                    items=[{
                        "title": "普通博客公开文章",
                        "content": "搜索接口返回的相关片段",
                        "url": "https://blog.example.com/public-post",
                        "source": "示例博客",
                        "pub_time": "",
                        "search_origin": "baidu_qianfan_web_search",
                        "keyword": keyword,
                    }],
                )

        crawler = NewsCrawler(baidu_web_search_adapter=FakeBaiduAdapter())
        crawler.anti_crawl.delay = lambda *args, **kwargs: None
        enriched_urls = []

        def enrich(record):
            enriched_urls.append(record["url"])
            record["content"] = "正文采集链获得的完整博客正文"
            record["detail_source"] = "scrapling_stealth"

        crawler._enrich_with_article_content = enrich
        request = next(
            item
            for item in crawler._build_public_news_source_requests(
                keyword="普通博客",
                province=None,
                city=None,
            )
            if item["parser"] == "baidu_qianfan_web_search"
        )

        records, failures = crawler._collect_from_source_requests(
            source_requests=[request],
            keyword="普通博客",
            region="全国",
            collect_level="最小采集",
            start_time=None,
            end_time=None,
            remaining=2,
        )

        self.assertEqual(failures, [])
        self.assertEqual(calls, [("普通博客", 2, "普通博客")])
        self.assertEqual(enriched_urls, ["https://blog.example.com/public-post"])
        self.assertEqual(records[0]["content"], "正文采集链获得的完整博客正文")
        self.assertEqual(records[0]["detail_source"], "scrapling_stealth")
        self.assertEqual(records[0]["source_group"], "public_news")

    def test_bing_news_rss_deduplicates_wrappers_for_same_article(self):
        rss = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0"><channel>
          <item><title>短摘要</title>
            <link>https://www.bing.com/news/apiclick.aspx?url=https%3A%2F%2Fnews.example.com%2Fsame</link>
            <description>短</description></item>
          <item><title>完整摘要</title>
            <link>https://www.bing.com/news/apiclick.aspx?ref=two&amp;url=https%3A%2F%2Fnews.example.com%2Fsame</link>
            <description>这是更完整的新闻摘要内容</description></item>
        </channel></rss>"""

        items = self.crawler._parse_bing_news_rss(
            rss,
            keyword="新闻",
            platform="Bing 新闻",
            channel="Bing News RSS",
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://news.example.com/same")
        self.assertEqual(items[0]["content"], "这是更完整的新闻摘要内容")

    def test_bing_news_rss_preserves_publisher_url_query_parameter(self):
        rss = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0"><channel><item>
          <title>带原站跳转参数的新闻</title>
          <link>https://publisher.example/read?url=https%3A%2F%2Fcdn.example%2Fvideo&amp;id=7</link>
          <description>原站链接必须保留</description>
        </item></channel></rss>"""

        items = self.crawler._parse_bing_news_rss(
            rss,
            keyword="新闻",
            platform="Bing 新闻",
            channel="Bing News RSS",
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0]["url"],
            "https://publisher.example/read?url=https%3A%2F%2Fcdn.example%2Fvideo&id=7",
        )

    def test_xml_response_honors_declared_utf8_before_encoding_heuristics(self):
        class FakeResponse:
            content = (
                '<?xml version="1.0" encoding="utf-8"?>'
                '<rss><title>人工智能新闻</title>'
                '<link>https://news.example.com/中文路径</link></rss>'
            ).encode("utf-8")
            headers = {"Content-Type": "application/xml; charset=ISO-8859-1"}
            apparent_encoding = "GB2312"
            encoding = "ISO-8859-1"

        text = self.crawler._decode_response_text(FakeResponse())

        self.assertIn("人工智能新闻", text)
        self.assertIn("/中文路径", text)

    def test_bing_news_rss_rejects_late_doctype_declaration(self):
        rss = (
            '<?xml version="1.0" encoding="utf-8"?>'
            + (" " * 5000)
            + '<!DOCTYPE rss><rss><channel><item>'
            '<title>不应解析</title><link>https://news.example.com/unsafe</link>'
            '</item></channel></rss>'
        )

        items = self.crawler._parse_bing_news_rss(
            rss,
            keyword="新闻",
            platform="Bing 新闻",
            channel="Bing News RSS",
        )

        self.assertEqual(items, [])

    def test_bing_news_rss_skips_malformed_url_without_losing_other_items(self):
        rss = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0"><channel>
          <item><title>坏链接</title><link>http://[invalid</link></item>
          <item><title>有效链接</title><link>https://news.example.com/valid</link></item>
        </channel></rss>"""

        items = self.crawler._parse_bing_news_rss(
            rss,
            keyword="新闻",
            platform="Bing 新闻",
            channel="Bing News RSS",
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://news.example.com/valid")

    def test_custom_date_range_includes_complete_end_date(self):
        start, end = self.crawler._parse_time_range("2026-07-01 至 2026-07-28")

        self.assertEqual(start, datetime(2026, 7, 1))
        self.assertEqual(end, datetime(2026, 7, 28, 23, 59, 59))

    def test_custom_date_range_rejects_reversed_dates(self):
        with self.assertRaisesRegex(ValueError, "结束日期不能早于开始日期"):
            self.crawler._parse_time_range("2026-07-28 至 2026-07-01")

    def test_social_collection_attempts_every_selected_platform_and_balances_results(self):
        platforms = ["微博", "B站", "小红书", "抖音", "百度贴吧"]
        attempts = []

        def fake_collect(**kwargs):
            platform = kwargs["source_requests"][0]["platform"]
            attempts.append(platform)
            records = [
                {
                    "title": f"{platform} 结果 {index}",
                    "content": f"{platform} 测试内容 {index}",
                    "url": f"https://example.com/{platform}/{index}",
                    "platform": platform,
                    "source": platform,
                    "source_group": "social",
                    "source_type": "public",
                    "data_type": "real",
                    "pub_time": "2026-07-28 00:00:00",
                }
                for index in range(10)
            ]
            return records, []

        self.crawler._collect_from_source_requests = fake_collect
        data = self.crawler.crawl(
            ["测试"],
            max_results=10,
            social_platforms=platforms,
            collect_level="最小采集",
            source_strategy="social",
            min_real_results=1,
        )

        self.assertEqual(attempts, platforms)
        self.assertEqual(len(data), 10)
        counts = {platform: 0 for platform in platforms}
        for item in data:
            counts[item["platform"]] += 1
        self.assertEqual(counts, {platform: 2 for platform in platforms})

    def test_extract_douyin_search_api_payload(self):
        payload = {
            "data": [
                {
                    "aweme_info": {
                        "aweme_id": "7525538910311632128",
                        "desc": "警方通报 测试视频",
                        "create_time": 1785000000,
                        "author": {"nickname": "平安测试"},
                        "statistics": {
                            "digg_count": 12,
                            "comment_count": 3,
                            "share_count": 2,
                            "play_count": 100,
                        },
                        "video": {"duration": 15000},
                    }
                }
            ]
        }

        items = extract_douyin_items_from_api_payload(payload)

        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0]["url"],
            "https://www.douyin.com/video/7525538910311632128",
        )
        self.assertEqual(items[0]["author"], "平安测试")
        self.assertEqual(items[0]["like_count"], 12)
        self.assertEqual(items[0]["search_origin"], "douyin_search_api")

    def test_official_listing_filters_by_keyword_and_extracts_date(self):
        html = """
        <ul>
          <li class="comItem"><a href="./202607/one.html">天津警方发布案件通报</a><span>2026-07-21</span></li>
          <li class="comItem"><a href="./202607/two.html">天津市公安局召开工作会议</a><span>2026-07-20</span></li>
        </ul>
        """
        items = self.crawler._parse_results(
            "天津市公安局公安要闻",
            html,
            "案件通报",
            "天津市公安局公安要闻",
            "https://ga.tj.gov.cn/gaxc/gayw/",
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["pub_time"], "2026-07-21")
        self.assertEqual(
            items[0]["url"],
            "https://ga.tj.gov.cn/gaxc/gayw/202607/one.html",
        )

    def test_official_listing_acceptance_mode_ignores_topic_filter_and_marks_probe(self):
        self.crawler._source_acceptance_mode = True
        html = """
        <ul>
          <li class="comItem"><a href="./202607/one.html">天津公安发布出入境通知 2026-07-21</a></li>
        </ul>
        """
        items = self.crawler._parse_results(
            "天津市公安局出入境通知",
            html,
            "完全无关的验收关键词",
            "天津市公安局出入境通知",
            "https://ga.tj.gov.cn/xxfb/tztg/crj1/",
        )
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["acceptance_probe"])
        self.assertEqual(items[0]["pub_time"], "2026-07-21")

    def test_nia_official_source_is_registered_and_parses_relative_article_links(self):
        source = next(
            item
            for item in STABLE_SOURCE_REGISTRY
            if item["name"] == "国家移民管理局移民管理要闻"
        )
        self.assertTrue(source["enabled"])
        self.assertEqual(source["source_region"], "")

        html = """
        <div class="list_bd">
          <ul>
            <li>
              <a href="../../n897453/c1787017/content.html">两名组织他人偷越国（边）境犯罪嫌疑人被遣返回国</a>
              <span>2026-06-15</span>
            </li>
          </ul>
        </div>
        """
        items = self.crawler._parse_results(
            source["name"],
            html,
            "偷越国境",
            source["name"],
            source["url_template"],
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["pub_time"], "2026-06-15")
        self.assertEqual(
            items[0]["url"],
            "https://www.nia.gov.cn/n897453/c1787017/content.html",
        )

    def test_official_source_registry_prioritizes_tianjin_and_removes_unrelated_cities(self):
        enabled_names = [
            item["name"]
            for item in STABLE_SOURCE_REGISTRY
            if item.get("enabled", True)
        ]
        self.assertEqual(
            enabled_names[:4],
            [
                "天津市公安局公安要闻",
                "天津市公安局出入境通知",
                "天津市政府新闻发布会",
                "天津市应急管理局工作动态",
            ],
        )
        self.assertNotIn("北京市公安局警务报道", enabled_names)
        self.assertNotIn("上海市公安局警务报道", enabled_names)

    def test_tianjin_press_listing_extracts_onclick_url_and_ancestor_date(self):
        html = """
        <div class="list-circle-red">
          <div class="list-item clear">
            <span class="list-item-con">
              <a href="javascript:void(0)"
                 onclick="jumpToDetail('./202607/t20260724_7341298.html')">
                天津市政府举行公共安全工作新闻发布会
              </a>
            </span>
            <span class="list-item-date">2026-07-24</span>
          </div>
        </div>
        """
        items = self.crawler._parse_results(
            "天津市政府新闻发布会",
            html,
            "公共安全",
            "天津市政府新闻发布会",
            "https://www.tj.gov.cn/sy/xwfbh/xwfbh_210907/",
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["pub_time"], "2026-07-24")
        self.assertEqual(
            items[0]["url"],
            "https://www.tj.gov.cn/sy/xwfbh/xwfbh_210907/202607/t20260724_7341298.html",
        )

    def test_tianjin_police_listing_rejects_navigation_outside_article_column(self):
        html = """
        <ul>
          <li class="comItem">
            <a href="/gaxc/fxjjsjyjxc/">反邪教警示教育进乡村</a>
          </li>
          <li class="comItem">
            <a href="./202607/t20260724_7341707.html">
              天津市公安局召开公共安全工作会议 2026-07-24
            </a>
          </li>
        </ul>
        """
        items = self.crawler._parse_results(
            "天津市公安局公安要闻",
            html,
            "公共安全",
            "天津市公安局公安要闻",
            "https://ga.tj.gov.cn/gaxc/gayw/",
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["pub_time"], "2026-07-24")
        self.assertIn("/gaxc/gayw/202607/", items[0]["url"])

    def test_all_social_platforms_have_browser_adapter_search_url(self):
        for platform in PLATFORM_LIST:
            with self.subTest(platform=platform):
                self.assertIn(platform, SOCIAL_PLATFORM_ADAPTERS)
                requests = self.crawler._build_social_source_requests(platform, "警方通报", None, None)
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0]["platform"], platform)
                self.assertEqual(requests[0]["source_group"], "social")
                self.assertTrue(requests[0]["url"].startswith("https://"))
                self.assertNotIn("www.baidu.com/s?wd=", requests[0]["url"])

    def test_browser_adapter_extracts_generic_social_items(self):
        note_url = (
            "/explore/6a40acc2000000000f0151b2"
            "?xsec_token=AB-NSag198AbIV6TYDyPkhAZz2oaO5UOH5yIqMrdRIzHk="
            "&xsec_source=pc_search&source=web_explore_feed"
        )
        html = """
        <section class="note-item">
          <a href="{note_url}" title="警方通报相关帖子">警方通报相关帖子</a>
          <span>作者甲</span>
          <p>这是登录后页面里的帖子摘要内容，包含关键词和事件进展。</p>
        </section>
        """.format(note_url=note_url)
        items = extract_search_items_from_html("小红书", html, "https://www.xiaohongshu.com/search_result")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["platform"], "小红书")
        self.assertEqual(items[0]["session_mode"], "browser_session")
        self.assertIn("xsec_token=", items[0]["url"])

    def test_xiaohongshu_search_keeps_note_results_for_keyword(self):
        html = """
        <section class="note-item">
          <a href="/explore/6a40acc2000000000f0151b2?xsec_token=AB-token-one=&xsec_source=pc_search&source=web_explore_feed" title="LOL打法争论被告上法庭">LOL打法争论被告上法庭</a>
          <span>爱吃干炒牛河</span>
          <span>1天前</span>
          <span>620</span>
        </section>
        <section class="note-item">
          <a href="/explore/6a40acc2000000000f0151b3?xsec_token=AB-token-two=&xsec_source=pc_search&source=web_explore_feed" title="这就是联盟玩家的攻击性吗">这就是联盟玩家的攻击性吗</a>
          <span>Kiki and Jinx</span>
          <span>4天前</span>
          <span>860</span>
        </section>
        """
        items = extract_search_items_from_html(
            "小红书",
            html,
            "https://www.xiaohongshu.com/search_result?keyword=lol",
            keyword="lol",
        )
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "LOL打法争论被告上法庭")
        self.assertTrue(all("xsec_source=pc_search" in item["url"] for item in items))

    def test_xiaohongshu_rejects_explore_home_url(self):
        html = """
        <section class="note-item">
          <a href="/explore" title="为什么代入LOL新手，才会觉得人生阶段快乐？">为什么代入LOL新手，才会觉得人生阶段快乐？</a>
          <span>昨天 22:00</span>
        </section>
        """
        items = extract_search_items_from_html(
            "小红书",
            html,
            "https://www.xiaohongshu.com/search_result?keyword=lol",
            keyword="lol",
        )
        self.assertEqual(items, [])

    def test_xiaohongshu_accepts_browser_extracted_note_id(self):
        html = """
        <script id="codex-extracted-social-items" type="application/json">
        [
          {
            "title": "LOL打法争论被告上法庭",
            "content": "LOL打法争论被告上法庭 爱吃干炒牛河 1天前 620",
            "url": "",
            "note_id": "6864abcdef1234567890abcd",
            "xsec_token": "AB-NSag198AbIV6TYDyPkhAZz2oaO5UOH5yIqMrdRIzHk=",
            "xsec_source": "pc_search"
          }
        ]
        </script>
        """
        items = extract_search_items_from_html(
            "小红书",
            html,
            "https://www.xiaohongshu.com/search_result?keyword=lol",
            keyword="lol",
        )
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["url"].startswith("https://www.xiaohongshu.com/explore/6864abcdef1234567890abcd?"))
        self.assertIn("xsec_token=", items[0]["url"])

    def test_xiaohongshu_accepts_pc_search_note_url_with_xsec_params(self):
        note_url = (
            "https://www.xiaohongshu.com/explore/6a40acc2000000000f0151b2"
            "?xsec_token=AB-NSag198AbIV6TYDyPkhAZz2oaO5UOH5yIqMrdRIzHk="
            "&xsec_source=pc_search&source=web_explore_feed"
        )
        html = f"""
        <section class="note-item">
          <a href="{note_url}" title="英雄联盟相关小红书笔记">英雄联盟相关小红书笔记</a>
          <span>刚刚</span>
        </section>
        """
        items = extract_search_items_from_html(
            "小红书",
            html,
            "https://www.xiaohongshu.com/search_result?keyword=英雄联盟",
            keyword="英雄联盟",
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], note_url)

    def test_xiaohongshu_accepts_style_source_urls_from_search_page(self):
        html = """
        <section class="note-item">
          <a href="/explore/6a43a10a000000001003f0d2?xsec_token=AB-style-token=&xsec_source=style&source=web_explore_feed" title="这是三十六计的哪一计">这是三十六计的哪一计</a>
          <span>艾克娃</span>
        </section>
        """
        items = extract_search_items_from_html(
            "小红书",
            html,
            "https://www.xiaohongshu.com/search_result?keyword=英雄联盟",
            keyword="英雄联盟",
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["xhs_source"], "style")
        self.assertEqual(items[0]["search_origin"], "xiaohongshu_dom")

    def test_xiaohongshu_rejects_non_search_source_urls(self):
        html = """
        <section class="note-item">
          <a href="/explore/6a43a10a000000001003f0d2?xsec_token=AB-home-token=&xsec_source=homefeed_recommend&source=web_explore_feed" title="这是三十六计的哪一计">这是三十六计的哪一计</a>
          <span>艾克娃</span>
        </section>
        """
        items = extract_search_items_from_html(
            "小红书",
            html,
            "https://www.xiaohongshu.com/search_result?keyword=英雄联盟",
            keyword="英雄联盟",
        )
        self.assertEqual(items, [])

    def test_xiaohongshu_api_payload_extracts_search_notes(self):
        payload = {
            "success": True,
            "data": {
                "items": [
                    {
                        "id": "6a40acc2000000000f0151b2",
                        "xsec_token": "AB-NSag198AbIV6TYDyPkhAZz2oaO5UOH5yIqMrdRIzHk=",
                        "xsec_source": "pc_search",
                        "note_card": {
                            "display_title": "英雄联盟技能释放练习基础",
                            "desc": "英雄联盟新手练习走位和技能释放",
                            "user": {"nickname": "召唤师甲"},
                            "interact_info": {"liked_count": "620", "comment_count": "12"},
                        },
                    }
                ]
            },
        }
        items = extract_xiaohongshu_items_from_api_payload(
            payload,
            "https://www.xiaohongshu.com/search_result?keyword=英雄联盟",
            keyword="英雄联盟",
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "英雄联盟技能释放练习基础")
        self.assertIn("xsec_token=", items[0]["url"])
        self.assertEqual(items[0]["author"], "召唤师甲")

    def test_xiaohongshu_detail_parser_extracts_note_body(self):
        html = """
        <main id="noteContainer">
          <a href="/user/profile/69388e6e0000000032018776?xsec_source=pc_note">fbdjdkffgj</a>
          <div id="detail-title">找个固定的英雄联盟搭子</div>
          <div id="detail-desc">找一个固定的英雄联盟搭子，我平时大概晚上八点之后开始打，除了射手不怎么玩，其他路都可以，心态很好，打游戏，就是下班之后的放松，不骂人，不开黄腔，反正就是游戏搭子，我声音不好听，介意的可以忽略哈。什么模式也都可以，一般都是娱乐心态，打发打发时间哈。希望你也是喜欢这个游戏，然后玩游戏不摆烂，不骂人就行。互相交流，互相尊重哈！</div>
          <span>编辑于 14小时前 安徽</span>
          <section class="comments">共 24 条评论 这个不应该进入正文</section>
        </main>
        """
        detail = extract_xiaohongshu_detail_from_html(html)
        self.assertEqual(detail["title"], "找个固定的英雄联盟搭子")
        self.assertIn("找一个固定的英雄联盟搭子", detail["content"])
        self.assertNotIn("共 24 条评论", detail["content"])
        self.assertEqual(detail["author"], "fbdjdkffgj")
        self.assertIn("/user/profile/69388e6e0000000032018776", detail["author_url"])

    def test_xiaohongshu_detail_enrichment_updates_search_card_content(self):
        crawler = NewsCrawler()
        crawler.anti_crawl.delay = lambda *args, **kwargs: None
        crawler.set_account("小红书", cookie="a1=fake-cookie; webId=fake-web-id", session_mode="manual_cookie")
        note_url = (
            "https://www.xiaohongshu.com/explore/6a455305000000001c025ad5"
            "?xsec_token=ABHbul12LW1Ma1VymM-gwXp6_-i1_VbFPZqdkQ2w8ONC0%3D"
            "&xsec_source=style&source=web_explore_feed"
        )
        full_content = (
            "找一个固定的英雄联盟搭子，我平时大概晚上八点之后开始打，除了射手不怎么玩，其他路都可以，"
            "心态很好，打游戏，就是下班之后的放松，不骂人，不开黄腔，反正就是游戏搭子，我声音不好听，"
            "介意的可以忽略哈。什么模式也都可以，一般都是娱乐心态，打发打发时间哈。希望你也是喜欢这个游戏，"
            "然后玩游戏不摆烂，不骂人就行。互相交流，互相尊重哈！"
        )
        detail_html = f"""
        <html><body>
          <script id="codex-extracted-xhs-detail" type="application/json">
          {json.dumps({"title": "找个固定的英雄联盟搭子", "content": full_content, "author": "fbdjdkffgj", "author_url": "https://www.xiaohongshu.com/user/profile/69388e6e0000000032018776", "pub_time": "14小时前"}, ensure_ascii=False)}
          </script>
        </body></html>
        """
        crawler._request_source_html = lambda url, channel, platform, source_group, timeout=10: ("<html></html>", url, None)
        crawler._request_browser_html = lambda url, platform, storage_state_text, timeout=10: (detail_html, url, None)
        crawler._probe_social_login = lambda platform: {
            "platform": platform,
            "reachable": True,
            "login_confirmed": True,
            "evidence": "manual cookie test",
            "cookie_used": True,
            "auth_mode": "cookie",
            "session_mode": "manual_cookie",
            "final_url": "",
        }
        crawler._parse_results = lambda platform, html, keyword, channel, base_url: [{
            "title": "找英雄联盟手游搭子",
            "content": "找英雄联盟手游搭子",
            "url": note_url,
            "source": "小红书",
            "platform": "小红书",
            "pub_time": "",
            "collector": "小红书搜索",
            "search_origin": "xiaohongshu_search_api",
            "xhs_source": "style",
        }]
        data = crawler.crawl(
            ["英雄联盟"],
            max_results=1,
            social_platforms=["小红书"],
            collect_level="最小采集",
            source_strategy="social",
            min_real_results=1,
            time_range="更早",
        )
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["url"], note_url)
        self.assertEqual(data[0]["title"], "找个固定的英雄联盟搭子")
        self.assertIn("找一个固定的英雄联盟搭子", data[0]["content"])
        self.assertEqual(data[0]["author"], "fbdjdkffgj")
        self.assertTrue(data[0]["detail_enriched"])
        self.assertEqual(data[0]["detail_source"], "xiaohongshu_detail")

    def test_xiaohongshu_detail_enrichment_ignores_profile_birthday(self):
        crawler = NewsCrawler()
        crawler.anti_crawl.delay = lambda *args, **kwargs: None
        crawler.set_account("小红书", cookie="a1=fake-cookie; webId=fake-web-id", session_mode="manual_cookie")
        detail_html = f"""
        <html><body>
          <script id="codex-extracted-xhs-detail" type="application/json">
          {json.dumps({"title": "小红书详情", "content": "作者资料 男 1995-09-07 处女座 查看个人主页", "author": "tester", "pub_time": "1995-09-07"}, ensure_ascii=False)}
          </script>
        </body></html>
        """
        crawler._request_browser_html = lambda url, platform, storage_state_text, timeout=10: (detail_html, url, None)
        record = {
            "title": "搜索卡片",
            "content": "搜索卡片摘要",
            "url": "https://www.xiaohongshu.com/explore/6a455305000000001c025ad5?xsec_source=style",
            "source": "小红书",
            "platform": "小红书",
            "pub_time": "",
            "time_basis": "unknown",
        }
        crawler._enrich_with_xiaohongshu_detail_content(record)
        self.assertEqual(record["pub_time"], "")
        self.assertEqual(record["time_basis"], "unknown")

    def test_xiaohongshu_footer_links_are_not_saved_as_posts(self):
        html = """
        <footer>
          <a href="https://beian.miit.gov.cn/">小红书_沪ICP备</a>
          <a href="/business-license">小红书_营业执照</a>
          <a href="/security">小红书_沪公网安备</a>
          <a href="/report">举报入口 您可选相应入口，举报网上有害信息</a>
          <a href="/permit">小红书_网络文化经营许可</a>
        </footer>
        """
        direct_items = extract_search_items_from_html(
            "小红书",
            html,
            "https://www.xiaohongshu.com/search_result?keyword=lol",
            keyword="lol",
        )
        parsed_items = self.crawler._parse_results(
            "小红书",
            html,
            "lol",
            "小红书搜索",
            "https://www.xiaohongshu.com/search_result?keyword=lol",
        )
        self.assertEqual(direct_items, [])
        self.assertEqual(parsed_items, [])

    def test_browser_session_records_include_session_mode(self):
        crawler = NewsCrawler()
        crawler.anti_crawl.delay = lambda *args, **kwargs: None
        crawler.set_account(
            "小红书",
            username="tester",
            browser_cookie="a1=fake-cookie",
            browser_session=json.dumps({"cookies": [], "origins": []}, ensure_ascii=False),
            session_mode="browser_session",
        )
        note_url = (
            "https://www.xiaohongshu.com/explore/6a40acc2000000000f0151b2"
            "?xsec_token=AB-NSag198AbIV6TYDyPkhAZz2oaO5UOH5yIqMrdRIzHk="
            "&xsec_source=pc_search&source=web_explore_feed"
        )
        search_html = """
        <section class="note-item">
          <a href="{note_url}" title="警方通报相关帖子">警方通报相关帖子</a>
          <p>这是登录后搜索结果里的帖子摘要内容。</p>
        </section>
        """.format(note_url=note_url)

        crawler._request_browser_html = lambda url, platform, storage_state_text, timeout=10: (search_html, url, None)
        crawler._probe_social_login = lambda platform: {
            "platform": platform,
            "reachable": True,
            "login_confirmed": True,
            "evidence": "browser session test",
            "cookie_used": True,
            "auth_mode": "browser_session",
            "session_mode": "browser_session",
            "final_url": "",
        }
        crawler._enrich_with_browser_article_content = lambda record, platform: None
        crawler._enrich_with_article_content = lambda record: None
        data = crawler.crawl(
            ["警方通报"],
            max_results=1,
            social_platforms=["小红书"],
            collect_level="最小采集",
            source_strategy="social",
            min_real_results=1,
        )
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["platform"], "小红书")
        self.assertEqual(data[0]["source_group"], "social")
        self.assertEqual(data[0]["session_mode"], "browser_session")
        self.assertTrue(data[0]["login_confirmed"])
        self.assertEqual(crawler.last_meta["summary"]["browser_session_record_count"], 1)

    def test_xiaohongshu_manual_cookie_uses_browser_rendering(self):
        crawler = NewsCrawler()
        crawler.set_account("小红书", cookie="a1=fake-cookie; webId=fake-web-id", session_mode="manual_cookie")
        calls = {}

        def fake_browser(url, platform, storage_state_text, timeout=10):
            calls["url"] = url
            calls["platform"] = platform
            calls["storage_state"] = json.loads(storage_state_text)
            return "<section class='note-item'><a href='/explore/abc123'>警方通报相关帖子</a></section>", url, None

        crawler._request_browser_html = fake_browser
        crawler._request_html = lambda *args, **kwargs: ("", args[0], "ordinary request should not be used")
        html, final_url, error = crawler._request_source_html(
            url="https://www.xiaohongshu.com/search_result?keyword=test",
            channel="小红书搜索",
            platform="小红书",
            source_group="social",
            timeout=10,
        )
        cookie_names = {cookie["name"] for cookie in calls["storage_state"]["cookies"]}
        self.assertIsNone(error)
        self.assertIn("note-item", html)
        self.assertEqual(calls["platform"], "小红书")
        self.assertIn("a1", cookie_names)
        self.assertIn("webId", cookie_names)

    def test_xiaohongshu_enrichment_does_not_replace_note_url_with_explore_home(self):
        crawler = NewsCrawler()
        crawler.anti_crawl.delay = lambda *args, **kwargs: None
        note_url = (
            "https://www.xiaohongshu.com/explore/6864abcdef1234567890abcd"
            "?xsec_token=AB-NSag198AbIV6TYDyPkhAZz2oaO5UOH5yIqMrdRIzHk="
            "&xsec_source=pc_search&source=web_explore_feed"
        )
        crawler._request_source_html = lambda url, channel, platform, source_group, timeout=10: ("<html></html>", url, None)
        crawler._parse_results = lambda platform, html, keyword, channel, base_url: [{
            "title": "LOL打法争论被告上法庭",
            "content": "LOL打法争论",
            "url": note_url,
            "source": "小红书",
            "platform": "小红书",
            "pub_time": "",
            "collector": "小红书搜索",
        }]
        crawler._enrich_with_browser_article_content = lambda record, platform: record.update({
            "url": "https://www.xiaohongshu.com/explore",
            "content": record["content"],
        })
        crawler._enrich_with_article_content = lambda record: None
        data = crawler.crawl(
            ["lol"],
            max_results=1,
            social_platforms=["小红书"],
            collect_level="最小采集",
            source_strategy="social",
            min_real_results=1,
        )
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["url"], note_url)

    def test_xiaohongshu_bare_note_url_is_filtered_before_save(self):
        crawler = NewsCrawler()
        crawler.anti_crawl.delay = lambda *args, **kwargs: None
        crawler._request_source_html = lambda url, channel, platform, source_group, timeout=10: ("<html></html>", url, None)
        crawler._parse_results = lambda platform, html, keyword, channel, base_url: [{
            "title": "LOL打法争论被告上法庭",
            "content": "LOL打法争论",
            "url": "https://www.xiaohongshu.com/explore/6864abcdef1234567890abcd",
            "source": "小红书",
            "platform": "小红书",
            "pub_time": "",
            "collector": "小红书搜索",
        }]
        data = crawler.crawl(
            ["lol"],
            max_results=1,
            social_platforms=["小红书"],
            collect_level="最小采集",
            source_strategy="social",
            min_real_results=1,
        )
        self.assertEqual(data, [])
        failures = crawler.last_meta.get("failures", [])
        self.assertTrue(any("invalid social url" in item.get("error", "") for item in failures))

    def test_xiaohongshu_style_source_url_is_saved_with_source_marker(self):
        crawler = NewsCrawler()
        crawler.anti_crawl.delay = lambda *args, **kwargs: None
        crawler._request_source_html = lambda url, channel, platform, source_group, timeout=10: ("<html></html>", url, None)
        crawler._parse_results = lambda platform, html, keyword, channel, base_url: [{
            "title": "这是三十六计的哪一计",
            "content": "这是三十六计的哪一计 艾克娃 1天前 493",
            "url": (
                "https://www.xiaohongshu.com/explore/6a43a10a000000001003f0d2"
                "?xsec_token=AB-style-token=&xsec_source=style&source=web_explore_feed"
            ),
            "source": "小红书",
            "platform": "小红书",
            "pub_time": "",
            "collector": "小红书搜索",
            "search_origin": "xiaohongshu_search_api",
            "xhs_source": "style",
            "search_rank": 1,
        }]
        data = crawler.crawl(
            ["英雄联盟"],
            max_results=1,
            social_platforms=["小红书"],
            collect_level="最小采集",
            source_strategy="social",
            min_real_results=1,
        )
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["xhs_source"], "style")
        self.assertEqual(data[0]["search_origin"], "xiaohongshu_search_api")

    def test_parse_baidu_news_result(self):
        html = """
        <html><body>
          <div class="result">
            <h3><a href="/link?url=https%3A%2F%2Fnews.example.com%2Fa">警方通报突发事件最新进展</a></h3>
            <div class="c-abstract">警方发布情况通报，事件正在进一步调查。</div>
            <span class="c-color-gray">新华社 2026-07-01 10:30</span>
          </div>
        </body></html>
        """
        items = self.crawler._parse_results("微博", html, "警方通报", "百度新闻", "https://www.baidu.com/s")
        self.assertEqual(len(items), 1)
        record = self.crawler._normalize_record(items[0], "微博", "警方通报", "全国", "百度新闻", "real", "最小采集")
        self.assertEqual(record["data_type"], "real")
        self.assertEqual(record["platform"], "微博")
        self.assertEqual(record["source_type"], "official")
        self.assertTrue(record["url"].startswith("https://news.example.com"))

    def test_parse_sogou_news_and_weixin(self):
        news_html = """
        <div class="vrwrap">
          <h3><a href="https://news.example.com/b">媒体报道公共安全事件</a></h3>
          <p>记者从现场了解到，相关部门正在处理。</p>
          <span>人民网 2小时前</span>
        </div>
        """
        weixin_html = """
        <ul>
          <li id="sogou_vr_1">
            <div class="txt-box">
              <h3><a href="/weixin?doc=1">官方情况通报</a></h3>
              <a class="account">平安湖北</a>
              <p>公安机关发布最新情况，提醒不信谣不传谣。</p>
              <span>昨天 12:00</span>
            </div>
          </li>
        </ul>
        """
        news = self.crawler._parse_results("微信公众平台", news_html, "公共安全", "搜狗新闻", "https://news.sogou.com/news")
        weixin = self.crawler._parse_results("微信公众平台", weixin_html, "通报", "搜狗微信", "https://weixin.sogou.com/weixin")
        self.assertGreaterEqual(len(news), 1)
        self.assertGreaterEqual(len(weixin), 1)
        wx_record = self.crawler._normalize_record(weixin[0], "微信公众平台", "通报", "湖北省", "搜狗微信", "real", "最小采集")
        self.assertIn("source_type", wx_record)
        self.assertEqual(wx_record["data_type"], "real")

    def test_extract_article_content(self):
        html = """
        <html><head>
          <title>新闻详情</title>
          <meta name="source" content="湖北日报">
          <meta name="publishdate" content="2026-07-01 09:20">
        </head><body>
          <article>
            <h1>官方发布突发事件处置情况</h1>
            <p>第一段正文内容较长，用于验证详情页正文抽取是否能够提取有效内容。</p>
            <p>第二段正文继续说明调查进展、处置措施和后续安排。</p>
          </article>
        </body></html>
        """
        detail = self.crawler._extract_article_content(html)
        self.assertEqual(detail["source"], "湖北日报")
        self.assertIn("第二段正文", detail["content"])
        self.assertEqual(detail["pub_time"], "2026-07-01 09:20")

    def test_parse_social_search_fixtures(self):
        weibo_html = """
        <div class="card-wrap">
          <a class="name" href="/u/1">平安湖北</a>
          <p class="txt">警方通报事件进展，相关调查正在依法进行。</p>
          <div class="from">刚刚 来自微博</div>
          <a href="//weibo.com/1/status">详情</a>
        </div>
        """
        tieba_html = """
        <div class="s_post">
          <a href="/p/123">警方通报相关讨论</a>
          <span class="p_author_name">贴吧用户</span>
          <span class="p_date">2026-07-01</span>
          <div>网友关注警方通报的后续处置情况。</div>
        </div>
        """
        tieba_new_html = """
        <div class="thread-content-box">
          <span class="forum-name-text">公共安全吧</span>
          <div class="title-wrap">警方通报相关讨论</div>
          <div class="abstract-wrap">网友关注警方通报的后续处置情况。</div>
          <a class="action-link-bg" href="/p/456"></a>
        </div>
        """
        douban_html = """
        <div class="result">
          <a href="https://www.douban.com/group/topic/1/">公共事件讨论记录</a>
          <p>豆瓣用户对事件处置进展进行讨论。</p>
        </div>
        """
        weibo = self.crawler._parse_results("微博", weibo_html, "警方通报", "微博搜索", "https://s.weibo.com/weibo")
        tieba = self.crawler._parse_results("百度贴吧", tieba_html, "警方通报", "贴吧搜索", "https://tieba.baidu.com")
        tieba_new = self.crawler._parse_results("百度贴吧", tieba_new_html, "警方通报", "贴吧搜索", "https://tieba.baidu.com")
        douban = self.crawler._parse_results("豆瓣", douban_html, "公共事件", "豆瓣搜索", "https://www.douban.com/search")
        self.assertGreaterEqual(len(weibo), 1)
        self.assertEqual(weibo[0]["platform"], "微博")
        self.assertGreaterEqual(len(tieba), 1)
        self.assertEqual(tieba[0]["platform"], "百度贴吧")
        self.assertEqual(tieba_new[0]["url"], "https://tieba.baidu.com/p/456")
        self.assertEqual(tieba_new[0]["source"], "公共安全吧")
        self.assertGreaterEqual(len(douban), 1)
        self.assertEqual(douban[0]["platform"], "豆瓣")

    def test_extract_tieba_new_detail_page(self):
        html = """
        <html><head><title>贴吧事件讨论</title></head><body>
          <div class="pb-content-wrap">楼主发布的事件经过和后续说明，供大家讨论。</div>
          <div class="pb-rich-text">第二层补充了新的处理进展和公开信息。</div>
          <div class="pb-lzl-item"><div class="comment-content">楼中楼回复内容。</div></div>
        </body></html>
        """
        detail = extract_tieba_detail_from_html(html)
        self.assertIn("楼主发布", detail["content"])
        self.assertGreaterEqual(len(detail["discussion_samples"]), 2)

    def test_extract_weibo_structured_detail(self):
        detail = extract_weibo_detail_from_payload({
            "idstr": "1234567890",
            "mblogid": "AbCdEf123",
            "text_raw": "警方通报事件处理进展。",
            "created_at": "Wed Jul 23 10:30:00 +0800 2026",
            "user": {"idstr": "998877", "screen_name": "平安测试"},
            "reposts_count": 3,
            "comments_count": 4,
            "attitudes_count": 5,
        })
        self.assertEqual(detail["content"], "警方通报事件处理进展。")
        self.assertEqual(detail["author"], "平安测试")
        self.assertEqual(detail["like_count"], 5)

    def test_weibo_parser_prefers_status_url_over_author_profile(self):
        html = """
        <div class="card-wrap">
          <a class="name" href="//weibo.com/5756404150?refer_flag=1001030103_">英雄联盟赛事</a>
          <p class="txt">2026LPL第三赛段赛制介绍 #英雄联盟#</p>
          <div class="from">
            <a href="//weibo.com/5756404150/ODpRqE3ue?refer_flag=1001030103_">06月29日 18:30</a>
            来自 微博网页版
          </div>
        </div>
        """
        items = self.crawler._parse_results(
            "微博",
            html,
            "英雄联盟",
            "微博搜索",
            "https://s.weibo.com/weibo?q=%E8%8B%B1%E9%9B%84%E8%81%94%E7%9B%9F",
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0]["url"],
            "https://weibo.com/5756404150/ODpRqE3ue?refer_flag=1001030103_",
        )

    def test_weibo_parser_rejects_author_profile_only_cards(self):
        html = """
        <div class="card-wrap">
          <a class="name" href="//weibo.com/5756404150?refer_flag=1001030103_">英雄联盟赛事</a>
          <p class="txt">只有作者主页链接，不应该保存为推文结果 #英雄联盟#</p>
          <div class="from">06月29日 18:30 来自 微博网页版</div>
        </div>
        """
        items = self.crawler._parse_results(
            "微博",
            html,
            "英雄联盟",
            "微博搜索",
            "https://s.weibo.com/weibo?q=%E8%8B%B1%E9%9B%84%E8%81%94%E7%9B%9F",
        )
        self.assertEqual(items, [])

    def test_weibo_author_profile_is_filtered_before_save(self):
        crawler = NewsCrawler()
        crawler.anti_crawl.delay = lambda *args, **kwargs: None
        crawler._request_source_html = lambda url, channel, platform, source_group, timeout=10: ("<html></html>", url, None)
        crawler._parse_results = lambda platform, html, keyword, channel, base_url: [{
            "title": "作者主页链接不应入库",
            "content": "作者主页链接不应入库 #英雄联盟#",
            "url": "https://weibo.com/5756404150?refer_flag=1001030103_",
            "source": "英雄联盟赛事",
            "platform": "微博",
            "pub_time": "",
            "collector": "微博搜索",
        }]
        data = crawler.crawl(
            ["英雄联盟"],
            max_results=1,
            social_platforms=["微博"],
            collect_level="最小采集",
            source_strategy="social",
            min_real_results=1,
        )
        self.assertEqual(data, [])

    def test_social_article_parser_ignores_profile_birthday(self):
        html = """
        <html><body>
          <main>
            <h1>大战一触即发了 #2026MSI#</h1>
            <p>公开 大战一触即发了 #2026MSI# #bin 没想到doran会玩得这么菜#</p>
            <section class="profile">狂很子老 719 关注 211.2万 粉丝 男 1995-09-07 处女座 湖北 查看个人主页</section>
          </main>
        </body></html>
        """
        detail = extract_article_from_html(html)
        self.assertIn("大战一触即发", detail["content"])
        self.assertEqual(detail["pub_time"], "")


class CrawlerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.crawler = NewsCrawler()
        self.crawler.anti_crawl.delay = lambda min_delay=0.3, max_delay=1.0: None
        self.crawler._request_html = lambda url, channel, timeout=10: ("", url, "network disabled in test")

    def test_response_decoder_prefers_utf8_over_misdetected_latin1(self):
        class FakeResponse:
            content = "2026英雄联盟MSI淘汰赛赛程公布".encode("utf-8")
            headers = {"Content-Type": "text/html"}
            apparent_encoding = "ISO-8859-1"
            encoding = "ISO-8859-1"

        text = NewsCrawler._decode_response_text(FakeResponse())
        self.assertIn("英雄联盟", text)
        self.assertNotIn("è‹±", text)

    def test_response_decoder_keeps_gb18030_pages_readable(self):
        class FakeResponse:
            content = "警方通报突发事件处置情况".encode("gb18030")
            headers = {"Content-Type": "text/html; charset=gb2312"}
            apparent_encoding = "ISO-8859-1"
            encoding = "ISO-8859-1"

        text = NewsCrawler._decode_response_text(FakeResponse())
        self.assertIn("警方通报", text)

    def test_collection_uses_safe_default_request_interval(self):
        crawler = NewsCrawler()
        delay_calls = []
        crawler.anti_crawl.delay = lambda *args, **kwargs: delay_calls.append((args, kwargs))
        crawler._request_html = lambda url, channel, timeout=10: ("<html></html>", url, None)

        crawler.crawl(
            ["警方通报"],
            max_results=1,
            stable_sources=["天津市公安局公安要闻"],
            source_strategy="stable",
            collect_level="最小采集",
            min_real_results=1,
        )

        self.assertEqual(delay_calls, [((), {})])

    def test_request_html_does_not_retry_unauthorized_status(self):
        class FakeResponse:
            status_code = 403
            headers = {}
            url = "https://example.com/restricted"

        class FakeSession:
            def __init__(self):
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                return FakeResponse()

        crawler = NewsCrawler()
        crawler.session = FakeSession()
        _, _, error = crawler._request_html("https://example.com/restricted", "test")

        self.assertEqual(error, "HTTP 403")
        self.assertEqual(crawler.session.calls, 1)

    def test_request_html_stops_on_429_without_retry_after(self):
        class FakeResponse:
            status_code = 429
            headers = {}
            url = "https://example.com/limited"

        class FakeSession:
            def __init__(self):
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                return FakeResponse()

        crawler = NewsCrawler()
        crawler.session = FakeSession()
        _, _, error = crawler._request_html("https://example.com/limited", "test")

        self.assertEqual(error, "HTTP 429")
        self.assertEqual(crawler.session.calls, 1)

    def test_browser_verification_prompts_stop_automated_path(self):
        self.assertTrue(NewsCrawler._contains_verification_prompt("请输入验证码后继续"))
        self.assertTrue(NewsCrawler._contains_verification_prompt("请完成安全验证"))
        self.assertTrue(NewsCrawler._contains_verification_prompt("Drag to complete the security check"))
        self.assertFalse(NewsCrawler._contains_verification_prompt("搜索完成，共找到 10 条结果"))

    def test_mock_disabled_by_default(self):
        data = self.crawler.crawl(
            ["低频测试词"],
            platforms=["微博"],
            collect_level="最小采集",
            min_real_results=2,
        )
        self.assertEqual(data, [])
        self.assertEqual(self.crawler.last_meta["summary"]["mock_count"], 0)
        self.assertFalse(self.crawler.last_meta["reached_min_real_results"])

    def test_no_mock_fill_branch_exists(self):
        data = self.crawler.crawl(
            ["警情通报"],
            platforms=["微博"],
            collect_level="最小采集",
            min_real_results=2,
        )
        self.assertEqual(data, [])
        self.assertEqual(self.crawler.last_meta["summary"]["mock_count"], 0)
        self.assertFalse(self.crawler.last_meta["reached_min_real_results"])

    def test_missing_pub_time_does_not_fallback_to_crawl_time(self):
        record = self.crawler._normalize_record(
            item={
                "title": "Bilibili result without publish time",
                "content": "Bilibili result without publish time",
                "url": "https://www.bilibili.com/video/BV1abc",
                "source": "B站",
                "platform": "B站",
                "pub_time": "",
            },
            platform="B站",
            keyword="police",
            region="全国",
            collector="B站搜索",
            data_type="real",
            collect_level="最小采集",
        )
        self.assertEqual(record["pub_time"], "")
        self.assertEqual(record["time_basis"], "unknown")
        self.assertTrue(record["crawl_time"])

    def test_date_only_pub_time_is_preserved_as_date(self):
        record = self.crawler._normalize_record(
            item={
                "title": "News result with date only",
                "content": "News result with date only",
                "url": "https://news.example.com/a",
                "source": "百度新闻",
                "platform": "百度新闻",
                "pub_time": "2026-07-01",
            },
            platform="百度新闻",
            keyword="police",
            region="全国",
            collector="百度新闻",
            data_type="real",
            collect_level="最小采集",
        )
        self.assertEqual(record["pub_time"], "2026-07-01")
        self.assertEqual(record["time_basis"], "published_date")

    def test_social_profile_birthday_is_not_pub_time(self):
        for platform in PLATFORM_LIST:
            with self.subTest(platform=platform):
                record = self.crawler._normalize_record(
                    item={
                        "title": f"{platform} 详情内容",
                        "content": "作者资料 719 关注 211.2万 粉丝 男 1995-09-07 处女座 湖北 查看个人主页",
                        "url": f"https://example.com/{platform}/post/1",
                        "source": "测试作者",
                        "platform": platform,
                        "pub_time": "1995-09-07",
                    },
                    platform=platform,
                    keyword="MSI",
                    region="全国",
                    collector=f"{platform}搜索",
                    data_type="real",
                    collect_level="最小采集",
                )
                self.assertEqual(record["pub_time"], "")
                self.assertEqual(record["time_basis"], "unknown")

    def test_stable_sources_are_not_repeated_per_social_platform(self):
        requested_channels = []
        recent_time = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d 10:30")
        official_html = f"""
        <html><body>
          <ul><li class="comItem">
            <a href="./202607/stable.html">稳定源测试：警方发布公开通报</a>
            <span>{recent_time}</span>
          </li></ul>
        </body></html>
        """

        def fake_request(url, channel, timeout=10, **kwargs):
            requested_channels.append(channel)
            if channel == "天津市公安局公安要闻":
                return official_html, url, None
            return "", url, "disabled in test"

        self.crawler._request_html = fake_request
        data = self.crawler.crawl(
            ["稳定源测试"],
            platforms=["微博", "抖音"],
            collect_level="最小采集",
            max_results=2,
            min_real_results=1,
        )

        self.assertEqual(requested_channels.count("天津市公安局公安要闻"), 1)
        self.assertGreaterEqual(len(data), 1)
        self.assertTrue(all(item["platform"] in STABLE_CHANNELS for item in data))
        self.assertTrue(all(item["platform"] not in {"微博", "抖音"} for item in data))
        self.assertEqual(self.crawler.last_meta["summary"]["stable_real_count"], len(data))
        self.assertEqual(self.crawler.last_meta["summary"]["social_real_count"], 0)

    def test_all_strategy_runs_three_source_groups_independently(self):
        calls = []

        def fake_collect(source_requests, keyword, region, collect_level, start_time, end_time,
                         remaining, progress_callback=None):
            source_group = source_requests[0]["source_group"]
            calls.append(source_group)
            if source_group == "stable":
                return [{
                    "title": "政府官网结果",
                    "content": "政府官网公开信息。",
                    "url": "https://gov.example.cn/notices/1",
                    "platform": "测试政府官网",
                    "source": "测试政府官网",
                    "source_group": "stable",
                    "source_type": "official",
                    "data_type": "real",
                    "pub_time": "2026-08-22T13:00:00",
                }], []
            if source_group == "social":
                return [{
                    "title": "社交平台结果",
                    "content": "社交平台公开信息。",
                    "url": "https://weibo.com/1/example",
                    "platform": "微博",
                    "source": "测试账号",
                    "source_group": "social",
                    "source_type": "public",
                    "data_type": "real",
                    "pub_time": "2026-08-22T11:00:00",
                }], []
            return [{
                "title": "公开新闻补充结果",
                "content": "这是通过公开新闻检索补充的摘要。",
                "url": "https://news.example.com/public/1",
                "platform": "Bing 新闻",
                "source": "示例媒体",
                "source_group": "public_news",
                "source_type": "media",
                "data_type": "real",
                "pub_time": "2026-08-22T12:00:00",
            }], []

        self.crawler._collect_from_source_requests = fake_collect
        data = self.crawler.crawl(
            ["跨来源检索"],
            max_results=3,
            collect_level="最小采集",
            source_strategy="all",
            social_platforms=["微博"],
            min_real_results=1,
        )

        self.assertEqual(set(calls), {"stable", "public_news", "social"})
        self.assertEqual(len(data), 3)
        self.assertEqual(
            {item["source_group"] for item in data},
            {"stable", "public_news", "social"},
        )
        summary = self.crawler.last_meta["summary"]
        self.assertEqual(summary["stable_real_count"], 1)
        self.assertEqual(summary["public_news_real_count"], 1)
        self.assertEqual(summary["social_real_count"], 1)

    def test_all_strategy_runs_social_when_other_groups_have_no_results(self):
        calls = []

        def fake_collect(source_requests, keyword, region, collect_level, start_time, end_time,
                         remaining, progress_callback=None):
            source_group = source_requests[0]["source_group"]
            calls.append(source_group)
            if source_group in {"stable", "public_news"}:
                return [], []
            return [{
                "title": "社交平台补充线索",
                "content": "社交平台公开内容。",
                "url": "https://weibo.com/1/example",
                "platform": "微博",
                "source": "测试账号",
                "source_group": "social",
                "source_type": "public",
                "data_type": "real",
                "pub_time": "2026-08-22T10:00:00",
            }], []

        self.crawler._collect_from_source_requests = fake_collect
        data = self.crawler.crawl(
            ["跨来源检索"],
            max_results=2,
            collect_level="最小采集",
            source_strategy="all",
            social_platforms=["微博"],
            min_real_results=2,
        )

        self.assertEqual(set(calls), {"stable", "public_news", "social"})
        self.assertEqual({item["source_group"] for item in data}, {"social"})
        summary = self.crawler.last_meta["summary"]
        self.assertEqual(summary["public_news_real_count"], 0)
        self.assertEqual(summary["social_real_count"], 1)

    def test_all_strategy_isolates_source_group_failures(self):
        calls = []

        def fake_collect(source_requests, **kwargs):
            source_group = source_requests[0]["source_group"]
            calls.append(source_group)
            if source_group == "stable":
                raise RuntimeError("government source failure")
            return [{
                "title": f"{source_group} 仍可采集",
                "content": f"{source_group} 来源组不受其他来源失败影响。",
                "url": f"https://example.com/{source_group}",
                "platform": "微博" if source_group == "social" else "Bing 新闻",
                "source": "测试来源",
                "source_group": source_group,
                "source_type": "public" if source_group == "social" else "media",
                "data_type": "real",
                "pub_time": "2026-08-22T10:00:00",
            }], []

        self.crawler._collect_from_source_requests = fake_collect
        data = self.crawler.crawl(
            ["异常隔离"],
            max_results=3,
            collect_level="最小采集",
            source_strategy="all",
            social_platforms=["微博"],
            min_real_results=1,
        )

        self.assertEqual(set(calls), {"stable", "public_news", "social"})
        self.assertEqual(
            {item["source_group"] for item in data},
            {"public_news", "social"},
        )
        self.assertTrue(
            any("government source failure" in failure["error"]
                for failure in self.crawler.last_meta["failures"])
        )

    def test_legacy_stable_first_is_compatible_alias_for_all(self):
        self.assertEqual(self.crawler._normalize_source_strategy("stable_first"), "all")
        self.assertEqual(self.crawler._normalize_source_strategy("hybrid"), "all")

    def test_stable_only_does_not_use_public_news(self):
        calls = []

        def fake_collect(source_requests, keyword, region, collect_level, start_time, end_time,
                         remaining, progress_callback=None):
            calls.append(source_requests[0]["source_group"])
            return [], []

        self.crawler._collect_from_source_requests = fake_collect
        self.crawler.crawl(
            ["政府官网验收"],
            max_results=1,
            collect_level="最小采集",
            source_strategy="stable",
            min_real_results=1,
        )

        self.assertTrue(calls)
        self.assertEqual(set(calls), {"stable"})

    def test_progress_events_and_quality_metrics_are_emitted(self):
        events = []
        recent_time = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d 10:30")
        html = f"""
        <html><body>
          <ul><li class="comItem">
            <a href="./202607/progress.html">进度测试：警方通报最新进展</a>
            <span>{recent_time}</span>
          </li></ul>
        </body></html>
        """

        def fake_request(url, channel, timeout=10, **kwargs):
            if channel == "天津市公安局公安要闻":
                return html, url, None
            return "", url, "disabled in test"

        self.crawler._request_html = fake_request
        data = self.crawler.crawl(
            ["进度测试"],
            max_results=1,
            collect_level="最小采集",
            source_strategy="stable",
            stable_sources=["天津市公安局公安要闻"],
            min_real_results=1,
            progress_callback=events.append,
        )
        self.assertEqual(len(data), 1)
        event_types = {event["type"] for event in events}
        self.assertIn("crawl_start", event_types)
        self.assertIn("source_start", event_types)
        self.assertIn("source_success", event_types)
        self.assertIn("crawl_complete", event_types)
        self.assertIn("quality_metrics", self.crawler.last_meta)
        self.assertIn("source_health", self.crawler.last_meta)

    def test_social_cookie_auth_headers_are_platform_scoped(self):
        self.crawler.set_account("微博", username="tester", cookie="SUB=fake-cookie")
        headers = self.crawler._build_request_headers("https://s.weibo.com/weibo?q=test", "微博搜索")
        self.assertEqual(headers.get("Cookie"), "SUB=fake-cookie")
        self.assertEqual(self.crawler.account_manager.list_authorized_platforms(), ["微博"])

        enhanced_headers = self.crawler._build_request_headers(
            "https://www.baidu.com/s?wd=test%20抖音",
            "公开搜索增强-抖音",
        )
        self.assertNotIn("Cookie", enhanced_headers)

    def test_system_proxy_disabled_by_default(self):
        default_crawler = NewsCrawler()
        self.assertFalse(default_crawler.use_system_proxy)
        if default_crawler.session:
            self.assertFalse(default_crawler.session.trust_env)

        proxy_crawler = NewsCrawler(use_system_proxy=True)
        self.assertTrue(proxy_crawler.use_system_proxy)
        if proxy_crawler.session:
            self.assertTrue(proxy_crawler.session.trust_env)

    def test_bilibili_login_probe_success(self):
        crawler = NewsCrawler()
        crawler.set_account("B站", username="tester", cookie="SESSDATA=fake-cookie")
        nav_json = json.dumps({"data": {"isLogin": True, "uname": "tester", "mid": 123}}, ensure_ascii=False)
        search_html = """
        <div class="bili-video-card">
          <a href="//www.bilibili.com/video/BV1abc" title="警方通报视频讨论"></a>
          <h3 title="警方通报视频讨论">警方通报视频讨论</h3>
          <div class="bili-video-card__stats">1.2万播放</div>
        </div>
        """

        def fake_request(url, channel, timeout=10, **kwargs):
            if "api.bilibili.com/x/web-interface/nav" in url:
                return nav_json, url, None
            if "search.bilibili.com" in url:
                return search_html, url, None
            return "", url, "disabled in test"

        crawler._request_html = fake_request
        result = crawler.test_social_platform("B站", keyword="警方通报")
        self.assertTrue(result["reachable"])
        self.assertTrue(result["login_confirmed"])
        self.assertEqual(result["username_or_hint"], "tester")
        self.assertGreaterEqual(result["parsed_count"], 1)
        self.assertEqual(result["auth_mode"], "authorized_session")

    def test_weibo_browser_login_probe_uses_authorized_identity_route(self):
        crawler = NewsCrawler()
        crawler.set_account(
            "微博",
            browser_cookie="SUB=fake; SUBP=fake",
            browser_session=json.dumps({"cookies": [], "origins": []}),
            session_mode="browser_session",
        )
        calls = []

        def fake_browser_json(platform, url, timeout=12):
            calls.append((platform, url))
            return {
                "data": {
                    "login": True,
                    "uid": "123456",
                    "screen_name": "tester",
                }
            }, 200, url, None

        crawler._request_browser_json = fake_browser_json
        result = crawler._probe_weibo_login(crawler._base_auth_probe_result("微博"))
        self.assertTrue(result["login_confirmed"])
        self.assertEqual(calls, [("微博", "https://weibo.com/ajax/config/get_config")])
        self.assertIn("browser config returned login marker", result["evidence"])

    def test_weibo_platform_test_uses_saved_browser_session_reader(self):
        crawler = NewsCrawler()
        crawler.set_account(
            "微博",
            browser_cookie="SUB=fake; SUBP=fake",
            browser_session=json.dumps({"cookies": [], "origins": []}),
            session_mode="browser_session",
        )
        weibo_html = """
        <div class="card-wrap">
          <div class="content">
            <p class="txt">警方通报：测试读取结果。</p>
            <a class="name" href="//weibo.com/123456">测试账号</a>
            <p class="from"><a href="//weibo.com/123456/P0Test1234">刚刚</a></p>
          </div>
        </div>
        """
        crawler._request_html = lambda *args, **kwargs: self.fail("不应回退普通 HTTP 请求")
        crawler._request_source_html = lambda **kwargs: (
            weibo_html,
            kwargs["url"],
            None,
        )
        crawler._request_browser_json = lambda platform, url, timeout=12: (
            {},
            432,
            url,
            "HTTP 432",
        )
        crawler._request_browser_html = lambda **kwargs: (
            "<html><body>微博首页</body></html>",
            kwargs["url"],
            None,
        )
        result = crawler.test_social_platform("微博", keyword="警方通报")
        self.assertFalse(result["passed"])
        self.assertTrue(result["read_passed"])
        self.assertFalse(result["login_passed"])
        self.assertEqual(result["status"], "collection_only")
        self.assertEqual(result["parsed_count"], 1)
        self.assertIsNone(result["login_confirmed"])
        self.assertIn("no login marker", result["evidence"])

    def test_weibo_login_probe_falls_back_to_current_homepage_marker(self):
        crawler = NewsCrawler()
        crawler.set_account(
            "微博",
            browser_cookie="SUB=fake; SUBP=fake",
            browser_session=json.dumps({"cookies": [], "origins": []}),
            session_mode="browser_session",
        )
        crawler._request_browser_json = lambda *args, **kwargs: ({}, 432, args[1], "HTTP 432")
        crawler._request_browser_html = lambda **kwargs: (
            '<script>window.$CONFIG["uid"]="123456";</script>',
            kwargs["url"],
            None,
        )

        result = crawler._probe_weibo_login(crawler._base_auth_probe_result("微博"))

        self.assertTrue(result["login_confirmed"])
        self.assertIn("strong login marker", result["evidence"])

    def test_weibo_login_probe_prefers_visible_account_control_when_api_is_inconclusive(self):
        crawler = NewsCrawler(
            live_login_probe=lambda platform, timeout: {
                "reachable": True,
                "login_confirmed": True,
                "evidence": f"{platform}当前页面顶部或侧栏的账号控件可见",
                "final_url": "https://weibo.com/",
                "error": "",
            }
        )
        crawler.set_account(
            "微博",
            browser_cookie="SUB=fake; SUBP=fake",
            browser_session=json.dumps({"cookies": [], "origins": []}),
            session_mode="browser_session",
        )
        crawler._request_browser_json = lambda *args, **kwargs: (
            {"ok": 1, "data": {"ab_test": {}}},
            200,
            args[1],
            None,
        )

        result = crawler._probe_weibo_login(crawler._base_auth_probe_result("微博"))

        self.assertTrue(result["login_confirmed"])
        self.assertIn("账号控件可见", result["evidence"])

    def test_douyin_platform_test_reuses_visible_authorized_browser(self):
        calls = []
        douyin_html = """
        <div data-e2e="user-avatar"></div>
        <div data-e2e="search-card">
          <a href="https://www.douyin.com/video/1234567890">警方通报 视频结果</a>
        </div>
        """

        def live_reader(platform, url, timeout):
            calls.append((platform, url, timeout))
            return douyin_html, url, None

        crawler = NewsCrawler(live_browser_reader=live_reader)
        crawler.set_account(
            "抖音",
            browser_cookie="sessionid=fake",
            browser_session=json.dumps({"cookies": [], "origins": []}),
            session_mode="browser_session",
            browser_login_confirmed=True,
            browser_login_evidence="抖音 page matched login marker",
        )
        crawler._request_browser_html = lambda *args, **kwargs: self.fail(
            "可见辅助浏览器成功时不应新建无头浏览器"
        )

        result = crawler.test_social_platform("抖音", keyword="警方通报")

        self.assertTrue(result["passed"])
        self.assertTrue(result["login_confirmed"])
        self.assertEqual(result["parsed_count"], 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "抖音")
        self.assertIn("当前采集页面", result["evidence"])

    def test_douyin_saved_login_marker_without_current_page_marker_is_not_enough(self):
        douyin_html = """
        <div data-e2e="search-card">
          <a href="https://www.douyin.com/video/1234567890">警方通报 视频结果</a>
        </div>
        """
        crawler = NewsCrawler(
            live_browser_reader=lambda platform, url, timeout: (douyin_html, url, None)
        )
        crawler.set_account(
            "抖音",
            browser_cookie="sessionid=fake",
            browser_session=json.dumps({"cookies": [], "origins": []}),
            session_mode="browser_session",
            browser_login_confirmed=True,
        )

        result = crawler.test_social_platform("抖音", keyword="警方通报")

        self.assertFalse(result["passed"])
        self.assertTrue(result["read_passed"])
        self.assertFalse(result["login_passed"])
        self.assertIsNone(result["login_confirmed"])
        self.assertEqual(result["status"], "collection_only")

    def test_douyin_visible_account_control_is_not_overwritten_by_search_html(self):
        douyin_html = """
        <div data-e2e="search-card">
          <a href="https://www.douyin.com/video/1234567890">警方通报 视频结果</a>
        </div>
        """
        crawler = NewsCrawler(
            live_browser_reader=lambda platform, url, timeout: (douyin_html, url, None),
            live_login_probe=lambda platform, timeout: {
                "reachable": True,
                "login_confirmed": True,
                "evidence": "抖音当前页面顶部或侧栏的账号控件可见",
                "final_url": "https://www.douyin.com/",
                "error": "",
            },
        )
        crawler.set_account(
            "抖音",
            browser_cookie="sessionid=fake",
            browser_session=json.dumps({"cookies": [], "origins": []}),
            session_mode="browser_session",
        )

        result = crawler.test_social_platform("抖音", keyword="警方通报")

        self.assertTrue(result["passed"])
        self.assertTrue(result["login_confirmed"])
        self.assertIn("账号控件可见", result["evidence"])

    def test_douyin_visible_verification_stops_without_headless_fallback(self):
        crawler = NewsCrawler(
            live_browser_reader=lambda platform, url, timeout: (
                "",
                url,
                "human_verification_required: "
                "抖音需要在已打开的辅助浏览器中完成人工验证；完成后请重新测试",
            )
        )
        crawler.set_account(
            "抖音",
            browser_cookie="sessionid=fake",
            browser_session=json.dumps({"cookies": [], "origins": []}),
            session_mode="browser_session",
            browser_login_confirmed=True,
        )
        crawler._request_browser_html = lambda *args, **kwargs: self.fail(
            "出现人工验证时不应回退到无头浏览器"
        )

        result = crawler.test_social_platform("抖音", keyword="警方通报")

        self.assertFalse(result["passed"])
        self.assertIsNone(result["login_confirmed"])
        self.assertEqual(result["status"], "action_required")
        self.assertIn("已打开的辅助浏览器", result["message"])

    def test_douyin_visible_browser_failure_is_not_silently_hidden(self):
        crawler = NewsCrawler(
            live_browser_reader=lambda platform, url, timeout: (
                "",
                url,
                "抖音 auxiliary browser was closed",
            )
        )
        crawler.set_account(
            "抖音",
            browser_cookie="sessionid=fake",
            browser_session=json.dumps({"cookies": [], "origins": []}),
            session_mode="browser_session",
            browser_login_confirmed=True,
        )
        crawler._request_browser_html = lambda *args, **kwargs: self.fail(
            "可见浏览器失败时不应静默回退到无头浏览器"
        )

        result = crawler.test_social_platform("抖音", keyword="警方通报")

        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], "action_required")
        self.assertIn("auxiliary browser was closed", result["message"])

    def test_weibo_http_432_is_reported_as_platform_restriction(self):
        crawler = NewsCrawler()
        crawler.set_account(
            "微博",
            browser_cookie="SUB=fake; SUBP=fake",
            browser_session=json.dumps({"cookies": [], "origins": []}),
            session_mode="browser_session",
        )
        crawler._request_source_html = lambda **kwargs: (
            "",
            kwargs["url"],
            "HTTP 432; fallback failed: HTTP 432",
        )
        crawler._request_browser_json = lambda platform, url, timeout=12: (
            {},
            432,
            url,
            "HTTP 432",
        )
        crawler._request_browser_html = lambda **kwargs: (
            "",
            kwargs["url"],
            "homepage blocked",
        )
        result = crawler.test_social_platform("微博", keyword="警方通报")
        self.assertEqual(result["status"], "restricted")
        self.assertFalse(result["passed"])
        self.assertIn("平台拒绝当前自动读取", result["message"])
        self.assertIn("平台拒绝当前自动读取", result["message"])

    def test_tieba_browser_login_probe_accepts_new_identity_fields(self):
        crawler = NewsCrawler()
        crawler.set_account(
            "百度贴吧",
            browser_cookie="BDUSS=fake",
            browser_session=json.dumps({"cookies": [], "origins": []}),
            session_mode="browser_session",
        )
        crawler._request_browser_json = lambda *args, **kwargs: (
            {"no": 0, "data": {"is_login": 1, "user_name_show": "tester"}},
            200,
            args[1],
            None,
        )
        result = crawler._probe_tieba_login(crawler._base_auth_probe_result("百度贴吧"))
        self.assertTrue(result["login_confirmed"])

    def test_weibo_structured_detail_replaces_noisy_page_content(self):
        crawler = NewsCrawler()
        crawler.set_account(
            "微博",
            browser_cookie="SUB=fake; SUBP=fake",
            browser_session=json.dumps({"cookies": [], "origins": []}),
            session_mode="browser_session",
        )
        crawler._request_browser_json = lambda *args, **kwargs: ({
            "idstr": "1234567890",
            "mblogid": "AbCdEf123",
            "text_raw": "真实微博正文。",
            "created_at": "Wed Jul 23 10:30:00 +0800 2026",
            "user": {"idstr": "998877", "screen_name": "平安测试"},
            "reposts_count": 3,
            "comments_count": 4,
            "attitudes_count": 5,
        }, 200, args[1], None)
        record = {
            "url": "https://weibo.com/998877/AbCdEf123",
            "title": "搜索标题",
            "content": "导航和推荐内容" * 300,
            "platform": "微博",
        }

        crawler._enrich_with_weibo_detail(record)

        self.assertEqual(record["content"], "真实微博正文。")
        self.assertEqual(record["detail_source"], "weibo_status_api")
        self.assertEqual(record["comment_count"], 4)
        self.assertTrue(record["pub_time"])
        self.assertEqual(record["time_basis"], "published_time")
        self.assertTrue(record["detail_enriched"])

    def test_extract_weibo_status_id_supports_known_url_shapes(self):
        self.assertEqual(NewsCrawler._extract_weibo_status_id("https://weibo.com/998877/AbCdEf123"), "AbCdEf123")
        self.assertEqual(NewsCrawler._extract_weibo_status_id("https://m.weibo.cn/detail/1234567890"), "1234567890")
        self.assertEqual(NewsCrawler._extract_weibo_status_id("https://m.weibo.cn/status/1234567890"), "1234567890")

    def test_xiaohongshu_login_probe_success(self):
        crawler = NewsCrawler()
        crawler.set_account("小红书", username="tester", cookie="a1=fake-cookie")
        payload = json.dumps(
            {"success": True, "data": {"user_id": "u123", "nickname": "tester"}},
            ensure_ascii=False,
        )
        crawler._request_html = lambda url, channel, timeout=10, **kwargs: (payload, url, None)
        result = crawler._probe_xiaohongshu_login(crawler._base_auth_probe_result("小红书"))
        self.assertTrue(result["reachable"])
        self.assertTrue(result["login_confirmed"])
        self.assertIn("selfinfo", result["evidence"])

    def test_xiaohongshu_login_probe_does_not_confirm_logged_out_page(self):
        crawler = NewsCrawler()
        crawler.set_account("小红书", username="tester", cookie="a1=fake-cookie")
        logged_out_html = """
        <script>
        window.__INITIAL_STATE__={"user":{"loggedIn":false,"userInfo":{"nickname":"placeholder"}}}
        </script>
        """

        def fake_request(url, channel, timeout=8, **kwargs):
            if "selfinfo" in url:
                return "", url, "selfinfo blocked"
            return logged_out_html, url, None

        crawler._request_html = fake_request
        result = crawler._probe_xiaohongshu_login(crawler._base_auth_probe_result("小红书"))
        self.assertTrue(result["reachable"])
        self.assertFalse(result["login_confirmed"])
        self.assertNotIn("strong login marker", result["evidence"])

    def test_xiaohongshu_page_login_marker_can_confirm_when_selfinfo_changed(self):
        crawler = NewsCrawler()
        crawler.set_account(
            "小红书",
            browser_cookie="a1=fake-cookie",
            browser_session=json.dumps({"cookies": [], "origins": []}),
            session_mode="browser_session",
        )
        crawler._request_browser_json = lambda *args, **kwargs: (
            {"success": False, "msg": "endpoint changed"},
            200,
            args[1],
            None,
        )
        crawler._request_html = lambda *args, **kwargs: ("", args[0], "blocked")
        crawler._request_browser_html = lambda **kwargs: (
            '<script>window.__INITIAL_STATE__={"user":{"loggedIn":true}}</script>',
            kwargs["url"],
            None,
        )

        result = crawler._probe_xiaohongshu_login(crawler._base_auth_probe_result("小红书"))

        self.assertTrue(result["login_confirmed"])
        self.assertIn("strong login marker", result["evidence"])

    def test_bilibili_noise_links_are_filtered(self):
        html = """
        <div class="bili-video-card">
          <a href="https://beian.miit.gov.cn/" title="ICP备案信息"></a>
          <h3 title="ICP备案信息">ICP备案信息</h3>
        </div>
        <div class="bili-video-card">
          <a href="//www.bilibili.com/video/BV1abc" title=""></a>
          <h3 title=""></h3>
        </div>
        """
        items = self.crawler._parse_results("B站", html, "警方通报", "B站搜索", "https://search.bilibili.com")
        self.assertEqual(items, [])

    def test_social_platform_test_reports_parse_failure_reason(self):
        crawler = NewsCrawler()
        crawler.set_account("知乎", cookie="z_c0=fake-cookie")
        crawler._request_html = lambda url, channel, timeout=10, **kwargs: (
            "",
            url,
            "network disabled in test",
        )
        result = crawler.test_social_platform("知乎", keyword="警方通报")
        self.assertFalse(result["reachable"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("network disabled", result["error"])
        self.assertIn("network disabled", result["message"])

    def test_social_records_include_auth_context(self):
        crawler = NewsCrawler()
        crawler.anti_crawl.delay = lambda *args, **kwargs: None
        crawler.set_account("B站", username="tester", cookie="SESSDATA=fake-cookie")
        nav_json = json.dumps({"data": {"isLogin": True, "uname": "tester", "mid": 123}}, ensure_ascii=False)
        search_html = """
        <div class="bili-video-card">
          <a href="//www.bilibili.com/video/BV1abc" title="警方通报视频讨论"></a>
          <h3 title="警方通报视频讨论">警方通报视频讨论</h3>
        </div>
        """

        def fake_request(url, channel, timeout=10, **kwargs):
            if "api.bilibili.com/x/web-interface/nav" in url:
                return nav_json, url, None
            if "search.bilibili.com" in url:
                return search_html, url, None
            return "", url, "disabled in test"

        crawler._request_html = fake_request
        data = crawler.crawl(
            ["警方通报"],
            max_results=1,
            social_platforms=["B站"],
            collect_level="最小采集",
            source_strategy="social",
            min_real_results=1,
        )
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["auth_mode"], "authorized_session")
        self.assertTrue(data[0]["login_confirmed"])
        self.assertIn("isLogin=true", data[0]["login_evidence"])
        self.assertEqual(crawler.last_meta["summary"]["login_confirmed_platform_count"], 1)

    def test_deduplicate_by_url_and_content(self):
        records = [
            {"url": "https://example.com/a", "title": "同一标题", "content": "短"},
            {"url": "https://example.com/a", "title": "同一标题", "content": "更完整的正文内容"},
            {"url": "", "title": "重复内容标题", "content": "重复内容正文"},
            {"url": "", "title": "重复内容标题", "content": "重复内容正文"},
        ]
        deduped = self.crawler._deduplicate_results(records)
        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[0]["content"], "更完整的正文内容")

    def test_deduplicate_same_body_across_different_urls(self):
        records = [
            {
                "url": "https://first.example.com/article",
                "title": "转载标题一",
                "content": "这是两个网页完全相同的正文内容。",
            },
            {
                "url": "https://second.example.com/repost",
                "title": "转载标题二",
                "content": "这是两个网页完全相同的正文内容。",
            },
        ]

        deduped = self.crawler._deduplicate_results(records)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["url"], "https://first.example.com/article")

    def test_deduplicate_keeps_different_bodies_with_same_prefix(self):
        shared_prefix = "相同开头" * 80
        records = [
            {
                "url": "https://example.com/a",
                "title": "标题一",
                "content": f"{shared_prefix}正文结尾甲",
            },
            {
                "url": "https://example.com/b",
                "title": "标题二",
                "content": f"{shared_prefix}正文结尾乙",
            },
        ]

        deduped = self.crawler._deduplicate_results(records)

        self.assertEqual(len(deduped), 2)

    def test_deduplicate_does_not_treat_failed_body_snippet_as_full_text(self):
        records = [
            {
                "url": "https://example.com/a",
                "content": "搜索接口返回的相同摘要",
                "body_fetch_status": "failed",
            },
            {
                "url": "https://example.com/b",
                "content": "搜索接口返回的相同摘要",
                "body_fetch_status": "failed",
            },
        ]

        deduped = self.crawler._deduplicate_results(records)

        self.assertEqual(len(deduped), 2)

    def test_parse_relative_times(self):
        now = datetime.now()
        just_now = self.crawler._parse_time("刚刚")
        hours_ago = self.crawler._parse_time("3小时前")
        yesterday = self.crawler._parse_time("昨天 12:30")
        date_text = self.crawler._parse_time("2026年7月1日")
        self.assertLess(abs((now - just_now).total_seconds()), 5)
        self.assertLess(abs(((now - timedelta(hours=3)) - hours_ago).total_seconds()), 5)
        self.assertEqual(yesterday.hour, 12)
        self.assertEqual(date_text.year, 2026)


class SiteSessionArticleTests(unittest.TestCase):
    ARTICLE_HTML = """
    <html><head><title>登录后新闻详情</title></head><body><article>
      <h1>登录后新闻详情</h1>
      <p>这是通过网站登录会话读取到的新闻正文，用于验证登录状态优先于匿名抓取方式，并且正文内容足够长。</p>
      <p>第二段继续补充事件经过、处置结果和公开回应，确保通用正文提取器能够稳定识别本次测试内容。</p>
    </article></body></html>
    """

    @staticmethod
    def _session_resolver(url):
        if urlparse(url).hostname == "news.example.com":
            return {
                "domain": "news.example.com",
                "storage_state": {"cookies": [], "origins": []},
                "session_version": "test-session-v1",
            }
        return None

    def test_matching_site_session_is_used_before_scrapling(self):
        class UnexpectedScrapling:
            @staticmethod
            def is_available():
                return True

            @staticmethod
            def fetch(**kwargs):
                raise AssertionError("会话成功后不应调用 Scrapling")

        adapters = type("Adapters", (), {"scrapling": UnexpectedScrapling()})()
        crawler = NewsCrawler(
            site_session_resolver=self._session_resolver,
            external_content_adapters=adapters,
        )
        browser_calls = []

        def fake_browser(**kwargs):
            browser_calls.append(kwargs)
            return self.ARTICLE_HTML, kwargs["url"], None

        crawler._request_browser_html = fake_browser
        crawler._request_html = lambda *args, **kwargs: self.fail("会话成功后不应普通回退")
        record = {"url": "https://news.example.com/a", "title": "短标题", "content": "摘要"}

        crawler._enrich_with_article_content(record)

        self.assertEqual(record["detail_source"], "site_browser_session")
        self.assertTrue(record["detail_enriched"])
        self.assertEqual(browser_calls[0]["exact_domain"], "news.example.com")
        self.assertEqual(json.loads(browser_calls[0]["storage_state_text"]), {"cookies": [], "origins": []})

    def test_plain_article_success_marks_body_success_even_when_time_is_unknown(self):
        unavailable_scrapling = type(
            "Scrapling",
            (),
            {"is_available": staticmethod(lambda: False)},
        )()
        crawler = NewsCrawler(
            external_content_adapters=type(
                "Adapters",
                (),
                {"scrapling": unavailable_scrapling},
            )(),
        )
        crawler._request_html = lambda url, channel: (self.ARTICLE_HTML, url, None)
        record = {
            "url": "https://news.example.com/a",
            "title": "新闻标题",
            "content": "搜索摘要" * 100,
            "pub_time": "",
            "time_basis": "unknown",
        }

        crawler._enrich_with_article_content(record)

        self.assertEqual(record["body_fetch_status"], "success")
        self.assertEqual(record["detail_source"], "ordinary_request")
        self.assertEqual(record["pub_time"], "")
        self.assertEqual(record["time_basis"], "unknown")
        self.assertIn("这是通过网站登录会话读取到的新闻正文", record["content"])

    def test_article_failure_keeps_snippet_and_marks_body_failed(self):
        unavailable_scrapling = type(
            "Scrapling",
            (),
            {"is_available": staticmethod(lambda: False)},
        )()
        crawler = NewsCrawler(
            external_content_adapters=type(
                "Adapters",
                (),
                {"scrapling": unavailable_scrapling},
            )(),
        )
        crawler._request_html = lambda url, channel: ("", url, "request timeout")
        record = {
            "url": "https://news.example.com/a",
            "title": "新闻标题",
            "content": "搜索接口返回的摘要",
            "pub_time": "2026-08-25T10:00:00",
            "time_basis": "published_time",
        }

        crawler._enrich_with_article_content(record)

        self.assertEqual(record["body_fetch_status"], "failed")
        self.assertEqual(record["content"], "搜索接口返回的摘要")
        self.assertEqual(record["pub_time"], "2026-08-25T10:00:00")

    def test_site_session_failure_falls_back_without_forwarding_state_to_scrapling(self):
        scrapling_calls = []

        class Scrapling:
            @staticmethod
            def is_available():
                return True

            @staticmethod
            def fetch(**kwargs):
                scrapling_calls.append(kwargs)
                return type("Outcome", (), {
                    "data": {
                        "html": SiteSessionArticleTests.ARTICLE_HTML.replace("网站登录会话", "Scrapling"),
                        "final_url": kwargs["url"],
                    }
                })()

        adapters = type("Adapters", (), {"scrapling": Scrapling()})()
        crawler = NewsCrawler(
            site_session_resolver=self._session_resolver,
            external_content_adapters=adapters,
        )
        crawler._request_browser_html = lambda **kwargs: (
            "",
            kwargs["url"],
            "site session authentication required",
        )
        crawler._request_html = lambda *args, **kwargs: self.fail("Scrapling 成功后不应普通回退")
        record = {"url": "https://news.example.com/a", "title": "短标题", "content": "摘要"}

        crawler._enrich_with_article_content(record)

        self.assertEqual(record["detail_source"], "scrapling_stealth")
        self.assertEqual(len(scrapling_calls), 1)
        self.assertNotIn("storage_state", scrapling_calls[0])
        self.assertNotIn("cookie", scrapling_calls[0])

    def test_site_session_short_content_falls_back_to_scrapling(self):
        scrapling_calls = []
        session_statuses = []
        session_html = "<html><body><article><p>" + ("会话页短内容" * 5) + "</p></article></body></html>"
        scrapling_html = (
            "<html><body><article><p>"
            + ("Scrapling 补充后的完整新闻正文，包含更充分的事件经过和公开回应。" * 10)
            + "</p></article></body></html>"
        )

        class Scrapling:
            @staticmethod
            def is_available():
                return True

            @staticmethod
            def fetch(**kwargs):
                scrapling_calls.append(kwargs)
                return type("Outcome", (), {
                    "data": {"html": scrapling_html, "final_url": kwargs["url"]}
                })()

        crawler = NewsCrawler(
            site_session_resolver=self._session_resolver,
            site_session_status_recorder=lambda domain, needs_relogin, session_version: session_statuses.append(
                (domain, needs_relogin, session_version)
            ),
            external_content_adapters=type("Adapters", (), {"scrapling": Scrapling()})(),
        )
        crawler._request_browser_html = lambda **kwargs: (
            session_html,
            kwargs["url"],
            None,
        )
        crawler._request_html = lambda *args, **kwargs: self.fail("Scrapling 成功后不应普通回退")
        record = {
            "url": "https://news.example.com/a",
            "title": "已有新闻标题",
            "content": "已有摘要内容" * 12,
        }

        crawler._enrich_with_article_content(record)

        self.assertEqual(len(scrapling_calls), 1)
        self.assertEqual(record["detail_source"], "scrapling_stealth")
        self.assertTrue(record["detail_enriched"])
        self.assertIn("Scrapling 补充后的完整新闻正文", record["content"])
        self.assertEqual(
            session_statuses,
            [("news.example.com", False, "test-session-v1")],
        )

    def test_scrapling_shell_page_falls_back_to_plain_request(self):
        class ShellPageScrapling:
            @staticmethod
            def is_available():
                return True

            @staticmethod
            def fetch(**kwargs):
                return type(
                    "Outcome",
                    (),
                    {
                        "data": {
                            "html": (
                                "<html><title>访问受限</title><body><p>"
                                + ("请完成安全验证后继续访问，本页面暂不提供新闻正文。" * 20)
                                + "</p></body></html>"
                            ),
                            "final_url": kwargs["url"],
                        }
                    },
                )()

        crawler = NewsCrawler(
            external_content_adapters=type(
                "Adapters",
                (),
                {"scrapling": ShellPageScrapling()},
            )(),
        )
        plain_calls = []

        def plain_request(url, channel, timeout=10):
            plain_calls.append((url, channel))
            return self.ARTICLE_HTML, url, None

        crawler._request_html = plain_request
        record = {
            "url": "https://news.example.com/a",
            "title": "已有新闻标题",
            "content": "公开摘要",
        }

        crawler._enrich_with_article_content(record)

        self.assertEqual(
            plain_calls,
            [("https://news.example.com/a", "article-detail")],
        )
        self.assertIn("这是通过网站登录会话读取到的新闻正文", record["content"])

    def test_deterministic_session_failure_circuit_breaks_domain_and_reports_relogin(self):
        resolver_calls = []
        browser_calls = []
        session_statuses = []

        def resolver(url):
            resolver_calls.append(url)
            return self._session_resolver(url)

        crawler = NewsCrawler(
            site_session_resolver=resolver,
            site_session_status_recorder=lambda domain, needs_relogin, session_version: session_statuses.append(
                (domain, needs_relogin, session_version)
            ),
            external_content_adapters=type(
                "Adapters",
                (),
                {"scrapling": type("Scrapling", (), {"is_available": staticmethod(lambda: False)})()},
            )(),
        )

        def failed_browser(**kwargs):
            browser_calls.append(kwargs)
            return "", kwargs["url"], "site session authentication required: HTTP 401"

        crawler._request_browser_html = failed_browser
        crawler._request_html = lambda url, channel: ("", url, "anonymous unavailable")

        for suffix in ("a", "b"):
            crawler._enrich_with_article_content({
                "url": f"https://news.example.com/{suffix}",
                "title": "新闻标题",
                "content": "公开摘要",
            })

        self.assertEqual(len(resolver_calls), 2)
        self.assertEqual(len(browser_calls), 1)
        self.assertEqual(
            session_statuses,
            [("news.example.com", True, "test-session-v1")],
        )

    def test_new_saved_session_is_retried_after_old_version_failed(self):
        versions = iter(("old-session", "new-session"))
        browser_versions = []
        session_statuses = []

        def resolver(_url):
            return {
                "domain": "news.example.com",
                "storage_state": {"cookies": [], "origins": []},
                "session_version": next(versions),
            }

        crawler = NewsCrawler(
            site_session_resolver=resolver,
            site_session_status_recorder=lambda domain, needs_relogin, session_version: session_statuses.append(
                (domain, needs_relogin, session_version)
            ),
            external_content_adapters=type(
                "Adapters",
                (),
                {"scrapling": type("Scrapling", (), {"is_available": staticmethod(lambda: False)})()},
            )(),
        )

        def browser_request(**kwargs):
            storage_state = json.loads(kwargs["storage_state_text"])
            browser_versions.append(storage_state)
            if len(browser_versions) == 1:
                return "", kwargs["url"], "site session authentication required"
            return self.ARTICLE_HTML, kwargs["url"], None

        crawler._request_browser_html = browser_request
        crawler._request_html = lambda url, channel: ("", url, "anonymous unavailable")

        first = {"url": "https://news.example.com/a", "title": "旧会话", "content": "摘要"}
        second = {"url": "https://news.example.com/b", "title": "新会话", "content": "摘要"}
        crawler._enrich_with_article_content(first)
        crawler._enrich_with_article_content(second)

        self.assertEqual(len(browser_versions), 2)
        self.assertEqual(second["detail_source"], "site_browser_session")
        self.assertEqual(
            session_statuses,
            [
                ("news.example.com", True, "old-session"),
                ("news.example.com", False, "new-session"),
            ],
        )

    def test_transient_session_failure_does_not_trip_relogin_circuit_breaker(self):
        browser_calls = []
        session_statuses = []
        crawler = NewsCrawler(
            site_session_resolver=self._session_resolver,
            site_session_status_recorder=lambda domain, needs_relogin, session_version: session_statuses.append(
                (domain, needs_relogin, session_version)
            ),
            external_content_adapters=type(
                "Adapters",
                (),
                {"scrapling": type("Scrapling", (), {"is_available": staticmethod(lambda: False)})()},
            )(),
        )

        def timed_out_browser(**kwargs):
            browser_calls.append(kwargs)
            return "", kwargs["url"], "browser session request timeout"

        crawler._request_browser_html = timed_out_browser
        crawler._request_html = lambda url, channel: ("", url, "anonymous unavailable")

        for suffix in ("a", "b"):
            crawler._enrich_with_article_content({
                "url": f"https://news.example.com/{suffix}",
                "title": "新闻标题",
                "content": "公开摘要",
            })

        self.assertEqual(len(browser_calls), 2)
        self.assertEqual(session_statuses, [])

    def test_crawl_resets_site_session_circuit_breaker_for_each_run(self):
        crawler = NewsCrawler()
        crawler._site_session_failed_versions.add(("news.example.com", "old-session"))
        crawler._site_session_statuses[("news.example.com", "old-session")] = True

        crawler.crawl(
            keywords=[],
            max_results=1,
            social_platforms=[],
            stable_sources=[],
            source_strategy="public_news",
            min_real_results=0,
        )

        self.assertEqual(crawler._site_session_failed_versions, set())
        self.assertEqual(crawler._site_session_statuses, {})

    def test_site_session_and_scrapling_failure_fall_back_to_plain_request(self):
        class UnavailableScrapling:
            @staticmethod
            def is_available():
                return False

        adapters = type("Adapters", (), {"scrapling": UnavailableScrapling()})()
        crawler = NewsCrawler(
            site_session_resolver=self._session_resolver,
            external_content_adapters=adapters,
        )
        crawler._request_browser_html = lambda **kwargs: ("", kwargs["url"], "HTTP 401")
        plain_calls = []

        def plain_request(url, channel, timeout=10):
            plain_calls.append((url, channel))
            return self.ARTICLE_HTML.replace("网站登录会话", "普通请求"), url, None

        crawler._request_html = plain_request
        record = {"url": "https://news.example.com/a", "title": "短标题", "content": "摘要"}

        crawler._enrich_with_article_content(record)

        self.assertEqual(plain_calls, [("https://news.example.com/a", "article-detail")])
        self.assertIn("普通请求", record["content"])

    def test_generic_browser_target_requires_https_exact_domain_and_public_dns(self):
        crawler = NewsCrawler()

        _, _, http_error = crawler._request_browser_html(
            url="http://news.example.com/a",
            platform="网站会话",
            storage_state_text="{}",
            exact_domain="news.example.com",
        )
        _, _, domain_error = crawler._request_browser_html(
            url="https://other.example.com/a",
            platform="网站会话",
            storage_state_text="{}",
            exact_domain="news.example.com",
        )
        with patch(
            "src.social_browser.socket.getaddrinfo",
            return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
            ],
        ):
            _, _, private_error = crawler._request_browser_html(
                url="https://news.example.com/a",
                platform="网站会话",
                storage_state_text="{}",
                exact_domain="news.example.com",
            )

        self.assertIn("HTTPS", http_error)
        self.assertIn("exact domain", domain_error)
        self.assertIn("public DNS", private_error)

    def test_generic_browser_proxy_mode_allows_fake_ip_and_blocks_private_subrequests(self):
        crawler = NewsCrawler(use_system_proxy=True)
        page = MagicMock()
        page.url = "https://news.example.com/a"
        page.main_frame = SimpleNamespace(parent_frame=None)
        page.goto.return_value = SimpleNamespace(status=200)
        page.evaluate.return_value = False
        page.locator.return_value.inner_text.return_value = "登录后新闻正文内容"
        page.content.return_value = self.ARTICLE_HTML
        routed = {}

        popup_frame = SimpleNamespace(parent_frame=None)
        iframe = SimpleNamespace(parent_frame=page.main_frame)

        def install_route(_pattern, handler):
            for name, request_url, is_navigation, frame in (
                ("private", "http://127.0.0.1/admin", False, None),
                ("private_dns", "https://private-dns.example/admin", False, None),
                ("public", "https://cdn.example.net/app.js", False, None),
                ("public_http_same", "http://news.example.com/asset.js", False, None),
                ("public_alt_port_same", "https://news.example.com:8443/asset.js", False, None),
                ("public_iframe", "https://news.example.com/embed", True, iframe),
                ("cross_navigation", "https://other.example.com/a", True, popup_frame),
            ):
                route = MagicMock()
                request = SimpleNamespace(
                    url=request_url,
                    is_navigation_request=lambda value=is_navigation: value,
                    frame=frame,
                )
                handler(route, request)
                routed[name] = route

        context = MagicMock()
        context.new_page.return_value = page
        context.route.side_effect = install_route
        websocket_routes = {}

        def install_websocket_route(_pattern, handler):
            for name, request_url in (
                ("private", "ws://127.0.0.1/admin"),
                ("cross_domain", "wss://other.example.com/socket"),
                ("same_domain", "wss://news.example.com/socket"),
            ):
                websocket = MagicMock()
                websocket.url = request_url
                handler(websocket)
                websocket_routes[name] = websocket

        context.route_web_socket.side_effect = install_websocket_route
        context_events = {}
        context.on.side_effect = lambda event, handler: context_events.setdefault(event, handler)
        browser = MagicMock()
        browser.new_context.return_value = context
        playwright = MagicMock()
        playwright.chromium.launch.return_value = browser
        playwright_context = MagicMock()
        playwright_context.__enter__.return_value = playwright

        dns_lookups = []

        def resolve_public_dns(host, _port, **_kwargs):
            dns_lookups.append(host)
            if host == "private-dns.example":
                return [
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.89", 443)),
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443)),
                ]
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.89", 443)),
            ]

        with (
            patch(
                "src.social_browser.socket.getaddrinfo",
                side_effect=resolve_public_dns,
            ),
            patch(
                "src.social_browser._has_loopback_system_proxy",
                return_value=True,
            ),
            patch("src.crawler.load_playwright", return_value=(lambda: playwright_context, TimeoutError)),
            patch("src.crawler.get_adapter", side_effect=AssertionError("generic 会话不应读取社交适配器")),
        ):
            html, final_url, error = crawler._request_browser_html(
                url="https://news.example.com/a",
                platform="网站会话",
                storage_state_text='{"cookies": [], "origins": []}',
                exact_domain="news.example.com",
            )

        self.assertIsNone(error)
        self.assertEqual(final_url, "https://news.example.com/a")
        self.assertIn("登录后新闻详情", html)
        self.assertEqual(browser.new_context.call_args.kwargs["service_workers"], "block")
        page.route.assert_not_called()
        context.route.assert_called_once()
        context.route_web_socket.assert_called_once()
        routed["private"].abort.assert_called_once_with("blockedbyclient")
        routed["private"].continue_.assert_not_called()
        routed["private_dns"].abort.assert_called_once_with("blockedbyclient")
        routed["public"].continue_.assert_called_once_with()
        routed["public_http_same"].abort.assert_called_once_with("blockedbyclient")
        routed["public_http_same"].continue_.assert_not_called()
        routed["public_alt_port_same"].abort.assert_called_once_with("blockedbyclient")
        routed["public_alt_port_same"].continue_.assert_not_called()
        routed["public_iframe"].continue_.assert_called_once_with()
        routed["cross_navigation"].abort.assert_called_once_with("blockedbyclient")
        websocket_routes["private"].close.assert_called_once()
        websocket_routes["private"].connect_to_server.assert_not_called()
        websocket_routes["cross_domain"].close.assert_called_once()
        websocket_routes["cross_domain"].connect_to_server.assert_not_called()
        websocket_routes["same_domain"].connect_to_server.assert_called_once_with()
        websocket_routes["same_domain"].close.assert_not_called()
        self.assertIn("cdn.example.net", dns_lookups)
        popup = MagicMock()
        context_events["page"](popup)
        popup.close.assert_called_once_with()

        page.url = "https://other.example.com/a"
        with (
            patch(
                "src.social_browser.socket.getaddrinfo",
                return_value=[
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.89", 443)),
                ],
            ),
            patch(
                "src.social_browser._has_loopback_system_proxy",
                return_value=True,
            ),
            patch("src.crawler.load_playwright", return_value=(lambda: playwright_context, TimeoutError)),
            patch("src.crawler.get_adapter", side_effect=AssertionError("generic 会话不应读取社交适配器")),
        ):
            _, rejected_url, final_error = crawler._request_browser_html(
                url="https://news.example.com/a",
                platform="网站会话",
                storage_state_text='{"cookies": [], "origins": []}',
                exact_domain="news.example.com",
            )

        self.assertEqual(rejected_url, "https://other.example.com/a")
        self.assertIn("exact domain", final_error)

    def test_obvious_login_page_and_auth_status_are_session_failures(self):
        crawler = NewsCrawler()

        self.assertTrue(crawler._site_session_auth_error(401, "https://news.example.com/a", ""))
        self.assertTrue(crawler._site_session_auth_error(403, "https://news.example.com/a", ""))
        self.assertTrue(crawler._site_session_auth_error(
            200,
            "https://news.example.com/login",
            '<form><input type="password" name="password"></form>',
        ))
        self.assertEqual(
            crawler._site_session_auth_error(
                200,
                "https://news.example.com/a",
                '<form><input type="password" name="password"></form>',
            ),
            "",
        )
        self.assertEqual(
            crawler._site_session_auth_error(200, "https://news.example.com/a", self.ARTICLE_HTML),
            "",
        )
        article_with_hidden_login = self.ARTICLE_HTML.replace(
            "</body>",
            '<div hidden><form><input type="password" name="password"></form></div></body>',
        )
        self.assertEqual(
            crawler._site_session_auth_error(
                200,
                "https://news.example.com/a",
                article_with_hidden_login,
            ),
            "",
        )

        page = MagicMock()
        page.locator.return_value.count.return_value = 1
        self.assertTrue(crawler._site_session_has_visible_password(page))
        page.locator.return_value.count.return_value = 0
        self.assertFalse(crawler._site_session_has_visible_password(page))

    def test_public_entrypoints_accept_optional_site_session_resolver(self):
        resolver = lambda url: None
        recorder = lambda domain, needs_relogin, session_version: None

        crawler = ProductionNewsCrawler(
            site_session_resolver=resolver,
            site_session_status_recorder=recorder,
        )

        self.assertIs(crawler.site_session_resolver, resolver)
        self.assertIs(crawler.site_session_status_recorder, recorder)
        self.assertIn("site_session_resolver", inspect.signature(crawl_and_save).parameters)
        self.assertIn("site_session_status_recorder", inspect.signature(crawl_and_save).parameters)

    def test_default_policy_allows_saved_session_without_robots_but_keeps_explicit_disable(self):
        def unexpected_fetch(*args, **kwargs):
            raise AssertionError("默认授权会话不应把 robots 当前置总开关")

        policy = SourceAccessPolicy(
            Path("config") / "source_access_rules.json",
            fetcher=unexpected_fetch,
        )

        unregistered = policy.check(
            "https://unregistered-session.example/article/1",
            access_mode=AUTHORIZED_SESSION_ACCESS_MODE,
        )
        explicitly_disabled = policy.check(
            "https://www.baidu.com/s?wd=test",
            access_mode=AUTHORIZED_SESSION_ACCESS_MODE,
        )

        self.assertTrue(unregistered.allowed)
        self.assertEqual(unregistered.code, "authorized_session_allowed")
        self.assertFalse(explicitly_disabled.allowed)
        self.assertEqual(explicitly_disabled.code, "authorized_session_disabled")


class DownstreamCompatibilityTests(unittest.TestCase):
    def test_preprocessor_and_analyzer_accept_new_contract(self):
        data = [{
            "title": "警方通报突发事件处置情况",
            "content": "公安机关发布最新情况，调查处置工作正在依法推进。",
            "url": "https://news.example.com/a",
            "pub_time": "2026-07-01T10:30:00",
            "source": "平安湖北",
            "platform": "微信公众平台",
            "source_type": "official",
            "keyword": "警方通报",
            "region": "湖北省",
            "data_type": "real",
            "collector": "搜狗微信",
            "crawl_time": "2026-07-01T10:31:00",
            "event_type": "police_briefing",
            "heat_index": 12.5,
        }]
        records = Preprocessor().process(data)
        self.assertEqual(records[0].source, "微信公众平台")
        self.assertEqual(records[0].extra["source_type"], "official")
        ctx = Analyzer(config={}).analyze(records)
        self.assertEqual(ctx.total_posts, 1)
        self.assertTrue(ctx.official_responses)


if __name__ == "__main__":
    unittest.main()
