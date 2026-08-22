#!/usr/bin/env python3
"""使用本机已保存的授权会话，批量执行五个平台的只读真实采集检查。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import web_app
from src.crawler import NewsCrawler, PLATFORM_LIST


DEFAULT_PLATFORMS = ["微博", "B站", "小红书", "抖音", "百度贴吧"]
SAFE_RESULT_FIELDS = (
    "status",
    "passed",
    "reachable",
    "login_confirmed",
    "parsed_count",
    "adapter_name",
    "adapter_backend",
    "adapter_fallback_error",
    "adapter_skipped_reason",
    "evidence",
    "login_error",
    "message",
    "error",
)


def configure_account(crawler: NewsCrawler, platform: str, account: dict) -> None:
    crawler.set_account(
        platform,
        account.get("username", ""),
        account.get("password", ""),
        account.get("cookie", ""),
        account.get("note", ""),
        browser_session=account.get("browser_session", ""),
        browser_cookie=account.get("browser_cookie", ""),
        session_mode=account.get("session_mode", ""),
    )


def safe_result(result: dict) -> dict:
    safe = {field: result.get(field) for field in SAFE_RESULT_FIELDS}
    safe["message"] = str(safe.get("message") or "")[:300]
    safe["error"] = str(safe.get("error") or "")[:500]
    safe["adapter_fallback_error"] = str(
        safe.get("adapter_fallback_error") or ""
    )[:500]
    safe["adapter_skipped_reason"] = str(
        safe.get("adapter_skipped_reason") or ""
    )[:500]
    safe["evidence"] = str(safe.get("evidence") or "")[:300]
    safe["login_error"] = str(safe.get("login_error") or "")[:300]
    safe["parsed_count"] = int(safe.get("parsed_count") or 0)
    return safe


def parse_platforms(raw: str) -> list[str]:
    selected = [
        item.strip()
        for item in str(raw or "").replace("，", ",").split(",")
        if item.strip()
    ]
    selected = selected or list(DEFAULT_PLATFORMS)
    invalid = [platform for platform in selected if platform not in PLATFORM_LIST]
    if invalid:
        raise ValueError(f"未知平台: {', '.join(invalid)}")
    return selected


def run(platforms: list[str], keyword: str, use_system_proxy: bool) -> dict:
    accounts = web_app.sanitize_accounts({}, include_saved=True)
    results = {}
    for platform in platforms:
        crawler = NewsCrawler(
            use_system_proxy=use_system_proxy,
            use_external_social_adapters=True,
        )
        crawler.anti_crawl.delay = lambda *args, **kwargs: None
        configure_account(crawler, platform, accounts.get(platform) or {})
        outcome = crawler.test_social_platform(platform, keyword=keyword)
        safe = safe_result(outcome)
        results[platform] = safe
        print(
            "PLATFORM_RESULT="
            + json.dumps({platform: safe}, ensure_ascii=False),
            flush=True,
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keyword", default="警方通报")
    parser.add_argument(
        "--platforms",
        default=",".join(DEFAULT_PLATFORMS),
        help="以英文逗号分隔的平台列表",
    )
    parser.add_argument(
        "--use-system-proxy",
        action="store_true",
        help="允许 requests 和外部只读适配器使用当前系统代理",
    )
    args = parser.parse_args()
    results = run(
        parse_platforms(args.platforms),
        keyword=str(args.keyword or "警方通报").strip() or "警方通报",
        use_system_proxy=bool(args.use_system_proxy),
    )
    print("SAFE_BATCH_RESULT=" + json.dumps(results, ensure_ascii=False))
    return 0 if all(item.get("passed") for item in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
