#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Playwright-backed social platform browser sessions."""

import html as html_lib
import hashlib
import ipaddress
import json
import queue
import re
import socket
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse, urlunparse
from urllib.request import getproxies

from src.sensitive_artifacts import (
    default_sensitive_root,
    ensure_private_directory,
    safe_remove_tree,
)


XIAOHONGSHU_SEARCH_SOURCES = {"pc_search", "style", "search", "web_search", "web_explore_feed"}
CLASH_FAKE_IP_NETWORK = ipaddress.ip_network("198.18.0.0/15")


@dataclass(frozen=True)
class SocialPlatformAdapter:
    name: str
    slug: str
    login_url: str
    search_url_template: str
    domains: Tuple[str, ...]
    login_markers: Tuple[str, ...]
    item_selectors: Tuple[str, ...]

    def search_url(self, keyword: str, region: str = "") -> str:
        query = f"{keyword} {region}".strip()
        return self.search_url_template.format(query=quote(query), keyword=quote(keyword))


SOCIAL_PLATFORM_ADAPTERS: Dict[str, SocialPlatformAdapter] = {
    "微博": SocialPlatformAdapter(
        name="微博",
        slug="weibo",
        login_url="https://weibo.com/",
        search_url_template="https://s.weibo.com/weibo?q={query}",
        domains=("weibo.com", "sina.com.cn"),
        login_markers=("我的首页", "退出登录", "profile", "me_name", "screen_name"),
        item_selectors=("div.card-wrap", "div[action-type='feed_list_item']", "div.card"),
    ),
    "B站": SocialPlatformAdapter(
        name="B站",
        slug="bilibili",
        login_url="https://www.bilibili.com/",
        search_url_template="https://search.bilibili.com/all?keyword={query}",
        domains=("bilibili.com",),
        login_markers=("isLogin", "退出登录", "个人中心", "nav-user-center"),
        item_selectors=("div.bili-video-card", "li.video-item", "div.video-item"),
    ),
    "小红书": SocialPlatformAdapter(
        name="小红书",
        slug="xiaohongshu",
        login_url="https://www.xiaohongshu.com/explore",
        search_url_template="https://www.xiaohongshu.com/search_result?keyword={query}",
        domains=("xiaohongshu.com",),
        login_markers=("退出登录", "创作中心", "个人主页", "userId", "nickname"),
        item_selectors=("section.note-item", "div.note-item", "a[href*='/explore/']"),
    ),
    "抖音": SocialPlatformAdapter(
        name="抖音",
        slug="douyin",
        login_url="https://www.douyin.com/",
        search_url_template="https://www.douyin.com/search/{query}",
        domains=("douyin.com",),
        login_markers=("退出登录", "creator", "用户中心", "douyin.com/user"),
        item_selectors=("div[data-e2e='search-card']", "li", "a[href*='/video/']"),
    ),
    "知乎": SocialPlatformAdapter(
        name="知乎",
        slug="zhihu",
        login_url="https://www.zhihu.com/",
        search_url_template="https://www.zhihu.com/search?type=content&q={query}",
        domains=("zhihu.com",),
        login_markers=("退出", "我的主页", "知乎首页", "AppHeader-profile"),
        item_selectors=("div.List-item", "div.SearchResult-Card", "div.ContentItem"),
    ),
    "微信公众平台": SocialPlatformAdapter(
        name="微信公众平台",
        slug="wechat_public",
        login_url="https://mp.weixin.qq.com/",
        search_url_template="https://weixin.sogou.com/weixin?type=2&query={query}",
        domains=("qq.com", "weixin.qq.com", "weixin.sogou.com"),
        login_markers=("退出", "公众号", "mp.weixin.qq.com", "微信公众平台"),
        item_selectors=("li[id^='sogou_vr']", "div.txt-box", "div.news-box"),
    ),
    "百度贴吧": SocialPlatformAdapter(
        name="百度贴吧",
        slug="tieba",
        login_url="https://tieba.baidu.com/",
        search_url_template="https://tieba.baidu.com/f/search/res?qw={query}",
        domains=("tieba.baidu.com", "baidu.com"),
        login_markers=("退出", "我的i贴吧", "用户名", "userbar"),
        item_selectors=("div.s_post", "div.threadlist_lz", "li"),
    ),
    "豆瓣": SocialPlatformAdapter(
        name="豆瓣",
        slug="douban",
        login_url="https://www.douban.com/",
        search_url_template="https://www.douban.com/search?q={query}",
        domains=("douban.com",),
        login_markers=("退出", "我的豆瓣", "账号", "douban.com/mine"),
        item_selectors=("div.result", "div.result-list", "div[class*='result']"),
    ),
    "快手": SocialPlatformAdapter(
        name="快手",
        slug="kuaishou",
        login_url="https://www.kuaishou.com/",
        search_url_template="https://www.kuaishou.com/search/video?searchKey={query}",
        domains=("kuaishou.com",),
        login_markers=("退出登录", "个人主页", "kwai", "userId"),
        item_selectors=("div[class*='video']", "a[href*='/short-video/']", "a[href*='/profile/']"),
    ),
    "今日头条": SocialPlatformAdapter(
        name="今日头条",
        slug="toutiao",
        login_url="https://www.toutiao.com/",
        search_url_template="https://so.toutiao.com/search?keyword={query}",
        domains=("toutiao.com",),
        login_markers=("退出登录", "个人主页", "用户中心", "toutiao"),
        item_selectors=("div[class*='result']", "a[href*='toutiao.com']", "li"),
    ),
}


# 登录判断只检查页面框架中的可见账号控件，避免把正文作者头像、脚本字段或
# 隐藏模板误判为当前操作者已经登录。身份接口仍由 crawler.py 优先调用；
# 这里是接口无结论时的浏览器可见证据层。
VISIBLE_LOGIN_CONTROL_RULES: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "微博": {
        "positive_selectors": (
            "[role='banner'] [class*='avatar' i]",
            "header [class*='avatar' i]",
            "[class*='header' i] [class*='avatar' i]",
            "nav a[href*='/u/'] img",
            "nav a[href*='/profile'] img",
        ),
        "positive_link_patterns": (
            r"(?:^|//)(?:www\.)?weibo\.com/(?:u/)?\d+(?:[/?#]|$)",
        ),
        "negative_selectors": (
            "[role='banner'] a[href*='login']",
            "header a[href*='login']",
            "nav a[href*='login']",
        ),
    },
    "B站": {
        "positive_selectors": (
            ".bili-header .header-avatar-wrap",
            ".bili-header .bili-avatar",
            "header .header-entry-mini",
            "header a[href*='space.bilibili.com'] img",
            "nav a[href*='space.bilibili.com'] img",
        ),
        "positive_link_patterns": (
            r"space\.bilibili\.com/\d+(?:[/?#]|$)",
        ),
        "negative_selectors": (
            ".bili-header .header-login-entry",
            "header [class*='login-entry' i]",
        ),
    },
    "小红书": {
        "positive_selectors": (
            "[class*='channel-list' i] a[href*='/user/profile/']",
            "header a[href*='/user/profile/'] img",
            "nav a[href*='/user/profile/'] img",
            "aside a[href*='/user/profile/'] img",
            "[class*='header' i] [class*='avatar' i]",
            "[class*='sidebar' i] a[href*='/user/profile/'] img",
        ),
        "positive_link_patterns": (
            r"xiaohongshu\.com/user/profile/[0-9a-zA-Z]+(?:[/?#]|$)",
            r"^/user/profile/[0-9a-zA-Z]+(?:[/?#]|$)",
        ),
        "negative_selectors": (
            "header [class*='login' i]",
            "nav [class*='login' i]",
            "aside [class*='login' i]",
        ),
    },
    "抖音": {
        "positive_selectors": (
            "[data-e2e='user-avatar']",
            "[data-e2e='user-profile']",
            "[data-e2e='header-user']",
            "header a[href*='/user/'] img",
            "nav a[href*='/user/'] img",
            "[class*='header' i] [class*='avatar' i]",
        ),
        "positive_link_patterns": (
            r"douyin\.com/user/[0-9A-Za-z_-]+(?:[/?#]|$)",
            r"^/user/[0-9A-Za-z_-]+(?:[/?#]|$)",
        ),
        "negative_selectors": (
            "[data-e2e='login-button']",
            "header [class*='login' i]",
            "nav [class*='login' i]",
        ),
    },
    "百度贴吧": {
        "positive_selectors": (
            "#top-bar img.user-avatar",
            ".top-nav-bar img.user-avatar",
            ".user-or-login img.user-avatar",
            ".top-nav-bar a[href*='/home/main']",
            "#com_userbar a[href*='/home/main']",
            "#com_userbar [class*='u_username']",
            ".userbar a[href*='/home/main']",
            "header a[href*='/home/main']",
            "nav a[href*='/home/main']",
        ),
        "positive_link_patterns": (
            r"tieba\.baidu\.com/home/main(?:[/?#]|$)",
            r"^/home/main(?:[/?#]|$)",
        ),
        "negative_selectors": (
            "#com_userbar a[href*='passport.baidu.com']",
            ".userbar a[href*='passport.baidu.com']",
            "header a[href*='passport.baidu.com']",
        ),
    },
}


