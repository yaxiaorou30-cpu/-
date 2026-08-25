#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Browser-based UI for the public-opinion crawler."""

import argparse
import base64
import ctypes
import ctypes.wintypes as wintypes
import hashlib
import hmac
import ipaddress
import json
import mimetypes
import os
import re
import socket
import threading
import uuid
import webbrowser
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from src.crawler import (
    COLLECT_LEVELS,
    NewsCrawler,
    PLATFORM_LIST,
    PRIMARY_SOCIAL_PLATFORMS,
    PUBLIC_DISCOVERY_SOURCES,
    STABLE_SOURCE_REGISTRY,
    TIME_RANGE_MAP,
    crawl_and_save,
)
from src.ai_confirmation import AiConfirmationError, OneShotAiConfirmationStore
from src.deepseek_report import (
    DeepSeekReportClient,
    DeepSeekReportError,
    build_ai_report_disclosure,
    deepseek_configuration_status,
)
from src.file_namer import ensure_unique_path, generate_filename
from src.heat_analyzer import HeatAnalyzer
from src.history_archive import HistoryArchiveStore
from src.monitoring import MonitorManager
from src.quality_checks import build_collection_assessment
from src.record_analysis import (
    CONTENT_CATEGORIES,
    SENTIMENT_LABELS,
    annotate_records,
    apply_human_review,
)
from src.sensitive_artifacts import DiagnosticSnapshotStore
from src.social_browser import (
    BrowserSessionManager,
    filter_storage_state_for_site,
    normalize_site_url,
)
from src.summary_builder import build_evidence_summary
from src.system_auth import (
    DEFAULT_ABSOLUTE_TIMEOUT_SECONDS,
    LoginAttemptLimiter,
    SessionManager,
    SystemAccountStore,
    generate_recovery_code,
)
from src.template_manager import TemplateManager


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
DATA_FILE = ROOT / "data" / "latest_news.json"
META_FILE = ROOT / "data" / "latest_news_meta.json"
SOURCE_ACCEPTANCE_DATA_FILE = ROOT / "data" / "source_acceptance_latest.json"
SOURCE_ACCEPTANCE_META_FILE = ROOT / "data" / "source_acceptance_latest_meta.json"
OUTPUT_DIR = ROOT / "output"
TASK_HISTORY_FILE = ROOT / "data" / "task_history.json"
ACCOUNT_STORE_FILE = ROOT / "data" / "social_accounts.secure.json"
SYSTEM_USER_STORE_FILE = ROOT / "data" / "system_users.secure.json"
BROWSER_SESSION_MANAGER = BrowserSessionManager(ROOT)
DIAGNOSTIC_STORE = DiagnosticSnapshotStore(ROOT, enabled=False)
SYSTEM_USER_STORE = SystemAccountStore(SYSTEM_USER_STORE_FILE)
SYSTEM_SESSION_MANAGER = SessionManager(SYSTEM_USER_STORE)
LOGIN_ATTEMPT_LIMITER = LoginAttemptLimiter()
AI_CONFIRMATION_STORE = OneShotAiConfirmationStore()
HISTORY_ARCHIVE_STORE = HistoryArchiveStore(ROOT)
SYSTEM_SESSION_COOKIE = "police_session"

TASKS = {}
TASK_LOCK = threading.Lock()
CRAWL_EXECUTION_LOCK = threading.Lock()
ACCOUNT_STORE_LOCK = threading.RLock()
SITE_AUTHORIZATION_LOCK = threading.RLock()
MAX_EVENTS = 120
MAX_HISTORY = 5000
HISTORY_SUMMARY_FIELDS = (
    "total",
    "real_count",
    "stable_real_count",
    "public_news_real_count",
    "social_real_count",
)
POLICY_BLOCK_CODES = {
    "automation_disabled",
    "embedded_credentials",
    "invalid_url",
    "local_path_denied",
    "path_not_registered",
    "private_network_target",
    "robots_disallowed",
    "robots_rate_limited",
    "robots_unreachable",
}

MONITOR_MANAGER = None


class AiReportExportScopeError(ValueError):
    """An applied AI draft no longer matches the current report evidence."""


AI_REPORT_SCOPE_RECORD_FIELDS = (
    "url",
    "title",
    "content",
    "pub_time",
    "time_basis",
    "source",
    "platform",
    "author",
    "source_type",
    "source_group",
    "data_type",
    "keyword",
    "region",
    "repost_count",
    "comment_count",
    "like_count",
    "view_count",
    "heat_index",
    "case_location",
    "case_type",
    "injury_count",
    "main_event_type",
    "event_type",
    "content_category",
    "content_category_source",
    "sentiment_label",
    "sentiment_source",
    "machine_content_category",
    "machine_sentiment_label",
    "machine_sentiment_score",
)

def read_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def crawl_and_save_serialized(**kwargs):
    """社交平台浏览器会话不能并行使用；一次只运行一个采集作业。"""
    with CRAWL_EXECUTION_LOCK:
        return crawl_and_save(**kwargs)


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _dpapi_protect(text: str) -> str:
    data = text.encode("utf-8")
    in_buffer = ctypes.create_string_buffer(data)
    in_blob = _DataBlob(len(data), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_char)))
    out_blob = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    ):
        raise OSError("DPAPI CryptProtectData failed")
    try:
        protected = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return base64.b64encode(protected).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(value: str) -> str:
    data = base64.b64decode(value.encode("ascii"))
    return _dpapi_unprotect_bytes(data).decode("utf-8")


