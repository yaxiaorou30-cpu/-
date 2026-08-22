"""Private storage and bounded diagnostics for browser-assisted collection."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_RETENTION_HOURS = 24
_PLATFORM_SLUGS = {
    "微博": "weibo",
    "B站": "bilibili",
    "小红书": "xiaohongshu",
    "抖音": "douyin",
    "知乎": "zhihu",
    "微信公众平台": "wechat",
    "百度贴吧": "tieba",
    "豆瓣": "douban",
    "快手": "kuaishou",
    "今日头条": "toutiao",
}


def default_sensitive_root(project_root: Path | str) -> Path:
    """Return a per-user private location, outside the project when possible."""
    configured = str(os.environ.get("OPINION_SYSTEM_SENSITIVE_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        local_app_data = str(os.environ.get("LOCALAPPDATA") or "").strip()
        if local_app_data:
            return Path(local_app_data) / "AI-Opinion-Monitor" / "sensitive"
    return Path(project_root) / "data" / "private"


def ensure_private_directory(path: Path | str, *, enforce_acl: bool = True) -> Path:
    """Create a directory and restrict it to the current OS user."""
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    try:
        target.chmod(0o700)
    except OSError:
        if enforce_acl:
            raise RuntimeError(f"无法限制敏感目录权限: {target}")

    if os.name == "nt" and enforce_acl:
        sid = _current_windows_sid()
        command = [
            "icacls",
            str(target),
            "/inheritance:r",
            "/grant:r",
            f"*{sid}:(OI)(CI)F",
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=15,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0:
            raise RuntimeError("无法设置当前用户专属的敏感目录权限")
    return target


def _current_windows_sid() -> str:
    try:
        completed = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("无法读取当前 Windows 用户 SID，敏感目录未启用") from exc
    match = re.search(rb"S-\d+(?:-\d+)+", completed.stdout or b"")
    if completed.returncode != 0 or not match:
        raise RuntimeError("无法读取当前 Windows 用户 SID，敏感目录未启用")
    return match.group(0).decode("ascii")


def safe_remove_tree(target: Path | str, allowed_root: Path | str) -> bool:
    """Delete one child tree only after proving it is scoped under allowed_root."""
    target_path = Path(target)
    if not target_path.exists() and not target_path.is_symlink():
        return False
    allowed = Path(allowed_root).resolve()
    resolved = target_path.resolve()
    try:
        relative = resolved.relative_to(allowed)
    except ValueError as exc:
        raise ValueError("拒绝清除敏感目录范围外的路径") from exc
    if not relative.parts:
        raise ValueError("拒绝清除整个敏感数据根目录")
    if target_path.is_symlink():
        target_path.unlink()
    elif target_path.is_dir():
        shutil.rmtree(target_path)
    else:
        target_path.unlink()
    return True


class DiagnosticSnapshotStore:
    """Store sanitized parse diagnostics. Raw HTML is never persisted."""

    def __init__(
        self,
        project_root: Path | str,
        *,
        sensitive_root: Path | str | None = None,
        enabled: bool = False,
        retention_hours: int = DEFAULT_RETENTION_HOURS,
        enforce_acl: bool = True,
    ):
        self.project_root = Path(project_root)
        self.sensitive_root = (
            Path(sensitive_root)
            if sensitive_root is not None
            else default_sensitive_root(self.project_root)
        )
        self.diagnostic_root = self.sensitive_root / "diagnostics"
        self.enabled = bool(enabled)
        self.retention_hours = max(1, min(int(retention_hours), 24 * 30))
        self.enforce_acl = bool(enforce_acl)

    def write(
        self,
        *,
        platform: str,
        channel: str,
        url: str,
        html_text: str,
    ) -> str:
        if not self.enabled or not html_text:
            return ""
        ensure_private_directory(self.diagnostic_root, enforce_acl=self.enforce_acl)
        self.clean_expired()
        slug = platform_slug(platform)
        now = datetime.now(timezone.utc)
        parsed = urlparse(str(url or ""))
        text = str(html_text)
        record = {
            "version": 1,
            "platform": str(platform or ""),
            "channel": str(channel or ""),
            "saved_at": now.replace(microsecond=0).isoformat(),
            "retention_hours": self.retention_hours,
            "origin": _safe_origin(parsed),
            "path_category": _path_category(parsed.path),
            "response_bytes": len(text.encode("utf-8", errors="replace")),
            "content_sha256": hashlib.sha256(
                text.encode("utf-8", errors="replace")
            ).hexdigest(),
            "html_summary": {
                "script_count": len(re.findall(r"<script\b", text, re.I)),
                "link_count": len(re.findall(r"<a\b", text, re.I)),
                "form_count": len(re.findall(r"<form\b", text, re.I)),
                "has_login_prompt": bool(re.search(r"登录|扫码|sign[ -]?in|log[ -]?in", text, re.I)),
                "has_verification_prompt": bool(re.search(r"验证码|安全验证|captcha|verify", text, re.I)),
                "has_access_denied_hint": bool(re.search(r"访问受限|拒绝访问|forbidden|access denied", text, re.I)),
            },
        }
        filename = (
            f"{slug}_{now.strftime('%Y%m%dT%H%M%SZ')}_"
            f"{secrets.token_hex(4)}.diagnostic.json"
        )
        target = self.diagnostic_root / filename
        temp = self.diagnostic_root / f".{filename}.{secrets.token_hex(4)}.tmp"
        try:
            temp.write_text(
                json.dumps(record, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        return f"private-diagnostics/{filename}"

    def clean_expired(self) -> int:
        if not self.diagnostic_root.exists():
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.retention_hours)
        removed = 0
        for candidate in self.diagnostic_root.glob("*.diagnostic.json"):
            try:
                modified = datetime.fromtimestamp(candidate.stat().st_mtime, timezone.utc)
                if modified < cutoff:
                    candidate.unlink()
                    removed += 1
            except OSError:
                continue
        return removed

    def clear_platform(self, platform: str) -> int:
        slug = platform_slug(platform)
        removed = self._clear_matching(f"{slug}_*.diagnostic.json")
        removed += self._clear_legacy(slug)
        return removed

    def clear_all(self) -> int:
        removed = self._clear_matching("*.diagnostic.json")
        legacy = self.project_root / "data" / "debug"
        if legacy.exists():
            for candidate in legacy.glob("latest_*_search.html"):
                try:
                    candidate.unlink()
                    removed += 1
                except OSError:
                    continue
        return removed

    def _clear_matching(self, pattern: str) -> int:
        if not self.diagnostic_root.exists():
            return 0
        removed = 0
        for candidate in self.diagnostic_root.glob(pattern):
            try:
                candidate.unlink()
                removed += 1
            except OSError:
                continue
        return removed

    def _clear_legacy(self, slug: str) -> int:
        legacy = self.project_root / "data" / "debug"
        removed = 0
        for candidate in legacy.glob(f"latest_{slug}_search.html"):
            try:
                candidate.unlink()
                removed += 1
            except OSError:
                continue
        return removed


def platform_slug(platform: str) -> str:
    known = _PLATFORM_SLUGS.get(str(platform or ""))
    if known:
        return known
    slug = re.sub(r"[^0-9A-Za-z_-]+", "_", str(platform or "")).strip("_")
    return slug or "social"


def _safe_origin(parsed) -> str:
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname.casefold()}{port}"


def _path_category(path: str) -> str:
    parts = [part for part in str(path or "/").split("/") if part]
    return "/" if not parts else f"/{parts[0]}/…"
