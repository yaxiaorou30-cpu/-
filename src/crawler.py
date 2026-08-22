#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
舆情采集模块
支持多平台、多渠道、多阈值等级采集
"""
import json
import re
import random
import time
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
from datetime import datetime, timedelta
from typing import Callable, List, Dict, Optional, Tuple
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
    CRAWLER_AVAILABLE = True
except ImportError:
    CRAWLER_AVAILABLE = False

from src.utils.logger import get_logger
from src.heat_analyzer import PROVINCES_DATA, get_all_provinces, get_cities_by_province
from src.social_browser import (
    SOCIAL_PLATFORM_ADAPTERS,
    XIAOHONGSHU_SEARCH_SOURCES,
    extract_article_from_html,
    extract_search_items_from_html,
    extract_tieba_detail_from_html,
    extract_weibo_detail_from_payload,
    extract_xiaohongshu_detail_from_html,
    extract_xiaohongshu_items_from_api_payload,
    get_adapter,
    load_playwright,
)
from src.social_cli_adapters import (
    ExternalSocialAdapterRegistry,
    create_default_external_social_registry,
)
from src.external_content_adapters import (
    ExternalContentAdapters,
    create_default_external_content_adapters,
)
from src.sensitive_artifacts import DiagnosticSnapshotStore
from src.quality_checks import build_collection_assessment
from src.source_policy import (
    AUTHORIZED_SESSION_ACCESS_MODE,
    EXTERNAL_ADAPTER_ACCESS_MODE,
    PUBLIC_CRAWLER_ACCESS_MODE,
    SOURCE_POLICY_USER_AGENT,
    SourceAccessPolicy,
)

logger = get_logger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


TIME_RANGE_MAP = {
    "今天": 0,
    "近一周": 7,
    "近一个月": 30,
    "近一年": 365,
    "近三年": 1095,
    "近五年": 1825,
    "更早": -1,
    "自定义": -2,
}

PRIMARY_SOCIAL_PLATFORMS = ["微博", "B站", "小红书", "抖音", "百度贴吧"]

PLATFORM_LIST = PRIMARY_SOCIAL_PLATFORMS + [
    "知乎", "微信公众平台", "豆瓣", "快手", "今日头条"
]

COLLECT_LEVELS = {
    "深度采集": {"max_results": 100, "min_content": 50, "multi_channel": True},
    "标准采集": {"max_results": 50, "min_content": 30, "multi_channel": True},
    "快速采集": {"max_results": 20, "min_content": 20, "multi_channel": False},
    "最小采集": {"max_results": 10, "min_content": 10, "multi_channel": False},
}

STABLE_SOURCE_REGISTRY = [
    {
        "name": "天津市公安局公安要闻",
        "parser": "official_listing",
        "priority": 5,
        "timeout": 15,
        "enabled": True,
        "source_region": "天津市",
        "url_template": "https://ga.tj.gov.cn/gaxc/gayw/",
        "link_selectors": ["li.comItem a"],
        "article_path_prefixes": ["/gaxc/gayw/"],
        "require_date": True,
    },
    {
        "name": "天津市公安局出入境通知",
        "parser": "official_listing",
        "priority": 10,
        "timeout": 15,
        "enabled": True,
        "source_region": "天津市",
        "url_template": "https://ga.tj.gov.cn/xxfb/tztg/crj1/",
        "link_selectors": ["li.comItem a"],
        "article_path_prefixes": ["/xxfb/tztg/crj1/"],
        "require_date": True,
    },
    {
        "name": "天津市政府新闻发布会",
        "parser": "official_listing",
        "priority": 15,
        "timeout": 15,
        "enabled": True,
        "source_region": "天津市",
        "url_template": "https://www.tj.gov.cn/sy/xwfbh/xwfbh_210907/",
        "link_selectors": [".list-circle-red .list-item-con a"],
        "article_path_prefixes": ["/sy/xwfbh/xwfbh_210907/"],
        "require_date": True,
    },
    {
        "name": "天津市应急管理局工作动态",
        "parser": "official_listing",
        "priority": 20,
        "timeout": 15,
        "enabled": True,
        "source_region": "天津市",
        "url_template": "https://yjgl.tj.gov.cn/SY5239/bjdt/",
        "link_selectors": ["li.page_t a"],
        "article_path_prefixes": ["/SY5239/bjdt/"],
        "require_date": True,
    },
    {
        "name": "国家移民管理局移民管理要闻",
        "parser": "official_listing",
        "priority": 30,
        "timeout": 15,
        "enabled": True,
        "source_region": "",
        "url_template": "https://www.nia.gov.cn/n741435/n741517/index.html",
        "link_selectors": [".list_bd li a"],
        "article_path_prefixes": ["/n897453/"],
        "require_date": True,
    },
    {
        "name": "外交部新闻",
        "parser": "official_listing",
        "priority": 40,
        "timeout": 15,
        "enabled": True,
        "source_region": "",
        "url_template": "https://www.mfa.gov.cn/web/wjbxw_new/",
        "link_selectors": [".newsBd .list1 li a"],
        "article_path_prefixes": ["/web/wjbxw_new/"],
        "require_date": True,
    },
    {
        "name": "应急管理部灾害事故信息",
        "parser": "official_listing",
        "priority": 50,
        "timeout": 15,
        "enabled": True,
        "source_region": "",
        "url_template": "https://www.mem.gov.cn/xw/zhsgxx/index.shtml",
        "link_selectors": [".cont li a"],
        "article_path_prefixes": ["/xw/yjglbgzdt/", "/xw/yjyw/"],
        "require_date": True,
    },
    {
        "name": "百度新闻",
        "parser": "baidu",
        "priority": 110,
        "timeout": 10,
        "enabled": False,
        "disabled_reason": "robots.txt 明确禁止自动访问搜索结果路径",
        "url_template": "https://www.baidu.com/s?wd={query}&tn=news&rtt=4",
    },
    {
        "name": "百度资讯",
        "parser": "baidu",
        "priority": 120,
        "timeout": 10,
        "enabled": False,
        "disabled_reason": "robots.txt 明确禁止自动访问搜索结果路径",
        "url_template": "https://www.baidu.com/s?wd={query}&tn=news&rtt=1",
    },
    {
        "name": "搜狗新闻",
        "parser": "sogou_news",
        "priority": 130,
        "timeout": 10,
        "enabled": False,
        "disabled_reason": "robots.txt 明确禁止自动访问新闻搜索路径",
        "url_template": "https://news.sogou.com/news?query={query}",
    },
    {
        "name": "搜狗微信",
        "parser": "sogou_weixin",
        "priority": 140,
        "timeout": 10,
        "enabled": False,
        "disabled_reason": "robots.txt 明确禁止自动访问微信搜索路径",
        "url_template": "https://weixin.sogou.com/weixin?type=2&query={query}",
    },
]

STABLE_CHANNELS = {source["name"] for source in STABLE_SOURCE_REGISTRY}
SOCIAL_ENHANCEMENT_PLATFORMS = {
    "微博",
    "知乎",
    "B站",
    "百度贴吧",
    "豆瓣",
    "小红书",
    "抖音",
    "快手",
    "今日头条",
    "微信公众平台",
}
SOURCE_STRATEGIES = ("stable_first", "stable", "social", "hybrid")


class AntiCrawlStrategy:
    """反爬策略"""

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
        "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile",
    ]

    def __init__(self):
        self.request_count = 0
        self.last_request_time = 0

    def get_random_headers(self) -> Dict:
        ua = random.choice(self.USER_AGENTS)
        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
        }

    def delay(self, min_sec: float = 2, max_sec: float = 5):
        elapsed = time.time() - self.last_request_time
        wait = random.uniform(min_sec, max_sec)
        
        if self.request_count > 50:
            wait *= 2
        elif self.request_count > 20:
            wait *= 1.5
        
        if elapsed < wait:
            time.sleep(wait - elapsed)
        
        self.last_request_time = time.time()
        self.request_count += 1

    def reset_counter(self):
        self.request_count = 0


class AccountManager:
    """账号管理（仅内存存储）"""

    def __init__(self):
        self._accounts: Dict[str, Dict] = {}

    def set_account(
        self,
        platform: str,
        username: str = "",
        password: str = "",
        cookie: str = "",
        note: str = "",
        browser_session: str = "",
        browser_cookie: str = "",
        session_mode: str = "",
        browser_login_confirmed: Optional[bool] = None,
        browser_login_evidence: str = "",
    ):
        username = (username or "").strip()
        password = password or ""
        cookie = (cookie or "").strip()
        browser_cookie = (browser_cookie or "").strip()
        browser_session = browser_session or ""
        effective_cookie = cookie or browser_cookie
        effective_mode = session_mode or ("manual_cookie" if cookie else ("browser_session" if browser_cookie else ""))
        note = (note or "").strip()
        if username or password or effective_cookie or browser_session:
            self._accounts[platform] = {
                "username": username,
                "password_enc": self._encrypt(password) if password else "",
                "cookie_enc": self._encrypt(effective_cookie) if effective_cookie else "",
                "browser_session_enc": self._encrypt(browser_session) if browser_session else "",
                "browser_cookie_enc": self._encrypt(browser_cookie) if browser_cookie else "",
                "session_mode": effective_mode or "cookie",
                "browser_login_confirmed": browser_login_confirmed,
                "browser_login_evidence": str(browser_login_evidence or ""),
                "note": note,
            }

    def get_account(self, platform: str) -> Optional[Dict]:
        if platform in self._accounts:
            acc = self._accounts[platform]
            return {
                "username": acc.get("username", ""),
                "password": self._decrypt(acc.get("password_enc", "")) if acc.get("password_enc") else "",
                "cookie": self._decrypt(acc.get("cookie_enc", "")) if acc.get("cookie_enc") else "",
                "browser_session": self._decrypt(acc.get("browser_session_enc", "")) if acc.get("browser_session_enc") else "",
                "browser_cookie": self._decrypt(acc.get("browser_cookie_enc", "")) if acc.get("browser_cookie_enc") else "",
                "session_mode": acc.get("session_mode", "cookie"),
                "browser_login_confirmed": acc.get("browser_login_confirmed"),
                "browser_login_evidence": acc.get("browser_login_evidence", ""),
                "note": acc.get("note", ""),
            }
        return None

    def list_authorized_platforms(self) -> List[str]:
        return [
            platform for platform, account in self._accounts.items()
            if account.get("cookie_enc") or account.get("browser_session_enc") or account.get("username")
        ]

    def clear_all(self):
        self._accounts.clear()

    def _encrypt(self, text: str) -> str:
        key = "舆情系统安全密钥"
        return "".join(chr(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(text))

    def _decrypt(self, text: str) -> str:
        return self._encrypt(text)


class NewsCrawler:
    """舆情采集器"""

    def __init__(
        self,
        use_system_proxy: bool = False,
        use_external_social_adapters: bool = False,
        external_social_registry: Optional[ExternalSocialAdapterRegistry] = None,
        use_external_content_adapters: Optional[bool] = None,
        external_content_adapters: Optional[ExternalContentAdapters] = None,
        source_policy: Optional[SourceAccessPolicy] = None,
        enable_debug_snapshots: bool = False,
        diagnostic_store: Optional[DiagnosticSnapshotStore] = None,
        live_browser_reader: Optional[Callable[[str, str, int], Tuple[str, str, Optional[str]]]] = None,
        live_login_probe: Optional[Callable[[str, int], Dict]] = None,
    ):
        self.session = requests.Session() if CRAWLER_AVAILABLE else None
        if self.session:
            self.session.trust_env = bool(use_system_proxy)
        self.use_system_proxy = bool(use_system_proxy)
        self.anti_crawl = AntiCrawlStrategy()
        self.account_manager = AccountManager()
        self.last_meta: Dict = {}
        self._auth_probe_cache: Dict[str, Dict] = {}
        self._source_acceptance_mode = False
        self._active_parser_hint = ""
        self.live_browser_reader = live_browser_reader
        self.live_login_probe = live_login_probe
        self.source_policy = source_policy or SourceAccessPolicy(
            PROJECT_ROOT / "config" / "source_access_rules.json",
            audit_path=PROJECT_ROOT / "data" / "source_policy_cache.json",
            use_system_proxy=self.use_system_proxy,
        )
        self.diagnostic_store = diagnostic_store or DiagnosticSnapshotStore(
            PROJECT_ROOT,
            enabled=enable_debug_snapshots,
        )
        self.external_social_registry = external_social_registry
        if self.external_social_registry is None and use_external_social_adapters:
            self.external_social_registry = create_default_external_social_registry()
        if use_external_content_adapters is None:
            use_external_content_adapters = use_external_social_adapters
        self.external_content_adapters = external_content_adapters
        if self.external_content_adapters is None and use_external_content_adapters:
            self.external_content_adapters = create_default_external_content_adapters()

    def set_account(
        self,
        platform: str,
        username: str = "",
        password: str = "",
        cookie: str = "",
        note: str = "",
        browser_session: str = "",
        browser_cookie: str = "",
        session_mode: str = "",
        browser_login_confirmed: Optional[bool] = None,
        browser_login_evidence: str = "",
    ):
        self.account_manager.set_account(
            platform,
            username,
            password,
            cookie,
            note,
            browser_session=browser_session,
            browser_cookie=browser_cookie,
            session_mode=session_mode,
            browser_login_confirmed=browser_login_confirmed,
            browser_login_evidence=browser_login_evidence,
        )

    def crawl(
        self,
        keywords: List[str],
        max_results: int = None,
        platforms: List[str] = None,
        social_platforms: List[str] = None,
        stable_sources: List[str] = None,
        region: str = None,
        time_range: str = "近一周",
        collect_level: str = "标准采集",
        source_strategy: str = "stable_first",
        min_real_results: int = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
        source_acceptance: bool = False,
    ) -> List[Dict]:
        """
        多渠道舆情采集
        
        Args:
            keywords: 关键词列表
            max_results: 最大结果数
            platforms: 兼容旧参数，作为社交平台列表使用
            social_platforms: 第二阶段社交平台增强列表
            stable_sources: 第一阶段政府官网名称列表
            region: 地区（省份+城市）
            time_range: 时间范围
            collect_level: 采集阈值等级
            source_strategy: stable_first / stable / social / hybrid
            min_real_results: 最低真实结果数，默认取采集等级的 min_content
            source_acceptance: 仅验证稳定源连通性、解析和最小字段，不按关键词/时间过滤
        """
        source_strategy = self._normalize_source_strategy(source_strategy)
        self._source_acceptance_mode = bool(source_acceptance and source_strategy == "stable")
        level_config = COLLECT_LEVELS.get(collect_level, COLLECT_LEVELS["标准采集"])
        target_count = max_results or level_config["max_results"]
        min_real = min_real_results if min_real_results is not None else level_config["min_content"]
        min_real = min(min_real, target_count)

        if social_platforms is None:
            social_platforms = platforms if platforms is not None else PRIMARY_SOCIAL_PLATFORMS
        stable_source_names = self._select_stable_source_names(stable_sources)
        results = []
        failures = []
        start_time, end_time = self._parse_time_range(time_range)
        province, city = self._parse_region(region)
        started_at = datetime.now()
        self._auth_probe_cache = {}

        logger.info(f"开始采集: 关键词={keywords}, 地区={region or '全国'}")
        logger.info(
            f"采集等级: {collect_level}, 最大结果: {target_count}, "
            f"数据源策略: {source_strategy}, 稳定源={stable_source_names}, "
            f"社交增强={social_platforms}"
        )
        self._emit_progress(progress_callback, {
            "type": "crawl_start",
            "message": "采集任务开始",
            "keywords": keywords,
            "source_strategy": source_strategy,
            "stable_sources": stable_source_names,
            "social_platforms": social_platforms,
        })

        if not CRAWLER_AVAILABLE:
            message = "爬虫依赖未安装，请安装 requests 和 beautifulsoup4"
            logger.warning(message)
            failures.append({"channel": "dependency", "url": "", "error": message})

        if CRAWLER_AVAILABLE:
            try:
                for keyword in keywords:
                    if source_strategy in ("stable_first", "stable"):
                        stable_requests_all = self._build_stable_source_requests(
                            keyword=keyword,
                            province=None if self._source_acceptance_mode else province,
                            city=None if self._source_acceptance_mode else city,
                            stable_sources=stable_source_names,
                        )
                        stable_requests = stable_requests_all
                        if not level_config.get("multi_channel", True):
                            stable_requests = stable_requests[:3]
                        collected, source_failures = self._collect_from_source_requests(
                            source_requests=stable_requests,
                            keyword=keyword,
                            region=region or "全国",
                            collect_level=collect_level,
                            start_time=None if self._source_acceptance_mode else start_time,
                            end_time=None if self._source_acceptance_mode else end_time,
                            remaining=max(target_count - len(results), 0),
                            progress_callback=progress_callback,
                        )
                        results = self._deduplicate_results(results + collected)
                        failures.extend(source_failures)
                        logger.info(f"政府官网关键词 '{keyword}' 新增 {len(collected)} 条")

                        stable_real_count = self._count_real_by_group(results, "stable")
                        if (
                            source_strategy == "stable_first"
                            and not level_config.get("multi_channel", True)
                            and stable_real_count < min_real
                            and len(stable_requests_all) > len(stable_requests)
                            and len(results) < target_count
                        ):
                            extra_requests = stable_requests_all[len(stable_requests):]
                            collected, source_failures = self._collect_from_source_requests(
                                source_requests=extra_requests,
                                keyword=keyword,
                                region=region or "全国",
                                collect_level=collect_level,
                                start_time=None if self._source_acceptance_mode else start_time,
                                end_time=None if self._source_acceptance_mode else end_time,
                                remaining=max(target_count - len(results), 0),
                                progress_callback=progress_callback,
                            )
                            results = self._deduplicate_results(results + collected)
                            failures.extend(source_failures)
                            logger.info(f"政府官网补充采集关键词 '{keyword}' 新增 {len(collected)} 条")
                        if len(results) >= target_count:
                            break

                    if len(results) >= target_count:
                        break

                stable_real_count = self._count_real_by_group(results, "stable")
                should_run_social = (
                    source_strategy == "social"
                    or (
                        source_strategy == "stable_first"
                        and stable_real_count >= min_real
                        and len(results) < target_count
                    )
                )

                if should_run_social:
                    for keyword in keywords:
                        for platform in social_platforms:
                            social_requests = self._build_social_source_requests(platform, keyword, province, city)
                            if not level_config.get("multi_channel", True):
                                social_requests = social_requests[:1]
                            remaining = (
                                target_count
                                if source_strategy == "social"
                                else max(target_count - len(results), 0)
                            )
                            collected, source_failures = self._collect_from_source_requests(
                                source_requests=social_requests,
                                keyword=keyword,
                                region=region or "全国",
                                collect_level=collect_level,
                                start_time=start_time,
                                end_time=end_time,
                                remaining=remaining,
                                progress_callback=progress_callback,
                            )
                            results = self._deduplicate_results(results + collected)
                            failures.extend(source_failures)
                            logger.info(f"社交增强平台 '{platform}' 关键词 '{keyword}' 新增 {len(collected)} 条")
                            if source_strategy != "social" and len(results) >= target_count:
                                break
                        if source_strategy != "social" and len(results) >= target_count:
                            break
                elif source_strategy == "stable_first" and stable_real_count < min_real:
                    logger.warning(f"政府官网真实数据不足，暂不进入社交平台采集: {stable_real_count}/{min_real}")
            except Exception as e:
                logger.warning(f"真实采集异常: {e}")
                failures.append({"channel": "crawler", "url": "", "error": str(e)})

        self.anti_crawl.reset_counter()

        results = self._deduplicate_results(results)
        if source_strategy == "social":
            results = self._limit_results_with_platform_coverage(
                records=results,
                max_results=target_count,
                platforms=social_platforms,
            )
        real_count = sum(1 for r in results if r.get("data_type") == "real")
        if real_count < min_real:
            logger.warning(f"真实采集数据不足: {real_count}/{min_real}")

        results = results[:target_count]
        self.last_meta = self._build_meta(
            data=results,
            keywords=keywords,
            platforms=social_platforms,
            stable_sources=stable_source_names,
            region=region or "全国",
            time_range=time_range,
            collect_level=collect_level,
            source_strategy=source_strategy,
            min_real_results=min_real,
            failures=failures,
            started_at=started_at,
            source_acceptance=self._source_acceptance_mode,
        )
        self._emit_progress(progress_callback, {
            "type": "crawl_complete",
            "message": "采集任务完成",
            "summary": self.last_meta.get("summary", {}),
        })
        return results

    def _request_html(
        self,
        url: str,
        channel: str,
        timeout: int = 10,
        access_mode: str = PUBLIC_CRAWLER_ACCESS_MODE,
    ) -> Tuple[str, str, Optional[str]]:
        """请求公开网页，不做登录绕过。"""
        if not self.session:
            return "", url, "requests session unavailable"

        last_error = None
        for attempt in range(2):
            current_url = url
            try:
                for redirect_count in range(6):
                    decision = self.source_policy.check(
                        current_url,
                        channel,
                        access_mode=access_mode,
                    )
                    if not decision.allowed:
                        return (
                            "",
                            current_url,
                            f"source policy blocked [{decision.code}]: {decision.reason}",
                        )
                    headers = self._build_request_headers(current_url, channel)
                    resp = self.session.get(
                        current_url,
                        headers=headers,
                        timeout=timeout,
                        allow_redirects=False,
                    )
                    location = (getattr(resp, "headers", {}) or {}).get("Location")
                    if 300 <= resp.status_code < 400 and location:
                        if redirect_count >= 5:
                            last_error = "too many redirects"
                            break
                        current_url = urljoin(current_url, location)
                        continue
                    break
                else:  # pragma: no cover - bounded loop always exits via break/return.
                    last_error = "too many redirects"
                    continue
                if last_error == "too many redirects":
                    continue
                if resp.status_code != 200:
                    last_error = f"HTTP {resp.status_code}"
                    if resp.status_code in (401, 403):
                        break
                    if resp.status_code == 429:
                        retry_after = (getattr(resp, "headers", {}) or {}).get("Retry-After")
                        if attempt == 0 and str(retry_after or "").strip().isdigit():
                            retry_seconds = max(0, int(retry_after))
                            if retry_seconds <= min(timeout, 60):
                                time.sleep(retry_seconds)
                                continue
                            last_error = f"HTTP 429; Retry-After={retry_seconds}s"
                        break
                    continue
                text = self._decode_response_text(resp)
                if not text.strip():
                    last_error = "empty response"
                    continue
                return text, getattr(resp, "url", current_url) or current_url, None
            except Exception as e:
                last_error = str(e)
                if attempt == 0:
                    time.sleep(0.5)

        logger.debug(f"{channel} 请求失败: {last_error}")
        return "", url, last_error or "request failed"

    @classmethod
    def _decode_response_text(cls, resp) -> str:
        content = resp.content or b""
        if not content:
            return ""

        candidates = []
        content_type = resp.headers.get("Content-Type", "") if getattr(resp, "headers", None) else ""
        header_match = re.search(r"charset=([A-Za-z0-9_\-]+)", content_type, re.I)
        if header_match:
            candidates.append(header_match.group(1))

        head = content[:4096]
        meta_match = re.search(br"<meta[^>]+charset=[\"']?\s*([A-Za-z0-9_\-]+)", head, re.I)
        if meta_match:
            try:
                candidates.append(meta_match.group(1).decode("ascii", errors="ignore"))
            except Exception:
                pass

        candidates.extend([
            "utf-8",
            "utf-8-sig",
            "gb18030",
            "gbk",
            getattr(resp, "apparent_encoding", None),
            getattr(resp, "encoding", None),
        ])

        seen = set()
        decoded_options = []
        for encoding in candidates:
            normalized = str(encoding or "").strip()
            if not normalized:
                continue
            key = normalized.lower().replace("_", "-")
            if key in seen:
                continue
            seen.add(key)
            try:
                text = content.decode(normalized, errors="replace")
            except LookupError:
                continue
            decoded_options.append((cls._decoded_text_score(text), text, normalized))

        if not decoded_options:
            return content.decode("utf-8", errors="replace")
        decoded_options.sort(key=lambda item: item[0])
        return decoded_options[0][1]

    @staticmethod
    def _decoded_text_score(text: str) -> float:
        if not text:
            return 10_000
        replacement = text.count("\ufffd")
        cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
        mojibake_markers = (
            "Ã",
            "Â",
            "â€",
            "â€œ",
            "â€�",
            "å",
            "æ",
            "ç",
            "è",
            "é",
            "ä",
            "ã€",
            "ï¼",
            "ðŸ",
        )
        mojibake = sum(text.count(marker) for marker in mojibake_markers)
        control = len(re.findall(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", text))
        return replacement * 100 + mojibake * 8 + control * 20 - cjk * 0.5

    def _request_source_html(
        self,
        url: str,
        channel: str,
        platform: str,
        source_group: str,
        timeout: int = 10,
    ) -> Tuple[str, str, Optional[str]]:
        account = self.account_manager.get_account(platform) or {}
        if (
            source_group == "social"
            and account.get("session_mode") == "browser_session"
            and account.get("browser_session")
        ):
            live_error = ""
            require_visible_browser = platform in {"小红书", "抖音"}
            if self.live_browser_reader and require_visible_browser:
                try:
                    live_html, live_url, live_error = self.live_browser_reader(
                        platform,
                        url,
                        max(timeout, 12),
                    )
                except Exception as exc:
                    live_html, live_url = "", url
                    live_error = f"{platform} auxiliary browser read failed: {exc}"
                if not live_error:
                    return live_html, live_url, None
                if "human_verification_required:" in live_error:
                    return "", live_url, live_error
                return (
                    "",
                    live_url,
                    f"visible_browser_failed: {live_error}",
                )
            html, final_url, error = self._request_browser_html(
                url=url,
                platform=platform,
                storage_state_text=account.get("browser_session", ""),
                timeout=timeout,
            )
            if not error:
                return html, final_url, None
            logger.debug(f"{channel} 浏览器会话请求失败，回退普通请求: {error}")
            fallback_html, fallback_url, fallback_error = self._request_html(url, channel, timeout=timeout)
            if fallback_error:
                return "", fallback_url, f"{error}; fallback failed: {fallback_error}"
            return fallback_html, fallback_url, None
        if source_group == "social" and platform == "小红书" and account.get("cookie"):
            storage_state_text = self._browser_storage_state_from_cookie(platform, account.get("cookie", ""))
            if storage_state_text:
                html, final_url, error = self._request_browser_html(
                    url=url,
                    platform=platform,
                    storage_state_text=storage_state_text,
                    timeout=max(timeout, 12),
                )
                if not error:
                    return html, final_url, None
                logger.debug(f"{channel} 手动 Cookie 浏览器渲染失败，回退普通请求: {error}")
        return self._request_html(url, channel, timeout=timeout)

    def _browser_storage_state_from_cookie(self, platform: str, cookie_header: str) -> str:
        """把手动 Cookie 转成 Playwright storage_state，让动态站点也能走浏览器渲染。"""
        cookie_header = (cookie_header or "").strip()
        if not cookie_header:
            return ""
        try:
            adapter = get_adapter(platform)
        except Exception:
            return ""
        jar = SimpleCookie()
        try:
            jar.load(cookie_header)
        except Exception:
            return ""
        ignored_names = {"path", "domain", "expires", "max-age", "secure", "httponly", "samesite"}
        domain = "." + adapter.domains[0].lstrip(".")
        cookies = []
        for name, morsel in jar.items():
            if not name or name.lower() in ignored_names:
                continue
            value = morsel.value or ""
            if not value:
                continue
            cookies.append({
                "name": name,
                "value": value,
                "domain": domain,
                "path": morsel["path"] or "/",
                "expires": -1,
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            })
        if not cookies:
            return ""
        return json.dumps({"cookies": cookies, "origins": []}, ensure_ascii=False)

    def _request_browser_html(
        self,
        url: str,
        platform: str,
        storage_state_text: str,
        timeout: int = 10,
    ) -> Tuple[str, str, Optional[str]]:
        decision = self.source_policy.check(
            url,
            f"{platform}浏览器采集",
            access_mode=AUTHORIZED_SESSION_ACCESS_MODE,
        )
        if not decision.allowed:
            return "", url, f"source policy blocked [{decision.code}]: {decision.reason}"
        try:
            storage_state = json.loads(storage_state_text or "{}")
        except Exception:
            return "", url, "browser session storage state is invalid"
        try:
            sync_playwright, PlaywrightTimeoutError = load_playwright()
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    storage_state=storage_state,
                    viewport={"width": 1280, "height": 860},
                    locale="zh-CN",
                    extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
                )
                page = context.new_page()
                blocked_navigation = []

                def guard_main_navigation(route, request):
                    try:
                        is_main_navigation = (
                            request.is_navigation_request()
                            and request.frame == page.main_frame
                        )
                        if is_main_navigation:
                            route_decision = self.source_policy.check(
                                request.url,
                                f"{platform}浏览器导航",
                                access_mode=AUTHORIZED_SESSION_ACCESS_MODE,
                            )
                            if not route_decision.allowed:
                                blocked_navigation.append(route_decision)
                                route.abort("blockedbyclient")
                                return
                        route.continue_()
                    except Exception:
                        route.abort("blockedbyclient")

                page.route("**/*", guard_main_navigation)
                parsed_target = urlparse(url)
                is_xhs_detail_page = (
                    platform == "小红书"
                    and parsed_target.netloc.endswith("xiaohongshu.com")
                    and bool(re.fullmatch(r"/explore/[0-9a-zA-Z]+/?", parsed_target.path))
                )
                captured_xhs_payloads = []
                if platform == "小红书":
                    def capture_xhs_search_response(response):
                        response_url = response.url or ""
                        if "xiaohongshu.com" not in response_url or "/api/sns/web/v1/search" not in response_url:
                            return
                        try:
                            content_type = (response.headers or {}).get("content-type", "")
                            if "json" not in content_type.lower():
                                return
                            payload = json.loads(response.text())
                            captured_xhs_payloads.append(payload)
                        except Exception:
                            return

                    page.on("response", capture_xhs_search_response)
                try:
                    main_response = page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=max(timeout, 5) * 1000,
                    )
                    if main_response and main_response.status >= 400:
                        return "", page.url, f"HTTP {main_response.status}"
                    try:
                        page.wait_for_load_state("networkidle", timeout=5000)
                    except PlaywrightTimeoutError:
                        pass
                    try:
                        adapter = get_adapter(platform)
                        selector = ", ".join(adapter.item_selectors)
                        if is_xhs_detail_page:
                            page.wait_for_selector(
                                "#detail-title, #detail-desc, a[href*='/user/profile/']",
                                timeout=min(max(timeout, 8) * 1000, 15000),
                            )
                        elif selector:
                            page.wait_for_selector(
                                selector,
                                timeout=min(max(timeout, 8) * 1000, 15000),
                            )
                    except PlaywrightTimeoutError:
                        pass
                    try:
                        page.evaluate("window.scrollTo(0, Math.min(document.body.scrollHeight, 2200))")
                        page.wait_for_timeout(800)
                    except Exception:
                        page.wait_for_timeout(800)
                    try:
                        visible_text = page.locator("body").inner_text(timeout=2000)
                    except Exception:
                        visible_text = ""
                    try:
                        visible_verification_widget = bool(page.evaluate(
                            """() => {
                                const visible = (node) => {
                                    if (!node) return false;
                                    const style = getComputedStyle(node);
                                    const rect = node.getBoundingClientRect();
                                    return style.display !== "none"
                                        && style.visibility !== "hidden"
                                        && rect.width > 0
                                        && rect.height > 0;
                                };
                                return Array.from(document.querySelectorAll(
                                    "iframe[src*='captcha'], iframe[src*='verify'], "
                                    + "[id*='captcha'], [class*='captcha'], "
                                    + "[id*='verify-dialog'], [class*='verify-dialog']"
                                )).some(visible);
                            }"""
                        ))
                    except Exception:
                        visible_verification_widget = False
                    if visible_verification_widget or self._contains_verification_prompt(visible_text):
                        return "", page.url, f"{platform} requires human verification; automated path stopped"
                    extracted_items = []
                    extracted_xhs_detail = {}
                    if platform == "小红书" and is_xhs_detail_page:
                        try:
                            extracted_xhs_detail = page.evaluate(
                                """() => {
                                    const clean = (text) => (text || "").replace(/\\s+/g, " ").trim();
                                    const stripTags = (text) => clean((text || "").replace(/#[^#\\s]+/g, ""));
                                    const root = document.querySelector("#noteContainer")
                                        || document.querySelector("[class*='note-detail']")
                                        || document.querySelector("[class*='NoteDetail']")
                                        || document.querySelector("main")
                                        || document.body;
                                    const pickText = (selectors, scope = root) => {
                                        for (const selector of selectors) {
                                            const node = scope && scope.querySelector(selector);
                                            const text = node ? clean(node.innerText || node.textContent || "") : "";
                                            if (text) return text;
                                        }
                                        return "";
                                    };
                                    const title = pickText([
                                        "#detail-title",
                                        "[class*='title']",
                                        "[class*='Title']",
                                        "h1",
                                        "h2"
                                    ]);
                                    let content = "";
                                    const descNode = root.querySelector("#detail-desc")
                                        || root.querySelector(".desc")
                                        || root.querySelector("[class*='desc']")
                                        || root.querySelector("[class*='Desc']");
                                    if (descNode) {
                                        const cloned = descNode.cloneNode(true);
                                        cloned.querySelectorAll("a, button, [class*='tag'], [class*='Tag'], [class*='search'], [class*='Search']")
                                            .forEach((node) => node.remove());
                                        content = stripTags(cloned.innerText || cloned.textContent || "");
                                    }
                                    if (!content) {
                                        content = stripTags(pickText([
                                            "[class*='content']",
                                            "[class*='Content']"
                                        ]));
                                    }
                                    const authorLink = root.querySelector("a[href*='/user/profile/']");
                                    const author = clean(
                                        (authorLink && (authorLink.innerText || authorLink.textContent)) ||
                                        pickText([
                                            ".username",
                                            "[class*='username']",
                                            "[class*='user-name']",
                                            "[class*='author']",
                                            "[class*='Author']"
                                        ])
                                    );
                                    const authorUrl = authorLink ? new URL(authorLink.getAttribute("href"), location.href).href : "";
                                    const allText = clean(root.innerText || root.textContent || "");
                                    const timeMatch = allText.match(/(?:编辑于|发布于)?\\s*(刚刚|\\d+\\s*分钟前|\\d+\\s*小时前|昨天\\s*\\d{1,2}:\\d{2}|前天\\s*\\d{1,2}:\\d{2}|\\d{4}[-/年]\\d{1,2}[-/月]\\d{1,2}日?(?:\\s+\\d{1,2}:\\d{2})?|\\d{1,2}月\\d{1,2}日(?:\\s+\\d{1,2}:\\d{2})?)/);
                                    return {
                                        title,
                                        content,
                                        author,
                                        author_url: authorUrl,
                                        pub_time: timeMatch ? timeMatch[1] : ""
                                    };
                                }"""
                            ) or {}
                        except Exception:
                            extracted_xhs_detail = {}
                    if platform == "小红书" and not is_xhs_detail_page:
                        keyword = (parse_qs(urlparse(url).query).get("keyword") or [""])[0]
                        for payload in captured_xhs_payloads:
                            if len(extracted_items) >= 30:
                                break
                            extracted_items.extend(
                                extract_xiaohongshu_items_from_api_payload(
                                    payload,
                                    page.url or url,
                                    keyword=keyword,
                                    limit=30 - len(extracted_items),
                                )
                            )
                        try:
                            dom_items = page.evaluate(
                                """() => {
                                    const abs = (url) => {
                                        try { return new URL(url, location.href).href; } catch (_) { return ""; }
                                    };
                                    const selectors = [
                                        "section.note-item",
                                        "div.note-item",
                                        "[class*='note-item']",
                                        "[class*='NoteItem']",
                                        "[data-note-id]",
                                        "[data-noteid]",
                                        "[data-id]"
                                    ].join(",");
                                    return Array.from(document.querySelectorAll(selectors)).map((el) => {
                                        const text = (el.innerText || "").trim();
                                        const html = el.innerHTML || "";
                                        const decodedHtml = html.replace(/&amp;/g, "&");
                                        let noteId = el.getAttribute("data-note-id")
                                            || el.getAttribute("data-noteid")
                                            || el.getAttribute("data-id")
                                            || "";
                                        const urlMatch = decodedHtml.match(/\\/explore\\/[0-9a-zA-Z]{12,40}(?:\\?[^"'<>\\s]+)?/);
                                        const idMatch = decodedHtml.match(/\\/explore\\/([0-9a-zA-Z]{12,40})/)
                                            || decodedHtml.match(/noteId["'\\s:=]+([0-9a-zA-Z]{12,40})/);
                                        if (!noteId && idMatch) noteId = idMatch[1];
                                        const link = Array.from(el.querySelectorAll("a[href]"))
                                            .map((a) => abs(a.getAttribute("href")))
                                            .find((href) => /\\/explore\\/[0-9a-zA-Z]{12,40}/i.test(href)) || "";
                                        const tokenMatch = decodedHtml.match(/(?:xsec_token|xsecToken)["'\\s:=]+([0-9A-Za-z_\\-=]+)/);
                                        const sourceMatch = decodedHtml.match(/(?:xsec_source|xsecSource)["'\\s:=]+([0-9A-Za-z_\\-]+)/);
                                        const titleEl = el.querySelector("[class*='title'], [class*='Title'], a[title], a, span");
                                        const title = (
                                            (titleEl && (titleEl.getAttribute("title") || titleEl.innerText)) ||
                                            text.split("\\n").find(Boolean) ||
                                            ""
                                        ).trim();
                                        let url = link;
                                        if (!url && urlMatch) url = abs(urlMatch[0]);
                                        if (!url && noteId && tokenMatch) {
                                            const params = new URLSearchParams({
                                                xsec_token: tokenMatch[1],
                                                xsec_source: sourceMatch ? sourceMatch[1] : "pc_search",
                                                source: "web_explore_feed"
                                            });
                                            url = `https://www.xiaohongshu.com/explore/${noteId}?${params.toString()}`;
                                        }
                                        if (!url && noteId) url = `https://www.xiaohongshu.com/explore/${noteId}`;
                                        return {
                                            title,
                                            content: text,
                                            url,
                                            note_id: noteId,
                                            xsec_token: tokenMatch ? tokenMatch[1] : "",
                                            xsec_source: sourceMatch ? sourceMatch[1] : ""
                                        };
                                    }).filter((item) => item.title && item.url).slice(0, 30);
                                }"""
                            )
                            seen_urls = {item.get("url") for item in extracted_items}
                            for item in dom_items or []:
                                if item.get("url") not in seen_urls:
                                    extracted_items.append(item)
                                    seen_urls.add(item.get("url"))
                                if len(extracted_items) >= 30:
                                    break
                        except Exception:
                            pass
                    html = page.content()
                    if extracted_items:
                        payload = json.dumps(extracted_items, ensure_ascii=False).replace("</", "<\\/")
                        html += f'\n<script id="codex-extracted-social-items" type="application/json">{payload}</script>'
                    if extracted_xhs_detail:
                        payload = json.dumps(extracted_xhs_detail, ensure_ascii=False).replace("</", "<\\/")
                        html += f'\n<script id="codex-extracted-xhs-detail" type="application/json">{payload}</script>'
                    final_url = page.url
                except PlaywrightTimeoutError:
                    if blocked_navigation:
                        blocked = blocked_navigation[-1]
                        return (
                            "",
                            url,
                            f"source policy blocked [{blocked.code}]: {blocked.reason}",
                        )
                    return "", url, "browser session request timeout"
                except Exception:
                    if blocked_navigation:
                        blocked = blocked_navigation[-1]
                        return (
                            "",
                            url,
                            f"source policy blocked [{blocked.code}]: {blocked.reason}",
                        )
                    raise
                finally:
                    context.close()
                    browser.close()
            if not html.strip() or not BeautifulSoup(html, "html.parser").get_text(" ", strip=True):
                return "", url, "browser session returned empty page"
            return html, final_url, None
        except Exception as exc:
            return "", url, f"browser session request failed: {exc}"

    @staticmethod
    def _contains_verification_prompt(text: str) -> bool:
        normalized = re.sub(r"\s+", "", str(text or "")).lower()
        markers = (
            "请输入验证码",
            "请完成安全验证",
            "完成验证后继续",
            "拖动滑块完成验证",
            "点击进行验证",
            "访问过于频繁请验证",
            "captchaverification",
            "completethesecuritycheck",
        )
        return any(marker in normalized for marker in markers)

    def _request_browser_json(
        self,
        platform: str,
        url: str,
        timeout: int = 12,
    ) -> Tuple[Dict, int, str, Optional[str]]:
        """Call a read-only JSON endpoint with the saved Playwright session."""
        decision = self.source_policy.check(
            url,
            f"{platform}身份接口",
            access_mode=AUTHORIZED_SESSION_ACCESS_MODE,
        )
        if not decision.allowed:
            return (
                {},
                0,
                url,
                f"source policy blocked [{decision.code}]: {decision.reason}",
            )
        account = self.account_manager.get_account(platform) or {}
        storage_state_text = account.get("browser_session", "")
        if not storage_state_text:
            return {}, 0, url, "browser session unavailable"
        try:
            storage_state = json.loads(storage_state_text)
        except Exception:
            return {}, 0, url, "browser session storage state is invalid"
        try:
            sync_playwright, _ = load_playwright()
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    storage_state=storage_state,
                    locale="zh-CN",
                )
                try:
                    current_url = url
                    response = None
                    for redirect_count in range(6):
                        route_decision = self.source_policy.check(
                            current_url,
                            f"{platform}身份接口",
                            access_mode=AUTHORIZED_SESSION_ACCESS_MODE,
                        )
                        if not route_decision.allowed:
                            return (
                                {},
                                0,
                                current_url,
                                f"source policy blocked [{route_decision.code}]: "
                                f"{route_decision.reason}",
                            )
                        response = context.request.get(
                            current_url,
                            headers={
                                "Accept": "application/json, text/plain, */*",
                                "Accept-Encoding": "identity",
                                "Referer": f"https://{urlparse(current_url).netloc}/",
                                "X-Requested-With": "XMLHttpRequest",
                            },
                            timeout=max(timeout, 1) * 1000,
                            fail_on_status_code=False,
                            max_redirects=0,
                        )
                        location = (response.headers or {}).get("location")
                        if 300 <= response.status < 400 and location:
                            if redirect_count >= 5:
                                return {}, response.status, current_url, "too many redirects"
                            current_url = urljoin(current_url, location)
                            continue
                        break
                    body = response.body()
                    text = ""
                    for encoding in ("utf-8", "gb18030"):
                        try:
                            text = body.decode(encoding)
                            break
                        except UnicodeDecodeError:
                            continue
                    if not text:
                        text = body.decode("utf-8", errors="replace")
                    payload, parse_error = self._parse_json_text(text)
                    if parse_error:
                        return {}, response.status, response.url, f"non-json response: {parse_error}"
                    return payload, response.status, response.url, None
                finally:
                    context.close()
                    browser.close()
        except Exception as exc:
            return {}, 0, url, f"browser session JSON request failed: {exc}"

    def _enrich_with_browser_article_content(self, record: Dict, platform: str):
        account = self.account_manager.get_account(platform) or {}
        if account.get("session_mode") != "browser_session" or not account.get("browser_session"):
            return
        url = record.get("url", "")
        if not url.startswith(("http://", "https://")):
            return
        html, final_url, error = self._request_browser_html(
            url=url,
            platform=platform,
            storage_state_text=account.get("browser_session", ""),
            timeout=12,
        )
        if error:
            record["detail_error"] = error
            return
        detail = (
            extract_tieba_detail_from_html(html)
            if platform == "百度贴吧"
            else extract_article_from_html(html)
        )
        original_content = record.get("content", "")
        if detail.get("content") and len(detail["content"]) > len(record.get("content", "")):
            record["content"] = detail["content"][:3000]
        if detail.get("title") and len(record.get("title", "")) < 12:
            record["title"] = detail["title"][:160]
        if detail.get("pub_time"):
            pub_time, time_basis = self._normalize_pub_time(detail["pub_time"])
            if pub_time and not self._is_suspicious_social_pub_time(platform, pub_time, detail["pub_time"], detail.get("content", "")):
                record["pub_time"] = pub_time
                record["time_basis"] = time_basis
        if final_url:
            record["url"] = self._normalize_url(final_url, "")
        if platform == "百度贴吧":
            samples = detail.get("discussion_samples") or []
            if samples:
                record["discussion_samples"] = samples[:10]
            if len(record.get("content", "")) > len(original_content) or samples:
                previous_error = record.pop("detail_error", "")
                if previous_error:
                    record["detail_fallback_reason"] = previous_error
                record["detail_enriched"] = True
                record["detail_source"] = "browser_session"

    def _enrich_tieba_record(self, record: Dict):
        """Prefer the logged-in browser and use aiotieba only as a final fallback."""
        self._enrich_with_browser_article_content(record, "百度贴吧")
        if not record.get("detail_enriched"):
            self._enrich_with_tieba_thread(record)

    def _enrich_with_weibo_detail(self, record: Dict):
        """Use Weibo's read-only structured detail endpoint instead of noisy page text."""
        account = self.account_manager.get_account("微博") or {}
        if account.get("session_mode") != "browser_session" or not account.get("browser_session"):
            return
        status_id = self._extract_weibo_status_id(record.get("url", ""))
        if not status_id:
            return
        payload, status, _, error = self._request_browser_json(
            "微博",
            f"https://weibo.com/ajax/statuses/show?id={quote(status_id)}",
            timeout=20,
        )
        if error or not payload:
            record["detail_error"] = error or f"微博详情接口 HTTP {status}"
            return
        detail = extract_weibo_detail_from_payload(payload)
        content = self._clean_text(detail.get("content", ""))
        if not content:
            record["detail_error"] = "微博详情接口未返回正文"
            return

        record["content"] = content[:3000]
        record["title"] = (detail.get("title") or content[:80])[:160]
        if detail.get("author"):
            record["author"] = detail["author"]
            record["source"] = detail["author"]
        if detail.get("author_url"):
            record["author_url"] = detail["author_url"]
        if detail.get("pub_time"):
            pub_time, time_basis = self._normalize_pub_time(detail["pub_time"])
            if pub_time and not self._is_suspicious_social_pub_time(
                "微博", pub_time, detail["pub_time"], content
            ):
                record["pub_time"] = pub_time
                record["time_basis"] = time_basis
        for field in ("repost_count", "comment_count", "like_count"):
            record[field] = self._safe_int(detail.get(field))
        if detail.get("external_id"):
            record["external_id"] = detail["external_id"]
        if detail.get("mblogid"):
            record["mblogid"] = detail["mblogid"]
        record["is_long_text"] = bool(detail.get("is_long_text"))
        record["detail_enriched"] = True
        record["detail_source"] = "weibo_status_api"

    @staticmethod
    def _extract_weibo_status_id(url: str) -> str:
        parsed = urlparse(url or "")
        segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
        if len(segments) >= 2 and segments[0] in {"detail", "status"}:
            return segments[1]
        if len(segments) >= 2 and segments[0].isdigit():
            return segments[1]
        if len(segments) >= 3 and segments[:2] == ["tv", "show"]:
            return segments[2]
        return ""

    def _enrich_with_tieba_thread(self, record: Dict):
        """用 aiotieba 只读补充已发现帖子的楼层与高赞楼中楼。"""
        if not self.external_content_adapters:
            return
        tid = self._extract_tieba_tid(record.get("url", ""))
        if not tid:
            return

        account = self.account_manager.get_account("百度贴吧") or {}
        cookie_header = account.get("cookie", "")
        bduss = self._cookie_token(cookie_header, "BDUSS")
        stoken = self._cookie_token(cookie_header, "STOKEN")
        outcome = self.external_content_adapters.tieba.fetch(
            tid=tid,
            bduss=bduss,
            stoken=stoken,
            max_posts=20,
            max_comments=4,
            use_system_proxy=self.use_system_proxy,
            timeout=30,
        )
        if not outcome.data:
            if outcome.attempted and outcome.error:
                record["detail_error"] = outcome.error
            return

        detail = outcome.data
        title = self._clean_text(detail.get("title", ""))
        content = self._clean_text(detail.get("content", ""))
        posts = detail.get("posts") if isinstance(detail.get("posts"), list) else []
        if not content:
            content = "\n".join(
                self._clean_text(post.get("content", ""))
                for post in posts[:3]
                if isinstance(post, dict) and post.get("content")
            )
        if title:
            record["title"] = title[:160]
        if content and len(content) > len(record.get("content", "")):
            record["content"] = content[:3000]
        if detail.get("author"):
            record["author"] = self._clean_text(detail["author"])[:80]
        if detail.get("forum"):
            record["forum"] = self._clean_text(detail["forum"])[:80]
        if detail.get("pub_time"):
            pub_time, time_basis = self._normalize_pub_time(detail["pub_time"])
            if pub_time and not self._is_suspicious_social_pub_time(
                "百度贴吧", pub_time, detail["pub_time"], content
            ):
                record["pub_time"] = pub_time
                record["time_basis"] = time_basis

        record["url"] = f"https://tieba.baidu.com/p/{tid}"
        record["external_id"] = str(tid)
        record["view_count"] = self._safe_int(detail.get("view_count"))
        record["comment_count"] = max(
            self._safe_int(record.get("comment_count")),
            self._safe_int(detail.get("reply_count")),
        )
        record["repost_count"] = max(
            self._safe_int(record.get("repost_count")),
            self._safe_int(detail.get("share_count")),
        )
        record["discussion_samples"] = posts[:10]
        record["detail_enriched"] = True
        record["detail_source"] = "aiotieba"

    @staticmethod
    def _extract_tieba_tid(url: str) -> Optional[int]:
        parsed = urlparse(url or "")
        path_match = re.fullmatch(r"/p/(\d+)/?", parsed.path)
        if path_match:
            return int(path_match.group(1))
        query = parse_qs(parsed.query)
        for key in ("kz", "tid"):
            value = (query.get(key) or [""])[0]
            if str(value).isdigit():
                return int(value)
        return None

    @staticmethod
    def _cookie_token(cookie_header: str, name: str) -> str:
        if not cookie_header:
            return ""
        jar = SimpleCookie()
        try:
            jar.load(cookie_header)
        except Exception:
            return ""
        target = name.lower()
        for cookie_name, morsel in jar.items():
            if cookie_name.lower() == target:
                return morsel.value
        return ""

    def _enrich_with_xiaohongshu_detail_content(self, record: Dict):
        account = self.account_manager.get_account("小红书") or {}
        storage_state_text = ""
        session_mode = account.get("session_mode") or ""
        if account.get("session_mode") == "browser_session" and account.get("browser_session"):
            storage_state_text = account.get("browser_session", "")
        elif account.get("cookie"):
            storage_state_text = self._browser_storage_state_from_cookie("小红书", account.get("cookie", ""))
            session_mode = session_mode or "manual_cookie"
        elif account.get("browser_session"):
            storage_state_text = account.get("browser_session", "")
            session_mode = session_mode or "browser_session"
        if not storage_state_text:
            return

        url = record.get("url", "")
        if not url.startswith(("http://", "https://")):
            return
        html, _final_url, error = self._request_browser_html(
            url=url,
            platform="小红书",
            storage_state_text=storage_state_text,
            timeout=12,
        )
        if error:
            record["detail_error"] = error
            return
        detail = extract_xiaohongshu_detail_from_html(html)
        content = self._clean_text(detail.get("content", ""))
        if content and len(content) > max(len(record.get("content", "")), 20):
            record["content"] = content[:3000]
            record["detail_enriched"] = True
            record["detail_source"] = "xiaohongshu_detail"
        title = self._clean_text(detail.get("title", ""))
        if title and (len(record.get("title", "")) < 12 or title != record.get("title")):
            record["title"] = title[:160]
        author = self._clean_text(detail.get("author", ""))
        if author:
            record["author"] = author[:80]
        if detail.get("author_url"):
            record["author_url"] = detail.get("author_url")
        if detail.get("pub_time"):
            pub_time, time_basis = self._normalize_pub_time(detail["pub_time"])
            if pub_time and not self._is_suspicious_social_pub_time("小红书", pub_time, detail["pub_time"], content):
                record["pub_time"] = pub_time
                record["time_basis"] = time_basis
        if session_mode and not record.get("session_mode"):
            record["session_mode"] = session_mode

    def _build_request_headers(self, url: str, channel: str) -> Dict:
        headers = self.anti_crawl.get_random_headers()
        headers["User-Agent"] = SOURCE_POLICY_USER_AGENT
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

        platform = self._auth_platform_from_channel(channel)
        if platform:
            account = self.account_manager.get_account(platform)
            cookie = (account or {}).get("cookie", "")
            if cookie:
                headers["Cookie"] = cookie
        return headers

    @staticmethod
    def _auth_platform_from_channel(channel: str) -> Optional[str]:
        if not channel:
            return None
        channel_map = {
            "微博搜索": "微博",
            "知乎搜索": "知乎",
            "B站搜索": "B站",
            "贴吧搜索": "百度贴吧",
            "豆瓣搜索": "豆瓣",
            "搜狗微信": "微信公众平台",
        }
        if channel in channel_map:
            return channel_map[channel]
        for platform in PLATFORM_LIST:
            if channel.startswith(platform):
                return platform
        return None

    def test_social_platform(self, platform: str, keyword: str = "警方通报") -> Dict:
        """同时验证当前登录和真实读取；两项均通过才算平台测试通过。"""
        keyword = (keyword or "警方通报").strip() or "警方通报"
        account = self.account_manager.get_account(platform) or {}
        auth_context = self._get_social_auth_context(platform, keyword)
        result = {
            "platform": platform,
            "channel": "",
            "status": "failed",
            "reachable": False,
            "passed": False,
            "read_passed": False,
            "login_passed": auth_context.get("login_confirmed") is True,
            "login_confirmed": auth_context.get("login_confirmed"),
            "username_or_hint": auth_context.get("username_or_hint", ""),
            "evidence": auth_context.get("login_evidence", ""),
            "parsed_count": 0,
            "error": "",
            "login_error": auth_context.get("error", ""),
            "cookie_used": bool(account.get("cookie")),
            "auth_mode": auth_context.get("auth_mode", "guest"),
            "session_mode": auth_context.get("session_mode", auth_context.get("auth_mode", "guest")),
            "final_url": "",
            "message": "",
            "adapter_name": "",
            "adapter_backend": "",
            "adapter_fallback_error": "",
            "adapter_skipped_reason": "",
        }

        requests_to_make = self._build_social_source_requests(platform, keyword, None, None)
        if not requests_to_make:
            result["error"] = "no public search entry configured"
            result["message"] = "访问失败: no public search entry configured"
            return result

        req = requests_to_make[0]
        result["channel"] = req["channel"]
        adapter_error = ""
        if (
            self.external_social_registry
            and self.external_social_registry.supports(platform)
        ):
            adapter_decision = self.source_policy.check(
                req["url"],
                req["channel"],
                access_mode=EXTERNAL_ADAPTER_ACCESS_MODE,
            )
            if adapter_decision.allowed:
                adapter_outcome = self.external_social_registry.search(
                    platform=platform,
                    keyword=keyword,
                    limit=20,
                    timeout=max(req.get("timeout", 10), 45),
                    auth_payload=self._build_external_adapter_auth_payload(platform),
                )
                result["adapter_name"] = adapter_outcome.adapter_name
                if adapter_outcome.items:
                    valid_items = [
                        item
                        for item in adapter_outcome.items
                        if self._is_valid_social_record_url(item, platform, "social")
                    ]
                    if valid_items:
                        result["reachable"] = True
                        result["parsed_count"] = len(valid_items)
                        result["read_passed"] = True
                        result["adapter_backend"] = valid_items[0].get(
                            "adapter_backend",
                            "external_bridge",
                        )
                        result["evidence"] = (
                            f"{result['evidence']}; "
                            f"{adapter_outcome.adapter_name} returned structured results"
                        ).strip("; ")
                        self._finalize_platform_test_result(
                            result,
                            read_description=f"{adapter_outcome.adapter_name} 真实读取",
                        )
                        return result
                adapter_error = adapter_outcome.error or (
                    f"{adapter_outcome.adapter_name} returned no valid results"
                )
            else:
                result["adapter_skipped_reason"] = (
                    f"source policy blocked [{adapter_decision.code}]: "
                    f"{adapter_decision.reason}"
                )

        html, final_url, error = self._request_source_html(
            url=req["url"],
            channel=req["channel"],
            platform=req["platform"],
            source_group=req.get("source_group", "social"),
            timeout=req.get("timeout", 10),
        )
        result["final_url"] = final_url or req["url"]
        if error:
            if adapter_error:
                error = f"{result['adapter_name'] or 'external adapter'}: {adapter_error}; browser: {error}"
            result["error"] = error
            if "human_verification_required:" in error:
                result["status"] = "action_required"
                result["message"] = error.split("human_verification_required:", 1)[1].strip()
            elif "visible_browser_failed:" in error:
                result["status"] = "action_required"
                reason = error.split("visible_browser_failed:", 1)[1].strip()
                result["message"] = f"可见辅助浏览器读取失败：{reason}"
            elif platform == "微博" and "HTTP 432" in error:
                result["status"] = "restricted"
                result["message"] = (
                    "平台拒绝当前自动读取（HTTP 432）；浏览器会话已保存，"
                    "但程序不会绕过平台访问限制"
                )
            else:
                result["message"] = f"访问失败: {error}"
            return result

        parsed = self._parse_results(platform, html, keyword, req["channel"], final_url or req["url"])
        if adapter_error:
            result["adapter_fallback_error"] = adapter_error
        result["reachable"] = True
        result["parsed_count"] = len(parsed)
        result["read_passed"] = len(parsed) > 0
        if (
            platform == "抖音"
            and not self.live_login_probe
            and result.get("login_confirmed") is None
        ):
            current_login, login_evidence = self._infer_current_page_login(platform, html)
            result["login_confirmed"] = current_login
            result["login_passed"] = current_login is True
            if login_evidence:
                result["evidence"] = login_evidence
        self._finalize_platform_test_result(result)
        if len(parsed) == 0:
            result["error"] = "reachable but no parseable result"
            if adapter_error:
                result["error"] = f"{adapter_error}; {result['error']}"
        return result

    @staticmethod
    def _finalize_platform_test_result(result: Dict, read_description: str = "真实采集") -> None:
        """Apply the product acceptance rule: current login AND valid records."""
        result["login_passed"] = result.get("login_confirmed") is True
        result["read_passed"] = bool(result.get("read_passed"))
        result["passed"] = result["login_passed"] and result["read_passed"]
        count = int(result.get("parsed_count") or 0)
        if result["passed"]:
            result["status"] = "ok"
            result["message"] = f"登录通过，{read_description}通过（{count} 条有效结果）"
        elif result["read_passed"]:
            result["status"] = "collection_only"
            result["message"] = f"{read_description}通过（{count} 条有效结果），但当前登录未通过"
        elif result["login_passed"]:
            result["status"] = "no_results"
            result["message"] = "登录通过，但未采集到有效结果"
        else:
            result["status"] = "no_results"
            result["message"] = "当前登录未通过，且未采集到有效结果"

    @staticmethod
    def _infer_current_page_login(platform: str, html: str) -> Tuple[Optional[bool], str]:
        """Infer login only from explicit account UI/state on the page just collected."""
        text = html or ""
        if platform != "抖音" or not text.strip():
            return None, ""
        positive_patterns = (
            r'data-e2e=["\'](?:user-avatar|user-profile|header-user)["\']',
            r'"(?:isLogin|is_login|loggedIn|loginStatus)"\s*:\s*true',
            r'>\s*退出登录\s*<',
        )
        if any(re.search(pattern, text, re.I) for pattern in positive_patterns):
            return True, "抖音当前采集页面匹配到已登录账号标记"
        negative_patterns = (
            r'"(?:isLogin|is_login|loggedIn|loginStatus)"\s*:\s*false',
            r'data-e2e=["\']login-button["\']',
        )
        if any(re.search(pattern, text, re.I) for pattern in negative_patterns):
            return False, "抖音当前采集页面匹配到登录入口或未登录标记"
        return None, "抖音当前采集页面未找到可确认身份的账号标记"

    def _build_external_adapter_auth_payload(self, platform: str) -> Dict:
        """Extract only the selected platform's cookies for an isolated stdin bridge."""
        account = self.account_manager.get_account(platform) or {}
        cookies: Dict[str, str] = {}
        try:
            adapter = get_adapter(platform)
            allowed_domains = tuple(
                str(domain or "").lstrip(".").casefold()
                for domain in adapter.domains
                if str(domain or "").strip()
            )
        except Exception:
            allowed_domains = ()

        storage_state_text = (account.get("browser_session") or "").strip()
        if storage_state_text:
            try:
                storage_state = json.loads(storage_state_text)
            except Exception:
                storage_state = {}
            for entry in storage_state.get("cookies") or []:
                if not isinstance(entry, dict):
                    continue
                domain = str(entry.get("domain") or "").lstrip(".").casefold()
                if allowed_domains and not any(
                    domain == allowed or domain.endswith("." + allowed)
                    for allowed in allowed_domains
                ):
                    continue
                name = str(entry.get("name") or "").strip()
                value = str(entry.get("value") or "")
                if name and value:
                    cookies[name] = value

        cookie_header = (account.get("cookie") or "").strip()
        if cookie_header:
            jar = SimpleCookie()
            try:
                jar.load(cookie_header)
            except Exception:
                jar = SimpleCookie()
            for name, morsel in jar.items():
                value = morsel.value or ""
                if name and value:
                    cookies[name] = value

        return {
            "cookies": cookies,
            "use_system_proxy": self.use_system_proxy,
        }

    def _get_social_auth_context(self, platform: str, keyword: str = "") -> Dict:
        account = self.account_manager.get_account(platform) or {}
        cookie = (account.get("cookie") or "").strip()
        browser_session = (account.get("browser_session") or "").strip()
        if not cookie and not browser_session:
            return {
                "auth_mode": "guest",
                "session_mode": "guest",
                "login_confirmed": None,
                "login_evidence": "no cookie supplied",
                "username_or_hint": "",
                "error": "",
            }
        probe = self._get_auth_probe(platform)
        session_mode = account.get("session_mode") or ("browser_session" if browser_session else "cookie")
        return {
            "auth_mode": "authorized_session",
            "session_mode": session_mode,
            "login_confirmed": probe.get("login_confirmed"),
            "login_evidence": probe.get("evidence") or probe.get("error") or "cookie supplied",
            "username_or_hint": probe.get("username_or_hint", ""),
            "error": probe.get("error", ""),
        }

    def _get_auth_probe(self, platform: str) -> Dict:
        if platform not in self._auth_probe_cache:
            self._auth_probe_cache[platform] = self._probe_social_login(platform)
        return self._auth_probe_cache[platform]

    def _base_auth_probe_result(self, platform: str) -> Dict:
        account = self.account_manager.get_account(platform) or {}
        cookie_saved = bool((account.get("cookie") or "").strip())
        browser_session_saved = bool((account.get("browser_session") or "").strip())
        return {
            "platform": platform,
            "reachable": False,
            "login_confirmed": None,
            "username_or_hint": "",
            "evidence": "",
            "error": "",
            "cookie_used": cookie_saved,
            "browser_session_used": browser_session_saved,
            "auth_mode": "authorized_session" if (cookie_saved or browser_session_saved) else "guest",
            "session_mode": account.get("session_mode") or (
                "browser_session" if browser_session_saved else ("cookie" if cookie_saved else "guest")
            ),
            "final_url": "",
        }

    def _probe_social_login(self, platform: str) -> Dict:
        result = self._base_auth_probe_result(platform)
        if not result["cookie_used"] and not result["browser_session_used"]:
            result["evidence"] = "no authorized session supplied"
            return result
        if platform == "B站":
            return self._probe_bilibili_login(result)
        if platform == "知乎":
            return self._probe_zhihu_login(result)
        if platform == "微博":
            return self._probe_weibo_login(result)
        if platform == "百度贴吧":
            return self._probe_tieba_login(result)
        if platform == "小红书":
            return self._probe_xiaohongshu_login(result)
        if platform == "抖音":
            return self._probe_douyin_login(result)
        result["evidence"] = "login probe not implemented for this platform"
        return result

    def _probe_douyin_login(self, result: Dict) -> Dict:
        if self.live_login_probe:
            return self._probe_page_login(
                platform="抖音",
                url="https://www.douyin.com/",
                positive_markers=[],
            )

        account = self.account_manager.get_account("抖音") or {}
        confirmed = account.get("browser_login_confirmed")
        evidence = str(account.get("browser_login_evidence") or "").strip()
        if confirmed is True:
            result["evidence"] = (
                f"{evidence or '抖音辅助登录保存时已确认登录'}；"
                "仍需由本次采集页面重新确认当前登录"
            )
        elif confirmed is False:
            result["evidence"] = evidence or "抖音辅助登录保存时未确认登录"
        else:
            result["evidence"] = "抖音浏览器会话已保存；仍需由本次采集页面确认当前登录"
        return result

    def _probe_bilibili_login(self, result: Dict) -> Dict:
        account = self.account_manager.get_account("B站") or {}
        if account.get("browser_session"):
            payload, status, final_url, browser_error = self._request_browser_json(
                "B站",
                "https://api.bilibili.com/x/web-interface/nav",
                timeout=12,
            )
            if payload:
                result["reachable"] = True
                result["final_url"] = final_url
                data = payload.get("data", {}) if isinstance(payload, dict) else {}
                is_login = data.get("isLogin")
                if is_login is True:
                    result["login_confirmed"] = True
                    result["username_or_hint"] = str(data.get("uname") or data.get("name") or data.get("mid") or "")
                    result["evidence"] = "B站 browser nav isLogin=true"
                    return result
                if is_login is False:
                    result["login_confirmed"] = False
                    result["evidence"] = "B站 browser nav isLogin=false"
                    return result
            if browser_error:
                result["error"] = browser_error

        html, final_url, error = self._request_html(
            "https://api.bilibili.com/x/web-interface/nav",
            "B站身份接口",
            timeout=8,
            access_mode=AUTHORIZED_SESSION_ACCESS_MODE,
        )
        result["final_url"] = final_url
        if error:
            result["error"] = error
            page_probe = self._probe_page_login(
                platform="B站",
                url="https://www.bilibili.com/",
                positive_markers=["退出登录", "个人中心", "nav-user-center"],
                strong_patterns=[
                    r'"isLogin"\s*:\s*true',
                    r'class=["\'][^"\']*(?:header-avatar-wrap|bili-avatar)[^"\']*["\']',
                ],
                negative_patterns=[r'"isLogin"\s*:\s*false'],
            )
            if page_probe.get("reachable"):
                return page_probe
            result["evidence"] = f"B站 nav request failed: {error}"
            return result
        result["reachable"] = True
        payload, parse_error = self._parse_json_text(html)
        if parse_error:
            result["evidence"] = f"B站 nav returned non-json: {parse_error}"
            return result
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        is_login = data.get("isLogin")
        if is_login is True:
            result["login_confirmed"] = True
            result["username_or_hint"] = str(data.get("uname") or data.get("name") or data.get("mid") or "")
            result["evidence"] = "B站 nav isLogin=true"
        elif is_login is False:
            result["login_confirmed"] = False
            result["evidence"] = "B站 nav isLogin=false"
        else:
            page_probe = self._probe_page_login(
                platform="B站",
                url="https://www.bilibili.com/",
                positive_markers=["退出登录", "个人中心", "nav-user-center"],
                strong_patterns=[
                    r'"isLogin"\s*:\s*true',
                    r'class=["\'][^"\']*(?:header-avatar-wrap|bili-avatar)[^"\']*["\']',
                ],
                negative_patterns=[r'"isLogin"\s*:\s*false'],
            )
            if page_probe.get("reachable"):
                return page_probe
            result["evidence"] = "B站 nav reachable but isLogin missing"
        return result

    def _probe_zhihu_login(self, result: Dict) -> Dict:
        html, final_url, error = self._request_html(
            "https://www.zhihu.com/api/v4/me",
            "知乎身份接口",
            timeout=8,
            access_mode=AUTHORIZED_SESSION_ACCESS_MODE,
        )
        result["final_url"] = final_url
        if not error:
            result["reachable"] = True
            payload, parse_error = self._parse_json_text(html)
            if not parse_error and isinstance(payload, dict):
                username = payload.get("name") or payload.get("url_token") or payload.get("id")
                if username:
                    result["login_confirmed"] = True
                    result["username_or_hint"] = str(username)
                    result["evidence"] = "知乎 /api/v4/me returned profile"
                    return result
                if payload.get("error") or payload.get("code"):
                    result["login_confirmed"] = False
                    result["evidence"] = "知乎 /api/v4/me returned login error"
                    return result
            result["evidence"] = f"知乎 /api/v4/me inconclusive: {parse_error or 'profile fields missing'}"
            return result

        result["error"] = error
        page_probe = self._probe_page_login(
            platform="知乎",
            url="https://www.zhihu.com/",
            positive_markers=["AppHeader-profileEntry", "\"viewer\"", "\"urlToken\"", "\"name\""],
            strong_patterns=[r'"id"\s*:\s*"[^"]{6,}"', r'"urlToken"\s*:\s*"[^"]+"'],
        )
        if page_probe.get("reachable"):
            result.update(page_probe)
            if result.get("login_confirmed") is None and any(code in error for code in ("401", "403")):
                result["login_confirmed"] = False
                result["evidence"] = f"知乎 /api/v4/me {error}; homepage did not confirm login"
            return result
        result["evidence"] = f"知乎 /api/v4/me request failed: {error}"
        return result

    def _probe_weibo_login(self, result: Dict) -> Dict:
        account = self.account_manager.get_account("微博") or {}
        cookie = account.get("cookie", "")
        has_auth_cookie = bool(self._cookie_token(cookie, "SUB"))
        has_browser_session = bool(
            account.get("session_mode") == "browser_session"
            and account.get("browser_session")
        )
        result["username_or_hint"] = str(account.get("username") or "")
        config_evidence = ""

        if has_browser_session:
            payload, status, final_url, browser_error = self._request_browser_json(
                "微博",
                "https://weibo.com/ajax/config/get_config",
                timeout=12,
            )
            result["final_url"] = final_url
            if payload:
                result["reachable"] = True
                data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
                username = self._find_json_value(
                    data,
                    {"screen_name", "user_name", "name", "uid", "id"},
                )
                login_marker = self._find_json_value(
                    data,
                    {"login", "isLogin", "is_login", "loggedIn"},
                )
                if login_marker in (True, 1, "1"):
                    result["login_confirmed"] = True
                    result["username_or_hint"] = str(username or result["username_or_hint"])
                    result["evidence"] = "微博 browser config returned login marker"
                    return result
                if login_marker in (False, 0, "0"):
                    config_evidence = "微博 browser config returned logged-out marker"
            if browser_error:
                result["error"] = browser_error

            page_probe = self._probe_page_login(
                platform="微博",
                url="https://weibo.com/",
                positive_markers=["退出登录", "我的首页"],
                strong_patterns=[
                    r'\$CONFIG\[["\']uid["\']\]\s*=\s*["\']\d+["\']',
                    r'"(?:login|isLogin|is_login|loggedIn)"\s*:\s*true',
                ],
                negative_patterns=[
                    r'"(?:login|isLogin|is_login|loggedIn)"\s*:\s*false',
                ],
            )
            if page_probe.get("login_confirmed") is not None:
                return page_probe
            if page_probe.get("reachable"):
                result["reachable"] = True
                result["final_url"] = page_probe.get("final_url", result.get("final_url", ""))
                page_evidence = page_probe.get("evidence", "")
                result["evidence"] = "; ".join(
                    item for item in (config_evidence, page_evidence) if item
                )
            elif page_probe.get("error") and not result.get("error"):
                result["error"] = page_probe["error"]

        if not result.get("evidence") and has_browser_session and has_auth_cookie:
            result["evidence"] = (
                "微博浏览器会话与登录 Cookie 已保存；在线身份接口未能确认登录"
            )
        elif not result.get("evidence") and has_browser_session:
            result["evidence"] = (
                "微博浏览器会话已保存，但未识别到登录 Cookie，在线身份接口未能确认登录"
            )
        elif not result.get("evidence") and has_auth_cookie:
            result["evidence"] = "微博登录 Cookie 已保存，但没有可用于在线验证的浏览器会话"
        elif not result.get("evidence"):
            result["evidence"] = "未保存可用于微博读取的浏览器会话或登录 Cookie"
        return result

    def _probe_tieba_login(self, result: Dict) -> Dict:
        account = self.account_manager.get_account("百度贴吧") or {}
        if account.get("session_mode") == "browser_session" and account.get("browser_session"):
            payload, status, final_url, browser_error = self._request_browser_json(
                "百度贴吧",
                "https://tieba.baidu.com/f/user/json_userinfo",
                timeout=12,
            )
            result["final_url"] = final_url
            if payload:
                result["reachable"] = True
                data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                is_login = data.get("is_login")
                username = self._find_json_value(
                    data,
                    {"user_name_show", "show_nickname", "user_name_link", "user_portrait", "open_uid"},
                )
                if is_login in (True, 1, "1") or username:
                    result["login_confirmed"] = True
                    result["evidence"] = "贴吧 browser json_userinfo returned login marker"
                    return result
                if is_login in (False, 0, "0") or payload.get("no") not in (None, 0, "0"):
                    result["login_confirmed"] = False
                    result["evidence"] = "贴吧 browser json_userinfo returned logged-out marker"
                    return result
            if browser_error:
                result["error"] = browser_error

        html, final_url, error = self._request_html(
            "https://tieba.baidu.com/f/user/json_userinfo",
            "百度贴吧身份接口",
            timeout=8,
            access_mode=AUTHORIZED_SESSION_ACCESS_MODE,
        )
        result["final_url"] = final_url
        if not error:
            result["reachable"] = True
            payload, parse_error = self._parse_json_text(html)
            if not parse_error and isinstance(payload, dict):
                username = self._find_json_value(payload, {"user_name", "name_show", "name", "portrait"})
                if username:
                    result["login_confirmed"] = True
                    result["username_or_hint"] = str(username)
                    result["evidence"] = "贴吧 json_userinfo returned user profile"
                    return result
                status_code = payload.get("no") or payload.get("errno") or payload.get("code")
                if status_code not in (None, 0, "0"):
                    result["login_confirmed"] = False
                    result["evidence"] = f"贴吧 json_userinfo returned code={status_code}"
                    return result
            page_probe = self._probe_page_login(
                platform="百度贴吧",
                url="https://tieba.baidu.com/index.html",
                positive_markers=["user_name", "name_show", "portrait", "BDUSS"],
                strong_patterns=[r'"user_name"\s*:\s*"[^"]+"', r'"portrait"\s*:\s*"[^"]+"'],
            )
            if page_probe.get("reachable"):
                return page_probe
            result["evidence"] = f"贴吧 json_userinfo inconclusive: {parse_error or 'profile fields missing'}"
            return result

        result["error"] = error
        page_probe = self._probe_page_login(
            platform="百度贴吧",
            url="https://tieba.baidu.com/index.html",
            positive_markers=["user_name", "name_show", "portrait", "BDUSS"],
            strong_patterns=[r'"user_name"\s*:\s*"[^"]+"', r'"portrait"\s*:\s*"[^"]+"'],
        )
        if page_probe.get("reachable"):
            return page_probe
        result["evidence"] = f"贴吧 json_userinfo request failed: {error}"
        return result

    def _probe_xiaohongshu_login(self, result: Dict) -> Dict:
        account = self.account_manager.get_account("小红书") or {}
        explicit_logged_out = False
        identity_evidence = ""
        if account.get("browser_session"):
            payload, status, final_url, browser_error = self._request_browser_json(
                "小红书",
                "https://edith.xiaohongshu.com/api/sns/web/v1/user/selfinfo",
                timeout=12,
            )
            result["final_url"] = final_url
            if payload:
                result["reachable"] = True
                flattened = json.dumps(payload, ensure_ascii=False)
                login_success = self._find_json_value(payload, {"success"}) is True
                has_user = bool(
                    re.search(r'"user_id"\s*:\s*"[^"]+"', flattened)
                    or re.search(r'"nickname"\s*:\s*"[^"]+"', flattened)
                )
                if login_success and has_user:
                    result["login_confirmed"] = True
                    result["username_or_hint"] = str(
                        self._find_json_value(payload, {"nickname", "name", "user_id"}) or ""
                    )
                    result["evidence"] = "小红书 browser selfinfo returned user marker"
                    return result
                if re.search(r'"success"\s*:\s*false', flattened, re.I):
                    explicit_logged_out = True
                    identity_evidence = "小红书 browser selfinfo returned success=false"
            if browser_error:
                result["error"] = browser_error

        html, final_url, error = self._request_html(
            "https://edith.xiaohongshu.com/api/sns/web/v1/user/selfinfo",
            "小红书身份接口",
            timeout=8,
            access_mode=AUTHORIZED_SESSION_ACCESS_MODE,
        )
        result["final_url"] = final_url
        if not error:
            result["reachable"] = True
            payload, parse_error = self._parse_json_text(html)
            if not parse_error and isinstance(payload, dict):
                flattened = json.dumps(payload, ensure_ascii=False)
                login_success = self._find_json_value(payload, {"success"}) is True
                has_user = bool(
                    re.search(r'"user_id"\s*:\s*"[^"]+"', flattened)
                    or re.search(r'"nickname"\s*:\s*"[^"]+"', flattened)
                )
                if login_success and has_user:
                    result["login_confirmed"] = True
                    result["username_or_hint"] = str(
                        self._find_json_value(payload, {"nickname", "name", "user_id"}) or ""
                    )
                    result["evidence"] = "小红书 selfinfo returned user marker"
                    return result
                if re.search(r'"success"\s*:\s*false', flattened, re.I):
                    explicit_logged_out = True
                    identity_evidence = "小红书 selfinfo returned success=false"
            if not identity_evidence:
                identity_evidence = (
                    f"小红书 selfinfo reachable but inconclusive: "
                    f"{parse_error or 'login marker missing'}"
                )

        result["error"] = error
        page_probe = self._probe_page_login(
            platform="小红书",
            url="https://www.xiaohongshu.com/explore",
            positive_markers=["退出登录", "logout"],
            strong_patterns=[r'"loggedIn"\s*:\s*true', r'"isLogin"\s*:\s*true'],
            negative_patterns=[r'"loggedIn"\s*:\s*false', r'"isLogin"\s*:\s*false'],
        )
        if page_probe.get("reachable"):
            if page_probe.get("login_confirmed") is not None:
                return page_probe
            page_probe["login_confirmed"] = False if explicit_logged_out else None
            page_probe["evidence"] = "; ".join(
                item
                for item in (
                    identity_evidence,
                    page_probe.get("evidence") or "小红书页面可访问但登录标记不明确",
                )
                if item
            )
            return page_probe
        if explicit_logged_out:
            result["login_confirmed"] = False
            result["evidence"] = identity_evidence
        return result

    def _probe_page_login(
        self,
        platform: str,
        url: str,
        positive_markers: List[str],
        strong_patterns: List[str] = None,
        negative_patterns: List[str] = None,
    ) -> Dict:
        result = self._base_auth_probe_result(platform)
        if self.live_login_probe:
            try:
                visible = self.live_login_probe(platform, 15) or {}
            except Exception as exc:
                visible = {
                    "reachable": False,
                    "login_confirmed": None,
                    "evidence": f"{platform}可见账号控件检查失败",
                    "error": str(exc),
                    "final_url": url,
                }
            result["reachable"] = bool(visible.get("reachable"))
            result["login_confirmed"] = visible.get("login_confirmed")
            result["evidence"] = str(
                visible.get("evidence") or f"{platform}可见账号控件检查无结论"
            )
            result["error"] = str(visible.get("error") or "")
            result["final_url"] = str(visible.get("final_url") or url)
            return result

        account = self.account_manager.get_account(platform) or {}
        if account.get("browser_session"):
            html, final_url, error = self._request_browser_html(
                url=url,
                platform=platform,
                storage_state_text=account.get("browser_session", ""),
                timeout=8,
            )
        else:
            html, final_url, error = self._request_html(
                url,
                f"{platform}身份接口",
                timeout=8,
                access_mode=AUTHORIZED_SESSION_ACCESS_MODE,
            )
        result["final_url"] = final_url
        if error:
            result["error"] = error
            result["evidence"] = f"{platform} homepage request failed: {error}"
            return result
        result["reachable"] = True
        strong_patterns = strong_patterns or []
        for pattern in strong_patterns:
            if re.search(pattern, html, re.I):
                result["login_confirmed"] = True
                result["evidence"] = f"{platform} homepage matched strong login marker"
                return result
        negative_patterns = negative_patterns or []
        for pattern in negative_patterns:
            if re.search(pattern, html, re.I):
                result["login_confirmed"] = False
                result["evidence"] = f"{platform} homepage matched logged-out marker"
                return result
        matches = [marker for marker in positive_markers if marker in html]
        if matches:
            result["evidence"] = f"{platform} homepage marker matched: {', '.join(matches[:3])}"
        else:
            result["evidence"] = f"{platform} homepage reachable but no login marker"
        return result

    @staticmethod
    def _parse_json_text(text: str) -> Tuple[Dict, str]:
        try:
            return json.loads(text or "{}"), ""
        except Exception as exc:
            return {}, str(exc)

    def _find_json_value(self, payload, keys: set):
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key in keys and value not in (None, "", [], {}):
                    return value
                nested = self._find_json_value(value, keys)
                if nested not in (None, "", [], {}):
                    return nested
        elif isinstance(payload, list):
            for item in payload:
                nested = self._find_json_value(item, keys)
                if nested not in (None, "", [], {}):
                    return nested
        return None

    def _normalize_source_strategy(self, source_strategy: str) -> str:
        strategy = (source_strategy or "stable_first").strip().lower()
        aliases = {
            "hybrid": "stable_first",
            "stable-first": "stable_first",
            "stablefirst": "stable_first",
            "public_first": "stable_first",
            "public": "stable",
        }
        strategy = aliases.get(strategy, strategy)
        if strategy not in {"stable_first", "stable", "social"}:
            logger.warning(f"未知数据源策略 {source_strategy!r}，已回退为 stable_first")
            return "stable_first"
        return strategy

    def _select_stable_source_names(self, stable_sources: Optional[List[str]]) -> List[str]:
        registry = sorted(
            (source for source in STABLE_SOURCE_REGISTRY if source.get("enabled", True)),
            key=lambda item: item.get("priority", 999),
        )
        available = {source["name"]: source for source in registry}
        if not stable_sources:
            return [source["name"] for source in registry]

        selected = []
        for name in stable_sources:
            if name in available and name not in selected:
                selected.append(name)
            else:
                logger.warning(f"政府官网不可用或未注册: {name}")
        return selected or [source["name"] for source in registry]

    def _build_search_query(self, keyword: str, province: Optional[str], city: Optional[str]) -> str:
        region_kw = ""
        if province:
            region_kw = province
        if city:
            region_kw = f"{province or ''}{city}"
        return f"{keyword} {region_kw}".strip() if region_kw else keyword

    def _build_stable_source_requests(
        self,
        keyword: str,
        province: Optional[str],
        city: Optional[str],
        stable_sources: List[str],
    ) -> List[Dict]:
        """从政府官网注册表生成第一阶段请求，不依赖社交平台循环。"""
        query = self._build_search_query(keyword, province, city)
        encoded_query = quote(query)
        selected = set(stable_sources or [])
        requests_to_make = []
        for source in sorted(STABLE_SOURCE_REGISTRY, key=lambda item: item.get("priority", 999)):
            if not source.get("enabled", True):
                continue
            if selected and source["name"] not in selected:
                continue
            source_region = str(source.get("source_region") or "")
            requested_region = city or province or ""
            if requested_region and source_region and requested_region not in source_region:
                continue
            url = source["url_template"].format(query=encoded_query, keyword=quote(keyword))
            requests_to_make.append({
                "channel": source["name"],
                "platform": source["name"],
                "source_group": "stable",
                "parser": source.get("parser", "generic"),
                "source_region": source_region,
                "url": url,
                "timeout": source.get("timeout", 10),
            })
        return requests_to_make

    def _build_social_source_requests(
        self,
        platform: str,
        keyword: str,
        province: Optional[str],
        city: Optional[str],
    ) -> List[Dict]:
        """生成第二阶段社交平台公开搜索请求；高门槛平台只做公开结果增强。"""
        query = self._build_search_query(keyword, province, city)
        encoded_query = quote(query)
        encoded_keyword = quote(keyword)
        requests_to_make = []

        if platform in SOCIAL_PLATFORM_ADAPTERS:
            adapter = get_adapter(platform)
            region_query = query[len(keyword):].strip() if query.startswith(keyword) else ""
            channel_name = {
                "微博": "微博搜索",
                "知乎": "知乎搜索",
                "B站": "B站搜索",
                "百度贴吧": "贴吧搜索",
                "豆瓣": "豆瓣搜索",
                "微信公众平台": "搜狗微信",
            }.get(platform, f"{platform}搜索")
            requests_to_make.append((channel_name, adapter.search_url(keyword, region_query)))
        elif platform == "微信公众平台":
            requests_to_make.append(("搜狗微信", f"https://weixin.sogou.com/weixin?type=2&query={encoded_query}"))
        else:
            enhanced = quote(f"{query} {platform}")
            requests_to_make.append((f"公开搜索增强-{platform}", f"https://www.baidu.com/s?wd={enhanced}"))

        return [
            {
                "channel": channel,
                "platform": platform,
                "source_group": "social",
                "parser": "generic",
                "url": url,
                "timeout": 10,
            }
            for channel, url in requests_to_make
        ]

    def _collect_from_source_requests(
        self,
        source_requests: List[Dict],
        keyword: str,
        region: str,
        collect_level: str,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        remaining: int,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> Tuple[List[Dict], List[Dict]]:
        records = []
        failures = []
        if remaining <= 0:
            return records, failures

        for request_info in source_requests:
            if len(records) >= remaining:
                break
            channel = request_info["channel"]
            url = request_info["url"]
            platform = request_info["platform"]
            source_group = request_info.get("source_group", "unknown")
            source_region = request_info.get("source_region", "")
            auth_context = None
            external_adapter_enabled = False
            if source_group == "social":
                auth_context = self._get_social_auth_context(platform, keyword)
                adapter_supported = bool(
                    self.external_social_registry
                    and self.external_social_registry.supports(platform)
                )
                if adapter_supported:
                    adapter_decision = self.source_policy.check(
                        url,
                        channel,
                        access_mode=EXTERNAL_ADAPTER_ACCESS_MODE,
                    )
                    if adapter_decision.allowed:
                        access_decision = adapter_decision
                        external_adapter_enabled = True
                    else:
                        account = self.account_manager.get_account(platform) or {}
                        has_authorized_session = bool(
                            (account.get("cookie") or "").strip()
                            or (account.get("browser_session") or "").strip()
                        )
                        access_decision = self.source_policy.check(
                            url,
                            channel,
                            access_mode=(
                                AUTHORIZED_SESSION_ACCESS_MODE
                                if has_authorized_session
                                else PUBLIC_CRAWLER_ACCESS_MODE
                            ),
                        )
                else:
                    account = self.account_manager.get_account(platform) or {}
                    has_authorized_session = bool(
                        (account.get("cookie") or "").strip()
                        or (account.get("browser_session") or "").strip()
                    )
                    access_decision = self.source_policy.check(
                        url,
                        channel,
                        access_mode=(
                            AUTHORIZED_SESSION_ACCESS_MODE
                            if has_authorized_session
                            else PUBLIC_CRAWLER_ACCESS_MODE
                        ),
                    )
            else:
                access_decision = self.source_policy.check(
                    url,
                    channel,
                    access_mode=PUBLIC_CRAWLER_ACCESS_MODE,
                )
            if not access_decision.allowed:
                failure = {
                    "channel": channel,
                    "platform": platform,
                    "source_group": source_group,
                    "url": url,
                    "error": (
                        f"source policy blocked [{access_decision.code}]: "
                        f"{access_decision.reason}"
                    ),
                    "policy_code": access_decision.code,
                    "source_rule_id": access_decision.source_rule_id,
                    "robots_status": access_decision.robots_status,
                    "duration_seconds": 0,
                }
                failures.append(failure)
                self._emit_progress(progress_callback, {
                    "type": "source_failure",
                    "message": f"{channel} 已被来源策略阻止: {access_decision.reason}",
                    **failure,
                })
                continue

            self.anti_crawl.delay()
            request_started = datetime.now()
            self._emit_progress(progress_callback, {
                "type": "source_start",
                "message": f"正在请求 {channel}",
                "channel": channel,
                "platform": platform,
                "source_group": source_group,
                "url": url,
                "keyword": keyword,
                "auth_mode": (auth_context or {}).get("auth_mode"),
                "session_mode": (auth_context or {}).get("session_mode"),
                "login_confirmed": (auth_context or {}).get("login_confirmed"),
                "external_adapter_enabled": external_adapter_enabled,
                "source_rule_id": access_decision.source_rule_id,
                "robots_status": access_decision.robots_status,
            })
            html_text = ""
            final_url = url
            error = None
            parsed_items = []
            adapter_name = ""
            adapter_backend = "html"
            adapter_error = ""

            if (
                source_group == "social"
                and self.external_social_registry
                and external_adapter_enabled
            ):
                adapter_outcome = self.external_social_registry.search(
                    platform=platform,
                    keyword=keyword,
                    limit=max(remaining - len(records), 1),
                    timeout=max(request_info.get("timeout", 10), 45),
                    auth_payload=self._build_external_adapter_auth_payload(platform),
                )
                adapter_name = adapter_outcome.adapter_name
                adapter_error = adapter_outcome.error
                if adapter_outcome.items:
                    parsed_items = adapter_outcome.items
                    adapter_backend = parsed_items[0].get(
                        "adapter_backend",
                        "external_bridge",
                    )
                    auth_context = {
                        "auth_mode": "external_cli",
                        "session_mode": "external_cli",
                        "login_confirmed": None,
                        "login_evidence": f"{adapter_name} returned structured read-only search results",
                    }
                elif adapter_outcome.available:
                    reason = adapter_error or "adapter returned no results"
                    self._emit_progress(progress_callback, {
                        "type": "adapter_fallback",
                        "message": f"{adapter_name} 未返回可用数据，回退现有浏览器采集: {reason}",
                        "channel": channel,
                        "platform": platform,
                        "source_group": source_group,
                        "adapter_name": adapter_name,
                        "error": reason,
                    })

            if not parsed_items:
                html_text, final_url, error = self._request_source_html(
                    url=url,
                    channel=channel,
                    platform=platform,
                    source_group=source_group,
                    timeout=request_info.get("timeout", 10),
                )
            elapsed = round((datetime.now() - request_started).total_seconds(), 2)
            if error:
                if adapter_error:
                    error = f"{adapter_name}: {adapter_error}; browser fallback: {error}"
                failure = {
                    "channel": channel,
                    "platform": platform,
                    "source_group": source_group,
                    "url": url,
                    "error": error,
                    "duration_seconds": elapsed,
                    "source_rule_id": access_decision.source_rule_id,
                    "source_support_level": access_decision.support_level,
                    "source_access_type": access_decision.access_type,
                    "platform_rule_status": access_decision.platform_rule_status,
                    "robots_status": access_decision.robots_status,
                }
                failures.append(failure)
                self._emit_progress(progress_callback, {
                    "type": "source_failure",
                    "message": f"{channel} 请求失败: {error}",
                    **failure,
                })
                continue

            if not parsed_items:
                previous_parser_hint = self._active_parser_hint
                self._active_parser_hint = request_info.get("parser", "")
                try:
                    parsed_items = self._parse_results(
                        platform,
                        html_text,
                        keyword,
                        channel,
                        final_url or url,
                    )
                finally:
                    self._active_parser_hint = previous_parser_hint
            if not parsed_items:
                debug_snapshot = self._write_social_parse_debug(
                    platform=platform,
                    channel=channel,
                    keyword=keyword,
                    url=final_url or url,
                    html_text=html_text,
                ) if source_group == "social" else ""
                parse_error = self._diagnose_social_parse_failure(platform, html_text) or "no parseable result"
                failure = {
                    "channel": channel,
                    "platform": platform,
                    "source_group": source_group,
                    "url": final_url or url,
                    "error": parse_error,
                    "duration_seconds": elapsed,
                    "source_rule_id": access_decision.source_rule_id,
                    "source_support_level": access_decision.support_level,
                    "source_access_type": access_decision.access_type,
                    "platform_rule_status": access_decision.platform_rule_status,
                    "robots_status": access_decision.robots_status,
                }
                if debug_snapshot:
                    failure["debug_snapshot"] = debug_snapshot
                failures.append(failure)
                self._emit_progress(progress_callback, {
                    "type": "source_failure",
                    "message": f"{channel} 未解析到有效结果: {parse_error}",
                    **failure,
                })
                continue

            before_count = len(records)
            filtered_reasons = []
            for item in parsed_items:
                item["source_group"] = source_group
                if source_region:
                    item["region"] = source_region
                item["source_rule_id"] = access_decision.source_rule_id
                item["source_support_level"] = access_decision.support_level
                item["source_access_type"] = access_decision.access_type
                item["platform_rule_status"] = access_decision.platform_rule_status
                item["robots_status"] = access_decision.robots_status
                if auth_context:
                    item["auth_mode"] = auth_context.get("auth_mode")
                    item["session_mode"] = auth_context.get("session_mode")
                    item["login_confirmed"] = auth_context.get("login_confirmed")
                    item["login_evidence"] = auth_context.get("login_evidence", "")
                record = self._normalize_record(
                    item=item,
                    platform=platform,
                    keyword=keyword,
                    region=region,
                    collector=channel,
                    data_type="real",
                    collect_level=collect_level,
                )
                initial_url = record.get("url", "")
                if not self._is_valid_social_record_url(record, platform, source_group):
                    filtered_reasons.append(f"invalid social url before enrichment: {initial_url or 'empty'}")
                    continue
                pub_dt = self._parse_time_optional(record.get("pub_time"))
                if pub_dt:
                    if start_time and pub_dt < start_time:
                        filtered_reasons.append(f"out of time range: {record.get('pub_time')}")
                        continue
                    if end_time and pub_dt > end_time + timedelta(days=1):
                        filtered_reasons.append(f"future/out of time range: {record.get('pub_time')}")
                        continue
                if source_group == "social" and platform == "百度贴吧":
                    self._enrich_tieba_record(record)
                if source_group == "social" and platform == "微博":
                    self._enrich_with_weibo_detail(record)
                if source_group == "social" and platform == "小红书" and len(record.get("content", "")) < 120:
                    self._enrich_with_xiaohongshu_detail_content(record)
                    if not self._is_valid_social_record_url(record, platform, source_group):
                        record["url"] = initial_url
                should_enrich_article = (
                    len(record.get("content", "")) < 80
                    or channel == "官方公开网页"
                )
                if (
                    should_enrich_article
                    and not self._source_acceptance_mode
                    and platform not in ("小红书", "百度贴吧", "微博")
                ):
                    if source_group == "social":
                        self._enrich_with_browser_article_content(record, platform)
                        if not self._is_valid_social_record_url(record, platform, source_group):
                            record["url"] = initial_url
                    if len(record.get("content", "")) < 80 or channel == "官方公开网页":
                        self._enrich_with_article_content(record)
                        if not self._is_valid_social_record_url(record, platform, source_group):
                            record["url"] = initial_url
                if not self._is_valid_social_record_url(record, platform, source_group):
                    filtered_reasons.append(f"invalid social url after enrichment: {record.get('url') or 'empty'}")
                    continue
                records.append(record)
                if len(records) >= remaining:
                    break

            added_count = len(records) - before_count
            if added_count == 0:
                reason_text = "; ".join(dict.fromkeys(filtered_reasons)) or "parsed results filtered before save"
                failure = {
                    "channel": channel,
                    "platform": platform,
                    "source_group": source_group,
                    "url": final_url or url,
                    "error": reason_text,
                    "duration_seconds": elapsed,
                    "parsed_count": len(parsed_items),
                    "source_rule_id": access_decision.source_rule_id,
                    "source_support_level": access_decision.support_level,
                    "source_access_type": access_decision.access_type,
                    "platform_rule_status": access_decision.platform_rule_status,
                    "robots_status": access_decision.robots_status,
                }
                debug_snapshot = self._write_social_parse_debug(
                    platform=platform,
                    channel=channel,
                    keyword=keyword,
                    url=final_url or url,
                    html_text=html_text,
                ) if source_group == "social" else ""
                if debug_snapshot:
                    failure["debug_snapshot"] = debug_snapshot
                failures.append(failure)
                self._emit_progress(progress_callback, {
                    "type": "source_failure",
                    "message": f"{channel} 解析到 {len(parsed_items)} 条但均未通过入库校验: {reason_text}",
                    **failure,
                })

            self._emit_progress(progress_callback, {
                "type": "source_success",
                "message": f"{channel} 新增 {added_count} 条候选数据",
                "channel": channel,
                "platform": platform,
                "source_group": source_group,
                "url": final_url or url,
                "duration_seconds": elapsed,
                "parsed_count": len(parsed_items),
                "auth_mode": (auth_context or {}).get("auth_mode"),
                "session_mode": (auth_context or {}).get("session_mode"),
                "login_confirmed": (auth_context or {}).get("login_confirmed"),
                "adapter_backend": adapter_backend,
                "adapter_name": adapter_name,
                "source_rule_id": access_decision.source_rule_id,
                "source_support_level": access_decision.support_level,
                "source_access_type": access_decision.access_type,
                "platform_rule_status": access_decision.platform_rule_status,
                "robots_status": access_decision.robots_status,
            })

        return self._deduplicate_results(records), failures

    def _write_social_parse_debug(
        self,
        platform: str,
        channel: str,
        keyword: str,
        url: str,
        html_text: str,
    ) -> str:
        """按显式开关保存脱敏诊断摘要；不落盘原始 HTML、关键词或查询参数。"""
        try:
            return self.diagnostic_store.write(
                platform=platform,
                channel=channel,
                url=url,
                html_text=html_text,
            )
        except Exception as exc:
            logger.debug(f"保存脱敏社交解析诊断失败: {exc}")
            return ""

    def _diagnose_social_parse_failure(self, platform: str, html_text: str) -> str:
        if platform != "小红书":
            return ""
        text = html_text or ""
        if re.search(r'"loggedIn"\s*:\s*false', text):
            return "小红书搜索页显示 loggedIn=false，请重新保存小红书 Cookie 或浏览器会话"
        if re.search(r'"feeds"\s*:\s*\[\s*\]', text) and "searchContext" in text:
            return "小红书搜索页已打开，但搜索结果 feeds 为空；可能是会话未生效、接口被风控或该关键词暂未返回网页端结果"
        if "验证码" in text or ("验证" in text and "登录" in text):
            return "小红书页面要求验证或登录，当前会话无法直接采集"
        if "searchContext" in text:
            return "小红书搜索页已打开，但页面中没有可解析的笔记卡片或搜索接口结果"
        return ""

    @staticmethod
    def _emit_progress(progress_callback: Optional[Callable[[Dict], None]], event: Dict):
        if not progress_callback:
            return
        payload = dict(event)
        payload.setdefault("time", datetime.now().isoformat())
        try:
            progress_callback(payload)
        except Exception as exc:
            logger.debug(f"progress callback failed: {exc}")

    def _count_real_by_group(self, records: List[Dict], source_group: str) -> int:
        return sum(
            1 for record in records
            if record.get("data_type") == "real" and record.get("source_group") == source_group
        )

    def _build_multi_channel_urls(self, platform: str, keyword: str,
                                   province: Optional[str], city: Optional[str],
                                   source_strategy: str = "hybrid") -> Dict[str, str]:
        """构建多渠道搜索URL"""
        region_kw = ""
        if province:
            region_kw = province
        if city:
            region_kw = f"{province}{city}"
        
        full_kw = f"{keyword} {region_kw}" if region_kw else keyword
        encoded_kw = quote(full_kw)
        encoded_keyword = quote(keyword)
        
        urls = {}

        if source_strategy in ("stable", "hybrid"):
            urls["百度新闻"] = f"https://www.baidu.com/s?wd={encoded_kw}&tn=news&rtt=4"
            urls["百度资讯"] = f"https://www.baidu.com/s?wd={encoded_kw}&tn=news&rtt=1"
            urls["搜狗新闻"] = f"https://news.sogou.com/news?query={encoded_kw}"
            urls["搜狗微信"] = f"https://weixin.sogou.com/weixin?type=2&query={encoded_kw}"

        if source_strategy in ("social", "hybrid"):
            if platform == "微博":
                urls["微博搜索"] = f"https://s.weibo.com/weibo?q={encoded_keyword}"
            elif platform == "知乎":
                urls["知乎搜索"] = f"https://www.zhihu.com/search?type=content&q={encoded_keyword}"
            elif platform == "B站":
                urls["B站搜索"] = f"https://search.bilibili.com/all?keyword={encoded_keyword}"
            elif platform == "百度贴吧":
                urls["贴吧搜索"] = f"https://tieba.baidu.com/f/search/res?qw={encoded_keyword}"
            elif platform == "豆瓣":
                urls["豆瓣搜索"] = f"https://www.douban.com/search?q={encoded_keyword}"
            elif platform in {"小红书", "抖音", "快手", "今日头条"}:
                enhanced = quote(f"{full_kw} {platform}")
                urls[f"百度增强-{platform}"] = f"https://www.baidu.com/s?wd={enhanced}&tn=news&rtt=1"
            elif platform == "微信公众平台":
                urls["搜狗微信"] = f"https://weixin.sogou.com/weixin?type=2&query={encoded_kw}"

        return urls

    def _parse_results(
        self,
        platform: str,
        html: str,
        keyword: str,
        channel: str = "",
        base_url: str = "",
    ) -> List[Dict]:
        """解析采集结果"""
        results = []
        
        try:
            soup = BeautifulSoup(html, "html.parser")
            parser = self._active_parser_hint or next(
                (source.get("parser") for source in STABLE_SOURCE_REGISTRY if source.get("name") == channel),
                "",
            )
            social_search_channel = (
                platform in SOCIAL_PLATFORM_ADAPTERS
                and not parser
                and channel not in STABLE_CHANNELS
                and not channel.startswith("百度")
                and channel not in {"搜狗新闻", "搜狗微信"}
            )

            if channel.startswith("百度") or parser == "baidu":
                results.extend(self._parse_baidu_news(soup, keyword, platform, channel, base_url))
            elif channel == "搜狗新闻" or parser == "sogou_news":
                results.extend(self._parse_sogou_news(soup, keyword, platform, channel, base_url))
            elif channel == "搜狗微信" or parser == "sogou_weixin":
                results.extend(self._parse_sogou_weixin(soup, keyword, platform, channel, base_url))
            elif parser == "official_listing":
                results.extend(self._parse_official_listing(soup, keyword, platform, base_url))
            elif channel == "微博搜索":
                results.extend(self._parse_weibo(soup, keyword, base_url))
            elif channel == "知乎搜索":
                results.extend(self._parse_zhihu(soup, keyword, base_url))
            elif channel == "B站搜索":
                results.extend(self._parse_bilibili(soup, keyword, base_url))
            elif channel == "贴吧搜索":
                results.extend(self._parse_tieba(soup, keyword, base_url))
            elif channel == "豆瓣搜索":
                results.extend(self._parse_douban(soup, keyword, base_url))
            elif platform in SOCIAL_PLATFORM_ADAPTERS:
                results.extend(extract_search_items_from_html(platform, html, base_url, keyword=keyword))
            else:
                results.extend(self._parse_generic(soup, keyword, platform, base_url))

            if len(results) < 3 and not social_search_channel and parser != "official_listing":
                generic_results = self._parse_generic(soup, keyword, platform, base_url)
                results.extend(generic_results)

        except Exception as e:
            logger.warning(f"{platform} 解析失败: {e}")

        return self._deduplicate_results(results)

    def _parse_official_listing(
        self,
        soup,
        keyword: str,
        platform: str,
        base_url: str = "",
    ) -> List[Dict]:
        """解析政府公开信息列表；业务采集按关键词信号过滤，验收模式只测连通与字段。"""
        results = []
        base_host = urlparse(base_url or "").hostname or ""
        date_pattern = re.compile(r"(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})日?")
        source_config = next(
            (
                source
                for source in STABLE_SOURCE_REGISTRY
                if source.get("name") == platform
            ),
            {},
        )
        link_selectors = list(source_config.get("link_selectors") or [])
        if link_selectors:
            links = []
            seen_links = set()
            for selector in link_selectors:
                for candidate in soup.select(selector):
                    marker = id(candidate)
                    if marker not in seen_links:
                        seen_links.add(marker)
                        links.append(candidate)
        else:
            links = soup.find_all("a", href=True)
        article_path_prefixes = tuple(source_config.get("article_path_prefixes") or ())
        require_date = bool(source_config.get("require_date", False))

        for link in links:
            raw_title = self._clean_text(link.get_text(" ", strip=True))
            raw_href = str(link.get("href", "") or "").strip()
            if raw_href.casefold().startswith("javascript:"):
                onclick_match = re.search(
                    r"""jumpToDetail\(\s*['"]([^'"]+)['"]\s*\)""",
                    str(link.get("onclick", "") or ""),
                    re.I,
                )
                raw_href = onclick_match.group(1) if onclick_match else ""
            normalized_url = self._normalize_url(raw_href, base_url)
            parsed_host = urlparse(normalized_url).hostname or ""
            if not raw_title or not normalized_url.startswith(("http://", "https://")):
                continue
            if base_host and parsed_host != base_host:
                continue
            normalized_path = urlparse(normalized_url).path or "/"
            if article_path_prefixes and not any(
                normalized_path.startswith(prefix)
                for prefix in article_path_prefixes
            ):
                continue

            context_parts = [raw_title]
            ancestor = link.parent
            for _ in range(2):
                if ancestor is None:
                    break
                context_parts.append(ancestor.get_text(" ", strip=True))
                ancestor = ancestor.parent
            context = self._clean_text(" ".join(context_parts))
            date_match = date_pattern.search(raw_title) or date_pattern.search(context[:500])
            if not date_match:
                date_match = re.search(
                    r"/(20\d{2})(\d{2})/t20\d{4}(\d{2})_",
                    normalized_path,
                )
            pub_time = ""
            if date_match:
                pub_time = (
                    f"{int(date_match.group(1)):04d}-"
                    f"{int(date_match.group(2)):02d}-"
                    f"{int(date_match.group(3)):02d}"
                )
            if require_date and not pub_time:
                continue
            title = date_pattern.sub("", raw_title)
            title = re.sub(r"\s+\d{1,2}:\d{2}(?::\d{2})?\s*$", "", title)
            title = re.sub(r"[（(]\s*[）)]", "", title).strip(" -_|·")
            if not (8 < len(title) < 200):
                continue
            if self._is_noise_result(title, normalized_url):
                continue
            if not self._source_acceptance_mode and not self._matches_keyword_signal(title, keyword):
                continue

            item = {
                "title": title[:160],
                "url": normalized_url,
                "source": platform,
                "platform": platform,
                "source_type": "official",
                "pub_time": pub_time,
                "content": title[:200],
                "collector": platform,
            }
            if self._source_acceptance_mode:
                item["acceptance_probe"] = True
                item["acceptance_scope"] = "source_connectivity_and_parse"
            results.append(item)
            if len(results) >= 15:
                break
        return results

    @staticmethod
    def _matches_keyword_signal(text: str, keyword: str) -> bool:
        clean_text = re.sub(r"\s+", "", str(text or "")).casefold()
        clean_keyword = re.sub(r"\s+", "", str(keyword or "")).casefold()
        if not clean_keyword:
            return True
        if clean_keyword in clean_text:
            return True
        chinese_runs = re.findall(r"[\u4e00-\u9fff]+", clean_keyword)
        signals = set()
        for run in chinese_runs:
            if len(run) <= 2:
                signals.add(run)
            else:
                signals.update(run[index:index + 2] for index in range(len(run) - 1))
        latin_tokens = re.findall(r"[a-z0-9]{2,}", clean_keyword)
        signals.update(latin_tokens)
        return any(signal in clean_text for signal in signals)

    def _parse_baidu_news(self, soup, keyword: str, platform: str, channel: str, base_url: str) -> List[Dict]:
        """解析百度新闻搜索结果"""
        results = []
        
        try:
            candidates = soup.find_all("div", class_="result")
            if not candidates:
                candidates = soup.select("div.result-op, div.c-container, div[class*=result]")

            for result in candidates:
                try:
                    title_elem = result.find("h3")
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    link_elem = title_elem.find("a", href=True)
                    url = self._normalize_url(link_elem["href"] if link_elem else "", base_url)
                    
                    content_elem = result.find("div", class_="c-abstract")
                    if not content_elem:
                        content_elem = result.find(["span", "div"], class_=lambda x: x and ("abstract" in x or "summary" in x or "text" in x))
                    content = content_elem.get_text(strip=True) if content_elem else title
                    
                    meta_text = " ".join(span.get_text(" ", strip=True) for span in result.find_all("span"))
                    source, pub_time = self._split_source_time(meta_text, fallback_source=channel)
                    
                    results.append({
                        "title": title[:120],
                        "url": url,
                        "source": source,
                        "platform": platform,
                        "pub_time": pub_time,
                        "content": content[:300],
                        "source_site": source,
                        "collector": channel,
                    })
                except:
                    continue
            
            if len(results) < 3:
                for item in soup.find_all("div", class_=lambda x: x and ("result" in x or "news" in x)):
                    try:
                        title_elem = item.find(["h3", "h4", "h2"])
                        if title_elem and title_elem.get_text(strip=True):
                            title = title_elem.get_text(strip=True)
                            link = title_elem.find("a", href=True)
                            url = self._normalize_url(link["href"] if link else "", base_url)
                            results.append({
                                "title": title[:120],
                                "url": url,
                                "source": channel,
                                "platform": platform,
                                "pub_time": "",
                                "content": title[:200],
                                "collector": channel,
                            })
                    except:
                        continue
                    
                    if len(results) >= 10:
                        break
        except:
            pass
        
        return results

    def _parse_sogou_news(self, soup, keyword: str, platform: str, channel: str, base_url: str) -> List[Dict]:
        """解析搜狗新闻搜索结果"""
        results = []
        selectors = ["div.vrwrap", "div.news-box", "li", "div.results"]
        for selector in selectors:
            for item in soup.select(selector):
                title_elem = item.find(["h3", "h4", "a"])
                if not title_elem:
                    continue
                title = title_elem.get_text(" ", strip=True)
                link = title_elem if title_elem.name == "a" else title_elem.find("a", href=True)
                if not title or len(title) < 6 or not link:
                    continue
                text = item.get_text(" ", strip=True)
                source, pub_time = self._split_source_time(text, fallback_source=channel)
                results.append({
                    "title": title[:120],
                    "url": self._normalize_url(link.get("href", ""), base_url),
                    "source": source,
                    "platform": platform,
                    "pub_time": pub_time,
                    "content": text[:300],
                    "collector": channel,
                })
                if len(results) >= 10:
                    return results
        return results

    def _parse_sogou_weixin(self, soup, keyword: str, platform: str, channel: str, base_url: str) -> List[Dict]:
        """解析搜狗微信搜索结果"""
        results = []
        for item in soup.select("li[id^=sogou_vr], div.txt-box, div.news-box"):
            title_elem = item.find(["h3", "h4"])
            link = title_elem.find("a", href=True) if title_elem else item.find("a", href=True)
            if not link:
                continue
            title = link.get_text(" ", strip=True)
            if not title or len(title) < 6:
                continue
            source_elem = item.find(class_=lambda x: x and ("account" in x or "s-p" in x))
            source = source_elem.get_text(" ", strip=True) if source_elem else "微信公众平台"
            text = item.get_text(" ", strip=True)
            _, pub_time = self._split_source_time(text, fallback_source=source)
            results.append({
                "title": title[:120],
                "url": self._normalize_url(link.get("href", ""), base_url),
                "source": source or "微信公众平台",
                "platform": platform,
                "pub_time": pub_time,
                "content": text[:300],
                "collector": channel,
            })
            if len(results) >= 10:
                break
        return results

    def _parse_weibo(self, soup, keyword: str, base_url: str = "") -> List[Dict]:
        """解析微博搜索结果"""
        results = []
        try:
            cards = soup.find_all("div", class_="card-wrap")
            if not cards:
                cards = soup.select("div[action-type='feed_list_item'], div.card, div[class*=card]")
            for card in cards:
                try:
                    text_elem = card.find("p", class_="txt") or card.select_one("[node-type='feed_list_content']")
                    if text_elem:
                        content = text_elem.get_text(" ", strip=True)
                        title = content[:60] + "..." if len(content) > 60 else content
                        time_elem = card.find("div", class_="from") or card.find(class_=lambda x: x and "from" in x)
                        author_elem = card.find("a", class_=lambda x: x and ("name" in x or "user" in x)) or card.find("a", attrs={"nick-name": True})
                        status_url = self._extract_weibo_status_url(card, base_url or "https://s.weibo.com")
                        if not status_url:
                            continue
                        
                        results.append({
                            "title": title,
                            "url": status_url,
                            "source": author_elem.get_text(" ", strip=True) if author_elem else "微博",
                            "platform": "微博",
                            "pub_time": time_elem.get_text(strip=True) if time_elem else "",
                            "content": content[:200],
                            "collector": "微博搜索",
                        })
                except:
                    continue
        except:
            pass
        return results

    def _extract_weibo_status_url(self, card, base_url: str = "") -> str:
        """优先提取单条微博详情 URL，避免把作者主页保存为结果 URL。"""
        candidates = []
        from_elem = card.find("div", class_="from") or card.find(class_=lambda x: x and "from" in x)
        if from_elem:
            candidates.extend(from_elem.find_all("a", href=True))
        candidates.extend(card.select(
            "a[action-type='feed_list_item_date'][href], "
            "a[action-type='fl_time'][href], "
            "a[href*='weibo.com/detail/'], "
            "a[href*='m.weibo.cn/status/'], "
            "a[href*='weibo.com/'][href]"
        ))

        for link in candidates:
            url = self._normalize_url(link.get("href", ""), base_url or "https://s.weibo.com")
            if self._is_weibo_status_url(url):
                return url
        return ""

    @staticmethod
    def _is_weibo_status_url(url: str) -> bool:
        parsed = urlparse(url or "")
        host = parsed.netloc.lower()
        if not (host.endswith("weibo.com") or host.endswith("weibo.cn")):
            return False
        segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
        if len(segments) >= 2 and segments[0] == "detail" and re.fullmatch(r"\d{6,}", segments[1]):
            return True
        if len(segments) >= 2 and segments[0] == "status" and re.fullmatch(r"\d{6,}", segments[1]):
            return True
        if len(segments) >= 3 and segments[0] == "tv" and segments[1] == "show":
            return True
        if len(segments) >= 2 and segments[0].isdigit():
            return bool(re.fullmatch(r"[0-9A-Za-z]+", segments[1]))
        return False

    def _is_valid_social_record_url(self, record: Dict, platform: str, source_group: str) -> bool:
        if source_group != "social":
            return True
        normalized_platform = record.get("platform") or platform
        url = record.get("url", "")
        if normalized_platform == "微博":
            return self._is_weibo_status_url(url)
        if normalized_platform == "小红书":
            parsed = urlparse(url or "")
            query = parse_qs(parsed.query)
            source_values = {value.lower() for value in query.get("xsec_source", [])}
            return (
                parsed.netloc.endswith("xiaohongshu.com")
                and bool(re.fullmatch(r"/explore/[0-9a-zA-Z]+/?", parsed.path))
                and bool(query.get("xsec_token", [""])[0])
                and bool(source_values & XIAOHONGSHU_SEARCH_SOURCES)
            )
        return True

    def _parse_zhihu(self, soup, keyword: str, base_url: str = "") -> List[Dict]:
        """解析知乎搜索结果"""
        results = []
        try:
            items = soup.find_all("div", class_="List-item")
            if not items:
                items = soup.select("div.SearchResult-Card, div.ContentItem, div[class*=SearchResult]")
            for item in items:
                try:
                    title_elem = item.find("h2") or item.find(["h3", "a"], class_=lambda x: x and ("title" in x.lower() or "Title" in x))
                    if title_elem:
                        title = title_elem.get_text(" ", strip=True)
                        link = title_elem.find("a", href=True)
                        if title_elem.name == "a" and title_elem.get("href"):
                            link = title_elem
                        excerpt = item.find("div", class_="RichText")
                        if not excerpt:
                            excerpt = item.find(class_=lambda x: x and ("excerpt" in x.lower() or "content" in x.lower()))
                        
                        results.append({
                            "title": title,
                            "url": self._normalize_url(link["href"] if link else "", base_url or "https://www.zhihu.com"),
                            "source": "知乎",
                            "platform": "知乎",
                            "pub_time": "",
                            "content": excerpt.get_text(strip=True)[:200] if excerpt else title,
                            "collector": "知乎搜索",
                        })
                except:
                    continue
        except:
            pass
        return results

    def _parse_bilibili(self, soup, keyword: str, base_url: str = "") -> List[Dict]:
        """解析B站搜索结果"""
        results = []
        try:
            videos = soup.find_all("div", class_="bili-video-card")
            if not videos:
                videos = soup.select("li.video-item, div.video-item, div[class*=video-card]")
            for video in videos:
                try:
                    title_elem = video.find("h3") or video.find("a", title=True)
                    if title_elem:
                        title = title_elem.get("title") or title_elem.get_text(" ", strip=True)
                        if not title or len(title.strip()) < 2:
                            continue
                        link = video.find("a", href=True)
                        normalized_url = self._normalize_url(link["href"] if link else "", base_url or "https://search.bilibili.com")
                        if self._is_noise_result(title, normalized_url):
                            continue
                        stats = video.find("div", class_="bili-video-card__stats")
                        
                        results.append({
                            "title": title,
                            "url": normalized_url,
                            "source": "B站",
                            "platform": "B站",
                            "pub_time": "",
                            "content": title[:200],
                            "stats": stats.get_text(strip=True) if stats else "",
                            "collector": "B站搜索",
                        })
                except:
                    continue
        except:
            pass
        return results

    def _parse_generic(self, soup, keyword: str, platform: str, base_url: str = "") -> List[Dict]:
        """通用解析"""
        results = []
        try:
            for link in soup.find_all("a", href=True):
                title = link.get_text(strip=True)
                href = link["href"]
                
                if title and len(title) > 8 and len(title) < 200:
                    normalized_url = self._normalize_url(href, base_url)
                    if self._is_noise_result(title, normalized_url):
                        continue
                    results.append({
                        "title": title[:120],
                        "url": normalized_url,
                        "source": platform,
                        "platform": platform,
                        "pub_time": "",
                        "content": title[:200],
                        "collector": "generic",
                    })
                    
                if len(results) >= 15:
                    break
        except:
            pass
        return results

    def _parse_tieba(self, soup, keyword: str, base_url: str = "") -> List[Dict]:
        """解析百度贴吧搜索结果"""
        results = []
        try:
            items = soup.select(
                "div.s_post, div.threadlist_lz, div[class*=post], "
                "div.thread-content-box, li"
            )
            for item in items:
                try:
                    link = item.select_one("a[href*='/p/']") or item.find("a", href=True)
                    if not link:
                        continue
                    title_elem = item.select_one(".title-wrap")
                    title = (
                        title_elem.get_text(" ", strip=True) if title_elem else ""
                    ) or link.get_text(" ", strip=True) or link.get("title", "")
                    if len(title) < 6:
                        continue
                    abstract_elem = item.select_one(".abstract-wrap")
                    content = (
                        abstract_elem.get_text(" ", strip=True)
                        if abstract_elem else item.get_text(" ", strip=True)
                    )
                    forum_elem = item.select_one(".forum-name-text, .forum-name")
                    author_elem = item.find(class_=lambda x: x and ("author" in x.lower() or "user" in x.lower()))
                    time_elem = item.find(class_=lambda x: x and ("time" in x.lower() or "date" in x.lower()))
                    results.append({
                        "title": title[:120],
                        "url": self._normalize_url(link.get("href", ""), base_url or "https://tieba.baidu.com"),
                        "source": (
                            forum_elem.get_text(" ", strip=True) if forum_elem
                            else author_elem.get_text(" ", strip=True) if author_elem
                            else "百度贴吧"
                        ),
                        "platform": "百度贴吧",
                        "pub_time": time_elem.get_text(" ", strip=True) if time_elem else "",
                        "content": content[:300],
                        "collector": "贴吧搜索",
                    })
                    if len(results) >= 10:
                        break
                except:
                    continue
        except:
            pass
        return results

    def _parse_douban(self, soup, keyword: str, base_url: str = "") -> List[Dict]:
        """解析豆瓣搜索结果"""
        results = []
        try:
            items = soup.select("div.result, div.result-list, div[class*=result]")
            for item in items:
                try:
                    link = item.find("a", href=True)
                    if not link:
                        continue
                    title = link.get_text(" ", strip=True) or link.get("title", "")
                    if len(title) < 6:
                        continue
                    content_elem = item.find("p") or item.find(class_=lambda x: x and ("content" in x.lower() or "info" in x.lower()))
                    source_elem = item.find(class_=lambda x: x and ("source" in x.lower() or "user" in x.lower()))
                    results.append({
                        "title": title[:120],
                        "url": self._normalize_url(link.get("href", ""), base_url or "https://www.douban.com"),
                        "source": source_elem.get_text(" ", strip=True) if source_elem else "豆瓣",
                        "platform": "豆瓣",
                        "pub_time": "",
                        "content": content_elem.get_text(" ", strip=True)[:300] if content_elem else title[:200],
                        "collector": "豆瓣搜索",
                    })
                    if len(results) >= 10:
                        break
                except:
                    continue
        except:
            pass
        return results

    def _normalize_record(
        self,
        item: Dict,
        platform: str,
        keyword: str,
        region: str,
        collector: str,
        data_type: str,
        collect_level: str,
    ) -> Dict:
        """统一采集数据契约，保持 downstream 仍可读取 JSON list。"""
        title = self._clean_text(item.get("title", ""))
        content = self._clean_text(item.get("content", ""))
        source = self._clean_text(item.get("source") or item.get("source_site") or platform or "未知来源")
        normalized_platform = item.get("platform") or platform or source
        pub_time, time_basis = self._normalize_pub_time(item.get("pub_time", ""))
        url = self._normalize_url(item.get("url", ""), "")
        source_type = item.get("source_type") or self._infer_source_type(source, normalized_platform, title, content)
        event_type = item.get("event_type") or self._infer_event_type(title, content, source_type)
        source_group = item.get("source_group")
        if not source_group:
            if normalized_platform in STABLE_CHANNELS:
                source_group = "stable"
            elif normalized_platform in SOCIAL_ENHANCEMENT_PLATFORMS:
                source_group = "social"
            else:
                source_group = "unknown"
        if source_group == "social" and self._is_suspicious_social_pub_time(
            normalized_platform,
            pub_time,
            item.get("pub_time", ""),
            content,
        ):
            pub_time = ""
            time_basis = "unknown"

        repost = self._safe_int(item.get("repost_count", item.get("reposts", 0)))
        comment = self._safe_int(item.get("comment_count", item.get("comments", 0)))
        like = self._safe_int(item.get("like_count", item.get("likes", 0)))
        heat_index = item.get("heat_index")
        if heat_index is None:
            heat_index = round(min((repost * 1.5 + comment * 2 + like) / 100, 100), 2)

        record = {
            "title": title[:160],
            "content": content,
            "url": url,
            "pub_time": pub_time,
            "time_basis": time_basis,
            "source": source,
            "platform": normalized_platform,
            "source_type": source_type,
            "keyword": keyword,
            "region": item.get("region") or region,
            "data_type": data_type,
            "collector": item.get("collector") or collector,
            "source_group": source_group,
            "crawl_time": datetime.now().isoformat(),
            "event_type": event_type,
            "heat_index": heat_index,
            "repost_count": repost,
            "comment_count": comment,
            "like_count": like,
            "collect_level": collect_level,
        }

        for key in (
            "author",
            "case_location",
            "case_type",
            "injury_count",
            "main_event_type",
            "video_id",
            "original_platform",
            "search_origin",
            "xhs_source",
            "search_rank",
            "author_url",
            "detail_enriched",
            "detail_source",
            "adapter_backend",
            "adapter_name",
            "external_id",
            "view_count",
            "duration",
            "source_rule_id",
            "source_support_level",
            "source_access_type",
            "platform_rule_status",
            "robots_status",
            "acceptance_probe",
            "acceptance_scope",
        ):
            if item.get(key):
                record[key] = item[key]

        if "auth_mode" in item:
            record["auth_mode"] = item.get("auth_mode") or "guest"
        if "session_mode" in item:
            record["session_mode"] = item.get("session_mode") or record.get("auth_mode") or "guest"
        if "login_confirmed" in item:
            record["login_confirmed"] = item.get("login_confirmed")
        if item.get("login_evidence"):
            record["login_evidence"] = item.get("login_evidence")

        return record

    def _enrich_with_article_content(self, record: Dict):
        """尝试抓取详情页正文，失败时保留搜索摘要。"""
        url = record.get("url", "")
        if not url.startswith(("http://", "https://")):
            return
        if any(domain in urlparse(url).netloc for domain in ["baidu.com", "sogou.com"]):
            return

        html_text, final_url, error = self._request_html(url, "article-detail")
        if error:
            return
        detail = self._extract_article_content(html_text, final_url or url)
        if detail.get("content") and len(detail["content"]) > len(record.get("content", "")):
            record["content"] = detail["content"][:2000]
        if detail.get("title") and len(record.get("title", "")) < 12:
            record["title"] = detail["title"][:160]
        if detail.get("source"):
            record["source"] = detail["source"]
            record["source_type"] = self._infer_source_type(
                record["source"], record.get("platform", ""), record.get("title", ""), record.get("content", "")
            )
        if detail.get("pub_time"):
            pub_time, time_basis = self._normalize_pub_time(detail["pub_time"])
            if pub_time:
                record["pub_time"] = pub_time
                record["time_basis"] = time_basis
        if final_url:
            record["url"] = self._normalize_url(final_url, "")
        if detail.get("detail_source"):
            record["detail_enriched"] = True
            record["detail_source"] = detail["detail_source"]

    def _extract_article_content(self, html_text: str, url: str = "") -> Dict:
        """从通用新闻详情页抽取正文、标题、来源、时间。"""
        soup = BeautifulSoup(html_text, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
            tag.decompose()

        title = ""
        if soup.title:
            title = self._clean_text(soup.title.get_text(" ", strip=True))
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            title = self._clean_text(h1.get_text(" ", strip=True))

        source = ""
        pub_time = ""
        for meta in soup.find_all("meta"):
            name = (meta.get("name") or meta.get("property") or "").lower()
            value = meta.get("content", "")
            if not value:
                continue
            if name in {"author", "article:author", "source", "mediaid"}:
                source = self._clean_text(value)
            if name in {"article:published_time", "pubdate", "publishdate", "date"}:
                pub_time = value

        page_text = soup.get_text(" ", strip=True)
        if not pub_time:
            _, pub_time = self._split_source_time(page_text, fallback_source=source or "")

        paragraphs = []
        for p in soup.find_all("p"):
            text = self._clean_text(p.get_text(" ", strip=True))
            if len(text) >= 20:
                paragraphs.append(text)
        content = "\n".join(paragraphs)
        if len(content) < 80:
            article = soup.find(["article", "main"]) or soup.find(class_=lambda x: x and any(k in x.lower() for k in ["article", "content", "正文", "detail"]))
            if article:
                content = self._clean_text(article.get_text(" ", strip=True))

        result = {
            "title": title,
            "source": source,
            "pub_time": pub_time,
            "content": content[:3000],
        }
        if self.external_content_adapters and self._is_government_url(url):
            outcome = self.external_content_adapters.newspaper.extract(
                html=html_text,
                url=url,
                language="zh",
                timeout=20,
            )
            if outcome.data:
                external = outcome.data
                external_content = self._clean_text(external.get("content", ""))
                if len(external_content) > len(result.get("content", "")):
                    result["content"] = external_content[:3000]
                if external.get("title"):
                    result["title"] = self._clean_text(external["title"])[:160]
                if external.get("source"):
                    result["source"] = self._clean_text(external["source"])[:80]
                if external.get("pub_time"):
                    result["pub_time"] = external["pub_time"]
                result["detail_source"] = "newspaper4k"
        return result

    @staticmethod
    def _is_government_url(url: str) -> bool:
        host = urlparse(url or "").netloc.lower().split(":", 1)[0]
        return host == "gov.cn" or host.endswith(".gov.cn")

    def _deduplicate_results(self, records: List[Dict]) -> List[Dict]:
        """按 URL 和内容指纹去重，优先保留正文更完整的记录。"""
        best_by_key = {}
        order = []
        for record in records:
            url = self._normalize_url(record.get("url", ""), "")
            text = self._clean_text((record.get("title", "") + record.get("content", ""))[:300])
            fingerprint = re.sub(r"\W+", "", text.lower())[:120]
            key = url or fingerprint
            if not key:
                continue
            if key not in best_by_key:
                order.append(key)
                best_by_key[key] = record
                continue
            existing = best_by_key[key]
            if len(record.get("content", "")) > len(existing.get("content", "")):
                best_by_key[key] = record
        return [best_by_key[k] for k in order]

    @staticmethod
    def _limit_results_with_platform_coverage(
        records: List[Dict],
        max_results: int,
        platforms: List[str],
    ) -> List[Dict]:
        """轮询各已选平台取数，避免第一个平台耗尽整个任务配额。"""
        if max_results <= 0:
            return []

        platform_order = list(dict.fromkeys(platforms or []))
        buckets = {platform: [] for platform in platform_order}
        other = []
        for record in records:
            platform = record.get("platform")
            if platform in buckets:
                buckets[platform].append(record)
            else:
                other.append(record)

        selected = []
        while len(selected) < max_results:
            added = False
            for platform in platform_order:
                if buckets[platform]:
                    selected.append(buckets[platform].pop(0))
                    added = True
                    if len(selected) >= max_results:
                        break
            if not added:
                break

        if len(selected) < max_results:
            selected.extend(other[: max_results - len(selected)])
        return selected

    def _build_meta(
        self,
        data: List[Dict],
        keywords: List[str],
        platforms: List[str],
        region: str,
        time_range: str,
        collect_level: str,
        source_strategy: str,
        min_real_results: int,
        failures: List[Dict],
        started_at: datetime,
        stable_sources: List[str] = None,
        source_acceptance: bool = False,
    ) -> Dict:
        total = len(data)
        real_count = sum(1 for item in data if item.get("data_type") == "real")
        stable_real_count = sum(
            1 for item in data
            if item.get("data_type") == "real" and item.get("source_group") == "stable"
        )
        social_real_count = sum(
            1 for item in data
            if item.get("data_type") == "real" and item.get("source_group") == "social"
        )
        mock_count = sum(1 for item in data if item.get("data_type") == "mock")
        valid_url_count = sum(1 for item in data if str(item.get("url", "")).startswith(("http://", "https://")))
        valid_time_count = 0
        content_lengths = []
        for item in data:
            try:
                datetime.fromisoformat(str(item.get("pub_time", "")).split("+")[0])
                valid_time_count += 1
            except Exception:
                pass
            content_lengths.append(len(item.get("content", "") or ""))

        empty_content_count = sum(1 for item in data if not item.get("content"))
        avg_content_length = round(sum(content_lengths) / total, 2) if total else 0
        platform_dist = {}
        source_type_dist = {}
        for item in data:
            platform_dist[item.get("platform") or item.get("source") or "未知"] = platform_dist.get(item.get("platform") or item.get("source") or "未知", 0) + 1
            source_type_dist[item.get("source_type") or "unknown"] = source_type_dist.get(item.get("source_type") or "unknown", 0) + 1

        now = datetime.now()
        recent_24h_count = 0
        title_counts = {}
        for item in data:
            title_key = re.sub(r"\W+", "", self._clean_text(item.get("title", "")).lower())
            if title_key:
                title_counts[title_key] = title_counts.get(title_key, 0) + 1
            try:
                pub_dt = datetime.fromisoformat(str(item.get("pub_time", "")).split("+")[0])
                if 0 <= (now - pub_dt).total_seconds() <= 86400:
                    recent_24h_count += 1
            except Exception:
                pass

        duplicate_title_count = sum(count - 1 for count in title_counts.values() if count > 1)
        title_duplicate_rate = round(duplicate_title_count / total, 2) if total else 0
        valid_url_rate = round(valid_url_count / total, 2) if total else 0
        valid_time_rate = round(valid_time_count / total, 2) if total else 0
        recent_24h_ratio = round(recent_24h_count / total, 2) if total else 0
        official_media_count = source_type_dist.get("official", 0) + source_type_dist.get("media", 0)
        official_media_ratio = round(official_media_count / total, 2) if total else 0
        public_ratio = round(source_type_dist.get("public", 0) / total, 2) if total else 0

        source_health = self._build_source_health(data, failures)
        social_auth = {}
        for platform, probe in self._auth_probe_cache.items():
            social_auth[platform] = {
                "reachable": probe.get("reachable"),
                "login_confirmed": probe.get("login_confirmed"),
                "username_or_hint": probe.get("username_or_hint", ""),
                "evidence": probe.get("evidence", ""),
                "error": probe.get("error", ""),
                "cookie_used": probe.get("cookie_used", False),
                "auth_mode": probe.get("auth_mode", "guest"),
                "session_mode": probe.get("session_mode", probe.get("auth_mode", "guest")),
                "final_url": probe.get("final_url", ""),
            }
        login_confirmed_count = sum(1 for probe in social_auth.values() if probe.get("login_confirmed") is True)
        cookie_platform_count = sum(1 for probe in social_auth.values() if probe.get("cookie_used"))
        browser_session_platform_count = sum(
            1 for probe in social_auth.values()
            if probe.get("session_mode") == "browser_session"
        )
        browser_session_record_count = sum(
            1 for item in data
            if item.get("session_mode") == "browser_session"
        )
        external_adapter_record_count = sum(
            1 for item in data
            if item.get("adapter_backend") == "external_cli"
        )
        external_adapter_status = (
            self.external_social_registry.status()
            if self.external_social_registry
            else []
        )
        external_content_status = (
            self.external_content_adapters.status()
            if self.external_content_adapters
            else []
        )
        external_enrichment_record_count = sum(
            1 for item in data
            if item.get("detail_source") in {"aiotieba", "newspaper4k"}
        )

        real_ratio = round(real_count / total, 2) if total else 0
        reached_min_real = real_count >= min_real_results
        quality_assessment = build_collection_assessment(data, {
            "min_real_results": min_real_results,
            "social_platforms": platforms,
            "stable_sources": stable_sources or [],
            "failures": failures,
        })
        if source_acceptance:
            quality_assessment["status_detail"] = (
                f"稳定源验收取得 {real_count} 条真实公开记录；"
                "该结果只证明来源连通、列表可解析且最小字段有效，不代表关键词覆盖或业务数据质量。"
            )

        return {
            "generated_at": datetime.now().isoformat(),
            "started_at": started_at.isoformat(),
            "duration_seconds": round((datetime.now() - started_at).total_seconds(), 2),
            "keywords": keywords,
            "stable_sources": stable_sources or [],
            "social_platforms": platforms,
            "platforms": platforms,
            "region": region,
            "time_range": time_range,
            "collect_level": collect_level,
            "source_strategy": source_strategy,
            "source_acceptance_mode": bool(source_acceptance),
            "acceptance_scope": (
                "source_connectivity_and_parse" if source_acceptance else ""
            ),
            "use_system_proxy": self.use_system_proxy,
            "authorized_social_platforms": self.account_manager.list_authorized_platforms(),
            "min_real_results": min_real_results,
            "reached_min_real_results": reached_min_real,
            "summary": {
                "total": total,
                "real_count": real_count,
                "stable_real_count": stable_real_count,
                "social_real_count": social_real_count,
                "mock_count": mock_count,
                "real_ratio": real_ratio,
                "platform_count": len(platform_dist),
                "valid_url_count": valid_url_count,
                "valid_time_count": valid_time_count,
                "valid_url_rate": valid_url_rate,
                "valid_time_rate": valid_time_rate,
                "recent_24h_count": recent_24h_count,
                "recent_24h_ratio": recent_24h_ratio,
                "official_media_ratio": official_media_ratio,
                "public_ratio": public_ratio,
                "title_duplicate_rate": title_duplicate_rate,
                "empty_content_count": empty_content_count,
                "avg_content_length": avg_content_length,
                "check_status_code": quality_assessment["status_code"],
                "check_status_label": quality_assessment["status_label"],
                "check_status_detail": quality_assessment["status_detail"],
                "login_confirmed_platform_count": login_confirmed_count,
                "cookie_platform_count": cookie_platform_count,
                "browser_session_platform_count": browser_session_platform_count,
                "browser_session_record_count": browser_session_record_count,
                "external_adapter_record_count": external_adapter_record_count,
                "external_enrichment_record_count": external_enrichment_record_count,
            },
            "quality_metrics": {
                "valid_url_rate": valid_url_rate,
                "valid_time_rate": valid_time_rate,
                "recent_24h_ratio": recent_24h_ratio,
                "official_media_ratio": official_media_ratio,
                "public_ratio": public_ratio,
                "title_duplicate_rate": title_duplicate_rate,
                "avg_content_length": avg_content_length,
                "empty_content_count": empty_content_count,
            },
            "quality_assessment": quality_assessment,
            "source_health": source_health,
            "social_auth": social_auth,
            "external_social_adapters": external_adapter_status,
            "external_content_adapters": external_content_status,
            "platform_distribution": platform_dist,
            "source_type_distribution": source_type_dist,
            "failures": failures[:30],
        }

    def _build_source_health(self, data: List[Dict], failures: List[Dict]) -> List[Dict]:
        health = {}
        for item in data:
            channel = item.get("collector") or item.get("platform") or "未知源"
            entry = health.setdefault(channel, {
                "channel": channel,
                "platform": item.get("platform") or "",
                "source_group": item.get("source_group") or "unknown",
                "success_count": 0,
                "failure_count": 0,
                "last_error": "",
                "duration_seconds": 0,
                "status": "ok",
            })
            entry["success_count"] += 1
        for failure in failures:
            channel = failure.get("channel") or "未知源"
            entry = health.setdefault(channel, {
                "channel": channel,
                "platform": failure.get("platform") or "",
                "source_group": failure.get("source_group") or "unknown",
                "success_count": 0,
                "failure_count": 0,
                "last_error": "",
                "duration_seconds": 0,
                "status": "failed",
            })
            entry["failure_count"] += 1
            entry["last_error"] = failure.get("error", "")
            entry["duration_seconds"] = max(entry.get("duration_seconds", 0), failure.get("duration_seconds", 0) or 0)
        for entry in health.values():
            if entry["success_count"] and entry["failure_count"]:
                entry["status"] = "partial"
            elif entry["success_count"]:
                entry["status"] = "ok"
            elif entry["failure_count"]:
                entry["status"] = "failed"
        return sorted(health.values(), key=lambda item: (item.get("source_group", ""), item.get("channel", "")))

    @staticmethod
    def _is_noise_result(title: str, url: str) -> bool:
        text = f"{title or ''} {url or ''}".lower()
        parsed = urlparse(url or "")
        host = parsed.netloc.lower()
        if any(domain in host for domain in {"beian.miit.gov.cn", "miit.gov.cn"}):
            return True
        noise_terms = [
            "备案", "icp", "许可证", "用户协议", "隐私政策", "隐私权政策",
            "关于我们", "联系我们", "帮助中心", "copyright", "营业执照",
        ]
        if any(term in text for term in noise_terms):
            return True
        if title and title.strip().startswith(("http://", "https://")) and len(title.strip()) > 40:
            return True
        return False

    def _normalize_url(self, raw_url: str, base_url: str = "") -> str:
        if not raw_url:
            return ""
        url = str(raw_url).strip()
        if url.startswith("//"):
            url = "https:" + url
        elif base_url and not url.startswith(("http://", "https://")):
            url = urljoin(base_url, url)

        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        for key in ("url", "u", "target"):
            if key in query and query[key]:
                candidate = unquote(query[key][0])
                if candidate.startswith(("http://", "https://")):
                    url = candidate
                    parsed = urlparse(url)
                    break

        if parsed.fragment:
            url = parsed._replace(fragment="").geturl()
        return url

    def _split_source_time(self, text: str, fallback_source: str) -> Tuple[str, str]:
        clean = self._clean_text(text)
        if not clean:
            return fallback_source, ""

        time_patterns = [
            r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?",
            r"\d{1,2}月\d{1,2}日(?:\s+\d{1,2}:\d{2})?",
            r"\d+\s*分钟前",
            r"\d+\s*小时前",
            r"刚刚",
            r"昨天(?:\s+\d{1,2}:\d{2})?",
            r"前天(?:\s+\d{1,2}:\d{2})?",
        ]
        pub_time = ""
        for pattern in time_patterns:
            match = re.search(pattern, clean)
            if match:
                pub_time = match.group(0)
                break

        source = fallback_source
        if pub_time:
            before = clean.split(pub_time)[0]
            parts = [p for p in re.split(r"[\s|·_-]+", before) if p]
            if parts:
                source = parts[-1][:40]
        return source or fallback_source, pub_time or ""

    def _normalize_pub_time(self, time_str: str) -> Tuple[str, str]:
        """Return a display-safe publication time and its confidence basis."""
        text = self._clean_text(str(time_str or ""))
        if not text:
            return "", "unknown"

        if re.fullmatch(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?", text):
            parsed = self._parse_time_optional(text)
            return (parsed.date().isoformat(), "published_date") if parsed else ("", "unknown")

        if re.fullmatch(r"\d{1,2}月\d{1,2}日", text):
            parsed = self._parse_time_optional(text)
            return (parsed.date().isoformat(), "published_date") if parsed else ("", "unknown")

        parsed = self._parse_time_optional(text)
        if not parsed:
            return "", "unknown"

        if re.search(r"\d{1,2}:\d{2}", text) or any(marker in text for marker in ("刚刚", "分钟前", "小时前")):
            return parsed.replace(microsecond=0).isoformat(), "published_time"

        return parsed.date().isoformat(), "published_date"

    def _is_suspicious_social_pub_time(self, platform: str, pub_time: str, raw_time: str = "", context: str = "") -> bool:
        if platform not in SOCIAL_ENHANCEMENT_PLATFORMS:
            return False
        parsed = self._parse_time_optional(pub_time)
        if not parsed:
            return False
        if parsed.year > datetime.now().year - 5:
            return False
        text = self._clean_text(f"{raw_time} {context}")[:1500]
        profile_markers = (
            "生日",
            "星座",
            "个人主页",
            "粉丝",
            "关注",
            "微博热搜",
            "热搜",
            "网站备案",
            "营业执照",
            "Copyright",
        )
        if any(marker in text for marker in profile_markers):
            return True
        return True

    @staticmethod
    def _clean_text(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", "", str(text))
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _safe_int(value) -> int:
        try:
            if isinstance(value, str):
                value = value.replace(",", "").replace("+", "")
                match = re.search(r"\d+", value)
                return int(match.group(0)) if match else 0
            return int(value)
        except Exception:
            return 0

    @staticmethod
    def _infer_source_type(source: str, platform: str, title: str, content: str) -> str:
        text = f"{source} {platform} {title} {content}"
        official_terms = ["官方", "公安", "警方", "交警", "政府", "应急", "发布", "通报", "人民政府"]
        media_terms = ["日报", "晚报", "新闻", "网", "电视台", "央广", "中新网", "记者", "媒体"]
        expert_terms = ["专家", "学者", "教授", "律师", "研究员", "解读"]
        public_platforms = {"微博", "知乎", "B站", "百度贴吧", "豆瓣", "小红书", "抖音", "快手", "今日头条"}

        if any(term in text for term in official_terms):
            return "official"
        if any(term in text for term in expert_terms):
            return "expert"
        if any(term in source for term in media_terms):
            return "media"
        if platform in public_platforms:
            return "public"
        return "unknown"

    @staticmethod
    def _infer_event_type(title: str, content: str, source_type: str) -> str:
        text = f"{title} {content}"
        if source_type == "official" and any(k in text for k in ["警情", "警方", "公安", "交警"]):
            return "police_briefing"
        if source_type == "official":
            return "official_response"
        if any(k in text for k in ["进展", "已控制", "调查", "勘查", "发布会", "处理"]):
            return "progress"
        if any(k in text for k in ["评论", "观察", "解读", "专家", "分析"]):
            return "analysis"
        if source_type == "public":
            return "public_opinion"
        return "media_report"

    def crawl_video(
        self,
        video_url: str,
        max_results: int = None,
        platforms: List[str] = None,
        social_platforms: List[str] = None,
        stable_sources: List[str] = None,
        time_range: str = "近一周",
        collect_level: str = "标准采集",
        source_strategy: str = "stable_first",
        min_real_results: int = None,
    ) -> List[Dict]:
        """针对特定视频进行多平台舆情采集"""
        level_config = COLLECT_LEVELS.get(collect_level, COLLECT_LEVELS["标准采集"])
        target_count = max_results or level_config["max_results"]

        source_platform, video_id = self._extract_video_id(video_url)
        if not video_id:
            video_id = video_url.strip()[:20]
            source_platform = "未知平台"

        if social_platforms is None:
            social_platforms = platforms if platforms is not None else PRIMARY_SOCIAL_PLATFORMS
        logger.info(f"视频采集: 来源={source_platform}, ID={video_id}")

        search_terms = [
            video_id,
            f"{source_platform} {video_id}",
            f"{video_id} 转载",
            f"{video_id} 讨论",
        ]
        results = self.crawl(
            keywords=search_terms,
            max_results=target_count,
            social_platforms=social_platforms,
            stable_sources=stable_sources,
            region=None,
            time_range=time_range,
            collect_level=collect_level,
            source_strategy=source_strategy,
            min_real_results=min_real_results,
        )

        for item in results:
            item["video_id"] = video_id
            item["original_platform"] = source_platform

        return results[:target_count]

    def _build_video_search_url(self, platform: str, keyword: str) -> str:
        """构建视频搜索URL"""
        encoded = requests.utils.quote(keyword)
        
        url_map = {
            "微博": f"https://s.weibo.com/weibo?q={encoded}",
            "知乎": f"https://www.zhihu.com/search?q={encoded}",
            "B站": f"https://search.bilibili.com/all?keyword={encoded}",
            "百度贴吧": f"https://tieba.baidu.com/f/search/res?qw={encoded}",
            "豆瓣": f"https://www.douban.com/search?q={encoded}",
            "今日头条": f"https://www.toutiao.com/search/?keyword={encoded}",
            "小红书": f"https://www.xiaohongshu.com/search?keyword={encoded}",
            "抖音": f"https://www.douyin.com/search?keyword={encoded}",
            "快手": f"https://www.kuaishou.com/search?keyword={encoded}",
        }
        return url_map.get(platform, f"https://www.baidu.com/s?wd={encoded}")

    def _extract_video_id(self, url: str) -> Tuple[str, str]:
        """提取视频ID"""
        patterns = {
            "B站": [r"bilibili\.com/video/(BV\w+)", r"BV(\w+)"],
            "抖音": [r"douyin\.com/video/(\d+)", r"v=(\d+)"],
            "快手": [r"kuaishou\.com/short-video/(\w+)"],
            "小红书": [r"xiaohongshu\.com/explore/(\w+)"],
            "微博": [r"weibo\.com/\d+/(\w+)"],
        }
        
        for platform, pats in patterns.items():
            for pat in pats:
                match = re.search(pat, url)
                if match:
                    return platform, match.group(1)
        
        return "未知平台", ""

    def _parse_region(self, region: str) -> Tuple[Optional[str], Optional[str]]:
        """解析地区字符串"""
        if not region:
            return None, None
        
        # 尝试匹配省份
        for province in get_all_provinces():
            if province in region:
                # 尝试匹配城市
                cities = get_cities_by_province(province)
                for city in cities:
                    if city in region:
                        return province, city
                return province, None
        
        return None, None

    def _parse_time_range(self, time_range: str) -> Tuple[Optional[datetime], Optional[datetime]]:
        """解析时间范围"""
        now = datetime.now()

        custom_match = re.fullmatch(
            r"\s*(\d{4}-\d{2}-\d{2})\s*至\s*(\d{4}-\d{2}-\d{2})\s*",
            time_range or "",
        )
        if custom_match:
            start = datetime.strptime(custom_match.group(1), "%Y-%m-%d")
            end = datetime.strptime(custom_match.group(2), "%Y-%m-%d").replace(
                hour=23,
                minute=59,
                second=59,
            )
            if end < start:
                raise ValueError("结束日期不能早于开始日期")
            return start, end

        if time_range == "自定义":
            return None, None
        
        days = TIME_RANGE_MAP.get(time_range, 7)
        
        if days < 0:
            return None, None
        
        start = now - timedelta(days=days)
        return start, now

    def _parse_time(self, time_str: str) -> datetime:
        """解析时间字符串"""
        return self._parse_time_optional(time_str) or datetime.now()

    def _parse_time_optional(self, time_str: str) -> Optional[datetime]:
        """解析发布时间；无法确认时返回 None，不用当前时间兜底。"""
        now = datetime.now()
        if not time_str:
            return None

        text = self._clean_text(str(time_str))
        if not text:
            return None

        if "刚刚" in text:
            return now

        match = re.search(r"(\d+)\s*分钟前", text)
        if match:
            return now - timedelta(minutes=int(match.group(1)))

        match = re.search(r"(\d+)\s*小时前", text)
        if match:
            return now - timedelta(hours=int(match.group(1)))

        match = re.search(r"昨天(?:\s*(\d{1,2}):(\d{2}))?", text)
        if match:
            base = now - timedelta(days=1)
            if match.group(1):
                return base.replace(hour=int(match.group(1)), minute=int(match.group(2)), second=0, microsecond=0)
            return base

        match = re.search(r"前天(?:\s*(\d{1,2}):(\d{2}))?", text)
        if match:
            base = now - timedelta(days=2)
            if match.group(1):
                return base.replace(hour=int(match.group(1)), minute=int(match.group(2)), second=0, microsecond=0)
            return base
        
        try:
            iso_text = text.strip().replace("Z", "+00:00")
            parsed_iso = datetime.fromisoformat(iso_text)
            if parsed_iso.tzinfo is not None:
                parsed_iso = parsed_iso.astimezone().replace(tzinfo=None)
            return parsed_iso
        except (TypeError, ValueError):
            pass

        # Weibo's statuses/show endpoint uses an RFC 2822-style timestamp,
        # for example: "Wed Jul 23 10:30:00 +0800 2026".
        try:
            parsed_email = parsedate_to_datetime(text.strip())
            if parsed_email is not None:
                if parsed_email.tzinfo is not None:
                    parsed_email = parsed_email.astimezone().replace(tzinfo=None)
                return parsed_email
        except (TypeError, ValueError, OverflowError):
            pass

        try:
            # 尝试多种格式
            formats = [
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d",
                "%Y/%m/%d %H:%M:%S",
                "%Y/%m/%d %H:%M",
                "%Y/%m/%d",
                "%Y年%m月%d日 %H:%M",
                "%Y年%m月%d日",
            ]
            for fmt in formats:
                try:
                    parsed = datetime.strptime(text.strip(), fmt)
                    return parsed
                except (TypeError, ValueError):
                    continue
            for fmt in ("%Y年%m月%d日 %H:%M", "%Y年%m月%d日"):
                try:
                    return datetime.strptime(f"{now.year}年{text.strip()}", fmt)
                except (TypeError, ValueError):
                    continue
        except (TypeError, ValueError):
            pass
        
        return None

    def save_to_json(self, data: List[Dict], output_path: str, meta_path: str = None):
        """保存数据到JSON文件"""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        if meta_path is None:
            path = Path(output_path)
            meta_path = str(path.with_name(f"{path.stem}_meta{path.suffix}"))

        if self.last_meta:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(self.last_meta, f, ensure_ascii=False, indent=2)
            logger.info(f"采集元数据已保存: {meta_path}")
        
        logger.info(f"数据已保存: {output_path} ({len(data)} 条)")


def parse_time_range(time_range: str) -> Tuple[datetime, datetime]:
    """解析时间范围"""
    now = datetime.now()

    custom_match = re.fullmatch(
        r"\s*(\d{4}-\d{2}-\d{2})\s*至\s*(\d{4}-\d{2}-\d{2})\s*",
        time_range or "",
    )
    if custom_match:
        start = datetime.strptime(custom_match.group(1), "%Y-%m-%d")
        end = datetime.strptime(custom_match.group(2), "%Y-%m-%d").replace(
            hour=23,
            minute=59,
            second=59,
        )
        if end < start:
            raise ValueError("结束日期不能早于开始日期")
        return start, end

    days = TIME_RANGE_MAP.get(time_range, 7)
    
    if time_range == "自定义":
        return None, None
    
    if days < 0:
        return None, None
    
    start = now - timedelta(days=days)
    return start, now


def crawl_and_save(
    keywords: List[str],
    output_path: str = "data/latest_news.json",
    platforms: List[str] = None,
    social_platforms: List[str] = None,
    stable_sources: List[str] = None,
    max_results: int = None,
    region: str = None,
    time_range: str = "近一周",
    collect_level: str = "标准采集",
    accounts: Dict[str, Dict] = None,
    source_strategy: str = "stable_first",
    min_real_results: int = None,
    meta_path: str = None,
    progress_callback: Optional[Callable[[Dict], None]] = None,
    use_system_proxy: bool = False,
    use_external_social_adapters: bool = True,
    enable_debug_snapshots: bool = False,
    source_acceptance: bool = False,
    live_browser_reader: Optional[Callable[[str, str, int], Tuple[str, str, Optional[str]]]] = None,
    live_login_probe: Optional[Callable[[str, int], Dict]] = None,
    topic: str = None,
) -> str:
    """采集并保存数据"""
    crawler = NewsCrawler(
        use_system_proxy=use_system_proxy,
        use_external_social_adapters=use_external_social_adapters,
        enable_debug_snapshots=enable_debug_snapshots,
        live_browser_reader=live_browser_reader,
        live_login_probe=live_login_probe,
    )
    
    if accounts:
        for platform, acc in accounts.items():
            crawler.set_account(
                platform,
                acc.get("username", ""),
                acc.get("password", ""),
                acc.get("cookie", ""),
                acc.get("note", ""),
                browser_session=acc.get("browser_session", ""),
                browser_cookie=acc.get("browser_cookie", ""),
                session_mode=acc.get("session_mode", ""),
                browser_login_confirmed=acc.get("browser_login_confirmed"),
                browser_login_evidence=acc.get("browser_login_evidence", ""),
            )
    
    data = crawler.crawl(
        keywords=keywords,
        max_results=max_results,
        platforms=platforms,
        social_platforms=social_platforms,
        stable_sources=stable_sources,
        region=region,
        time_range=time_range,
        collect_level=collect_level,
        source_strategy=source_strategy,
        min_real_results=min_real_results,
        progress_callback=progress_callback,
        source_acceptance=source_acceptance,
    )

    if topic and crawler.last_meta:
        crawler.last_meta["topic"] = topic

    crawler.save_to_json(data, output_path, meta_path=meta_path)
    
    if accounts:
        crawler.account_manager.clear_all()
    
    return output_path


def crawl_video_and_save(
    video_url: str,
    output_path: str = "data/video_news.json",
    platforms: List[str] = None,
    social_platforms: List[str] = None,
    stable_sources: List[str] = None,
    time_range: str = "近一周",
    collect_level: str = "标准采集",
    accounts: Dict[str, Dict] = None,
    source_strategy: str = "stable_first",
    min_real_results: int = None,
    meta_path: str = None,
    use_external_social_adapters: bool = True,
) -> str:
    """视频舆情采集并保存"""
    crawler = NewsCrawler(use_external_social_adapters=use_external_social_adapters)
    
    if accounts:
        for platform, acc in accounts.items():
            crawler.set_account(
                platform,
                acc.get("username", ""),
                acc.get("password", ""),
                acc.get("cookie", ""),
                acc.get("note", ""),
                browser_session=acc.get("browser_session", ""),
                browser_cookie=acc.get("browser_cookie", ""),
                session_mode=acc.get("session_mode", ""),
            )
    
    data = crawler.crawl_video(
        video_url=video_url,
        platforms=platforms,
        social_platforms=social_platforms,
        stable_sources=stable_sources,
        time_range=time_range,
        collect_level=collect_level,
        source_strategy=source_strategy,
        min_real_results=min_real_results,
    )
    
    crawler.save_to_json(data, output_path, meta_path=meta_path)
    
    if accounts:
        crawler.account_manager.clear_all()
    
    return output_path

