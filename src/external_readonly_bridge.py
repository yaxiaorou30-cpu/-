#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在候选项目独立虚拟环境中运行的只读桥接脚本。

输入仅从 stdin 读取 JSON，输出仅向 stdout 写入 JSON。账号令牌不会写回结果。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def _read_payload() -> dict:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    return payload


def _safe_text(value) -> str:
    return str(value or "").strip()


def _prepare_runtime(payload: dict) -> None:
    """Use the candidate repository as an isolated import root and honor proxy choice."""
    candidate_root = str(Path.cwd())
    if candidate_root not in sys.path:
        sys.path.insert(0, candidate_root)
    if bool(payload.get("use_system_proxy", False)):
        return
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ.pop(name, None)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"


def _read_cookie_dict(payload: dict) -> dict[str, str]:
    raw = payload.get("cookies")
    if not isinstance(raw, dict):
        return {}
    cookies = {}
    for raw_name, raw_value in list(raw.items())[:200]:
        name = _safe_text(raw_name)
        value = _safe_text(raw_value)
        if name and value and len(name) <= 128 and len(value) <= 8192:
            cookies[name] = value
    return cookies


def _search_limit(payload: dict) -> int:
    return min(max(int(payload.get("limit") or 20), 1), 50)


def _timestamp(value) -> str:
    try:
        timestamp = int(value or 0)
        return datetime.fromtimestamp(timestamp).astimezone().isoformat() if timestamp > 0 else ""
    except (TypeError, ValueError, OSError):
        return ""


def extract_newspaper(payload: dict) -> dict:
    from newspaper import Article

    html = _safe_text(payload.get("html"))
    if not html:
        raise ValueError("html is required")
    url = _safe_text(payload.get("url")) or "https://example.invalid/article"
    language = _safe_text(payload.get("language")) or "zh"
    article = Article(url, language=language, fetch_images=False)
    article.download(input_html=html)
    article.parse()

    publish_date = article.publish_date
    if publish_date and hasattr(publish_date, "isoformat"):
        publish_date = publish_date.isoformat()
    authors = [str(author).strip() for author in (article.authors or []) if str(author).strip()]
    return {
        "title": _safe_text(article.title),
        "content": _safe_text(article.text),
        "source": "、".join(authors),
        "authors": authors,
        "pub_time": _safe_text(publish_date),
        "canonical_url": _safe_text(getattr(article, "canonical_link", "")),
    }


def _user_name(user) -> str:
    if user is None:
        return ""
    for name in ("show_name", "nick_name_new", "nick_name", "user_name"):
        value = _safe_text(getattr(user, name, ""))
        if value:
            return value
    return ""


def _comment_payload(comment) -> dict:
    user = getattr(comment, "user", None)
    return {
        "id": str(getattr(comment, "pid", "") or ""),
        "content": _safe_text(getattr(comment, "text", "")),
        "author": _user_name(user),
        "like_count": int(getattr(comment, "agree", 0) or 0),
        "pub_time": _timestamp(getattr(comment, "create_time", 0)),
    }


async def _fetch_tieba_thread(payload: dict) -> dict:
    import aiotieba

    tid = int(payload.get("tid") or 0)
    if tid <= 0:
        raise ValueError("positive tid is required")
    max_posts = min(max(int(payload.get("max_posts") or 20), 1), 30)
    max_comments = min(max(int(payload.get("max_comments") or 4), 0), 20)
    include_comments = bool(payload.get("include_comments", True)) and max_comments > 0
    bduss = _safe_text(payload.get("bduss"))
    stoken = _safe_text(payload.get("stoken"))
    use_system_proxy = bool(payload.get("use_system_proxy", False))

    async with aiotieba.Client(
        BDUSS=bduss,
        STOKEN=stoken,
        try_ws=False,
        proxy=use_system_proxy,
    ) as client:
        posts = await client.get_posts(
            tid,
            pn=1,
            rn=max_posts,
            with_comments=include_comments,
            comment_rn=max_comments or 1,
        )

    captured_error = getattr(posts, "err", None)
    if captured_error:
        raise RuntimeError(str(captured_error))
    thread = getattr(posts, "thread", None)
    if thread is None:
        raise RuntimeError("aiotieba returned no thread")

    post_items = []
    comment_total = 0
    for post in list(posts)[:max_posts]:
        comments = []
        for comment in list(getattr(post, "comments", []) or [])[:max_comments]:
            normalized = _comment_payload(comment)
            if normalized["content"]:
                comments.append(normalized)
        comment_total += len(comments)
        post_items.append({
            "id": str(getattr(post, "pid", "") or ""),
            "floor": int(getattr(post, "floor", 0) or 0),
            "content": _safe_text(getattr(post, "text", "")),
            "author": _user_name(getattr(post, "user", None)),
            "reply_count": int(getattr(post, "reply_num", 0) or 0),
            "like_count": int(getattr(post, "agree", 0) or 0),
            "pub_time": _timestamp(getattr(post, "create_time", 0)),
            "comments": comments,
        })

    result = {
        "tid": str(tid),
        "title": _safe_text(getattr(thread, "title", "")),
        "content": _safe_text(getattr(thread, "text", "")),
        "author": _user_name(getattr(thread, "user", None)),
        "forum": _safe_text(getattr(thread, "fname", "")),
        "pub_time": _timestamp(getattr(thread, "create_time", 0)),
        "view_count": int(getattr(thread, "view_num", 0) or 0),
        "reply_count": int(getattr(thread, "reply_num", 0) or 0),
        "share_count": int(getattr(thread, "share_num", 0) or 0),
        "posts": post_items,
        "post_count": len(post_items),
        "comment_count": comment_total,
    }
    if not result["title"] and not result["content"] and not result["posts"]:
        raise RuntimeError("thread is unavailable or returned empty data")
    return result


