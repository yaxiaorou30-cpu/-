import json
import unittest
from datetime import datetime, timedelta

from src.analyzer import Analyzer
from src.crawler import (
    NewsCrawler as ProductionNewsCrawler,
    PLATFORM_LIST,
    STABLE_CHANNELS,
    STABLE_SOURCE_REGISTRY,
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
from tests.helpers import AllowAllSourcePolicy


class NewsCrawler(ProductionNewsCrawler):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("source_policy", AllowAllSourcePolicy())
        kwargs.setdefault("use_external_social_adapters", False)
        super().__init__(*args, **kwargs)


class CrawlerParsingTests(unittest.TestCase):
    def setUp(self):
        self.crawler = NewsCrawler()

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
