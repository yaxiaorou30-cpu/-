#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读社交平台 CLI 适配器。

候选开源项目运行在各自的虚拟环境中，本模块仅通过固定的 ``search``
命令读取结构化 JSON，不加载它们的包，也不暴露点赞、评论或发布能力。
"""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence
from urllib.parse import urlencode

from src.external_content_adapters import StdinJsonBridgeRunner


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class AdapterSearchOutcome:
    platform: str
    adapter_name: str
    available: bool
    attempted: bool = False
    items: List[Dict] = field(default_factory=list)
    error: str = ""
    duration_seconds: float = 0.0


class SubprocessCommandRunner:
    """运行白名单 CLI 命令；不经过 shell，避免参数被再次解释。"""

    def run(self, command: Sequence[str], cwd: Path, timeout: int) -> CommandResult:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            creationflags=creationflags,
            check=False,
        )
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


class ReadOnlyCliSearchAdapter:
    platform = ""
    adapter_name = ""
    executable_name = ""
    bridge_action = ""

    def __init__(
        self,
        repo_dir: Path,
        runner: Optional[SubprocessCommandRunner] = None,
        bridge_runner: Optional[StdinJsonBridgeRunner] = None,
        bridge_script: Optional[Path] = None,
    ):
        self.repo_dir = Path(repo_dir)
        self.runner = runner or SubprocessCommandRunner()
        self.bridge_runner = bridge_runner or StdinJsonBridgeRunner()
        self.bridge_script = (
            Path(bridge_script)
            if bridge_script
            else Path(__file__).with_name("external_readonly_bridge.py")
        )

    @property
    def executable_path(self) -> Path:
        if os.name == "nt":
            return self.repo_dir / ".venv" / "Scripts" / f"{self.executable_name}.exe"
        return self.repo_dir / ".venv" / "bin" / self.executable_name

    @property
    def python_path(self) -> Path:
        if os.name == "nt":
            return self.repo_dir / ".venv" / "Scripts" / "python.exe"
        return self.repo_dir / ".venv" / "bin" / "python"

    def bridge_is_available(self) -> bool:
        return bool(
            self.bridge_action
            and self.python_path.is_file()
            and self.bridge_script.is_file()
        )

    def is_available(self) -> bool:
        return self.bridge_is_available() or self.executable_path.is_file()

    def build_search_args(self, keyword: str, limit: int) -> List[str]:
        raise NotImplementedError

    def normalize_payload(self, payload) -> List[Dict]:
        raise NotImplementedError

    def search(
        self,
        keyword: str,
        limit: int = 20,
        timeout: int = 45,
        auth_payload: Optional[Dict] = None,
    ) -> AdapterSearchOutcome:
        outcome = AdapterSearchOutcome(
            platform=self.platform,
            adapter_name=self.adapter_name,
            available=self.is_available(),
        )
        if not outcome.available:
            outcome.error = f"{self.adapter_name} executable not found"
            return outcome

        if self.bridge_is_available():
            return self._search_via_bridge(
                keyword=keyword,
                limit=limit,
                timeout=timeout,
                auth_payload=auth_payload or {},
            )

        command = [str(self.executable_path), *self.build_search_args(keyword, max(1, limit))]
        started = time.monotonic()
        outcome.attempted = True
        try:
            result = self.runner.run(command, cwd=self.repo_dir, timeout=timeout)
        except subprocess.TimeoutExpired:
            outcome.error = f"{self.adapter_name} search timed out after {timeout}s"
            outcome.duration_seconds = round(time.monotonic() - started, 2)
            return outcome
        except Exception as exc:
            outcome.error = f"{self.adapter_name} failed to start: {exc}"
            outcome.duration_seconds = round(time.monotonic() - started, 2)
            return outcome

        outcome.duration_seconds = round(time.monotonic() - started, 2)
        if result.returncode != 0:
            detail = _compact_error(result.stderr or result.stdout)
            outcome.error = f"{self.adapter_name} exited with {result.returncode}: {detail}"
            return outcome

        try:
            payload = decode_json_output(result.stdout)
            normalized = self.normalize_payload(payload)
        except Exception as exc:
            outcome.error = f"{self.adapter_name} returned invalid JSON: {exc}"
            return outcome

        for item in normalized[:limit]:
            item.setdefault("platform", self.platform)
            item.setdefault("source_group", "social")
            item["adapter_backend"] = "external_cli"
            item["adapter_name"] = self.adapter_name
        outcome.items = normalized[:limit]
        return outcome

    def _search_via_bridge(
        self,
        keyword: str,
        limit: int,
        timeout: int,
        auth_payload: Dict,
    ) -> AdapterSearchOutcome:
        outcome = AdapterSearchOutcome(
            platform=self.platform,
            adapter_name=self.adapter_name,
            available=True,
            attempted=True,
        )
        payload = {
            "keyword": keyword,
            "limit": max(1, limit),
            "timeout": timeout,
            **dict(auth_payload or {}),
        }
        command = [str(self.python_path), str(self.bridge_script), self.bridge_action]
        started = time.monotonic()
        try:
            result = self.bridge_runner.run(
                command,
                payload=payload,
                cwd=self.repo_dir,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            outcome.error = f"{self.adapter_name} search timed out after {timeout}s"
            outcome.duration_seconds = round(time.monotonic() - started, 2)
            return outcome
        except Exception as exc:
            outcome.error = f"{self.adapter_name} failed to start: {exc}"
            outcome.duration_seconds = round(time.monotonic() - started, 2)
            return outcome

        outcome.duration_seconds = round(time.monotonic() - started, 2)
        try:
            response = decode_json_output(result.stdout)
        except Exception as exc:
            outcome.error = f"{self.adapter_name} returned invalid bridge JSON: {exc}"
            return outcome
        if result.returncode != 0 or not isinstance(response, dict) or response.get("ok") is not True:
            detail = response.get("error") if isinstance(response, dict) else ""
            outcome.error = f"{self.adapter_name}: {_compact_error(detail or result.stderr)}"
            return outcome
        data = response.get("data")
        raw_items = data.get("items") if isinstance(data, dict) and "items" in data else data
        try:
            normalized = self.normalize_payload(raw_items)
        except Exception as exc:
            outcome.error = f"{self.adapter_name} returned invalid data: {exc}"
            return outcome
        for item in normalized[:limit]:
            item.setdefault("platform", self.platform)
            item.setdefault("source_group", "social")
            item["adapter_backend"] = "external_bridge"
            item["adapter_name"] = self.adapter_name
        outcome.items = normalized[:limit]
        return outcome


class XiaohongshuCliAdapter(ReadOnlyCliSearchAdapter):
    platform = "小红书"
    adapter_name = "xhs-cli"
    executable_name = "xhs"
    bridge_action = "xiaohongshu_search"

    def build_search_args(self, keyword: str, limit: int) -> List[str]:
        return ["search", keyword, "--json"]

    def normalize_payload(self, payload) -> List[Dict]:
        feeds = _as_item_list(payload, keys=("feeds", "items", "data"))
        records = []
        for rank, feed in enumerate(feeds, 1):
            if not isinstance(feed, dict):
                continue
            card = feed.get("note_card") or feed.get("noteCard") or {}
            if not isinstance(card, dict):
                continue
            note_id = str(feed.get("id") or card.get("note_id") or card.get("noteId") or "")
            token = str(feed.get("xsec_token") or feed.get("xsecToken") or "")
            if not note_id or not token:
                continue
            title = _clean_text(card.get("display_title") or card.get("displayTitle") or card.get("title"))
            content = _clean_text(card.get("desc") or card.get("description") or title)
            user = card.get("user") if isinstance(card.get("user"), dict) else {}
            interactions = card.get("interact_info") or card.get("interactInfo") or {}
            if not isinstance(interactions, dict):
                interactions = {}
            query = urlencode({
                "xsec_token": token,
                "xsec_source": "pc_search",
                "source": "web_explore_feed",
            })
            records.append({
                "title": title or content[:80],
                "content": content or title,
                "url": f"https://www.xiaohongshu.com/explore/{note_id}?{query}",
                "source": "小红书",
                "platform": self.platform,
                "author": _clean_text(user.get("nickname") or user.get("nick_name") or user.get("name")),
                "author_url": _xiaohongshu_author_url(user),
                "pub_time": card.get("time") or card.get("publish_time") or "",
                "like_count": parse_count(interactions.get("liked_count") or interactions.get("likedCount")),
                "comment_count": parse_count(interactions.get("comment_count") or interactions.get("commentCount")),
                "repost_count": parse_count(interactions.get("shared_count") or interactions.get("sharedCount")),
                "external_id": note_id,
                "search_origin": "xhs-cli",
                "xhs_source": "pc_search",
                "search_rank": rank,
                "collector": "xhs-cli只读搜索",
            })
        return records


class BilibiliCliAdapter(ReadOnlyCliSearchAdapter):
    platform = "B站"
    adapter_name = "bilibili-cli"
    executable_name = "bili"
    bridge_action = "bilibili_search"

    def build_search_args(self, keyword: str, limit: int) -> List[str]:
        return ["search", keyword, "--type", "video", "--max", str(limit), "--json"]

    def normalize_payload(self, payload) -> List[Dict]:
        videos = _as_item_list(payload, keys=("videos", "items", "data", "result"))
        records = []
        for rank, video in enumerate(videos, 1):
            if not isinstance(video, dict):
                continue
            bvid = str(video.get("bvid") or video.get("id") or "")
            if not re.fullmatch(r"BV[0-9A-Za-z]+", bvid):
                continue
            title = _clean_text(video.get("title"))
            records.append({
                "title": title,
                "content": title,
                "url": f"https://www.bilibili.com/video/{bvid}",
                "source": "B站",
                "platform": self.platform,
                "author": _clean_text(video.get("author")),
                "pub_time": video.get("pubdate") or video.get("created_at") or "",
                "view_count": parse_count(video.get("play") or video.get("view")),
                "duration": str(video.get("duration") or ""),
                "video_id": bvid,
                "external_id": bvid,
                "search_rank": rank,
                "search_origin": "bilibili-cli",
                "collector": "bilibili-cli只读搜索",
            })
        return records


class WeiboCliAdapter(ReadOnlyCliSearchAdapter):
    platform = "微博"
    adapter_name = "weibo-cli"
    executable_name = "weibo"
    bridge_action = "weibo_search"

    def build_search_args(self, keyword: str, limit: int) -> List[str]:
        return ["search", keyword, "--count", str(limit), "--page", "1", "--json"]

    def normalize_payload(self, payload) -> List[Dict]:
        statuses = list(_iter_weibo_statuses(payload))
        records = []
        for rank, status in enumerate(statuses, 1):
            status_id = str(status.get("id") or status.get("idstr") or "")
            bid = str(status.get("bid") or status.get("mblogid") or "")
            user = status.get("user") if isinstance(status.get("user"), dict) else {}
            uid = str(user.get("id") or user.get("idstr") or "")
            if uid and bid:
                url = f"https://weibo.com/{uid}/{bid}"
            elif status_id:
                url = f"https://m.weibo.cn/detail/{status_id}"
            else:
                continue
            content = _clean_text(status.get("text_raw") or status.get("text") or status.get("content"))
            if not content:
                continue
            records.append({
                "title": content[:80],
                "content": content,
                "url": url,
                "source": "微博",
                "platform": self.platform,
                "author": _clean_text(user.get("screen_name") or user.get("name")),
                "author_url": f"https://weibo.com/u/{uid}" if uid else "",
                "pub_time": status.get("created_at") or "",
                "repost_count": parse_count(status.get("reposts_count")),
                "comment_count": parse_count(status.get("comments_count")),
                "like_count": parse_count(status.get("attitudes_count")),
                "external_id": status_id or bid,
                "search_rank": rank,
                "search_origin": "weibo-cli",
                "collector": "weibo-cli只读搜索",
            })
        return records


class Crawl4WeiboAdapter(WeiboCliAdapter):
    """MIT-licensed crawl4weibo keyword-search bridge."""

    adapter_name = "crawl4weibo"
    executable_name = "crawl4weibo-cli"
    bridge_action = "crawl4weibo_search"

    def build_search_args(self, keyword: str, limit: int) -> List[str]:
        return [
            "search-posts",
            "--query",
            keyword,
            "--page",
            "1",
            "--detail",
            "full",
        ]


class ExternalSocialAdapterRegistry:
    def __init__(self, adapters: Sequence[ReadOnlyCliSearchAdapter]):
        self._adapters = {adapter.platform: adapter for adapter in adapters}

    def supports(self, platform: str) -> bool:
        return platform in self._adapters

    def search(
        self,
        platform: str,
        keyword: str,
        limit: int = 20,
        timeout: int = 45,
        auth_payload: Optional[Dict] = None,
    ) -> AdapterSearchOutcome:
        adapter = self._adapters.get(platform)
        if adapter is None:
            return AdapterSearchOutcome(platform=platform, adapter_name="", available=False, error="unsupported platform")
        return adapter.search(
            keyword=keyword,
            limit=limit,
            timeout=timeout,
            auth_payload=auth_payload,
        )

    def status(self) -> List[Dict]:
        return [
            {
                "platform": adapter.platform,
                "adapter_name": adapter.adapter_name,
                "available": adapter.is_available(),
            }
            for adapter in self._adapters.values()
        ]


def create_default_external_social_registry(
    candidates_root: Optional[Path] = None,
    runner: Optional[SubprocessCommandRunner] = None,
) -> ExternalSocialAdapterRegistry:
    root = Path(candidates_root) if candidates_root else Path(__file__).resolve().parents[1] / "opensource_candidates"
    return ExternalSocialAdapterRegistry([
        XiaohongshuCliAdapter(root / "xhs-cli", runner=runner),
        BilibiliCliAdapter(root / "bilibili-cli", runner=runner),
        Crawl4WeiboAdapter(root / "crawl4weibo", runner=runner),
    ])


def decode_json_output(output: str):
    """兼容 CLI 在 JSON 前输出告警或日志的情况。"""
    text = (output or "").lstrip("\ufeff\r\n ")
    if not text:
        raise ValueError("empty output")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char not in "[{":
                continue
            try:
                value, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, (dict, list)):
                return value
    raise ValueError("no JSON object or array found")


def parse_count(value) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)):
        return max(int(value), 0)
    text = str(value).strip().replace(",", "")
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*([万亿]?)", text)
    if not match:
        return 0
    number = float(match.group(1))
    multiplier = {"万": 10_000, "亿": 100_000_000}.get(match.group(2), 1)
    return max(int(number * multiplier), 0)


def _as_item_list(payload, keys: Sequence[str]) -> List:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _as_item_list(value, keys)
            if nested:
                return nested
    return []


def _iter_weibo_statuses(node):
    if isinstance(node, list):
        for item in node:
            yield from _iter_weibo_statuses(item)
        return
    if not isinstance(node, dict):
        return
    mblog = node.get("mblog")
    if isinstance(mblog, dict):
        yield mblog
    for key in ("data", "cards", "card_group", "items", "statuses"):
        child = node.get(key)
        if isinstance(child, (dict, list)):
            yield from _iter_weibo_statuses(child)


def _xiaohongshu_author_url(user: Dict) -> str:
    user_id = str(user.get("user_id") or user.get("userId") or user.get("id") or "")
    return f"https://www.xiaohongshu.com/user/profile/{user_id}" if user_id else ""


def _clean_text(value) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _compact_error(value: str, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[-limit:] if text else "no error details"
