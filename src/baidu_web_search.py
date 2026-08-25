"""Baidu Qianfan web-search discovery adapter.

Official contract (updated 2026-08-14):
https://cloud.baidu.com/doc/qianfan-api/s/Wmbq4z7e5
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
from typing import Any
from urllib.parse import urlparse

import requests


BAIDU_WEB_SEARCH_ENDPOINT = "https://qianfan.baidubce.com/v2/ai_search/web_search"
BAIDU_WEB_SEARCH_ENV = "BAIDU_QIANFAN_API_KEY"
MAX_QUERY_UNITS = 72
MAX_WEB_RESULTS = 50


@dataclass(frozen=True)
class BaiduWebSearchOutcome:
    available: bool
    attempted: bool
    items: list[dict] = field(default_factory=list)
    error: str = ""
    request_id: str = ""


class BaiduWebSearchAdapter:
    """One bounded official API call; no retries, pagination, or secret logging."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        session: Any | None = None,
        timeout_seconds: int = 20,
    ):
        self._api_key = (
            str(os.environ.get(BAIDU_WEB_SEARCH_ENV) or "").strip()
            if api_key is None
            else str(api_key or "").strip()
        )
        self._session = session or requests.Session()
        self.timeout_seconds = max(5, min(int(timeout_seconds), 60))

    def search(
        self,
        query: str,
        *,
        top_k: int = 20,
        keyword: str | None = None,
    ) -> BaiduWebSearchOutcome:
        if not self._api_key:
            return BaiduWebSearchOutcome(
                available=False,
                attempted=False,
                error=f"未配置 {BAIDU_WEB_SEARCH_ENV}，已跳过百度网页搜索",
            )

        query = str(query or "").strip()
        if not query:
            return BaiduWebSearchOutcome(
                available=True,
                attempted=False,
                error="百度网页搜索关键词不能为空",
            )
        if _query_units(query) > MAX_QUERY_UNITS:
            return BaiduWebSearchOutcome(
                available=True,
                attempted=False,
                error="百度网页搜索关键词超过官方 72 字符单位限制",
            )

        try:
            bounded_top_k = max(1, min(int(top_k), MAX_WEB_RESULTS))
        except (TypeError, ValueError):
            bounded_top_k = 20
        payload = {
            "messages": [{"role": "user", "content": query}],
            "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": bounded_top_k}],
            "edition": "standard",
        }

        try:
            response = self._session.post(
                BAIDU_WEB_SEARCH_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=(5, self.timeout_seconds),
            )
        except requests.Timeout:
            return BaiduWebSearchOutcome(True, True, error="百度网页搜索请求超时")
        except Exception:
            return BaiduWebSearchOutcome(True, True, error="无法连接百度网页搜索服务")

        try:
            response_payload = response.json()
        except Exception:
            return BaiduWebSearchOutcome(True, True, error="百度网页搜索响应格式无效")
        if not isinstance(response_payload, dict):
            return BaiduWebSearchOutcome(True, True, error="百度网页搜索响应格式无效")

        request_id = _safe_identifier(
            response_payload.get("request_id") or response_payload.get("requestId")
        )
        status_code = int(getattr(response, "status_code", 0) or 0)
        references = response_payload.get("references")
        if not 200 <= status_code < 300:
            return BaiduWebSearchOutcome(
                True,
                True,
                error=_http_error(status_code, response_payload),
                request_id=request_id,
            )
        if references is None and (
            response_payload.get("code") is not None
            or response_payload.get("message") is not None
        ):
            return BaiduWebSearchOutcome(
                True,
                True,
                error=_http_error(status_code, response_payload),
                request_id=request_id,
            )
        if not isinstance(references, list):
            return BaiduWebSearchOutcome(
                True,
                True,
                error="百度网页搜索响应缺少有效结果列表",
                request_id=request_id,
            )

        result_keyword = str(keyword if keyword is not None else query).strip()
        items = [
            item
            for reference in references
            if (item := _map_reference(reference, result_keyword)) is not None
        ]
        return BaiduWebSearchOutcome(
            available=True,
            attempted=True,
            items=items,
            request_id=request_id,
        )


def _query_units(value: str) -> int:
    return sum(1 if ord(char) < 128 else 2 for char in value)


def _map_reference(reference: Any, keyword: str) -> dict | None:
    if not isinstance(reference, dict):
        return None
    if reference.get("type") not in (None, "", "web"):
        return None
    url = str(reference.get("url") or "").strip()
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not hostname:
        return None
    if parsed.username or parsed.password:
        return None

    title = str(reference.get("title") or reference.get("web_anchor") or url).strip()
    source = str(reference.get("website") or hostname).strip()
    content = str(reference.get("content") or reference.get("snippet") or "").strip()
    return {
        "title": title,
        "url": url,
        "source": source,
        "content": content,
        "pub_time": str(reference.get("date") or "").strip(),
        "search_origin": "baidu_qianfan_web_search",
        "keyword": keyword,
    }


def _safe_identifier(value: Any) -> str:
    text = str(value or "").strip()[:100]
    return text if re.fullmatch(r"[A-Za-z0-9._:-]+", text) else ""


def _http_error(status_code: int, payload: dict) -> str:
    code = _safe_identifier(payload.get("code"))
    details = f"，错误码 {code}" if code else ""
    return f"百度网页搜索请求失败（HTTP {status_code or '未知'}{details}）"