def probe_visible_login_controls(page, platform: str) -> Dict:
    """Inspect visible account controls in top/side navigation, without reading identity text."""
    rule = VISIBLE_LOGIN_CONTROL_RULES.get(platform)
    if not rule:
        return {
            "login_confirmed": None,
            "evidence": f"{platform}尚未配置可见账号控件规则",
            "matched_kind": "unsupported",
        }

    inspected = page.evaluate(
        """(rule) => {
            const chromeSelector = [
                "header", "nav", "aside", "[role='banner']", "[role='navigation']",
                "[id*='header' i]", "[id*='nav' i]", "[id*='userbar' i]",
                "[class*='header' i]", "[class*='navbar' i]", "[class*='sidebar' i]",
                "[class*='userbar' i]", "[class*='top-nav' i]", "[class*='top-bar' i]",
                "[class*='channel-list' i]"
            ].join(",");
            const isVisible = (node) => {
                if (!node || !node.isConnected) return false;
                const style = getComputedStyle(node);
                const rect = node.getBoundingClientRect();
                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && style.opacity !== "0"
                    && rect.width > 0
                    && rect.height > 0
                    && node.getClientRects().length > 0;
            };
            const inChrome = (node) => Boolean(node && node.closest(chromeSelector));
            const firstVisible = (selectors) => {
                for (const selector of selectors || []) {
                    let nodes = [];
                    try { nodes = Array.from(document.querySelectorAll(selector)); } catch (_) {}
                    const match = nodes.find((node) => isVisible(node) && inChrome(node));
                    if (match) return selector;
                }
                return "";
            };
            const positiveSelector = firstVisible(rule.positive_selectors);
            let positiveLink = "";
            if (!positiveSelector) {
                const patterns = (rule.positive_link_patterns || []).map((value) => new RegExp(value, "i"));
                const links = Array.from(document.querySelectorAll("a[href]"));
                const match = links.find((node) => {
                    if (!isVisible(node) || !inChrome(node)) return false;
                    const href = node.getAttribute("href") || "";
                    const absolute = node.href || href;
                    return patterns.some((pattern) => pattern.test(href) || pattern.test(absolute));
                });
                positiveLink = match ? "account_link" : "";
            }

            const negativeSelector = firstVisible(rule.negative_selectors);
            const loginLabels = new Set(["登录", "立即登录", "扫码登录", "账号登录", "sign in", "log in"]);
            let negativeText = "";
            if (!negativeSelector) {
                let controls = [];
                for (const root of document.querySelectorAll(chromeSelector)) {
                    controls.push(...root.querySelectorAll("a, button, [role='button']"));
                }
                const match = controls.find((node) => {
                    if (!isVisible(node)) return false;
                    const label = (node.innerText || node.textContent || node.getAttribute("aria-label") || "")
                        .replace(/\\s+/g, " ").trim().toLowerCase();
                    return loginLabels.has(label);
                });
                negativeText = match ? "login_prompt" : "";
            }

            const positive = positiveSelector || positiveLink;
            const negative = negativeSelector || negativeText;
            if (positive && negative) {
                return {state: null, kind: "conflict"};
            }
            if (positive) {
                return {state: true, kind: "account_control"};
            }
            if (negative) {
                return {state: false, kind: "login_prompt"};
            }
            return {state: null, kind: "inconclusive"};
        }""",
        {
            "positive_selectors": list(rule.get("positive_selectors") or ()),
            "positive_link_patterns": list(rule.get("positive_link_patterns") or ()),
            "negative_selectors": list(rule.get("negative_selectors") or ()),
        },
    ) or {}
    state = inspected.get("state")
    kind = str(inspected.get("kind") or "inconclusive")
    if state is True:
        evidence = f"{platform}当前页面顶部或侧栏的账号控件可见"
    elif state is False:
        evidence = f"{platform}当前页面顶部或侧栏显示登录入口"
    elif kind == "conflict":
        evidence = f"{platform}当前页面同时出现账号控件和登录入口，无法确认登录"
    else:
        evidence = f"{platform}当前页面顶部或侧栏未找到可确认身份的账号控件"
    return {
        "login_confirmed": state if state in (True, False) else None,
        "evidence": evidence,
        "matched_kind": kind,
    }


def get_adapter(platform: str) -> SocialPlatformAdapter:
    adapter = SOCIAL_PLATFORM_ADAPTERS.get(platform)
    if not adapter:
        raise ValueError(f"{platform} 暂未配置浏览器会话适配器")
    return adapter


def load_playwright():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("缺少 Playwright，请先运行: pip install playwright && python -m playwright install chromium") from exc
    return sync_playwright, PlaywrightTimeoutError


def domain_matches(host: str, domains: Tuple[str, ...]) -> bool:
    normalized = (host or "").lstrip(".").lower()
    for domain in domains:
        target = domain.lstrip(".").lower()
        if normalized == target or normalized.endswith("." + target):
            return True
    return False


def _normalize_site_domain(domain: str) -> str:
    raw = str(domain or "").strip().rstrip(".")
    if not raw or any(ord(character) < 33 for character in raw):
        raise ValueError("网站域名无效")
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    try:
        literal = ipaddress.ip_address(raw)
    except ValueError:
        try:
            normalized = raw.encode("idna").decode("ascii").casefold()
        except UnicodeError as exc:
            raise ValueError("网站域名无效") from exc
        labels = normalized.split(".")
        if (
            len(normalized) > 253
            or any(
                not label
                or len(label) > 63
                or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
                for label in labels
            )
        ):
            raise ValueError("网站域名无效")
        if normalized == "localhost" or normalized.endswith(".localhost"):
            raise ValueError("不允许使用本机网站地址")
        return normalized
    if not literal.is_global:
        raise ValueError("不允许使用私网或保留地址")
    return literal.compressed.casefold()


def _has_loopback_system_proxy() -> bool:
    """Return whether Windows/environment proxy settings point to this machine."""
    try:
        proxies = getproxies()
    except Exception:
        return False
    value = str(proxies.get("https") or proxies.get("all") or "").strip()
    if not value:
        return False
    try:
        parsed = urlparse(value if "://" in value else f"//{value}")
        hostname = str(parsed.hostname or "").casefold()
    except ValueError:
        return False
    if hostname == "localhost":
        return True
    try:
        if ipaddress.ip_address(hostname).is_loopback:
            return True
    except ValueError:
        pass
    return False


def _is_clash_fake_ip(address) -> bool:
    return address.version == 4 and address in CLASH_FAKE_IP_NETWORK