def fetch_tieba_thread(payload: dict) -> dict:
    return asyncio.run(_fetch_tieba_thread(payload))


def search_weibo(payload: dict) -> dict:
    """Read Weibo search results through the MIT-licensed crawl4weibo client."""
    from crawl4weibo import RateLimitConfig, WeiboClient

    keyword = _safe_text(payload.get("keyword"))
    if not keyword:
        raise ValueError("keyword is required")
    cookies = _read_cookie_dict(payload)
    if not cookies:
        raise ValueError("authorized Weibo cookies are required")
    client = WeiboClient(
        cookies=cookies,
        auto_fetch_cookies=False,
        use_browser_cookies=False,
        proxy_config=None,
        rate_limit_config=RateLimitConfig(
            base_delay=(1.0, 2.0),
            min_delay=(1.0, 2.0),
        ),
        log_level="ERROR",
    )
    try:
        posts, pagination = client.search_posts(
            keyword,
            page=1,
            with_comments=False,
            use_proxy=False,
        )
    finally:
        client.session.close()
    items = []
    for post in list(posts or [])[:_search_limit(payload)]:
        created_at = getattr(post, "created_at", None)
        items.append({
            "idstr": _safe_text(getattr(post, "id", "")),
            "bid": _safe_text(getattr(post, "bid", "")),
            "text_raw": _safe_text(getattr(post, "text", "")),
            "created_at": (
                created_at.isoformat()
                if created_at is not None and hasattr(created_at, "isoformat")
                else _safe_text(created_at)
            ),
            "user": {
                "idstr": _safe_text(getattr(post, "user_id", "")),
            },
            "reposts_count": int(getattr(post, "reposts_count", 0) or 0),
            "comments_count": int(getattr(post, "comments_count", 0) or 0),
            "attitudes_count": int(getattr(post, "attitudes_count", 0) or 0),
        })
    return {"items": items, "pagination": pagination}


def search_bilibili(payload: dict) -> dict:
    from bili_cli.client import search_video

    keyword = _safe_text(payload.get("keyword"))
    if not keyword:
        raise ValueError("keyword is required")
    items = asyncio.run(search_video(keyword, page=1))
    return {"items": list(items or [])[:_search_limit(payload)]}


def search_xiaohongshu(payload: dict) -> dict:
    from xhs_cli.client import XhsClient

    keyword = _safe_text(payload.get("keyword"))
    if not keyword:
        raise ValueError("keyword is required")
    cookies = _read_cookie_dict(payload)
    if not cookies:
        raise ValueError("authorized Xiaohongshu cookies are required")
    with XhsClient(cookies) as client:
        items = client.search_notes(keyword)
    return {"items": list(items or [])[:_search_limit(payload)]}


def main() -> int:
    try:
        action = sys.argv[1] if len(sys.argv) > 1 else ""
        payload = _read_payload()
        _prepare_runtime(payload)
        if action == "newspaper_extract":
            data = extract_newspaper(payload)
        elif action == "tieba_thread":
            data = fetch_tieba_thread(payload)
        elif action == "crawl4weibo_search":
            data = search_weibo(payload)
        elif action == "bilibili_search":
            data = search_bilibili(payload)
        elif action == "xiaohongshu_search":
            data = search_xiaohongshu(payload)
        else:
            raise ValueError("unsupported read-only action")
        print(json.dumps({"ok": True, "data": data}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