def _dpapi_unprotect_bytes(data: bytes) -> bytes:
    in_buffer = ctypes.create_string_buffer(data)
    in_blob = _DataBlob(len(data), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_char)))
    out_blob = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    ):
        raise OSError("DPAPI CryptUnprotectData failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _compat_key() -> bytes:
    seed = f"{os.environ.get('USERNAME', '')}|{os.environ.get('USERDOMAIN', '')}|{ROOT.resolve()}"
    return hashlib.sha256(seed.encode("utf-8", errors="ignore")).digest()


def _xor_bytes(data: bytes, key: bytes) -> bytes:
    return bytes(byte ^ key[index % len(key)] for index, byte in enumerate(data))


def encrypt_secret(text: str) -> dict:
    text = text or ""
    if not text:
        return {"scheme": "empty", "value": ""}
    if os.name != "nt":
        raise RuntimeError("当前系统不支持 Windows DPAPI，已拒绝保存账号或浏览器会话")
    try:
        return {"scheme": "dpapi", "value": _dpapi_protect(text)}
    except Exception as exc:
        raise RuntimeError("Windows DPAPI 加密失败，已拒绝保存账号或浏览器会话") from exc


def decrypt_secret(payload: dict) -> str:
    if not isinstance(payload, dict) or payload.get("scheme") == "empty":
        return ""
    scheme = payload.get("scheme")
    value = payload.get("value", "")
    try:
        if scheme == "dpapi":
            return _dpapi_unprotect(value)
        if scheme == "compat-xor":
            raw = base64.b64decode(value.encode("ascii"))
            return _xor_bytes(raw, _compat_key()).decode("utf-8")
    except Exception:
        return ""
    return ""


def mask_secret(value: str, tail: int = 4) -> str:
    value = value or ""
    if not value:
        return ""
    suffix = value[-tail:] if len(value) > tail else value
    return f"已保存，长度 {len(value)}，末尾 {suffix}"


def read_account_store() -> dict:
    with ACCOUNT_STORE_LOCK:
        store = read_json(ACCOUNT_STORE_FILE, {})
        if not isinstance(store, dict):
            store = {}
        store.setdefault("version", 1)
        if not isinstance(store.get("platforms"), dict):
            store["platforms"] = {}
        if not isinstance(store.get("sites"), dict):
            store["sites"] = {}
        return store


def write_account_store(store: dict):
    with ACCOUNT_STORE_LOCK:
        ACCOUNT_STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        store["updated_at"] = datetime.now().isoformat()
        temporary = ACCOUNT_STORE_FILE.with_name(
            f".{ACCOUNT_STORE_FILE.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with temporary.open("w", encoding="utf-8") as f:
                json.dump(store, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, ACCOUNT_STORE_FILE)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def decrypt_saved_accounts() -> dict:
    store = read_account_store()
    accounts = {}
    for platform, entry in store.get("platforms", {}).items():
        accounts[platform] = {
            "username": decrypt_secret(entry.get("username")),
            "password": decrypt_secret(entry.get("password")),
            "cookie": decrypt_secret(entry.get("cookie")),
            "browser_cookie": decrypt_secret(entry.get("browser_cookie")),
            "browser_session": decrypt_secret(entry.get("browser_session")),
            "session_mode": entry.get("session_mode", ""),
            "browser_login_confirmed": entry.get("browser_login_confirmed"),
            "browser_login_evidence": entry.get("browser_login_evidence", ""),
            "note": decrypt_secret(entry.get("note")),
        }
    return accounts


def save_site_browser_session(site_url: str, session_result: dict):
    with SITE_AUTHORIZATION_LOCK:
        site = normalize_site_url(site_url, resolve_dns=False)
        domain = site["domain"]
        storage_state = filter_storage_state_for_site(
            (session_result or {}).get("storage_state") or {},
            domain,
        )
        storage_state_text = json.dumps(storage_state, ensure_ascii=False)
        saved_at = str((session_result or {}).get("saved_at") or datetime.now().isoformat())
        with ACCOUNT_STORE_LOCK:
            store = read_account_store()
            store.setdefault("sites", {})[domain] = {
                "domain": domain,
                "site_url": f"https://{domain}/",
                "browser_session": encrypt_secret(storage_state_text),
                "session_version": uuid.uuid4().hex,
                "session_mode": "browser_session",
                "browser_saved_at": saved_at,
                "browser_cookie_count": len(storage_state.get("cookies") or []),
                "browser_origin_count": len(storage_state.get("origins") or []),
                "browser_has_local_storage": any(
                    (origin or {}).get("localStorage")
                    for origin in storage_state.get("origins") or []
                ),
                "needs_relogin": False,
                "session_checked_at": "",
                "updated_at": datetime.now().isoformat(),
            }
            write_account_store(store)


def site_session_status_summary(domain: str, entry: dict = None) -> dict:
    entry = entry if isinstance(entry, dict) else {}
    storage_state_text = decrypt_secret(entry.get("browser_session"))
    schemes = [
        entry[key].get("scheme")
        for key in ("browser_session",)
        if isinstance(entry.get(key), dict)
        and entry[key].get("scheme") not in (None, "empty")
    ]
    return {
        "domain": domain,
        "site_url": f"https://{domain}/",
        "saved": bool(storage_state_text),
        "browser_session_saved": bool(storage_state_text),
        "browser_saved_at": str(entry.get("browser_saved_at") or ""),
        "browser_cookie_count": int(entry.get("browser_cookie_count") or 0),
        "browser_origin_count": int(entry.get("browser_origin_count") or 0),
        "browser_has_local_storage": bool(entry.get("browser_has_local_storage")),
        "needs_relogin": bool(entry.get("needs_relogin")),
        "session_checked_at": str(entry.get("session_checked_at") or ""),
        "updated_at": str(entry.get("updated_at") or ""),
        "security_scheme": "dpapi" if "dpapi" in schemes else (schemes[0] if schemes else ""),
    }


def build_saved_site_session_statuses() -> dict:
    with SITE_AUTHORIZATION_LOCK:
        sites = read_account_store().get("sites", {})
        return {
            domain: site_session_status_summary(domain, sites[domain])
            for domain in sorted(sites)
        }


def _site_session_version(entry: dict) -> str:
    """Return the private compare-and-set token for one saved site session."""
    version = str((entry or {}).get("session_version") or "").strip()
    if version:
        return version
    encrypted_session = (entry or {}).get("browser_session")
    if not encrypted_session:
        return ""
    legacy_token = json.dumps(
        encrypted_session,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(legacy_token.encode("utf-8")).hexdigest()


def resolve_saved_site_session(url: str):
    with SITE_AUTHORIZATION_LOCK:
        site = normalize_site_url(url, resolve_dns=False)
        entry = read_account_store().get("sites", {}).get(site["domain"])
        if not isinstance(entry, dict):
            return None
        session_version = _site_session_version(entry)
        storage_state_text = decrypt_secret(entry.get("browser_session"))
        if not storage_state_text:
            record_site_session_status(site["domain"], True, session_version)
            return None
        try:
            storage_state = json.loads(storage_state_text)
            if not isinstance(storage_state, dict):
                raise ValueError("网站会话存储格式无效")
            storage_state = filter_storage_state_for_site(storage_state, site["domain"])
        except (AttributeError, TypeError, ValueError):
            record_site_session_status(site["domain"], True, session_version)
            return None
        has_local_storage = any(
            (origin or {}).get("localStorage")
            for origin in storage_state.get("origins") or []
        )
        if not storage_state.get("cookies") and not has_local_storage:
            record_site_session_status(site["domain"], True, session_version)
            return None
        return {
            "domain": site["domain"],
            "storage_state": storage_state,
            "session_version": session_version,
        }


def record_site_session_status(
    domain: str,
    needs_relogin: bool,
    session_version: str,
) -> bool:
    """Persist only crawler-safe session health metadata for an existing site."""
    if not isinstance(needs_relogin, bool):
        raise ValueError("网站会话状态必须是布尔值")
    session_version = str(session_version or "").strip()
    if not session_version:
        return False
    domain = str(domain or "").strip().lower().rstrip(".")
    site = normalize_site_url(f"https://{domain}/", resolve_dns=False)
    with SITE_AUTHORIZATION_LOCK:
        with ACCOUNT_STORE_LOCK:
            store = read_account_store()
            sites = store.get("sites", {})
            entry = sites.get(site["domain"])
            if not isinstance(entry, dict):
                return False
            if _site_session_version(entry) != session_version:
                return False
            updated = dict(entry)
            updated["needs_relogin"] = needs_relogin
            updated["session_checked_at"] = datetime.now().isoformat()
            sites[site["domain"]] = updated
            write_account_store(store)
    return True


def clear_site_authorization(site_url: str) -> dict:
    with SITE_AUTHORIZATION_LOCK:
        site = normalize_site_url(site_url, resolve_dns=False)
        browser_result = BROWSER_SESSION_MANAGER.clear_site_data(site["domain"])
        with ACCOUNT_STORE_LOCK:
            store = read_account_store()
            store.setdefault("sites", {}).pop(site["domain"], None)
            write_account_store(store)
        return {
            "domain": site["domain"],
            "browser": browser_result,
        }


def account_status_summary(platform: str, entry: dict = None) -> dict:
    entry = entry or {}
    username = decrypt_secret(entry.get("username"))
    password = decrypt_secret(entry.get("password"))
    cookie = decrypt_secret(entry.get("cookie"))
    browser_cookie = decrypt_secret(entry.get("browser_cookie"))
    browser_session = decrypt_secret(entry.get("browser_session"))
    note = decrypt_secret(entry.get("note"))
    schemes = [
        (entry.get(key) or {}).get("scheme")
        for key in ("username", "password", "cookie", "browser_cookie", "browser_session", "note")
        if (entry.get(key) or {}).get("scheme") not in (None, "empty")
    ]
    return {
        "platform": platform,
        "saved": bool(username or password or cookie or browser_cookie or browser_session or note),
        "username_saved": bool(username),
        "username_hint": mask_secret(username, tail=2),
        "password_saved": bool(password),
        "password_hint": mask_secret(password),
        "cookie_saved": bool(cookie),
        "cookie_hint": mask_secret(cookie),
        "browser_session_saved": bool(browser_session),
        "browser_cookie_saved": bool(browser_cookie),
        "browser_cookie_hint": mask_secret(browser_cookie),
        "session_mode": entry.get("session_mode", ""),
        "browser_saved_at": entry.get("browser_saved_at", ""),
        "browser_login_confirmed": entry.get("browser_login_confirmed"),
        "browser_login_evidence": entry.get("browser_login_evidence", ""),
        "browser_cookie_count": entry.get("browser_cookie_count", 0),
        "browser_origin_count": entry.get("browser_origin_count", 0),
        "browser_has_local_storage": entry.get("browser_has_local_storage", False),
        "note_saved": bool(note),
        "updated_at": entry.get("updated_at", ""),
        "security_scheme": "dpapi" if "dpapi" in schemes else (schemes[0] if schemes else ""),
        "last_test": entry.get("last_test") or {},
    }


def build_saved_account_statuses() -> dict:
    store = read_account_store()
    platforms = store.get("platforms", {})
    return {
        platform: account_status_summary(platform, platforms.get(platform, {}))
        for platform in PLATFORM_LIST
    }


def save_platform_account(platform: str, account: dict):
    if platform not in PLATFORM_LIST:
        raise ValueError("请选择有效的社交平台")
    with ACCOUNT_STORE_LOCK:
        store = read_account_store()
        current = store.setdefault("platforms", {}).get(platform, {})
        entry = dict(current)
        for key in ("username", "password", "cookie", "note"):
            value = (account or {}).get(key)
            if value is not None:
                entry[key] = encrypt_secret(str(value).strip() if key != "password" else str(value))
                if key == "cookie" and str(value).strip():
                    entry["session_mode"] = "manual_cookie"
        entry["updated_at"] = datetime.now().isoformat()
        store["platforms"][platform] = entry
        write_account_store(store)


def save_platform_browser_session(platform: str, session_result: dict):
    if platform not in PLATFORM_LIST:
        raise ValueError("请选择有效的社交平台")
    with ACCOUNT_STORE_LOCK:
        store = read_account_store()
        current = store.setdefault("platforms", {}).get(platform, {})
        entry = dict(current)
        storage_state = session_result.get("storage_state") or {}
        cookie_header = session_result.get("cookie_header") or ""
        entry["browser_session"] = encrypt_secret(json.dumps(storage_state, ensure_ascii=False))
        entry["browser_cookie"] = encrypt_secret(cookie_header)
        entry["session_mode"] = "browser_session"
        entry["browser_saved_at"] = datetime.now().isoformat()
        entry["browser_login_confirmed"] = session_result.get("login_confirmed")
        entry["browser_login_evidence"] = session_result.get("evidence", "")
        entry["browser_cookie_count"] = session_result.get("cookie_count", 0)
        entry["browser_origin_count"] = session_result.get("origin_count", 0)
        entry["browser_has_local_storage"] = session_result.get("has_local_storage", False)
        entry["updated_at"] = datetime.now().isoformat()
        store["platforms"][platform] = entry
        write_account_store(store)


def clear_platform_account(platform: str = ""):
    with ACCOUNT_STORE_LOCK:
        store = read_account_store()
        if platform:
            store.get("platforms", {}).pop(platform, None)
        else:
            store["platforms"] = {}
        write_account_store(store)


def clear_platform_authorization(platform: str = "") -> dict:
    """Clear encrypted credentials and the linked browser/diagnostic artifacts."""
    clear_platform_account(platform)
    if platform:
        browser_result = BROWSER_SESSION_MANAGER.clear_platform_data(platform)
        diagnostic_count = DIAGNOSTIC_STORE.clear_platform(platform)
    else:
        browser_result = BROWSER_SESSION_MANAGER.clear_all_data()
        diagnostic_count = DIAGNOSTIC_STORE.clear_all()
    return {
        "platform": platform,
        "browser": browser_result,
        "diagnostic_files_removed": diagnostic_count,
    }


def save_account_test_result(platform: str, result: dict):
    with ACCOUNT_STORE_LOCK:
        store = read_account_store()
        entry = store.setdefault("platforms", {}).get(platform)
        if entry is None:
            return
        entry["last_test"] = {
            "tested_at": datetime.now().isoformat(),
            "status": result.get("status", ""),
            "reachable": result.get("reachable"),
            "passed": bool(result.get("passed")),
            "read_passed": bool(result.get("read_passed")),
            "login_passed": bool(result.get("login_passed")),
            "login_confirmed": result.get("login_confirmed"),
            "parsed_count": result.get("parsed_count", 0),
            "error": result.get("error", ""),
            "evidence": result.get("evidence", ""),
            "message": result.get("message", ""),
        }
        store["platforms"][platform] = entry
        write_account_store(store)


def parse_keywords(raw):
    values = raw if isinstance(raw, list) else [raw]
    keywords = []
    seen = set()
    for value in values:
        for item in re.split(r"[,，;；\r\n]+", str(value or "")):
            keyword = item.strip()
            if keyword and keyword not in seen:
                keywords.append(keyword)
                seen.add(keyword)
    return keywords


def relative_to_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def build_download_content_disposition(filename: str) -> str:
    """生成只含ASCII的响应头，同时用RFC 5987保留UTF-8文件名。"""
    name = Path(str(filename or "download")).name
    suffix = Path(name).suffix
    ascii_name = name.encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_name).strip("._-")
    if not ascii_name or ascii_name == suffix.lstrip("."):
        ascii_name = f"download{suffix}"
    encoded_name = quote(name, safe="")
    return (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{encoded_name}"
    )


def sanitize_accounts(raw_accounts, include_saved: bool = False):
    accounts = decrypt_saved_accounts() if include_saved else {}
    for platform, account in (raw_accounts or {}).items():
        if platform not in PLATFORM_LIST:
            continue
        target = dict(accounts.get(platform, {}))
        for key in ("username", "password", "cookie", "note"):
            value = (account or {}).get(key)
            if value:
                target[key] = value
                if key == "cookie":
                    target["session_mode"] = "manual_cookie"
        if target.get("username") or target.get("password") or target.get("cookie"):
            accounts[platform] = target
    return {
        platform: prepare_account_for_crawler(account)
        for platform, account in accounts.items()
        if (
            account.get("username")
            or account.get("password")
            or account.get("cookie")
            or account.get("browser_cookie")
            or account.get("browser_session")
        )
    }


def prepare_account_for_crawler(account: dict) -> dict:
    prepared = dict(account or {})
    if prepared.get("cookie"):
        prepared.setdefault("session_mode", "manual_cookie")
        return prepared
    if prepared.get("browser_cookie"):
        prepared["cookie"] = prepared.get("browser_cookie", "")
        prepared["session_mode"] = "browser_session"
    return prepared


def browser_login_target(payload: dict, *, resolve_site_dns: bool) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    platform = str(payload.get("platform") or "").strip()
    site_url = str(payload.get("site_url") or "").strip()
    if bool(platform) == bool(site_url):
        raise ValueError("社交平台和网站地址必须二选一")
    if platform:
        return {"kind": "platform", "platform": platform}
    use_system_proxy = payload.get("use_system_proxy") is True
    site = normalize_site_url(
        site_url,
        resolve_dns=resolve_site_dns,
        allow_clash_fake_ip=use_system_proxy,
    )
    return {
        "kind": "site",
        **site,
        "use_system_proxy": use_system_proxy,
    }


def account_clear_target(payload: dict) -> dict:
    """Keep the legacy empty-body meaning: clear every social authorization."""
    payload = payload if isinstance(payload, dict) else {}
    platform = str(payload.get("platform") or "").strip()
    site_url = str(payload.get("site_url") or "").strip()
    if not platform and not site_url:
        return {"kind": "platform", "platform": ""}
    return browser_login_target(payload, resolve_site_dns=False)


def task_payload_summary(payload):
    min_real_results = payload.get("min_real_results")
    try:
        min_real_results = int(min_real_results) if min_real_results not in (None, "") else None
    except (TypeError, ValueError):
        min_real_results = None
    return {
        "topic": str(payload.get("topic") or "").strip(),
        "keywords": parse_keywords(payload.get("keywords")),
        "region": str(payload.get("region") or "").strip() or "全国",
        "source_strategy": payload.get("source_strategy") or "all",
        "collect_level": payload.get("collect_level") or "最小采集",
        "time_range": payload.get("time_range") or "近一周",
        "stable_sources": payload.get("stable_sources") or [],
        "social_platforms": payload.get("social_platforms") or [],
        "use_system_proxy": bool(payload.get("use_system_proxy", False)),
        "enable_debug_snapshots": bool(payload.get("enable_debug_snapshots", False)),
        "min_real_results": min_real_results,
        "source_acceptance": bool(payload.get("source_acceptance", False)),
        "account_platforms": sorted(list((payload.get("accounts") or {}).keys())),
    }


def sanitize_task_history_entry(entry):
    """只向历史记录页面暴露复用任务所需的非敏感元数据。"""
    if not isinstance(entry, dict):
        return None
    raw_payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
    raw_summary = entry.get("summary") if isinstance(entry.get("summary"), dict) else {}

    def text_list(value):
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def text_value(key, default=""):
        return str(raw_payload.get(key) or default).strip()

    min_real_results = raw_payload.get("min_real_results")
    try:
        min_real_results = int(min_real_results) if min_real_results not in (None, "") else None
    except (TypeError, ValueError):
        min_real_results = None

    safe_summary = {}
    for key in HISTORY_SUMMARY_FIELDS:
        value = raw_summary.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            safe_summary[key] = value

    safe_entry = {
        "task_id": str(entry.get("task_id") or "").strip(),
        "status": str(entry.get("status") or "").strip(),
        "created_at": str(entry.get("created_at") or "").strip(),
        "completed_at": str(entry.get("completed_at") or "").strip(),
        "message": str(entry.get("message") or "").strip(),
        "summary": safe_summary,
        "payload": {
            "topic": text_value("topic"),
            "keywords": text_list(raw_payload.get("keywords")),
            "region": text_value("region", "全国"),
            "source_strategy": text_value("source_strategy", "all"),
            "collect_level": text_value("collect_level", "最小采集"),
            "time_range": text_value("time_range", "近一周"),
            "stable_sources": text_list(raw_payload.get("stable_sources")),
            "social_platforms": text_list(raw_payload.get("social_platforms")),
            "use_system_proxy": bool(raw_payload.get("use_system_proxy", False)),
            "enable_debug_snapshots": bool(raw_payload.get("enable_debug_snapshots", False)),
            "min_real_results": min_real_results,
        },
    }
    archive_state = str(entry.get("archive_state") or "").strip()
    if archive_state:
        safe_entry["archive_state"] = archive_state
    for key in ("records_count", "report_count"):
        value = entry.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            safe_entry[key] = max(0, value)
    if entry.get("reviewed_at"):
        safe_entry["reviewed_at"] = str(entry.get("reviewed_at"))
    if entry.get("archive_updated_at"):
        safe_entry["archive_updated_at"] = str(entry.get("archive_updated_at"))
    return safe_entry


def write_json_atomic(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_raw_task_history():
    history = read_json(TASK_HISTORY_FILE, [])
    return history if isinstance(history, list) else []


def history_entry_from_manifest(manifest: dict) -> dict:
    review = manifest.get("review") if isinstance(manifest.get("review"), dict) else {}
    entry = sanitize_task_history_entry({
        **manifest,
        "archive_state": (
            "full"
            if manifest.get("has_records") and manifest.get("has_meta")
            else "task_only"
        ),
        "records_count": int(manifest.get("records_count") or 0),
        "report_count": len(manifest.get("reports") or []),
        "reviewed_at": review.get("reviewed_at", ""),
        "archive_updated_at": manifest.get("updated_at", ""),
    })
    return entry or {}


def read_task_history(limit=MAX_HISTORY):
    merged = {}
    for entry in read_raw_task_history():
        safe_entry = sanitize_task_history_entry(entry)
        if safe_entry and safe_entry.get("task_id"):
            safe_entry.setdefault("archive_state", "metadata_only")
            safe_entry.setdefault("records_count", 0)
            safe_entry.setdefault("report_count", 0)
            merged[safe_entry["task_id"]] = safe_entry
    for manifest in HISTORY_ARCHIVE_STORE.list_tasks():
        archive_entry = history_entry_from_manifest(manifest)
        task_id = archive_entry.get("task_id")
        if task_id:
            merged[task_id] = {**merged.get(task_id, {}), **archive_entry}
    safe_history = sorted(
        merged.values(),
        key=lambda item: str(item.get("completed_at") or item.get("created_at") or ""),
        reverse=True,
    )
    return safe_history[: max(0, int(limit))] if limit is not None else safe_history


def append_task_history(entry):
    safe_entry = sanitize_task_history_entry(entry)
    if not safe_entry or not safe_entry.get("task_id"):
        raise ValueError("任务历史缺少有效编号")
    history = [
        item for item in read_raw_task_history()
        if str((item or {}).get("task_id") or "") != safe_entry["task_id"]
    ]
    history.insert(0, safe_entry)
    write_json_atomic(TASK_HISTORY_FILE, history)


def remove_task_history_entry(task_id: str):
    history = [
        item for item in read_raw_task_history()
        if str((item or {}).get("task_id") or "") != str(task_id or "")
    ]
    write_json_atomic(TASK_HISTORY_FILE, history)


def upsert_history_manifest(manifest: dict):
    entry = history_entry_from_manifest(manifest)
    if entry:
        append_task_history(entry)


def archive_task_snapshot(task_id: str, history_entry: dict, data_file: Path, meta_file: Path):
    records = read_json(data_file, []) if data_file.exists() else None
    meta = read_json(meta_file, {}) if meta_file.exists() else None
    return HISTORY_ARCHIVE_STORE.archive_task(
        task_id,
        history_entry=history_entry,
        records=records if isinstance(records, list) else None,
        meta=meta if isinstance(meta, dict) else None,
    )


def ensure_current_history_archive() -> str:
    """Attach the pre-archive latest workspace to its most likely recorded task once."""
    if not DATA_FILE.exists() or not META_FILE.exists():
        return ""
    meta = read_json(META_FILE, {})
    data = read_json(DATA_FILE, [])
    if not isinstance(meta, dict) or not isinstance(data, list):
        return ""
    task_id = str(meta.get("task_id") or "").strip()
    history = read_raw_task_history()
    matched = None
    if task_id:
        matched = next(
            (item for item in history if str((item or {}).get("task_id") or "") == task_id),
            None,
        )
    if not task_id:
        topic = str(meta.get("topic") or "").strip()
        matched = next(
            (
                item for item in history
                if str(((item or {}).get("payload") or {}).get("topic") or "").strip() == topic
            ),
            None,
        )
        task_id = str((matched or {}).get("task_id") or "").strip()
    if not task_id:
        basis = f"{meta.get('generated_at', '')}|{meta.get('topic', '')}|{len(data)}"
        task_id = f"legacy_{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:12]}"
    if not matched:
        matched = {
            "task_id": task_id,
            "status": "done",
            "created_at": str(meta.get("started_at") or meta.get("generated_at") or ""),
            "completed_at": str(meta.get("generated_at") or ""),
            "summary": meta.get("summary") or {},
            "payload": {
                "topic": str(meta.get("topic") or ""),
                "keywords": meta.get("keywords") or [],
                "region": str(meta.get("region") or "全国"),
                "source_strategy": str(meta.get("source_strategy") or "all"),
                "collect_level": str(meta.get("collect_level") or "最小采集"),
                "time_range": str(meta.get("time_range") or "近一周"),
                "stable_sources": meta.get("stable_sources") or [],
                "social_platforms": meta.get("social_platforms") or [],
                "use_system_proxy": bool(meta.get("use_system_proxy", False)),
                "enable_debug_snapshots": False,
                "min_real_results": meta.get("min_real_results"),
            },
        }
        append_task_history(matched)
    safe_entry = sanitize_task_history_entry(matched)
    meta["task_id"] = task_id
    meta["task_payload"] = (safe_entry or {}).get("payload", {})
    write_json_atomic(META_FILE, meta)
    archive_task_snapshot(task_id, safe_entry or matched, DATA_FILE, META_FILE)
    return task_id


def update_current_history_archive() -> str:
    task_id = ensure_current_history_archive()
    if not task_id:
        return ""
    entry = next((item for item in read_task_history(None) if item.get("task_id") == task_id), None)
    if entry:
        manifest = archive_task_snapshot(task_id, entry, DATA_FILE, META_FILE)
        upsert_history_manifest(manifest)
    return task_id


def clear_current_workspace_if_task(task_id: str):
    meta = read_json(META_FILE, {})
    if str((meta or {}).get("task_id") or "") != str(task_id or ""):
        return False
    DATA_FILE.unlink(missing_ok=True)
    META_FILE.unlink(missing_ok=True)
    return True


def history_trash_summary(manifest: dict) -> dict:
    entry = history_entry_from_manifest(manifest)
    entry["trash_id"] = str(manifest.get("trash_id") or "")
    entry["deleted_at"] = str(manifest.get("deleted_at") or "")
    entry["deleted_by"] = str(manifest.get("deleted_by") or "")
    return entry


def build_history_catalog() -> dict:
    history = read_task_history(None)
    trash = [history_trash_summary(item) for item in HISTORY_ARCHIVE_STORE.list_trash()]
    return {
        "history": history,
        "trash": trash,
        "summary": {
            "total": len(history),
            "full_archives": sum(1 for item in history if item.get("archive_state") == "full"),
            "metadata_only": sum(1 for item in history if item.get("archive_state") == "metadata_only"),
            "trash_count": len(trash),
            "report_count": sum(int(item.get("report_count") or 0) for item in history),
        },
    }


def history_detail_payload(task_id: str) -> dict:
    task = HISTORY_ARCHIVE_STORE.get_task(task_id, include_records=True)
    manifest = task.get("manifest") or {}
    reports = []
    for report in manifest.get("reports") or []:
        archive_path = str((report or {}).get("archive_path") or "")
        reports.append({
            "report_id": str((report or {}).get("report_id") or ""),
            "filename": str((report or {}).get("filename") or ""),
            "created_at": str((report or {}).get("created_at") or ""),
            "size": int((report or {}).get("size") or 0),
            "template_id": str((report or {}).get("template_id") or ""),
            "download_url": f"/download?path={quote(archive_path, safe='/')}" if archive_path else "",
        })
    return {
        "task": history_entry_from_manifest(manifest),
        "records": task.get("records") if isinstance(task.get("records"), list) else [],
        "meta": task.get("meta") if isinstance(task.get("meta"), dict) else {},
        "reports": reports,
    }


def classify_crawl_task(meta: dict, source_acceptance: bool = False):
    summary = (meta or {}).get("summary") or {}
    real_count = int(summary.get("real_count") or 0)
    minimum = int((meta or {}).get("min_real_results") or 0)
    if (meta or {}).get("reached_min_real_results"):
        return (
            "done",
            f"稳定源验收通过：取得 {real_count} 条真实公开记录"
            if source_acceptance
            else "采集完成",
        )

    failures = (meta or {}).get("failures") or []
    if (
        real_count == 0
        and failures
        and all(item.get("policy_code") in POLICY_BLOCK_CODES for item in failures)
    ):
        return "blocked", "所有已选来源均被访问策略阻止"
    if source_acceptance:
        return "not_met", f"稳定源验收未通过：真实记录 {real_count}/{minimum}"
    return "done", f"采集完成，但真实记录 {real_count}/{minimum}，未达到最低阈值"


def run_crawl_job(task_id: str, payload: dict):
    def emit(event):
        with TASK_LOCK:
            task = TASKS.get(task_id)
            if not task:
                return
            events = task.setdefault("events", [])
            events.append(event)
            del events[:-MAX_EVENTS]
            if event.get("type") == "source_start":
                task["current_source"] = event.get("channel")
            if event.get("type") in {"source_success", "source_failure"}:
                task["last_event"] = event.get("message")

    with TASK_LOCK:
        TASKS[task_id]["status"] = "running"
        TASKS[task_id]["started_at"] = datetime.now().isoformat()
        TASKS[task_id]["message"] = "采集中"

    try:
        keywords = parse_keywords(payload.get("keywords")) or ["警方通报", "案件通报", "突发事件"]
        source_acceptance = bool(payload.get("source_acceptance", False))
        social_platforms = [] if source_acceptance else payload.get("social_platforms")
        if social_platforms is None:
            social_platforms = PRIMARY_SOCIAL_PLATFORMS
        min_real_results = payload.get("min_real_results")
        max_results = payload.get("max_results")
        if isinstance(min_real_results, str) and min_real_results.strip():
            min_real_results = int(min_real_results)
        elif min_real_results in ("", None):
            min_real_results = None
        if isinstance(max_results, str) and max_results.strip():
            max_results = int(max_results)
        elif max_results in ("", None):
            max_results = None

        output_file = SOURCE_ACCEPTANCE_DATA_FILE if source_acceptance else DATA_FILE
        meta_file = SOURCE_ACCEPTANCE_META_FILE if source_acceptance else META_FILE
        output_path = crawl_and_save_serialized(
            keywords=keywords,
            topic=str(payload.get("topic") or "").strip(),
            output_path=str(output_file),
            meta_path=str(meta_file),
            social_platforms=social_platforms,
            stable_sources=payload.get("stable_sources") or None,
            max_results=max_results,
            region=str(payload.get("region") or "").strip() or None,
            time_range=payload.get("time_range") or "近一周",
            collect_level=payload.get("collect_level") or "最小采集",
            accounts=(
                None
                if source_acceptance
                else sanitize_accounts(payload.get("accounts"), include_saved=True)
            ),
            source_strategy=payload.get("source_strategy") or "all",
            min_real_results=min_real_results,
            progress_callback=emit,
            use_system_proxy=bool(payload.get("use_system_proxy", False)),
            enable_debug_snapshots=bool(payload.get("enable_debug_snapshots", False)),
            use_external_social_adapters=not source_acceptance,
            source_acceptance=source_acceptance,
            live_browser_reader=BROWSER_SESSION_MANAGER.read_page,
            live_login_probe=BROWSER_SESSION_MANAGER.probe_login_controls,
            site_session_resolver=(
                None if source_acceptance else resolve_saved_site_session
            ),
            site_session_status_recorder=(
                None if source_acceptance else record_site_session_status
            ),
        )
        payload_summary = task_payload_summary(payload)
        generated_meta = read_json(meta_file, {})
        if isinstance(generated_meta, dict):
            generated_meta["task_id"] = task_id
            generated_meta["task_payload"] = (sanitize_task_history_entry({
                "task_id": task_id,
                "payload": payload_summary,
            }) or {}).get("payload", {})
            write_json_atomic(meta_file, generated_meta)
        latest = build_latest_payload(output_file, meta_file)
        task_status, task_message = classify_crawl_task(latest.get("meta", {}), source_acceptance)
        with TASK_LOCK:
            task = TASKS[task_id]
            task["status"] = task_status
            task["message"] = task_message
            task["completed_at"] = datetime.now().isoformat()
            task["latest"] = latest
            task["output_path"] = relative_to_root(Path(output_path))
        history_entry = {
            "task_id": task_id,
            "status": task_status,
            "created_at": TASKS[task_id]["created_at"],
            "completed_at": TASKS[task_id]["completed_at"],
            "summary": latest.get("meta", {}).get("summary", {}),
            "payload": payload_summary,
        }
        append_task_history(history_entry)
        manifest = archive_task_snapshot(task_id, history_entry, output_file, meta_file)
        upsert_history_manifest(manifest)
    except Exception as exc:
        with TASK_LOCK:
            task = TASKS.get(task_id)
            if task:
                task["status"] = "error"
                task["message"] = str(exc)
                task["completed_at"] = datetime.now().isoformat()
        history_entry = {
            "task_id": task_id,
            "status": "error",
            "created_at": TASKS.get(task_id, {}).get("created_at", ""),
            "completed_at": datetime.now().isoformat(),
            "message": str(exc),
            "payload": task_payload_summary(payload),
        }
        append_task_history(history_entry)
        manifest = HISTORY_ARCHIVE_STORE.archive_task(task_id, history_entry=history_entry)
        upsert_history_manifest(manifest)


def run_monitor_crawl(
    monitor_id: str,
    payload: dict,
    output_file: Path,
    meta_file: Path,
):
    """执行一轮监测采集；调度层负责互斥、增量比对和状态持久化。"""
    keywords = parse_keywords(payload.get("keywords")) or [
        "警方通报",
        "案件通报",
        "突发事件",
    ]
    min_real_results = payload.get("min_real_results")
    if isinstance(min_real_results, str) and min_real_results.strip():
        min_real_results = int(min_real_results)
    elif min_real_results in ("", None):
        min_real_results = None

    output_file.parent.mkdir(parents=True, exist_ok=True)
    crawl_and_save(
        keywords=keywords,
        topic=str(payload.get("topic") or "").strip(),
        output_path=str(output_file),
        meta_path=str(meta_file),
        social_platforms=payload.get("social_platforms") or [],
        stable_sources=payload.get("stable_sources") or [],
        region=str(payload.get("region") or "").strip() or None,
        time_range=payload.get("time_range") or "近一周",
        collect_level=payload.get("collect_level") or "最小采集",
        accounts=sanitize_accounts(None, include_saved=True),
        source_strategy=payload.get("source_strategy") or "all",
        min_real_results=min_real_results,
        use_system_proxy=bool(payload.get("use_system_proxy", False)),
        enable_debug_snapshots=bool(payload.get("enable_debug_snapshots", False)),
        use_external_social_adapters=True,
        source_acceptance=False,
        live_browser_reader=BROWSER_SESSION_MANAGER.read_page,
        live_login_probe=BROWSER_SESSION_MANAGER.probe_login_controls,
        site_session_resolver=resolve_saved_site_session,
        site_session_status_recorder=record_site_session_status,
    )
    return {
        "records": read_json(output_file, []),
        "meta": read_json(meta_file, {}),
        "monitor_id": monitor_id,
    }


def get_monitor_manager() -> MonitorManager:
    global MONITOR_MANAGER
    if MONITOR_MANAGER is None:
        MONITOR_MANAGER = MonitorManager(
            ROOT / "data" / "monitoring" / "monitor_state.json",
            ROOT / "data" / "monitoring",
            run_monitor_crawl,
            crawl_lock=CRAWL_EXECUTION_LOCK,
        )
    return MONITOR_MANAGER


def build_latest_payload(data_file: Path = DATA_FILE, meta_file: Path = META_FILE):
    data = read_json(data_file, [])
    analyzed_data = annotate_records(data)
    meta = read_json(meta_file, {})
    analyzer = HeatAnalyzer()
    heat = analyzer.calculate_heat_index(data)
    quality = build_collection_assessment(data, meta)
    return {
        "data": analyzed_data,
        "total": len(data),
        "meta": meta,
        "heat": heat,
        "quality": quality,
        "data_path": relative_to_root(data_file),
        "meta_path": relative_to_root(meta_file),
        "history": read_task_history(20),
    }


def build_reviewed_records(data: list, decisions: list, reviewer: str = "", reviewed_at: str = ""):
    """将前端审核决定合并回原始记录，禁止用前端请求覆盖来源证据字段。"""
    if not isinstance(decisions, list):
        raise ValueError("审核结果格式无效")
    decision_by_index = {}
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ValueError("审核结果包含无效记录")
        try:
            index = int(decision.get("index"))
        except (TypeError, ValueError):
            raise ValueError("审核结果缺少有效记录序号") from None
        if index < 0 or index >= len(data) or index in decision_by_index:
            raise ValueError("审核结果中的记录序号无效或重复")
        decision_by_index[index] = decision

    missing = [index for index in range(len(data)) if index not in decision_by_index]
    if missing:
        raise ValueError(f"仍有 {len(missing)} 条记录没有提交审核结果")

    timestamp = reviewed_at or datetime.now().isoformat(timespec="seconds")
    reviewed = []
    category_changed_count = 0
    sentiment_changed_count = 0
    noted_count = 0
    for index, record in enumerate(data):
        decision = decision_by_index[index]
        if not bool(decision.get("keep", False)):
            continue
        merged = apply_human_review(
            record,
            content_category=decision.get("content_category"),
            sentiment_label=decision.get("sentiment_label"),
            note=decision.get("note", ""),
            reviewer=reviewer,
            reviewed_at=timestamp,
        )
        human_review = merged.get("human_review") or {}
        category_changed_count += int(bool(human_review.get("category_changed")))
        sentiment_changed_count += int(bool(human_review.get("sentiment_changed")))
        noted_count += int(bool(human_review.get("note")))
        reviewed.append(merged)

    summary = {
        "reviewed_at": timestamp,
        "reviewed_by": reviewer,
        "original_total": len(data),
        "kept_total": len(reviewed),
        "removed_total": max(len(data) - len(reviewed), 0),
        "category_changed_count": category_changed_count,
        "sentiment_changed_count": sentiment_changed_count,
        "noted_count": noted_count,
        "labels_confirmed": True,
    }
    return reviewed, summary


def review_is_complete(data: list, meta: dict) -> bool:
    review = meta.get("review") if isinstance(meta.get("review"), dict) else {}
    try:
        kept_total = int(review.get("kept_total", -1))
    except (TypeError, ValueError):
        return False
    return bool(
        review.get("reviewed_at")
        and review.get("labels_confirmed")
        and kept_total == len(data)
    )


def filter_report_records(data: list, report_filter) -> tuple[list, dict]:
    """按审核页的当前筛选生成报告数据视图，不修改原始审核数据。"""
    if report_filter is None:
        report_filter = {}
    if not isinstance(report_filter, dict):
        raise ValueError("报告数据范围格式无效")

    normalized = {}
    for key in ("source", "category", "sentiment"):
        value = str(report_filter.get(key) or "").strip()
        if len(value) > 100:
            raise ValueError("报告数据范围条件过长")
        normalized[key] = value

    filtered = []
    for record in data:
        source = str(record.get("platform") or record.get("source") or "未知")
        category = str(record.get("content_category") or "其他")
        sentiment = str(record.get("sentiment_label") or "中性")
        if normalized["source"] and source != normalized["source"]:
            continue
        if normalized["category"] and category != normalized["category"]:
            continue
        if normalized["sentiment"] and sentiment != normalized["sentiment"]:
            continue
        filtered.append(record)

    if not filtered:
        raise ValueError("当前报告范围没有匹配数据，请返回“数据审核”调整筛选条件")

    return filtered, {
        "filters": normalized,
        "active": any(normalized.values()),
        "original_total": len(data),
        "matched_total": len(filtered),
    }


def build_ai_report_export_scope_token(
    records: list,
    meta: dict,
    template_id: str,
) -> str:
    """Bind an applied AI draft to the evidence snapshot used to generate it."""
    source_meta = meta if isinstance(meta, dict) else {}
    scoped_records = []
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        review = record.get("human_review")
        scoped_records.append({
            **{field: record.get(field) for field in AI_REPORT_SCOPE_RECORD_FIELDS},
            "human_reviewed_at": (
                str(review.get("reviewed_at") or "").strip()
                if isinstance(review, dict)
                else ""
            ),
        })
    canonical = json.dumps(
        {
            "version": "ai-report-export-scope-v1",
            "template_id": str(template_id or "event_report").strip(),
            "topic": str(source_meta.get("topic") or "").strip(),
            "keywords": source_meta.get("keywords") or [],
            "records": scoped_records,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8", errors="replace")
    return hashlib.sha256(canonical).hexdigest()


def validate_ai_report_export_scope(
    records: list,
    meta: dict,
    template_id: str,
    confirmed_token: object,
) -> None:
    token = str(confirmed_token or "").strip()
    if not token:
        return
    expected = build_ai_report_export_scope_token(records, meta, template_id)
    if not re.fullmatch(r"[0-9a-f]{64}", token) or not hmac.compare_digest(
        token,
        expected,
    ):
        raise AiReportExportScopeError(
            "AI 草稿对应的证据范围已变化或无效，请重新生成报告预览和 AI 草稿后再导出"
        )


def select_summary_records(data: list, payload: dict) -> tuple[list, dict]:
    """按摘要类型选择服务端已有线索，不接受前端回传正文或链接。"""
    if not isinstance(payload, dict):
        raise ValueError("摘要请求格式无效")
    scope_type = str(payload.get("scope_type") or "").strip()

    if scope_type == "record":
        try:
            index = int(payload.get("record_index"))
        except (TypeError, ValueError):
            raise ValueError("请选择需要摘要的线索") from None
        if index < 0 or index >= len(data):
            raise ValueError("需要摘要的线索不存在或已经变化")
        return [data[index]], {
            "type": "record",
            "label": "单条线索",
            "record_index": index,
            "original_total": len(data),
            "matched_total": 1,
        }

    if scope_type == "source":
        source = str(payload.get("source") or "").strip()
        if not source:
            raise ValueError("请先在“来源平台”中选择一个来源")
        if len(source) > 100:
            raise ValueError("来源名称过长")
        matched = [
            item for item in data
            if str(item.get("platform") or item.get("source") or "未知") == source
        ]
        if not matched:
            raise ValueError("当前来源没有可用数据")
        return matched, {
            "type": "source",
            "label": f"来源“{source}”",
            "source": source,
            "original_total": len(data),
            "matched_total": len(matched),
        }

    if scope_type == "filtered":
        matched, filter_scope = filter_report_records(data, payload.get("report_filter"))
        return matched, {
            **filter_scope,
            "type": "filtered",
            "label": "当前筛选结果" if filter_scope["active"] else "全部审核结果",
        }

    raise ValueError("请选择单条、单来源或当前筛选结果进行摘要")



class WebUIHandler(BaseHTTPRequestHandler):
    server_version = "OpinionWebUI/1.0"

    def log_message(self, fmt, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {fmt % args}")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in {"/login", "/login.html"}:
            if self.current_identity():
                self.redirect_to("/")
            else:
                self.send_static(WEB_DIR / "login.html", public=True)
            return
        if parsed.path == "/api/auth/status":
            self.handle_auth_status()
            return
        if not self.require_auth(parsed.path):
            return
        if parsed.path in {"", "/"}:
            self.send_static(WEB_DIR / "index.html")
            return
        if parsed.path.startswith("/static/"):
            self.send_static(WEB_DIR / parsed.path.lstrip("/"))
            return
        if parsed.path == "/api/options":
            self.send_json(self.build_options())
            return
        if parsed.path == "/api/accounts":
            self.send_json({
                "ok": True,
                "accounts": build_saved_account_statuses(),
                "site_sessions": build_saved_site_session_statuses(),
            })
            return
        if parsed.path == "/api/browser-login/status":
            self.send_json({
                "ok": True,
                "live_sessions": BROWSER_SESSION_MANAGER.status(),
                "accounts": build_saved_account_statuses(),
                "site_sessions": build_saved_site_session_statuses(),
            })
            return
        if parsed.path == "/api/latest":
            self.send_json(self.build_latest())
            return
        if parsed.path == "/api/task":
            self.handle_task_status(parsed.query)
            return
        if parsed.path == "/api/task-history/detail":
            self.handle_task_history_detail(parsed.query)
            return
        if parsed.path == "/api/task-history":
            self.send_json(build_history_catalog())
            return
        if parsed.path == "/api/monitors":
            self.handle_monitors(parsed.query)
            return
        if parsed.path == "/download":
            self.send_download(parsed.query)
            return
        self.send_error(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/auth/setup":
            self.handle_auth_setup()
            return
        if parsed.path == "/api/auth/login":
            self.handle_auth_login()
            return
        if parsed.path == "/api/auth/recover":
            self.handle_auth_recover()
            return
        if parsed.path == "/api/auth/logout":
            self.handle_auth_logout()
            return
        if not self.require_auth(parsed.path):
            return
        if parsed.path == "/api/auth/change-password":
            self.handle_auth_change_password()
            return
        if parsed.path == "/api/auth/recovery-code":
            self.handle_auth_recovery_code()
            return
        if parsed.path == "/api/crawl":
            self.handle_crawl()
            return
        if parsed.path == "/api/monitors/create":
            self.handle_monitor_create()
            return
        if parsed.path == "/api/monitors/action":
            self.handle_monitor_action()
            return
        if parsed.path == "/api/test-account":
            self.handle_test_account()
            return
        if parsed.path == "/api/accounts/save":
            self.handle_account_save()
            return
        if parsed.path == "/api/accounts/clear":
            self.handle_account_clear()
            return
        if parsed.path == "/api/browser-login/start":
            self.handle_browser_login_start()
            return
        if parsed.path == "/api/browser-login/save":
            self.handle_browser_login_save()
            return
        if parsed.path == "/api/browser-login/close":
            self.handle_browser_login_close()
            return
        if parsed.path == "/api/accounts/open-login":
            self.handle_browser_login_start()
            return
        if parsed.path == "/api/review-save":
            self.handle_review_save()
            return
        if parsed.path == "/api/summary":
            self.handle_summary()
            return
        if parsed.path == "/api/report-preview":
            self.handle_report_preview()
            return
        if parsed.path == "/api/report-ai-draft":
            self.handle_ai_report_draft()
            return
        if parsed.path == "/api/report":
            self.handle_report()
            return
        if parsed.path == "/api/task-history/load":
            self.handle_task_history_load()
            return
        if parsed.path == "/api/task-history/delete":
            self.handle_task_history_delete()
            return
        if parsed.path == "/api/task-history/trash-action":
            self.handle_task_history_trash_action()
            return
        if parsed.path == "/api/task-history/backup":
            self.handle_task_history_backup()
            return
        if parsed.path == "/api/task-history/restore":
            self.handle_task_history_restore()
            return
        self.send_error(404, "Not found")

    def read_body_json(self, *, max_bytes=None):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        if max_bytes is not None and length > max_bytes:
            raise ValueError("请求内容过大")
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw or "{}")

    def send_json(self, payload, status=200, extra_headers=None):
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, path: Path, *, public: bool = False):
        path = path.resolve()
        try:
            path.relative_to(WEB_DIR.resolve())
        except ValueError:
            self.send_error(404, "Static file not found")
            return
        if not path.exists() or path.is_dir():
            self.send_error(404, "Static file not found")
            return
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        if public:
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; connect-src 'self'; "
                "img-src 'self' data:; frame-ancestors 'none'; form-action 'self'",
            )
        self.end_headers()
        self.wfile.write(body)

    def cookie_value(self, name: str) -> str:
        raw = self.headers.get("Cookie", "")
        if not raw:
            return ""
        try:
            cookie = SimpleCookie()
            cookie.load(raw)
            morsel = cookie.get(name)
            return morsel.value if morsel else ""
        except Exception:
            return ""

    def current_identity(self, *, touch: bool = True):
        return SYSTEM_SESSION_MANAGER.resolve(
            self.cookie_value(SYSTEM_SESSION_COOKIE),
            touch=touch,
        )

    def redirect_to(self, location: str):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()

    def require_auth(self, path: str) -> bool:
        if self.current_identity():
            return True
        if path.startswith("/api/"):
            self.send_json(
                {
                    "ok": False,
                    "code": "authentication_required",
                    "message": "请先登录系统账号",
                },
                status=401,
            )
        else:
            self.redirect_to("/login")
        return False

    def handle_auth_status(self):
        identity = self.current_identity()
        setup_required = not SYSTEM_USER_STORE.has_users()
        configured_user = SYSTEM_USER_STORE.single_user()
        self.send_json({
            "ok": True,
            "authenticated": bool(identity),
            "user": identity,
            "setup_required": setup_required,
            "account_unavailable": bool(configured_user and not configured_user.get("enabled")),
            "single_account": True,
            "recovery_configured": bool(
                identity
                and configured_user
                and configured_user.get("recovery_configured")
            ),
        })

    def issue_auth_session(self, username: str, *, message: str, extra_payload=None):
        token, identity = SYSTEM_SESSION_MANAGER.create(username)
        cookie = (
            f"{SYSTEM_SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; "
            f"Max-Age={DEFAULT_ABSOLUTE_TIMEOUT_SECONDS}"
        )
        self.send_json(
            {
                "ok": True,
                "message": message,
                "user": identity,
                **(extra_payload or {}),
            },
            extra_headers={"Set-Cookie": cookie},
        )

    def handle_auth_setup(self):
        try:
            payload = self.read_body_json(max_bytes=24 * 1024)
            username = str(payload.get("username") or "").strip()
            password = str(payload.get("password") or "")
            confirmation = str(payload.get("password_confirmation") or "")
            if password != confirmation:
                raise ValueError("两次输入的密码不一致")
            if SYSTEM_USER_STORE.has_users():
                self.send_json(
                    {"ok": False, "message": "本机已完成账号设置，不能再创建第二个账号"},
                    status=409,
                )
                return
            recovery_code = generate_recovery_code()
            user = SYSTEM_USER_STORE.create_user(
                username,
                password,
                recovery_code=recovery_code,
            )
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json({"ok": False, "message": "首次设置请求格式无效"}, status=400)
            return
        except (ValueError, RuntimeError) as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=400)
            return
        self.issue_auth_session(
            user["username"],
            message="本机账号创建成功",
            extra_payload={"recovery_code": recovery_code, "recovery_rotated": True},
        )

    def handle_auth_login(self):
        try:
            payload = self.read_body_json(max_bytes=16 * 1024)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            self.send_json({"ok": False, "message": "登录请求格式无效"}, status=400)
            return
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        if len(username) > 64 or len(password) > 1024:
            self.send_json({"ok": False, "message": "账号或密码错误，或账号已停用"}, status=401)
            return
        if not SYSTEM_USER_STORE.has_users():
            self.send_json({
                "ok": False,
                "code": "setup_required",
                "message": "尚未配置本机系统账号，请先完成首次设置",
            }, status=503)
            return
        if not SYSTEM_USER_STORE.has_enabled_users():
            self.send_json({
                "ok": False,
                "code": "account_unavailable",
                "message": "本机账号当前不可用，请联系交付维护人员",
            }, status=503)
            return
        client = str(getattr(self, "client_address", ("unknown",))[0])
        if LOGIN_ATTEMPT_LIMITER.is_blocked(client, username):
            self.send_json({
                "ok": False,
                "code": "login_temporarily_blocked",
                "message": "登录失败次数过多，请稍后再试",
            }, status=429)
            return
        result = SYSTEM_USER_STORE.authenticate(username, password)
        if not result.ok:
            LOGIN_ATTEMPT_LIMITER.record_failure(client, username)
            self.send_json({"ok": False, "message": "账号或密码错误，或账号已停用"}, status=401)
            return
        LOGIN_ATTEMPT_LIMITER.clear(client, username)
        self.issue_auth_session(result.username, message="登录成功")

    def handle_auth_change_password(self):
        identity = self.current_identity(touch=False)
        try:
            payload = self.read_body_json(max_bytes=16 * 1024)
            current_password = str(payload.get("current_password") or "")
            new_password = str(payload.get("new_password") or "")
            confirmation = str(payload.get("password_confirmation") or "")
            if new_password != confirmation:
                raise ValueError("两次输入的新密码不一致")
            result = SYSTEM_USER_STORE.authenticate(identity["username"], current_password)
            if not result.ok:
                self.send_json({"ok": False, "message": "当前密码错误"}, status=401)
                return
            SYSTEM_USER_STORE.change_password(identity["username"], new_password)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json({"ok": False, "message": "密码修改请求格式无效"}, status=400)
            return
        except (ValueError, RuntimeError) as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=400)
            return
        SYSTEM_SESSION_MANAGER.revoke_user(identity["username"])
        cookie = f"{SYSTEM_SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
        self.send_json(
            {"ok": True, "message": "密码已修改，请使用新密码重新登录"},
            extra_headers={"Set-Cookie": cookie},
        )

    def handle_auth_recovery_code(self):
        identity = self.current_identity(touch=False)
        try:
            payload = self.read_body_json(max_bytes=8 * 1024)
            current_password = str(payload.get("current_password") or "")
            result = SYSTEM_USER_STORE.authenticate(identity["username"], current_password)
            if not result.ok:
                self.send_json({"ok": False, "message": "当前密码错误"}, status=401)
                return
            recovery_code = generate_recovery_code()
            SYSTEM_USER_STORE.set_recovery_code(identity["username"], recovery_code)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json({"ok": False, "message": "恢复码请求格式无效"}, status=400)
            return
        except (ValueError, RuntimeError) as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=400)
            return
        self.send_json({
            "ok": True,
            "message": "新的恢复码已生成；旧恢复码立即失效",
            "recovery_code": recovery_code,
            "recovery_rotated": True,
        })

    def handle_auth_recover(self):
        try:
            payload = self.read_body_json(max_bytes=24 * 1024)
            username = str(payload.get("username") or "").strip()
            recovery_code = str(payload.get("recovery_code") or "")
            new_password = str(payload.get("new_password") or "")
            confirmation = str(payload.get("password_confirmation") or "")
            if new_password != confirmation:
                raise ValueError("两次输入的新密码不一致")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json({"ok": False, "message": "密码恢复请求格式无效"}, status=400)
            return
        except ValueError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=400)
            return
        client = str(getattr(self, "client_address", ("unknown",))[0])
        limiter_username = f"recovery:{username}"
        if LOGIN_ATTEMPT_LIMITER.is_blocked(client, limiter_username):
            self.send_json({
                "ok": False,
                "code": "recovery_temporarily_blocked",
                "message": "恢复失败次数过多，请稍后再试",
            }, status=429)
            return
        replacement_code = generate_recovery_code()
        try:
            result = SYSTEM_USER_STORE.recover_password(
                username,
                recovery_code,
                new_password,
                replacement_code,
            )
        except (ValueError, RuntimeError):
            result = None
        if not result or not result.ok:
            LOGIN_ATTEMPT_LIMITER.record_failure(client, limiter_username)
            self.send_json({"ok": False, "message": "账号或恢复码错误"}, status=401)
            return
        LOGIN_ATTEMPT_LIMITER.clear(client, limiter_username)
        SYSTEM_SESSION_MANAGER.revoke_user(result.username)
        self.issue_auth_session(
            result.username,
            message="密码已重置；旧密码、旧会话和旧恢复码均已失效",
            extra_payload={"recovery_code": replacement_code, "recovery_rotated": True},
        )

    def handle_auth_logout(self):
        SYSTEM_SESSION_MANAGER.revoke(self.cookie_value(SYSTEM_SESSION_COOKIE))
        cookie = f"{SYSTEM_SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
        self.send_json(
            {"ok": True, "message": "已安全退出"},
            extra_headers={"Set-Cookie": cookie},
        )

    def send_download(self, query: str):
        params = parse_qs(query)
        raw_path = unquote((params.get("path") or [""])[0])
        candidate = (ROOT / raw_path).resolve()
        allowed_roots = [OUTPUT_DIR.resolve(), (ROOT / "data").resolve()]
        within_allowed_root = False
        for allowed_root in allowed_roots:
            try:
                candidate.relative_to(allowed_root)
                within_allowed_root = True
                break
            except ValueError:
                continue
        if not raw_path or not within_allowed_root:
            self.send_error(403, "Download path is not allowed")
            return
        if not candidate.exists() or candidate.is_dir():
            self.send_error(404, "Download file not found")
            return
        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header(
            "Content-Disposition",
            build_download_content_disposition(candidate.name),
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def build_options(self):
        templates = TemplateManager(str(ROOT / "config" / "templates")).list_templates()
        stable_sources = [
            source["name"] for source in STABLE_SOURCE_REGISTRY if source.get("enabled", True)
        ]
        history_catalog = build_history_catalog()
        return {
            "stable_sources": stable_sources,
            "public_news_sources": [source["name"] for source in PUBLIC_DISCOVERY_SOURCES],
            "social_platforms": PLATFORM_LIST,
            "primary_social_platforms": PRIMARY_SOCIAL_PLATFORMS,
            "time_ranges": list(TIME_RANGE_MAP.keys()),
            "collect_levels": list(COLLECT_LEVELS.keys()),
            "templates": templates,
            "content_categories": list(CONTENT_CATEGORIES),
            "sentiment_labels": list(SENTIMENT_LABELS),
            "task_history": history_catalog["history"][:20],
            "history_catalog": history_catalog,
            "saved_accounts": build_saved_account_statuses(),
            "site_sessions": build_saved_site_session_statuses(),
            "compliance_notice": "仅采集公开可访问内容；账号 Cookie/密码可加密保存在本机，不会写入采集结果、日志或报告；默认不使用系统代理，可按需手动开启。",
            "ai_provider": deepseek_configuration_status(),
            "latest": self.build_latest(),
        }

    def build_latest(self):
        return build_latest_payload()

    def handle_crawl(self):
        try:
            payload = self.read_body_json()
            if payload.get("async", True):
                task_id = uuid.uuid4().hex[:12]
                with TASK_LOCK:
                    TASKS[task_id] = {
                        "task_id": task_id,
                        "status": "queued",
                        "message": "任务已创建",
                        "created_at": datetime.now().isoformat(),
                        "events": [],
                        "payload": task_payload_summary(payload),
                    }
                thread = threading.Thread(target=run_crawl_job, args=(task_id, payload), daemon=True)
                thread.start()
                self.send_json({"ok": True, "task_id": task_id, "message": "采集任务已启动"})
                return

            task_id = uuid.uuid4().hex[:12]
            with TASK_LOCK:
                TASKS[task_id] = {
                    "task_id": task_id,
                    "status": "queued",
                    "message": "任务已创建",
                    "created_at": datetime.now().isoformat(),
                    "events": [],
                    "payload": task_payload_summary(payload),
                }
            run_crawl_job(task_id, payload)
            with TASK_LOCK:
                task = TASKS.get(task_id, {})
            if task.get("status") == "error":
                self.send_json({"ok": False, "task": task, "message": task.get("message", "采集失败")}, status=500)
            else:
                self.send_json({"ok": True, "task_id": task_id, "task": task, "latest": task.get("latest")})
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def handle_task_status(self, query: str):
        params = parse_qs(query)
        task_id = (params.get("id") or [""])[0]
        with TASK_LOCK:
            task = dict(TASKS.get(task_id, {}))
            if task.get("events"):
                task["events"] = list(task["events"])
        if not task:
            self.send_json({"ok": False, "message": "任务不存在"}, status=404)
            return
        self.send_json({"ok": True, "task": task})

    def handle_task_history_detail(self, query: str):
        params = parse_qs(query)
        task_id = (params.get("id") or [""])[0]
        try:
            self.send_json({"ok": True, **history_detail_payload(task_id)})
        except FileNotFoundError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=404)
        except ValueError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=400)
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def handle_task_history_load(self):
        try:
            payload = self.read_body_json(max_bytes=16 * 1024)
            task_id = str(payload.get("task_id") or "").strip()
            result = HISTORY_ARCHIVE_STORE.load_task(task_id, DATA_FILE, META_FILE)
            self.send_json({
                "ok": True,
                "message": f"历史任务已载入，共 {result['records_count']} 条正文",
                "latest": self.build_latest(),
                **build_history_catalog(),
            })
        except FileNotFoundError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=404)
        except ValueError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=400)
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def handle_task_history_delete(self):
        try:
            payload = self.read_body_json(max_bytes=16 * 1024)
            task_id = str(payload.get("task_id") or "").strip()
            if str(payload.get("confirm_task_id") or "").strip() != task_id:
                raise ValueError("删除确认与任务编号不一致")
            identity = self.current_identity(touch=False) or {}
            archived_ids = {item.get("task_id") for item in HISTORY_ARCHIVE_STORE.list_tasks()}
            if task_id in archived_ids:
                result = HISTORY_ARCHIVE_STORE.move_to_trash(
                    task_id,
                    deleted_by=str(identity.get("username") or ""),
                )
                message = "历史任务已移入回收站；已有加密备份不会随之删除"
            else:
                if not any(item.get("task_id") == task_id for item in read_task_history(None)):
                    raise FileNotFoundError("历史任务不存在")
                result = {"task_id": task_id, "metadata_only": True}
                message = "旧版任务信息已删除；该记录原本没有可恢复的正文归档"
            remove_task_history_entry(task_id)
            result["current_workspace_cleared"] = clear_current_workspace_if_task(task_id)
            self.send_json({
                "ok": True,
                "message": message,
                "result": result,
                "latest": self.build_latest(),
                **build_history_catalog(),
            })
        except FileNotFoundError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=404)
        except ValueError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=400)
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def handle_task_history_trash_action(self):
        try:
            payload = self.read_body_json(max_bytes=16 * 1024)
            trash_id = str(payload.get("trash_id") or "").strip()
            action = str(payload.get("action") or "").strip()
            if action == "restore":
                manifest = HISTORY_ARCHIVE_STORE.restore_from_trash(trash_id)
                upsert_history_manifest(manifest)
                message = "历史任务已从回收站恢复"
                result = {"task_id": manifest.get("task_id"), "trash_id": trash_id}
            elif action == "purge":
                if str(payload.get("confirm_trash_id") or "").strip() != trash_id:
                    raise ValueError("永久删除确认与回收站编号不一致")
                result = HISTORY_ARCHIVE_STORE.purge_trash(trash_id)
                message = "回收站记录已永久删除；已有加密备份不会随之删除"
            else:
                raise ValueError("不支持的回收站操作")
            self.send_json({
                "ok": True,
                "message": message,
                "result": result,
                **build_history_catalog(),
            })
        except FileNotFoundError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=404)
        except FileExistsError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=409)
        except ValueError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=400)
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def handle_task_history_backup(self):
        try:
            payload = self.read_body_json(max_bytes=16 * 1024)
            ensure_current_history_archive()
            backup = HISTORY_ARCHIVE_STORE.create_backup(str(payload.get("passphrase") or ""))
            relative_path = relative_to_root(backup.pop("path"))
            self.send_json({
                "ok": True,
                "message": f"加密备份已创建，包含 {backup['task_count']} 个完整任务归档",
                "backup": {
                    **backup,
                    "download_url": f"/download?path={quote(relative_path, safe='/')}",
                },
            })
        except ValueError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=400)
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def handle_task_history_restore(self):
        try:
            payload = self.read_body_json(max_bytes=96 * 1024 * 1024)
            encoded = str(payload.get("backup_base64") or "")
            if not encoded:
                raise ValueError("请选择本系统生成的 .aombak 备份文件")
            try:
                encrypted = base64.b64decode(encoded.encode("ascii"), validate=True)
            except (ValueError, UnicodeEncodeError) as exc:
                raise ValueError("备份文件编码无效") from exc
            restored = HISTORY_ARCHIVE_STORE.restore_backup(
                encrypted,
                str(payload.get("passphrase") or ""),
            )
            self.send_json({
                "ok": True,
                "message": (
                    f"恢复完成：新增 {len(restored['restored_task_ids'])} 个，"
                    f"已存在 {len(restored['skipped_task_ids'])} 个，"
                    f"冲突未覆盖 {len(restored['conflict_task_ids'])} 个"
                ),
                "restore": restored,
                **build_history_catalog(),
            })
        except ValueError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=400)
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def handle_monitors(self, query: str):
        params = parse_qs(query)
        monitor_id = (params.get("id") or [""])[0]
        manager = get_monitor_manager()
        try:
            plans = manager.list_plans()
            if not monitor_id and plans:
                monitor_id = plans[0]["id"]
            selected = manager.get_plan(monitor_id) if monitor_id else None
            self.send_json({
                "ok": True,
                "plans": plans,
                "selected": selected,
            })
        except KeyError as exc:
            self.send_json({"ok": False, "message": str(exc.args[0])}, status=404)

    def handle_monitor_create(self):
        try:
            request = self.read_body_json(max_bytes=256 * 1024)
            plan = get_monitor_manager().create_plan(
                request.get("payload") or {}, request.get("interval_minutes")
            )
            self.send_json({
                "ok": True,
                "message": "监测计划已创建，首次运行将自动建立基线",
                "plan": plan,
                "plans": get_monitor_manager().list_plans(),
            })
        except (ValueError, TypeError) as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=400)
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def handle_monitor_action(self):
        try:
            request = self.read_body_json(max_bytes=32 * 1024)
            plan = get_monitor_manager().action(
                request.get("monitor_id"), request.get("action")
            )
            self.send_json({
                "ok": True,
                "message": plan.get("last_message") or "监测计划已更新",
                "plan": plan,
                "plans": get_monitor_manager().list_plans(),
            })
        except KeyError as exc:
            self.send_json({"ok": False, "message": str(exc.args[0])}, status=404)
        except (ValueError, TypeError) as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=400)
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def handle_test_account(self):
        try:
            payload = self.read_body_json()
            platform = payload.get("platform") or ""
            account = payload.get("account") or {}
            keyword = payload.get("keyword") or "警方通报"
            if platform not in PLATFORM_LIST:
                raise ValueError("请选择有效的社交平台")
            merged_accounts = sanitize_accounts({platform: account}, include_saved=True)
            merged_account = merged_accounts.get(platform, {})
            crawler = NewsCrawler(
                use_system_proxy=bool(payload.get("use_system_proxy", False)),
                use_external_social_adapters=True,
                live_browser_reader=BROWSER_SESSION_MANAGER.read_page,
                live_login_probe=BROWSER_SESSION_MANAGER.probe_login_controls,
            )
            crawler.anti_crawl.delay = lambda *args, **kwargs: None
            crawler.set_account(
                platform,
                merged_account.get("username", ""),
                merged_account.get("password", ""),
                merged_account.get("cookie", ""),
                browser_session=merged_account.get("browser_session", ""),
                browser_cookie=merged_account.get("browser_cookie", ""),
                session_mode=merged_account.get("session_mode", ""),
                browser_login_confirmed=merged_account.get("browser_login_confirmed"),
                browser_login_evidence=merged_account.get("browser_login_evidence", ""),
            )
            result = crawler.test_social_platform(platform, keyword=keyword)
            if not merged_account.get("cookie") and (merged_account.get("username") or merged_account.get("password")):
                result["login_confirmed"] = None
                result["evidence"] = "已保存账号信息，但缺少 Cookie，无法确认登录"
                result["login_error"] = "missing cookie"
            save_account_test_result(platform, result)
            result["ok"] = True
            self.send_json(result, status=200)
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def handle_account_save(self):
        try:
            payload = self.read_body_json()
            platform = payload.get("platform") or ""
            account = payload.get("account") or {}
            save_platform_account(platform, account)
            self.send_json({
                "ok": True,
                "message": "账号授权信息已加密保存",
                "accounts": build_saved_account_statuses(),
                "site_sessions": build_saved_site_session_statuses(),
            })
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def handle_account_clear(self):
        try:
            payload = self.read_body_json()
            target = account_clear_target(payload)
        except ValueError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=400)
            return
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)
            return
        try:
            if target["kind"] == "site":
                with SITE_AUTHORIZATION_LOCK:
                    clear_result = clear_site_authorization(target["url"])
                    site_sessions = build_saved_site_session_statuses()
                    message = "网站辅助登录会话已清除"
            else:
                clear_result = clear_platform_authorization(target["platform"])
                site_sessions = build_saved_site_session_statuses()
                message = "账号授权、辅助登录会话、浏览器配置和关联诊断已清除"
            self.send_json({
                "ok": True,
                "message": message,
                "clear_result": clear_result,
                "accounts": build_saved_account_statuses(),
                "site_sessions": site_sessions,
            })
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def handle_browser_login_start(self):
        try:
            payload = self.read_body_json()
            target = browser_login_target(payload, resolve_site_dns=True)
        except ValueError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=400)
            return
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)
            return
        try:
            if target["kind"] == "site":
                with SITE_AUTHORIZATION_LOCK:
                    status = BROWSER_SESSION_MANAGER.start_site_login(
                        target["url"],
                        use_system_proxy=target["use_system_proxy"],
                    )
                    site_sessions = build_saved_site_session_statuses()
            else:
                status = BROWSER_SESSION_MANAGER.start_login(target["platform"])
                site_sessions = build_saved_site_session_statuses()
            self.send_json({
                "ok": True,
                "message": "辅助登录浏览器已打开，请在窗口中完成网页登录",
                "session": status,
                "site_sessions": site_sessions,
            })
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def handle_browser_login_save(self):
        try:
            payload = self.read_body_json()
            target = browser_login_target(payload, resolve_site_dns=False)
        except ValueError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=400)
            return
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)
            return
        try:
            if target["kind"] == "site":
                with SITE_AUTHORIZATION_LOCK:
                    result = BROWSER_SESSION_MANAGER.save_site_session(target["domain"])
                    save_site_browser_session(target["url"], result)
                    saved = {
                        "domain": target["domain"],
                        "cookie_count": result.get("cookie_count", 0),
                        "origin_count": result.get("origin_count", 0),
                        "has_local_storage": result.get("has_local_storage", False),
                    }
                    site_sessions = build_saved_site_session_statuses()
            else:
                platform = target["platform"]
                result = BROWSER_SESSION_MANAGER.save_session(platform)
                save_platform_browser_session(platform, result)
                test_result = {
                    "status": "login_only" if result.get("login_confirmed") is True else "partial",
                    "reachable": True,
                    "passed": False,
                    "read_passed": False,
                    "login_passed": result.get("login_confirmed") is True,
                    "login_confirmed": result.get("login_confirmed"),
                    "parsed_count": 0,
                    "error": "",
                    "evidence": result.get("evidence", ""),
                    "message": "浏览器会话已保存",
                }
                save_account_test_result(platform, test_result)
                saved = {
                    "platform": platform,
                    "cookie_count": result.get("cookie_count", 0),
                    "origin_count": result.get("origin_count", 0),
                    "has_local_storage": result.get("has_local_storage", False),
                    "login_confirmed": result.get("login_confirmed"),
                    "evidence": result.get("evidence", ""),
                }
                site_sessions = build_saved_site_session_statuses()
            self.send_json({
                "ok": True,
                "message": "浏览器会话已加密保存",
                "saved": saved,
                "accounts": build_saved_account_statuses(),
                "site_sessions": site_sessions,
            })
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def handle_browser_login_close(self):
        try:
            payload = self.read_body_json()
            target = browser_login_target(payload, resolve_site_dns=False)
        except ValueError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=400)
            return
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)
            return
        try:
            if target["kind"] == "site":
                with SITE_AUTHORIZATION_LOCK:
                    result = BROWSER_SESSION_MANAGER.close_site_session(target["domain"])
                    site_sessions = build_saved_site_session_statuses()
            else:
                result = BROWSER_SESSION_MANAGER.close_session(target["platform"])
                site_sessions = build_saved_site_session_statuses()
            self.send_json({
                "ok": True,
                "message": result.get("message", "辅助登录浏览器已关闭"),
                "session": result,
                "accounts": build_saved_account_statuses(),
                "site_sessions": site_sessions,
            })
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def handle_review_save(self):
        try:
            payload = self.read_body_json()
            data = read_json(DATA_FILE, [])
            decisions = payload.get("reviews")
            kept_indexes = payload.get("kept_indexes")
            edited_records = payload.get("records")
            review_summary = None
            if decisions is not None:
                identity = self.current_identity(touch=False) or {}
                reviewed, review_summary = build_reviewed_records(
                    data,
                    decisions,
                    reviewer=str(identity.get("username") or ""),
                )
                original_total = len(data)
            elif edited_records is not None:
                reviewed = [record for record in edited_records if isinstance(record, dict)]
                original_total = len(data)
            elif kept_indexes is not None:
                index_set = {int(index) for index in kept_indexes}
                reviewed = [record for idx, record in enumerate(data) if idx in index_set]
                original_total = len(data)
            else:
                raise ValueError("没有收到审核后的数据")

            write_json_atomic(DATA_FILE, reviewed)

            meta = read_json(META_FILE, {})
            meta["review"] = review_summary or {
                "reviewed_at": datetime.now().isoformat(),
                "original_total": original_total,
                "kept_total": len(reviewed),
                "removed_total": max(original_total - len(reviewed), 0),
            }
            meta["review"]["operator_note"] = str(payload.get("note") or "")[:500]
            write_json_atomic(META_FILE, meta)
            update_current_history_archive()
            self.send_json({"ok": True, "message": "审核结果已保存", "latest": self.build_latest()})
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def handle_report_preview(self):
        try:
            payload = self.read_body_json()
            template_id = payload.get("template_id") or "event_report"
            region = str(payload.get("region") or "").strip() or None
            time_range = payload.get("time_range") or None
            if not DATA_FILE.exists():
                raise FileNotFoundError("还没有采集数据，请先采集或准备 data/latest_news.json")
            current_data = read_json(DATA_FILE, [])
            current_meta = read_json(META_FILE, {})
            if not review_is_complete(current_data, current_meta):
                raise ValueError("当前数据尚未完成分类与情感人工审核，请先到“数据审核”保存审核结果")
            report_data, report_scope = filter_report_records(
                current_data,
                payload.get("report_filter"),
            )
            scoped_meta = {**current_meta, "report_scope": report_scope}
            from src.orchestrator import build_report_preview

            preview = build_report_preview(
                input_json=str(DATA_FILE),
                template_id=template_id,
                region=region,
                time_range=time_range,
                raw_data_override=report_data,
                meta_override=scoped_meta,
            )
            preview["scope"] = report_scope
            ai_status = deepseek_configuration_status()
            disclosure = build_ai_report_disclosure(
                report_data,
                preview,
                configured=ai_status["configured"],
                model=ai_status["model"],
                input_budget_tokens=ai_status.get("input_budget_tokens", 128_000),
            )
            disclosure["confirmation_id"] = (
                AI_CONFIRMATION_STORE.issue(
                    disclosure["scope_token"],
                    self.cookie_value(SYSTEM_SESSION_COOKIE),
                )
                if disclosure["can_generate"]
                else ""
            )
            disclosure["configuration_error"] = ai_status.get("configuration_error", "")
            preview["ai_assistance"] = disclosure
            self.send_json({
                "ok": True,
                "message": f"报告预览已生成，使用 {report_scope['matched_total']}/{report_scope['original_total']} 条数据",
                "preview": preview,
            })
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def handle_ai_report_draft(self):
        try:
            payload = self.read_body_json(max_bytes=32 * 1024)
            if payload.get("confirmed_external_send") is not True:
                raise ValueError("请先按甲方内部规则确认本次发送范围，再生成 AI 分析草稿")
            issued_scope_token = AI_CONFIRMATION_STORE.consume_once(
                str(payload.get("confirmation_id") or "").strip(),
                self.cookie_value(SYSTEM_SESSION_COOKIE),
            )
            template_id = str(payload.get("template_id") or "event_report").strip()
            if not DATA_FILE.exists():
                raise FileNotFoundError("还没有采集数据，请先完成采集和人工审核")

            current_data = read_json(DATA_FILE, [])
            current_meta = read_json(META_FILE, {})
            if not review_is_complete(current_data, current_meta):
                raise ValueError("当前数据尚未完成人工审核，不能发送给第三方 AI")
            report_data, report_scope = filter_report_records(
                current_data,
                payload.get("report_filter"),
            )
            scoped_meta = {**current_meta, "report_scope": report_scope}
            from src.orchestrator import build_report_preview

            preview = build_report_preview(
                input_json=str(DATA_FILE),
                template_id=template_id,
                region=str(payload.get("region") or "").strip() or None,
                time_range=payload.get("time_range") or None,
                raw_data_override=report_data,
                meta_override=scoped_meta,
            )
            ai_status = deepseek_configuration_status()
            current_disclosure = build_ai_report_disclosure(
                report_data,
                preview,
                configured=ai_status["configured"],
                model=ai_status["model"],
                input_budget_tokens=ai_status.get("input_budget_tokens", 128_000),
            )
            confirmed_scope_token = str(
                payload.get("confirmed_scope_token") or ""
            ).strip()
            if (
                confirmed_scope_token != issued_scope_token
                or confirmed_scope_token != current_disclosure["scope_token"]
            ):
                raise ValueError("本次拟发送的数据或模型范围已变化，请重新生成预览并确认")
            draft = DeepSeekReportClient().generate(
                report_data,
                preview,
                template_id=template_id,
            )
            draft["report_export_scope_token"] = build_ai_report_export_scope_token(
                report_data,
                scoped_meta,
                template_id,
            )
            self.send_json({
                "ok": True,
                "message": (
                    "DeepSeek 分析草稿已生成；尚未采用到报告，"
                    "请人工核对并明确采用"
                ),
                "draft": draft,
            })
        except FileNotFoundError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=404)
        except DeepSeekReportError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=502)
        except AiConfirmationError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=409)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=400)
        except Exception:
            self.send_json(
                {"ok": False, "message": "AI 分析草稿生成失败，规则报告仍保留"},
                status=500,
            )

    def handle_summary(self):
        try:
            payload = self.read_body_json(max_bytes=16 * 1024)
            if not DATA_FILE.exists():
                raise FileNotFoundError("还没有采集数据，请先完成采集")
            current_data = read_json(DATA_FILE, [])
            current_meta = read_json(META_FILE, {})
            summary_data, scope = select_summary_records(current_data, payload)
            summary = build_evidence_summary(
                summary_data,
                current_meta,
                scope_type=scope["type"],
                scope_label=scope["label"],
            )
            summary["scope"].update(scope)
            self.send_json({
                "ok": True,
                "message": f"摘要已生成，使用 {scope['matched_total']} 条线索",
                "summary": summary,
            })
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def handle_report(self):
        try:
            payload = self.read_body_json(max_bytes=8 * 1024 * 1024)
            template_id = payload.get("template_id") or "event_report"
            region = str(payload.get("region") or "").strip() or None
            time_range = payload.get("time_range") or None
            section_overrides = payload.get("section_overrides") or {}
            if not isinstance(section_overrides, dict):
                raise ValueError("报告修改内容格式无效")
            if not DATA_FILE.exists():
                raise FileNotFoundError("还没有采集数据，请先采集或准备 data/latest_news.json")
            task_id = update_current_history_archive()
            if not task_id:
                raise ValueError("当前任务无法建立历史归档，请先重新采集")

            current_data = read_json(DATA_FILE, [])
            current_meta = read_json(META_FILE, {})
            if not review_is_complete(current_data, current_meta):
                raise ValueError("当前数据尚未完成分类与情感人工审核，请先到“数据审核”保存审核结果")
            report_data, report_scope = filter_report_records(
                current_data,
                payload.get("report_filter"),
            )
            scoped_meta = {**current_meta, "report_scope": report_scope}
            validate_ai_report_export_scope(
                report_data,
                scoped_meta,
                template_id,
                payload.get("ai_report_scope_token"),
            )

            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            template = TemplateManager(str(ROOT / "config" / "templates")).load_template(template_id)
            filename = generate_filename(
                region=region,
                time_range=time_range,
                template_name=template.name,
                is_same_region_time=False,
            )
            output_path = Path(ensure_unique_path(str(OUTPUT_DIR), filename))
            from src.orchestrator import generate_report

            generated = generate_report(
                input_json=str(DATA_FILE),
                template_id=template_id,
                output_docx=str(output_path),
                region=region,
                time_range=time_range,
                section_overrides=section_overrides,
                raw_data_override=report_data,
                meta_override=scoped_meta,
            )
            generated_path = Path(generated)
            archived_report = HISTORY_ARCHIVE_STORE.archive_report(
                task_id,
                generated_path,
                metadata={
                    "template_id": template_id,
                    "region": region or "",
                    "time_range": time_range or "",
                    "scope": report_scope,
                    "section_names": sorted(str(key) for key in section_overrides),
                },
            )
            archived_path = (ROOT / archived_report["archive_path"]).resolve()
            try:
                if generated_path.resolve() != archived_path and generated_path.resolve().is_relative_to(OUTPUT_DIR.resolve()):
                    generated_path.unlink(missing_ok=True)
            except OSError:
                pass
            generated_relative_path = relative_to_root(archived_path)
            update_current_history_archive()
            self.send_json({
                "ok": True,
                "message": f"报告生成完成，使用 {report_scope['matched_total']}/{report_scope['original_total']} 条数据",
                "output_path": generated_relative_path,
                "download_url": f"/download?path={quote(generated_relative_path, safe='/')}",
                "history_catalog": build_history_catalog(),
            })
        except AiReportExportScopeError as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=409)
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)