def _validate_public_site_dns(
    domain: str,
    *,
    allow_clash_fake_ip: bool = False,
) -> None:
    try:
        ipaddress.ip_address(domain)
        return
    except ValueError:
        pass
    try:
        records = socket.getaddrinfo(
            domain,
            443,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ValueError("网站域名无法解析为公网地址") from exc
    addresses = {str(record[4][0]).split("%", 1)[0] for record in records if record[4]}
    if not addresses:
        raise ValueError("网站域名无法解析为公网地址")
    try:
        parsed_addresses = [ipaddress.ip_address(address) for address in addresses]
    except ValueError as exc:
        raise ValueError("网站域名解析结果无效") from exc
    non_public = [address for address in parsed_addresses if not address.is_global]
    if not non_public:
        return
    if all(_is_clash_fake_ip(address) for address in non_public):
        if allow_clash_fake_ip and _has_loopback_system_proxy():
            return
        raise ValueError(
            "网站域名解析为 Clash Fake-IP；请开启“使用系统代理”并确认 Clash 正在运行"
        )
    raise ValueError("网站域名解析到私网或保留地址")


def normalize_site_url(
    raw_url: str,
    *,
    resolve_dns: bool = True,
    allow_clash_fake_ip: bool = False,
) -> dict:
    """Normalize one exact HTTPS site and optionally prove all DNS results are public."""
    value = str(raw_url or "").strip()
    if not value or len(value) > 2048 or any(ord(character) < 32 for character in value):
        raise ValueError("网站登录网址无效")
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("网站登录网址无效") from exc
    if parsed.scheme.casefold() != "https" or not hostname:
        raise ValueError("网站登录网址必须使用 HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("网站登录网址不得包含账号凭据")
    if port not in (None, 443):
        raise ValueError("网站登录网址只允许 HTTPS 默认端口 443")
    domain = _normalize_site_domain(hostname)
    if resolve_dns:
        _validate_public_site_dns(
            domain,
            allow_clash_fake_ip=allow_clash_fake_ip,
        )
    try:
        ipaddress.IPv6Address(domain)
        netloc = f"[{domain}]"
    except ValueError:
        netloc = domain
    normalized_url = urlunparse(
        (
            "https",
            netloc,
            parsed.path or "/",
            parsed.params,
            parsed.query,
            "",
        )
    )
    return {"url": normalized_url, "domain": domain}


def _cookie_domain_can_send_to_host(cookie_domain: str, site_domain: str) -> bool:
    candidate = str(cookie_domain or "").strip().lstrip(".").rstrip(".")
    if not candidate:
        return False
    try:
        candidate = _normalize_site_domain(candidate)
    except ValueError:
        return False
    try:
        ipaddress.ip_address(candidate)
        return candidate == site_domain
    except ValueError:
        return site_domain == candidate or site_domain.endswith("." + candidate)


def _origin_matches_site(origin: str, site_domain: str) -> bool:
    try:
        parsed = urlparse(str(origin or ""))
        hostname = _normalize_site_domain(parsed.hostname or "")
        port = parsed.port
    except (TypeError, ValueError):
        return False
    return (
        parsed.scheme.casefold() == "https"
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
        and hostname == site_domain
        and parsed.path in ("", "/")
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


def filter_storage_state_for_site(storage_state: dict, domain: str) -> dict:
    """Keep only credentials the browser can send to one exact HTTPS host."""
    site_domain = _normalize_site_domain(domain)
    now = time.time()
    cookies = []
    for entry in (storage_state or {}).get("cookies") or []:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        expires = entry.get("expires")
        try:
            if expires is not None and float(expires) > 0 and float(expires) <= now:
                continue
        except (TypeError, ValueError):
            continue
        if _cookie_domain_can_send_to_host(entry.get("domain", ""), site_domain):
            cookie = dict(entry)
            cookie["domain"] = site_domain
            cookies.append(cookie)
    origins = [
        dict(entry)
        for entry in (storage_state or {}).get("origins") or []
        if isinstance(entry, dict)
        and _origin_matches_site(entry.get("origin", ""), site_domain)
    ]
    return {"cookies": cookies, "origins": origins}


def _public_http_request_target(
    url: str,
    *,
    allow_clash_fake_ip: bool = False,
) -> Optional[Tuple[str, str]]:
    """Return one public HTTPS:443 request target; ignore non-network schemes."""
    value = str(url or "")
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("网络请求地址无效") from exc
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"}:
        return None
    if scheme != "https" or port not in (None, 443):
        raise ValueError("网络请求只允许 HTTPS 默认端口 443")
    if not hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("网络请求地址无效")
    domain = _normalize_site_domain(hostname)
    _validate_public_site_dns(
        domain,
        allow_clash_fake_ip=allow_clash_fake_ip,
    )
    return scheme, domain


def _public_websocket_request_target(
    url: str,
    *,
    exact_domain: str = "",
    allow_clash_fake_ip: bool = False,
) -> Tuple[str, str]:
    """Return one public WSS:443 target, optionally limited to one exact host."""
    try:
        parsed = urlparse(str(url or ""))
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("WebSocket 地址无效") from exc
    if (
        parsed.scheme.casefold() != "wss"
        or port not in (None, 443)
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("WebSocket 只允许 WSS 默认端口 443")
    domain = _normalize_site_domain(hostname)
    if exact_domain and domain != _normalize_site_domain(exact_domain):
        raise ValueError("WebSocket 只允许连接保存会话的精确域名")
    _validate_public_site_dns(
        domain,
        allow_clash_fake_ip=allow_clash_fake_ip,
    )
    return "wss", domain


def _site_origin(domain: str) -> str:
    try:
        ipaddress.IPv6Address(domain)
        return f"https://[{domain}]/"
    except ValueError:
        return f"https://{domain}/"


def cookie_header_from_storage_state(storage_state: dict, domains: Tuple[str, ...]) -> str:
    cookies = {}
    for cookie in storage_state.get("cookies") or []:
        domain = cookie.get("domain", "")
        name = cookie.get("name", "")
        value = cookie.get("value", "")
        expires = cookie.get("expires")
        if not name or not value:
            continue
        if expires and expires > 0 and expires < time.time():
            continue
        if domain_matches(domain, domains):
            cookies[name] = value
    return "; ".join(f"{name}={value}" for name, value in sorted(cookies.items()))


def storage_state_summary(storage_state: dict, domains: Tuple[str, ...]) -> dict:
    cookie_count = sum(
        1 for cookie in storage_state.get("cookies") or []
        if domain_matches(cookie.get("domain", ""), domains)
    )
    origins = storage_state.get("origins") or []
    return {
        "cookie_count": cookie_count,
        "origin_count": len(origins),
        "has_local_storage": any(origin.get("localStorage") for origin in origins),
    }


def infer_login_from_html(platform: str, html: str) -> Tuple[Optional[bool], str]:
    adapter = get_adapter(platform)
    text = html or ""
    if not text.strip():
        return None, "empty page"
    if platform == "百度贴吧" and (
        re.search(r'href=["\'][^"\']*/home/main', text, re.I)
        or re.search(r'"is_login"\s*:\s*(?:true|1)', text, re.I)
        or re.search(r'"user_name_show"\s*:\s*"[^"]+"', text, re.I)
    ):
        return True, "百度贴吧 page matched authenticated user marker"
    if any(marker in text for marker in adapter.login_markers):
        return True, f"{platform} page matched login marker"
    negative_markers = ("登录", "立即登录", "扫码登录", "验证码", "login", "sign in")
    if any(marker in text.lower() for marker in negative_markers):
        if platform == "百度贴吧":
            return None, "百度贴吧 page contains login text but no visible-state evidence"
        return False, f"{platform} page matched login prompt"
    return None, f"{platform} login marker inconclusive"


def _keyword_tokens(keyword: str) -> List[str]:
    return [
        token.strip()
        for token in re.split(r"[\s,，;；、|/]+", clean_text(keyword))
        if token.strip()
    ]


def _is_keyword_relevant(keyword: str, title: str, content: str, url: str) -> bool:
    tokens = _keyword_tokens(keyword)
    if not tokens:
        return True
    haystack = f"{title or ''} {content or ''} {url or ''}".lower()
    return any(token.lower() in haystack for token in tokens)


def _is_noise_social_result(title: str, url: str, content: str = "") -> bool:
    text = f"{title or ''} {url or ''} {content or ''}".lower()
    parsed = urlparse(url or "")
    host = parsed.netloc.lower()
    if any(domain in host for domain in ("beian.miit.gov.cn", "miit.gov.cn")):
        return True
    noise_terms = (
        "备案", "icp", "营业执照", "许可证", "网安", "网文", "沪公网安备",
        "用户协议", "隐私政策", "隐私权政策", "帮助中心", "关于我们", "联系我们",
        "举报入口", "举报网上有害信息", "医疗器械网络交易服务", "互联网药品信息服务",
        "copyright", "增值电信业务经营许可证",
    )
    return any(term in text for term in noise_terms)


def _is_platform_result_url(platform: str, url: str) -> bool:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if platform == "小红书":
        return bool(re.fullmatch(r"/explore/[0-9a-z]+/?", path)) and domain_matches(host, ("xiaohongshu.com",))
    if platform == "B站":
        return domain_matches(host, ("bilibili.com",)) and path.startswith("/video/")
    if platform == "微博":
        return domain_matches(host, ("weibo.com", "sina.com.cn")) and bool(path.strip("/"))
    if platform == "抖音":
        return domain_matches(host, ("douyin.com",)) and "/video/" in path
    if platform == "知乎":
        return domain_matches(host, ("zhihu.com",)) and (
            path.startswith("/question/") or path.startswith("/pin/") or path.startswith("/p/")
        )
    if platform == "微信公众平台":
        return domain_matches(host, ("qq.com", "weixin.qq.com", "weixin.sogou.com")) and bool(path.strip("/"))
    if platform == "百度贴吧":
        return domain_matches(host, ("tieba.baidu.com", "baidu.com")) and path.startswith("/p/")
    if platform == "豆瓣":
        return domain_matches(host, ("douban.com",)) and any(
            marker in path for marker in ("/group/topic/", "/note/", "/review/", "/subject/")
        )
    if platform == "快手":
        return domain_matches(host, ("kuaishou.com",)) and (
            "/short-video/" in path or "/profile/" in path
        )
    if platform == "今日头条":
        return domain_matches(host, ("toutiao.com",)) and (
            "/article/" in path or path.startswith("/w/")
        )
    return False


def _decode_html_fragment(text: str) -> str:
    return html_lib.unescape(str(text or "").replace("\\/", "/").replace("\\u002F", "/"))


def _extract_xiaohongshu_url(text: str, base_url: str, fallback_note_id: str = "") -> str:
    decoded = _decode_html_fragment(text)
    fallback_url = ""
    patterns = (
        r"https?://www\.xiaohongshu\.com/explore/[0-9a-zA-Z]{12,40}(?:\?[^\"'<>\s]+)?",
        r"/explore/[0-9a-zA-Z]{12,40}(?:\?[^\"'<>\s]+)?",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, decoded):
            candidate_url = urljoin(base_url, match.group(0))
            if _is_xiaohongshu_openable_url(candidate_url):
                return candidate_url
            fallback_url = fallback_url or candidate_url

    note_id = fallback_note_id or _extract_note_id_from_text(decoded)
    if not note_id:
        return fallback_url
    token_match = re.search(
        r"(?:xsec_token|xsecToken)[\"'\s:=]+([0-9A-Za-z_\-=]+)",
        decoded,
    )
    source_match = re.search(
        r"(?:xsec_source|xsecSource)[\"'\s:=]+([0-9A-Za-z_\-]+)",
        decoded,
    )
    if token_match:
        source_value = source_match.group(1) if source_match else "pc_search"
        if source_value.lower() not in XIAOHONGSHU_SEARCH_SOURCES:
            return fallback_url
        query = {
            "xsec_token": token_match.group(1),
            "xsec_source": source_value,
            "source": "web_explore_feed",
        }
        return urljoin(base_url, f"/explore/{note_id}?{urlencode(query)}")
    return fallback_url or urljoin(base_url, f"/explore/{note_id}")


def _is_xiaohongshu_openable_url(url: str) -> bool:
    parsed = urlparse(url or "")
    if not (domain_matches(parsed.netloc, ("xiaohongshu.com",)) and re.fullmatch(r"/explore/[0-9a-z]+/?", parsed.path.lower())):
        return False
    query = parse_qs(parsed.query)
    source_values = {value.lower() for value in query.get("xsec_source", [])}
    return bool(query.get("xsec_token", [""])[0]) and bool(source_values & XIAOHONGSHU_SEARCH_SOURCES)


def _xiaohongshu_source_from_url(url: str) -> str:
    parsed = urlparse(url or "")
    query = parse_qs(parsed.query)
    values = query.get("xsec_source", [])
    return values[0] if values else ""


def _decode_js_string(text: str) -> str:
    text = str(text or "")
    try:
        return json.loads(f'"{text}"')
    except Exception:
        return html_lib.unescape(text)


def _pick_nested_value(payload, keys: set):
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in keys and value not in (None, "", [], {}):
                return value
        for value in payload.values():
            nested = _pick_nested_value(value, keys)
            if nested not in (None, "", [], {}):
                return nested
    elif isinstance(payload, list):
        for item in payload:
            nested = _pick_nested_value(item, keys)
            if nested not in (None, "", [], {}):
                return nested
    return None


def _format_xiaohongshu_timestamp(value) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return ""
    if numeric <= 0:
        return ""
    if numeric > 10_000_000_000:
        numeric = numeric / 1000
    try:
        return datetime.fromtimestamp(numeric).isoformat()
    except (OSError, OverflowError, ValueError):
        return ""


def _extract_note_id_from_text(text: str) -> str:
    patterns = (
        r"/explore/([0-9a-zA-Z]{12,40})",
        r'"(?:noteId|note_id)"\s*:\s*"([0-9a-zA-Z]{12,40})"',
        r'"id"\s*:\s*"([0-9a-fA-F]{16,40})"',
    )
    for pattern in patterns:
        match = re.search(pattern, text or "")
        if match:
            return match.group(1)
    return ""


def _extract_json_social_items(soup) -> List[Dict]:
    node = soup.find("script", id="codex-extracted-social-items")
    if not node:
        return []
    try:
        payload = json.loads(node.get_text() or "[]")
    except Exception:
        return []
    return payload if isinstance(payload, list) else []


def extract_xiaohongshu_detail_from_html(html: str) -> Dict:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise RuntimeError("缺少 beautifulsoup4，无法解析小红书详情页") from exc

    soup = BeautifulSoup(html or "", "html.parser")
    extracted = soup.find("script", id="codex-extracted-xhs-detail")
    if extracted:
        try:
            payload = json.loads(extracted.get_text() or "{}")
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            return {
                "title": clean_text(payload.get("title", ""))[:160],
                "content": clean_text(payload.get("content", "")),
                "author": clean_text(payload.get("author", ""))[:80],
                "author_url": str(payload.get("author_url") or ""),
                "pub_time": clean_text(payload.get("pub_time", "")),
            }

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    detail_root = (
        soup.select_one("#noteContainer")
        or soup.select_one("[class*='note-detail']")
        or soup.select_one("[class*='NoteDetail']")
        or soup.select_one("main")
        or soup
    )

    def first_text(selectors: Tuple[str, ...]) -> str:
        for selector in selectors:
            node = detail_root.select_one(selector)
            if node:
                text = clean_text(node.get_text(" ", strip=True))
                if text:
                    return text
        return ""

    title = first_text((
        "#detail-title",
        "[class*='title']",
        "[class*='Title']",
        "h1",
        "h2",
    ))
    content = first_text((
        "#detail-desc",
        ".desc",
        "[class*='desc']",
        "[class*='Desc']",
        "[class*='content']",
        "[class*='Content']",
    ))

    author = ""
    author_url = ""
    for link in detail_root.select("a[href*='/user/profile/']"):
        link_text = clean_text(link.get_text(" ", strip=True))
        if link_text:
            author = link_text
            author_url = urljoin("https://www.xiaohongshu.com", link.get("href", ""))
            break
    if not author:
        author = first_text((
            ".username",
            "[class*='username']",
            "[class*='user-name']",
            "[class*='author']",
            "[class*='Author']",
        ))

    page_text = clean_text(detail_root.get_text(" ", strip=True))
    pub_time = extract_time_text(page_text)
    if not pub_time:
        match = re.search(r"编辑于\s*([^。·|]+)", page_text)
        if match:
            pub_time = clean_text(match.group(1))

    return {
        "title": title[:160],
        "content": content,
        "author": author[:80],
        "author_url": author_url,
        "pub_time": pub_time,
    }


def extract_xiaohongshu_items_from_api_payload(
    payload,
    base_url: str,
    keyword: str = "",
    limit: int = 30,
) -> List[Dict]:
    items = []
    seen = set()

    def visit(node):
        if len(items) >= limit:
            return
        if isinstance(node, dict):
            card = node.get("note_card") if isinstance(node.get("note_card"), dict) else {}
            candidate = card or node
            note_id = str(
                node.get("id")
                or node.get("note_id")
                or node.get("noteId")
                or card.get("note_id")
                or card.get("noteId")
                or card.get("id")
                or ""
            )
            token = str(
                node.get("xsec_token")
                or node.get("xsecToken")
                or card.get("xsec_token")
                or card.get("xsecToken")
                or ""
            )
            source = str(
                node.get("xsec_source")
                or node.get("xsecSource")
                or card.get("xsec_source")
                or card.get("xsecSource")
                or "pc_search"
            )
            title = clean_text(
                candidate.get("display_title")
                or candidate.get("displayTitle")
                or candidate.get("title")
                or node.get("display_title")
                or node.get("displayTitle")
                or node.get("title")
                or ""
            )
            content = clean_text(
                candidate.get("desc")
                or candidate.get("description")
                or node.get("desc")
                or node.get("description")
                or title
            )
            if note_id and token and title and source.lower() in XIAOHONGSHU_SEARCH_SOURCES:
                query = {
                    "xsec_token": token,
                    "xsec_source": source or "pc_search",
                    "source": "web_explore_feed",
                }
                url = urljoin(base_url, f"/explore/{note_id}?{urlencode(query)}")
                if url not in seen and _is_keyword_relevant(keyword, title, content, url):
                    seen.add(url)
                    interact = card.get("interact_info") if isinstance(card.get("interact_info"), dict) else {}
                    user = card.get("user") if isinstance(card.get("user"), dict) else {}
                    pub_time = _format_xiaohongshu_timestamp(
                        candidate.get("time")
                        or candidate.get("last_update_time")
                        or node.get("time")
                        or node.get("last_update_time")
                    )
                    items.append({
                        "title": title[:160],
                        "url": url,
                        "source": "小红书",
                        "platform": "小红书",
                        "pub_time": pub_time,
                        "content": (content or title)[:500],
                        "author": clean_text(user.get("nickname") or user.get("name") or ""),
                        "collector": "小红书浏览器会话",
                        "session_mode": "browser_session",
                        "search_origin": "xiaohongshu_search_api",
                        "xhs_source": source,
                        "search_rank": len(items) + 1,
                        "like_count": interact.get("liked_count") or interact.get("like_count") or 0,
                        "comment_count": interact.get("comment_count") or 0,
                        "collect_count": interact.get("collected_count") or interact.get("collect_count") or 0,
                    })
                    if len(items) >= limit:
                        return
            for value in node.values():
                visit(value)
                if len(items) >= limit:
                    return
        elif isinstance(node, list):
            for item in node:
                visit(item)
                if len(items) >= limit:
                    return

    visit(payload)
    return items[:limit]


def extract_douyin_items_from_api_payload(payload, limit: int = 30) -> List[Dict]:
    """Extract real video records from Douyin web search response payloads."""
    items = []
    seen = set()

    def visit(node):
        if len(items) >= limit:
            return
        if isinstance(node, dict):
            candidate = (
                node.get("aweme_info")
                if isinstance(node.get("aweme_info"), dict)
                else node
            )
            aweme_id = str(
                candidate.get("aweme_id")
                or candidate.get("awemeId")
                or candidate.get("group_id")
                or ""
            )
            looks_like_video = bool(
                candidate.get("video")
                or candidate.get("statistics")
                or candidate.get("desc") is not None
            )
            if aweme_id.isdigit() and looks_like_video and aweme_id not in seen:
                seen.add(aweme_id)
                desc = clean_text(
                    candidate.get("desc")
                    or candidate.get("title")
                    or (
                        candidate.get("share_info", {}).get("share_title", "")
                        if isinstance(candidate.get("share_info"), dict)
                        else ""
                    )
                )
                author = (
                    candidate.get("author")
                    if isinstance(candidate.get("author"), dict)
                    else {}
                )
                statistics = (
                    candidate.get("statistics")
                    if isinstance(candidate.get("statistics"), dict)
                    else {}
                )
                items.append({
                    "title": (desc or f"抖音视频 {aweme_id}")[:160],
                    "url": f"https://www.douyin.com/video/{aweme_id}",
                    "source": "抖音",
                    "platform": "抖音",
                    "pub_time": _format_xiaohongshu_timestamp(
                        candidate.get("create_time")
                        or candidate.get("createTime")
                    ),
                    "content": (desc or f"抖音视频 {aweme_id}")[:500],
                    "author": clean_text(
                        author.get("nickname")
                        or author.get("unique_id")
                        or author.get("short_id")
                        or ""
                    )[:80],
                    "collector": "抖音可见浏览器会话",
                    "session_mode": "browser_session",
                    "search_origin": "douyin_search_api",
                    "external_id": aweme_id,
                    "like_count": statistics.get("digg_count") or 0,
                    "comment_count": statistics.get("comment_count") or 0,
                    "repost_count": statistics.get("share_count") or 0,
                    "view_count": statistics.get("play_count") or 0,
                })
                if len(items) >= limit:
                    return
            for value in node.values():
                visit(value)
                if len(items) >= limit:
                    return
        elif isinstance(node, list):
            for item in node:
                visit(item)
                if len(items) >= limit:
                    return

    visit(payload)
    return items[:limit]


def _extract_xiaohongshu_state_items(raw_html: str, base_url: str, keyword: str, limit: int) -> List[Dict]:
    items = []
    seen = set()
    html_text = raw_html or ""
    patterns = (
        r'"(?:noteId|note_id)"\s*:\s*"(?P<id>[0-9a-zA-Z]{12,40})".{0,1600}?"(?:displayTitle|title|desc)"\s*:\s*"(?P<title>(?:\\.|[^"\\]){2,220})"',
        r'"(?:displayTitle|title|desc)"\s*:\s*"(?P<title>(?:\\.|[^"\\]){2,220})".{0,1600}?"(?:noteId|note_id)"\s*:\s*"(?P<id>[0-9a-zA-Z]{12,40})"',
    )
    for pattern in patterns:
        for match in re.finditer(pattern, html_text, flags=re.S):
            note_id = match.group("id")
            title = clean_text(_decode_js_string(match.group("title")))
            if not note_id or not title or len(title) < 2:
                continue
            context_start = max(match.start() - 1200, 0)
            context_end = min(match.end() + 1200, len(html_text))
            url = _extract_xiaohongshu_url(html_text[context_start:context_end], base_url, note_id)
            if not _is_xiaohongshu_openable_url(url):
                continue
            if url in seen:
                continue
            if _is_noise_social_result(title, url, ""):
                continue
            if not _is_keyword_relevant(keyword, title, "", url):
                continue
            seen.add(url)
            items.append({
                "title": title[:160],
                "url": url,
                "source": "小红书",
                "platform": "小红书",
                "pub_time": "",
                "content": title,
                "collector": "小红书浏览器会话",
                "session_mode": "browser_session",
                "search_origin": "xiaohongshu_state",
                "xhs_source": _xiaohongshu_source_from_url(url),
                "search_rank": len(items) + 1,
            })
            if len(items) >= limit:
                return items
    return items


def extract_search_items_from_html(
    platform: str,
    html: str,
    base_url: str,
    limit: int = 15,
    keyword: str = "",
) -> List[Dict]:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise RuntimeError("缺少 beautifulsoup4，无法解析浏览器页面") from exc

    adapter = get_adapter(platform)
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        if tag.name == "script" and tag.get("id") == "codex-extracted-social-items":
            continue
        tag.decompose()
    embedded_items = _extract_json_social_items(soup)
    candidates = []
    for selector in adapter.item_selectors:
        candidates.extend(soup.select(selector))

    items = []
    seen = set()
    iterable = list(embedded_items) + candidates
    for node in iterable:
        if isinstance(node, dict):
            title = clean_text(node.get("title") or node.get("content") or "")
            text = clean_text(node.get("content") or title)
            raw_url = node.get("url", "")
            note_id = node.get("note_id", "")
            node_xhs_source = str(node.get("xhs_source") or node.get("xsec_source") or "")
            node_search_origin = str(node.get("search_origin") or "xiaohongshu_dom")
            url = urljoin(base_url, raw_url) if raw_url else ""
            if platform == "小红书" and not _is_xiaohongshu_openable_url(url) and note_id:
                url_context = " ".join([
                    raw_url,
                    text,
                    str(node.get("xsec_token", "")),
                    str(node.get("xsec_source", "")),
                ])
                if node.get("xsec_token"):
                    query = {
                        "xsec_token": str(node.get("xsec_token", "")),
                        "xsec_source": str(node.get("xsec_source") or "pc_search"),
                        "source": "web_explore_feed",
                    }
                    url = urljoin(base_url, f"/explore/{note_id}?{urlencode(query)}")
                    node_xhs_source = query["xsec_source"]
                else:
                    url = _extract_xiaohongshu_url(url_context, base_url, note_id)
        else:
            link = node if getattr(node, "name", "") == "a" and node.get("href") else node.find("a", href=True)
            title = ""
            if link:
                title = link.get("title") or link.get_text(" ", strip=True)
            if not title:
                title_node = node.find(["h1", "h2", "h3", "h4"]) if hasattr(node, "find") else None
                title = title_node.get_text(" ", strip=True) if title_node else ""
            text = node.get_text(" ", strip=True) if hasattr(node, "get_text") else title
            title = clean_text(title or text[:80])
            href = link.get("href", "") if link else ""
            url = urljoin(base_url, href) if href else ""
            if platform == "小红书" and not _is_xiaohongshu_openable_url(url):
                url = _extract_xiaohongshu_url(str(node), base_url)
            node_xhs_source = _xiaohongshu_source_from_url(url)
            node_search_origin = "xiaohongshu_dom"
        if len(title) < 4:
            continue
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            continue
        if _is_noise_social_result(title, url, text):
            continue
        result_url = _is_xiaohongshu_openable_url(url) if platform == "小红书" else _is_platform_result_url(platform, url)
        if not result_url and not _is_keyword_relevant(keyword, title, text, url):
            continue
        if platform == "小红书" and not result_url:
            continue
        key = url or title
        if key in seen:
            continue
        seen.add(key)
        item = {
            "title": title[:160],
            "url": url,
            "source": platform,
            "platform": platform,
            "pub_time": extract_time_text(text),
            "content": clean_text(text)[:500] or title,
            "collector": f"{platform}浏览器会话",
            "session_mode": "browser_session",
        }
        if platform == "小红书":
            item["search_origin"] = node_search_origin
            item["xhs_source"] = node_xhs_source or _xiaohongshu_source_from_url(url)
            item["search_rank"] = len(items) + 1
        items.append(item)
        if len(items) >= limit:
            break
    if platform == "小红书" and len(items) < limit:
        for item in _extract_xiaohongshu_state_items(html, base_url, keyword, limit - len(items)):
            if item["url"] not in seen:
                seen.add(item["url"])
                items.append(item)
    return items


def extract_article_from_html(html: str) -> Dict:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise RuntimeError("缺少 beautifulsoup4，无法解析浏览器页面") from exc
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    title = ""
    if soup.title:
        title = clean_text(soup.title.get_text(" ", strip=True))
    h1 = soup.find("h1")
    if h1:
        title = clean_text(h1.get_text(" ", strip=True)) or title
    text_blocks = []
    for selector in ("article", "main", "[class*='content']", "[class*='detail']", "[class*='note']"):
        for node in soup.select(selector):
            text = clean_text(node.get_text(" ", strip=True))
            if len(text) >= 40:
                text_blocks.append(text)
    if not text_blocks:
        for p in soup.find_all("p"):
            text = clean_text(p.get_text(" ", strip=True))
            if len(text) >= 20:
                text_blocks.append(text)
    content = "\n".join(dict.fromkeys(text_blocks))
    page_text = clean_text(soup.get_text(" ", strip=True))
    return {
        "title": title[:160],
        "content": content or page_text,
        "pub_time": extract_published_time_from_soup(soup),
    }


def extract_tieba_detail_from_html(html: str) -> Dict:
    """Extract the main post and visible discussion samples from the current Tieba page."""
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise RuntimeError("缺少 beautifulsoup4，无法解析贴吧详情页") from exc

    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    title = ""
    for selector in (".thread-title", ".pb-title", "h1", "title"):
        node = soup.select_one(selector)
        if node:
            title = clean_text(node.get_text(" ", strip=True))
            if title:
                break

    post_nodes = soup.select(".pb-content-wrap") or soup.select(".pb-rich-text")
    posts = []
    seen = set()
    for node in post_nodes:
        text = clean_text(node.get_text(" ", strip=True))
        if len(text) < 10 or text in seen:
            continue
        seen.add(text)
        posts.append({"content": text})
        if len(posts) >= 10:
            break

    comments = []
    for node in soup.select(".pb-lzl-item .comment-content, .pb-lzl-item"):
        text = clean_text(node.get_text(" ", strip=True))
        if len(text) < 4 or text in seen:
            continue
        seen.add(text)
        comments.append({"content": text})
        if len(comments) >= 10:
            break

    samples = posts + comments
    content = "\n".join(item["content"] for item in posts[:5])
    return {
        "title": title[:160],
        "content": content,
        "discussion_samples": samples[:10],
    }


def extract_weibo_detail_from_payload(payload: Dict) -> Dict:
    """Normalize the structured response returned by Weibo statuses/show."""
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("data"), dict) and not payload.get("text_raw"):
        payload = payload["data"]

    long_text = payload.get("longText") if isinstance(payload.get("longText"), dict) else {}
    raw_content = (
        long_text.get("longTextContent")
        or long_text.get("content")
        or payload.get("text_raw")
        or payload.get("text")
        or ""
    )
    content = clean_text(re.sub(r"<[^>]+>", " ", html_lib.unescape(str(raw_content))))
    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    author = clean_text(user.get("screen_name") or user.get("name") or "")
    uid = str(user.get("idstr") or user.get("id") or "")
    external_id = str(payload.get("idstr") or payload.get("id") or payload.get("mid") or "")
    mblogid = str(payload.get("mblogid") or "")
    return {
        "title": content[:80],
        "content": content,
        "author": author[:80],
        "author_url": f"https://weibo.com/u/{uid}" if uid else "",
        "pub_time": clean_text(payload.get("created_at") or ""),
        "external_id": external_id,
        "mblogid": mblogid,
        "repost_count": payload.get("reposts_count") or 0,
        "comment_count": payload.get("comments_count") or 0,
        "like_count": payload.get("attitudes_count") or 0,
        "is_long_text": bool(payload.get("isLongText") or long_text),
    }


def extract_published_time_from_soup(soup) -> str:
    meta_names = {
        "article:published_time",
        "pubdate",
        "publishdate",
        "datepublished",
        "date",
        "weibo:article:create_at",
    }
    for meta in soup.find_all("meta"):
        name = (meta.get("name") or meta.get("property") or meta.get("itemprop") or "").lower()
        value = meta.get("content", "")
        if name in meta_names and value:
            candidate = extract_time_text(value) or clean_text(value)
            if candidate:
                return candidate

    selectors = [
        "time",
        "[datetime]",
        "[class*='time']",
        "[class*='date']",
        "[class*='from']",
        "[class*='publish']",
        "[class*='created']",
        "[aria-label*='发布']",
    ]
    for selector in selectors:
        for node in soup.select(selector):
            parent_text = clean_text(node.parent.get_text(" ", strip=True) if node.parent else "")
            if is_suspicious_time_context(parent_text):
                continue
            values = [
                node.get("datetime", ""),
                node.get("content", ""),
                node.get("title", ""),
                node.get("aria-label", ""),
                node.get_text(" ", strip=True),
            ]
            for value in values:
                candidate = extract_time_text(value)
                if candidate:
                    return candidate
    return ""


def is_suspicious_time_context(text: str) -> bool:
    clean = clean_text(text)
    suspicious_markers = (
        "生日",
        "星座",
        "个人主页",
        "粉丝",
        "关注",
        "微博热搜",
        "热搜",
        "帮助中心",
        "自助服务中心",
        "网站备案",
        "营业执照",
        "Copyright",
    )
    return any(marker in clean for marker in suspicious_markers)


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def extract_time_text(text: str) -> str:
    clean = clean_text(text)
    patterns = [
        r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?",
        r"\d{1,2}月\d{1,2}日(?:\s+\d{1,2}:\d{2})?",
        r"\d+\s*分钟前",
        r"\d+\s*小时前",
        r"刚刚",
        r"昨天(?:\s+\d{1,2}:\d{2})?",
        r"前天(?:\s+\d{1,2}:\d{2})?",
    ]
    for pattern in patterns:
        match = re.search(pattern, clean)
        if match:
            return match.group(0)
    return ""


class BrowserSessionManager:
    def __init__(
        self,
        root: Path,
        *,
        sensitive_root: Path | None = None,
        enforce_acl: bool = True,
    ):
        self.root = Path(root)
        self.sensitive_root = (
            Path(sensitive_root)
            if sensitive_root is not None
            else default_sensitive_root(self.root)
        )
        self.profile_root = self.sensitive_root / "browser_profiles"
        self.site_profile_root = self.profile_root / "sites"
        self.legacy_profile_root = self.root / "data" / "browser_profiles"
        self.enforce_acl = bool(enforce_acl)
        self._sessions: Dict[str, dict] = {}
        self._playwright = None
        self._commands: queue.Queue = queue.Queue()
        self._worker_thread: threading.Thread | None = None
        self._worker_guard = threading.Lock()

    def start_site_login(
        self,
        login_url: str,
        *,
        use_system_proxy: bool = False,
    ) -> dict:
        return self._run_on_worker(
            self._start_site_login,
            login_url,
            bool(use_system_proxy),
        )

    def _start_site_login(self, login_url: str, use_system_proxy: bool = False) -> dict:
        target = normalize_site_url(
            login_url,
            allow_clash_fake_ip=use_system_proxy,
        )
        domain = target["domain"]
        session_key = f"site:{domain}"
        for existing_key in list(self._sessions):
            if existing_key.startswith("site:") and existing_key != session_key:
                self._discard_session(existing_key)

        existing_session = self._sessions.get(session_key)
        if (
            existing_session
            and bool(existing_session.get("use_system_proxy")) != bool(use_system_proxy)
        ):
            self._discard_session(session_key)

        if session_key in self._sessions:
            session = self._sessions[session_key]
            page = session.get("page")
            try:
                if page and not page.is_closed():
                    page.bring_to_front()
                    page.goto(target["url"], wait_until="domcontentloaded", timeout=30000)
                    session["login_url"] = target["url"]
                    return self._site_session_status(
                        domain,
                        live=True,
                        message="网站辅助登录浏览器已打开",
                    )
            except Exception:
                pass
            self._discard_session(session_key)

        playwright = self._ensure_playwright()
        browser = None
        context = None
        try:
            browser = playwright.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 860},
                service_workers="block",
            )

            def guard_public_websocket(websocket):
                try:
                    _public_websocket_request_target(
                        websocket.url,
                        allow_clash_fake_ip=use_system_proxy,
                    )
                    websocket.connect_to_server()
                except Exception:
                    websocket.close(code=1008, reason="blocked by site session policy")

            context.route_web_socket("**", guard_public_websocket)
            page = context.pages[0] if context.pages else context.new_page()

            def guard_public_network(route, request):
                try:
                    request_url = getattr(request, "url", "")
                    is_top_navigation = bool(
                        request.is_navigation_request()
                        and request.frame
                        and request.frame.parent_frame is None
                    )
                    if is_top_navigation:
                        navigation_target = normalize_site_url(
                            request_url,
                            allow_clash_fake_ip=use_system_proxy,
                        )
                        is_original_page = request.frame == page.main_frame
                        if (
                            not is_original_page
                            and navigation_target["domain"] != domain
                        ):
                            raise ValueError("弹窗只能返回原始网站")
                    else:
                        _public_http_request_target(
                            request_url,
                            allow_clash_fake_ip=use_system_proxy,
                        )
                    route.continue_()
                except Exception:
                    route.abort("blockedbyclient")

            context.route("**/*", guard_public_network)
            page.goto(target["url"], wait_until="domcontentloaded", timeout=30000)
        except Exception:
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if not self._sessions:
                self._stop_playwright()
            raise

        self._sessions[session_key] = {
            "browser": browser,
            "context": context,
            "page": page,
            "domain": domain,
            "login_url": target["url"],
            "use_system_proxy": bool(use_system_proxy),
            "started_at": time.time(),
        }
        return self._site_session_status(
            domain,
            live=True,
            message="网站辅助登录浏览器已打开",
        )

    def save_site_session(self, domain: str) -> dict:
        return self._run_on_worker(self._save_site_session, domain)

    def _save_site_session(self, domain: str) -> dict:
        site_domain = _normalize_site_domain(domain)
        session_key = f"site:{site_domain}"
        session = self._sessions.get(session_key)
        if not session:
            raise RuntimeError("请先打开该网站的辅助登录浏览器并完成登录")
        page = session.get("page")
        if not page or page.is_closed():
            self._discard_session(session_key)
            raise RuntimeError("网站辅助登录浏览器已关闭，请重新打开后再保存会话")
        open_pages = [
            candidate
            for candidate in session["context"].pages
            if not candidate.is_closed()
        ]
        if not open_pages:
            self._discard_session(session_key)
            raise RuntimeError("网站辅助登录浏览器已关闭，请重新打开后再保存会话")
        for candidate in open_pages:
            try:
                final_target = normalize_site_url(candidate.url, resolve_dns=False)
            except ValueError as exc:
                raise RuntimeError("当前页面不是可保存的公网 HTTPS 网站页面") from exc
            if final_target["domain"] != site_domain:
                raise RuntimeError("请关闭登录弹窗并返回该网站页面，再保存登录会话")

        storage_state = filter_storage_state_for_site(
            session["context"].storage_state(),
            site_domain,
        )
        cookie_count = len(storage_state["cookies"])
        origin_count = len(storage_state["origins"])
        has_local_storage = any(
            entry.get("localStorage") for entry in storage_state["origins"]
        )
        if not cookie_count and not has_local_storage:
            raise RuntimeError("未读取到该网站的 Cookie 或 LocalStorage，请确认登录完成")
        result = {
            "domain": site_domain,
            "login_url": _site_origin(site_domain),
            "storage_state": storage_state,
            "cookie_count": cookie_count,
            "origin_count": origin_count,
            "has_local_storage": has_local_storage,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "live": False,
            "message": "网站浏览器会话已读取并关闭，等待加密保存",
            "storage_scope": "current_user_private",
        }
        self._discard_session(session_key)
        return result

    def close_site_session(self, domain: str) -> dict:
        return self._run_on_worker(self._close_site_session, domain)

    def _close_site_session(self, domain: str) -> dict:
        site_domain = _normalize_site_domain(domain)
        session_key = f"site:{site_domain}"
        if session_key not in self._sessions:
            return self._site_session_status(
                site_domain,
                live=False,
                message="网站辅助登录浏览器未打开",
            )
        self._discard_session(session_key)
        return self._site_session_status(
            site_domain,
            live=False,
            message="网站辅助登录浏览器已关闭",
        )

    def clear_site_data(self, domain: str) -> dict:
        return self._run_on_worker(self._clear_site_data, domain)

    def _clear_site_data(self, domain: str) -> dict:
        site_domain = _normalize_site_domain(domain)
        self._discard_session(f"site:{site_domain}")
        profile_dir = self.site_profile_root / hashlib.sha256(
            site_domain.encode("utf-8")
        ).hexdigest()
        removed = int(safe_remove_tree(profile_dir, self.site_profile_root))
        return {
            "domain": site_domain,
            "profile_trees_removed": removed,
            "live": False,
            "message": "网站辅助登录会话已清除",
            "storage_scope": "current_user_private",
        }

    def start_login(self, platform: str) -> dict:
        return self._run_on_worker(self._start_login, platform)

    def _start_login(self, platform: str) -> dict:
        adapter = get_adapter(platform)
        if platform in self._sessions:
            session = self._sessions[platform]
            page = session.get("page")
            try:
                if page and not page.is_closed():
                    page.bring_to_front()
                    page.goto(adapter.login_url, wait_until="domcontentloaded", timeout=30000)
                    return self._session_status(platform, live=True, message="辅助登录浏览器已打开")
            except Exception:
                pass
            self._discard_session(platform)

        playwright = self._ensure_playwright()
        ensure_private_directory(self.profile_root, enforce_acl=self.enforce_acl)
        user_data_dir = self.profile_root / adapter.slug
        ensure_private_directory(user_data_dir, enforce_acl=self.enforce_acl)
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=False,
                viewport={"width": 1280, "height": 860},
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(adapter.login_url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            if not self._sessions:
                self._stop_playwright()
            raise

        self._sessions[platform] = {
            "context": context,
            "page": page,
            "started_at": time.time(),
        }
        return self._session_status(platform, live=True, message="辅助登录浏览器已打开")

    def save_session(self, platform: str) -> dict:
        return self._run_on_worker(self._save_session, platform)

    def _save_session(self, platform: str) -> dict:
        adapter = get_adapter(platform)
        session = self._sessions.get(platform)
        if not session:
            raise RuntimeError("请先打开辅助登录浏览器，并在其中完成网页登录")
        context = session["context"]
        page = session.get("page")
        if page and page.is_closed():
            self._discard_session(platform)
            raise RuntimeError("辅助登录浏览器已关闭，请重新打开网页登录后再保存会话")
        storage_state = context.storage_state()
        cookie_header = cookie_header_from_storage_state(storage_state, adapter.domains)
        if not cookie_header:
            raise RuntimeError("未读取到该平台 Cookie，请确认已在辅助登录浏览器中完成登录")
        summary = storage_state_summary(storage_state, adapter.domains)
        try:
            visible_probe = probe_visible_login_controls(page, platform) if page else {}
        except Exception as exc:
            visible_probe = {
                "login_confirmed": None,
                "evidence": f"{platform}可见账号控件检查失败：{exc}",
            }
        login_confirmed = visible_probe.get("login_confirmed")
        evidence = str(visible_probe.get("evidence") or "").strip()
        if login_confirmed is None:
            evidence = (
                f"{evidence or f'{platform}当前页面未确认登录'}；"
                f"已保存 {summary['cookie_count']} 个平台 Cookie（仅作辅助证据）"
            )
        return {
            "platform": platform,
            "storage_state": storage_state,
            "cookie_header": cookie_header,
            "cookie_count": summary["cookie_count"],
            "origin_count": summary["origin_count"],
            "has_local_storage": summary["has_local_storage"],
            "login_confirmed": login_confirmed,
            "evidence": evidence,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    def probe_login_controls(self, platform: str, timeout: int = 15) -> dict:
        """Inspect the current visible browser's top/side account controls."""
        return self._run_on_worker(self._probe_login_controls, platform, timeout)

    def _probe_login_controls(self, platform: str, timeout: int = 15) -> dict:
        adapter = get_adapter(platform)
        # Reuse the persistent profile and navigate to a stable platform page. This
        # also makes the evidence current instead of trusting the state saved earlier.
        self._start_login(platform)
        session = self._sessions.get(platform)
        page = (session or {}).get("page")
        if not page or page.is_closed():
            return {
                "platform": platform,
                "reachable": False,
                "login_confirmed": None,
                "evidence": f"{platform}辅助登录浏览器不可用",
                "error": f"{platform} auxiliary browser is unavailable",
                "final_url": adapter.login_url,
            }
        try:
            page.bring_to_front()
            try:
                page.wait_for_load_state(
                    "networkidle",
                    timeout=min(max(timeout, 5) * 1000, 15000),
                )
            except Exception:
                pass
            try:
                page.wait_for_timeout(700)
            except Exception:
                pass
            probe = probe_visible_login_controls(page, platform)
            probe.update({
                "platform": platform,
                "reachable": True,
                "error": "",
                "final_url": page.url or adapter.login_url,
            })
            return probe
        except Exception as exc:
            return {
                "platform": platform,
                "reachable": False,
                "login_confirmed": None,
                "evidence": f"{platform}可见账号控件检查失败",
                "error": str(exc),
                "final_url": getattr(page, "url", adapter.login_url) or adapter.login_url,
            }

    def read_page(self, platform: str, url: str, timeout: int = 15):
        """Read a page in the persistent visible browser owned by this manager."""
        return self._run_on_worker(self._read_page, platform, url, timeout)

    def _read_page(self, platform: str, url: str, timeout: int = 15):
        adapter = get_adapter(platform)
        session = self._sessions.get(platform)
        if not session:
            self._start_login(platform)
            session = self._sessions.get(platform)
        if not session:
            return "", url, f"{platform} auxiliary browser is unavailable"

        page = session.get("page")
        if not page or page.is_closed():
            self._discard_session(platform)
            return "", url, f"{platform} auxiliary browser was closed"

        captured_douyin_payloads = []
        response_handler_attached = False

        def capture_douyin_search_response(response):
            response_url = str(getattr(response, "url", "") or "")
            if (
                platform != "抖音"
                or "douyin.com" not in response_url
                or not ("search" in response_url or "/aweme/" in response_url)
            ):
                return
            try:
                content_type = (response.headers or {}).get("content-type", "")
                if "json" not in content_type.lower():
                    return
                captured_douyin_payloads.append(json.loads(response.text()))
            except Exception:
                return

        try:
            if platform == "抖音":
                try:
                    page.on("response", capture_douyin_search_response)
                    response_handler_attached = True
                except Exception:
                    response_handler_attached = False
            page.bring_to_front()
            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=max(timeout, 5) * 1000,
            )
            if response and response.status >= 400:
                return "", page.url, f"HTTP {response.status}"
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            try:
                selector = ", ".join(adapter.item_selectors)
                if selector:
                    page.wait_for_selector(
                        selector,
                        timeout=min(max(timeout, 8) * 1000, 15000),
                    )
            except Exception:
                pass
            try:
                page.evaluate("window.scrollTo(0, Math.min(document.body.scrollHeight, 2200))")
                page.wait_for_timeout(1000)
            except Exception:
                pass
            try:
                visible_text = page.locator("body").inner_text(timeout=2500)
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
            normalized = re.sub(r"\s+", "", visible_text).lower()
            verification_markers = (
                "请输入验证码",
                "请完成安全验证",
                "完成验证后继续",
                "拖动滑块完成验证",
                "点击进行验证",
                "访问过于频繁请验证",
                "captchaverification",
                "completethesecuritycheck",
            )
            if visible_verification_widget or any(
                marker in normalized for marker in verification_markers
            ):
                return (
                    "",
                    page.url,
                    f"human_verification_required: {platform}需要在已打开的辅助浏览器中"
                    "完成人工验证；完成后请重新测试",
                )
            html = page.content()
            if platform == "抖音":
                extracted_items = []
                seen_urls = set()
                for payload in captured_douyin_payloads:
                    for item in extract_douyin_items_from_api_payload(
                        payload,
                        limit=30 - len(extracted_items),
                    ):
                        if item["url"] in seen_urls:
                            continue
                        seen_urls.add(item["url"])
                        extracted_items.append(item)
                        if len(extracted_items) >= 30:
                            break
                    if len(extracted_items) >= 30:
                        break
                try:
                    dom_items = page.evaluate(
                        """() => {
                            const clean = (text) => (text || "").replace(/\\s+/g, " ").trim();
                            const result = [];
                            const seen = new Set();
                            for (const link of document.querySelectorAll("a[href*='/video/']")) {
                                let href = "";
                                try { href = new URL(link.getAttribute("href"), location.href).href; } catch (_) {}
                                const match = href.match(/\\/video\\/(\\d{10,30})/);
                                if (!match || seen.has(match[1])) continue;
                                const card = link.closest(
                                    "[data-e2e*='search'], [data-e2e*='card'], article, li, "
                                    + "[class*='search-card'], [class*='video-card']"
                                ) || link.parentElement || link;
                                const image = link.querySelector("img") || card.querySelector("img");
                                const title = clean(
                                    link.getAttribute("title")
                                    || link.getAttribute("aria-label")
                                    || (image && image.getAttribute("alt"))
                                    || card.innerText
                                    || link.innerText
                                    || ""
                                );
                                seen.add(match[1]);
                                result.push({
                                    title: title || `抖音视频 ${match[1]}`,
                                    content: title || `抖音视频 ${match[1]}`,
                                    url: `https://www.douyin.com/video/${match[1]}`,
                                    source: "抖音",
                                    platform: "抖音",
                                    collector: "抖音可见浏览器会话",
                                    session_mode: "browser_session",
                                    search_origin: "douyin_search_dom",
                                    external_id: match[1]
                                });
                                if (result.length >= 30) break;
                            }
                            return result;
                        }"""
                    ) or []
                    for item in dom_items:
                        if item.get("url") in seen_urls:
                            continue
                        seen_urls.add(item.get("url"))
                        extracted_items.append(item)
                        if len(extracted_items) >= 30:
                            break
                except Exception:
                    pass
                if extracted_items:
                    payload = json.dumps(
                        extracted_items,
                        ensure_ascii=False,
                    ).replace("</", "<\\/")
                    html += (
                        "\n<script id=\"codex-extracted-social-items\" "
                        f"type=\"application/json\">{payload}</script>"
                    )
            if not clean_text(visible_text):
                return "", page.url, f"{platform} auxiliary browser returned an empty page"
            return html, page.url, None
        except Exception as exc:
            return "", getattr(page, "url", url) or url, f"{platform} auxiliary browser read failed: {exc}"
        finally:
            if response_handler_attached:
                try:
                    page.remove_listener("response", capture_douyin_search_response)
                except Exception:
                    pass

    def close_session(self, platform: str) -> dict:
        return self._run_on_worker(self._close_session, platform)

    def _close_session(self, platform: str) -> dict:
        if platform not in self._sessions:
            return self._session_status(platform, live=False, message="辅助登录浏览器未打开")
        self._discard_session(platform)
        return self._session_status(platform, live=False, message="辅助登录浏览器已关闭")

    def clear_platform_data(self, platform: str) -> dict:
        """Close a live browser and delete only this platform's profile trees."""
        return self._run_on_worker(self._clear_platform_data, platform)

    def _clear_platform_data(self, platform: str) -> dict:
        adapter = get_adapter(platform)
        self._discard_session(platform)
        removed = 0
        for root in (self.profile_root, self.legacy_profile_root):
            if safe_remove_tree(root / adapter.slug, root):
                removed += 1
        return {
            "platform": platform,
            "profile_trees_removed": removed,
            "live": False,
            "message": "辅助登录会话和浏览器配置已清除",
        }

    def clear_all_data(self) -> dict:
        return self._run_on_worker(self._clear_all_data)

    def _clear_all_data(self) -> dict:
        for platform in list(self._sessions):
            if not platform.startswith("site:"):
                self._discard_session(platform)
        removed = 0
        slugs = {adapter.slug for adapter in SOCIAL_PLATFORM_ADAPTERS.values()}
        for root in (self.profile_root, self.legacy_profile_root):
            for slug in slugs:
                if safe_remove_tree(root / slug, root):
                    removed += 1
        return {
            "profile_trees_removed": removed,
            "live": False,
            "message": "全部辅助登录会话和浏览器配置已清除",
        }

    def _discard_session(self, platform: str):
        session = self._sessions.pop(platform, None)
        if not session:
            return
        try:
            context = session.get("context")
            if context:
                context.close()
        except Exception:
            pass
        try:
            browser = session.get("browser")
            if browser:
                browser.close()
        except Exception:
            pass

    def status(self) -> dict:
        return self._run_on_worker(self._status)

    def _status(self) -> dict:
        return {
            platform: self._session_status(platform, live=True, message="辅助登录浏览器运行中")
            for platform in self._sessions
            if not platform.startswith("site:")
        }

    def shutdown(self):
        """Close live browsers on their owning thread, then stop that thread."""
        worker = self._worker_thread
        if not worker or not worker.is_alive():
            return
        try:
            self._run_on_worker(self._close_all_live_sessions)
        finally:
            self._commands.put(None)
            worker.join(timeout=10)

    def _close_all_live_sessions(self):
        for platform in list(self._sessions):
            self._discard_session(platform)
        self._stop_playwright()

    def _ensure_playwright(self):
        if self._playwright is None:
            sync_playwright, _ = load_playwright()
            self._playwright = sync_playwright().start()
        return self._playwright

    def _stop_playwright(self):
        playwright = self._playwright
        self._playwright = None
        if not playwright:
            return
        try:
            playwright.stop()
        except Exception:
            pass

    def _run_on_worker(self, operation, *args, **kwargs):
        if threading.current_thread() is self._worker_thread:
            return operation(*args, **kwargs)
        self._ensure_worker()
        future = Future()
        self._commands.put((future, operation, args, kwargs))
        return future.result()

    def _ensure_worker(self):
        with self._worker_guard:
            if self._worker_thread and self._worker_thread.is_alive():
                return
            self._worker_thread = threading.Thread(
                target=self._worker_main,
                name="social-browser-session-owner",
                daemon=True,
            )
            self._worker_thread.start()

    def _worker_main(self):
        while True:
            command = self._commands.get()
            if command is None:
                return
            future, operation, args, kwargs = command
            if not future.set_running_or_notify_cancel():
                continue
            try:
                future.set_result(operation(*args, **kwargs))
            except BaseException as exc:
                future.set_exception(exc)

    def _session_status(self, platform: str, live: bool, message: str) -> dict:
        return {
            "platform": platform,
            "live": live,
            "message": message,
            "storage_scope": "current_user_private",
        }

    @staticmethod
    def _site_session_status(domain: str, live: bool, message: str) -> dict:
        return {
            "domain": domain,
            "login_url": _site_origin(domain),
            "live": live,
            "message": message,
            "storage_scope": "current_user_private",
        }