class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    """避免 Windows 允许两个进程同时绑定同一端口，导致旧代码随机响应。"""

    allow_reuse_address = False

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_EXCLUSIVEADDRUSE,
                1,
            )
        super().server_bind()


def create_server(host: str, port: int):
    for candidate in range(port, port + 20):
        try:
            return ExclusiveThreadingHTTPServer((host, candidate), WebUIHandler), candidate
        except OSError:
            continue
    raise OSError(f"无法在 {host}:{port}-{port + 19} 启动服务，请检查端口占用")


def is_loopback_host(host: str) -> bool:
    if str(host or "").strip().casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(str(host).strip()).is_loopback
    except ValueError:
        return False


def main():
    parser = argparse.ArgumentParser(description="AI+舆情检测系统 - 浏览器界面")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="只启动服务，不自动打开浏览器")
    args = parser.parse_args()

    if not is_loopback_host(args.host):
        raise SystemExit("为避免账号密码经明文 HTTP 传输，当前版本只允许绑定 localhost/回环地址")

    os.chdir(ROOT)
    try:
        migrated_task_id = ensure_current_history_archive()
        if migrated_task_id:
            print(f"当前任务历史归档已就绪: {migrated_task_id}")
    except Exception as exc:
        print(f"历史归档初始化失败，现有数据未删除: {exc}")
    server, port = create_server(args.host, args.port)
    diagnostic_cleanup_stop = threading.Event()

    def cleanup_diagnostics():
        while not diagnostic_cleanup_stop.wait(15 * 60):
            DIAGNOSTIC_STORE.clean_expired()

    DIAGNOSTIC_STORE.clean_expired()
    monitor_manager = get_monitor_manager()
    monitor_manager.start()
    diagnostic_cleanup_thread = threading.Thread(
        target=cleanup_diagnostics,
        name="diagnostic-retention-cleaner",
        daemon=True,
    )
    diagnostic_cleanup_thread.start()
    url = f"http://{args.host}:{port}"
    print(f"AI+舆情检测系统 Web UI 已启动: {url}")
    print("按 Ctrl+C 停止服务")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        diagnostic_cleanup_stop.set()
        monitor_manager.shutdown()
        server.server_close()
        BROWSER_SESSION_MANAGER.shutdown()


if __name__ == "__main__":
    main()

