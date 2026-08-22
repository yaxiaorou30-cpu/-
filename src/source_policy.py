"""Executable source registry and RFC 9309-style robots.txt checks."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import secrets
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

try:
    import requests
except ImportError:  # pragma: no cover - crawler already reports the missing dependency.
    requests = None


SOURCE_POLICY_PRODUCT_TOKEN = "OpinionMonitorBot"
SOURCE_POLICY_USER_AGENT = (
    "OpinionMonitorBot/1.0 (authorized public-opinion research; local operator)"
)
PUBLIC_CRAWLER_ACCESS_MODE = "public_crawler"
AUTHORIZED_SESSION_ACCESS_MODE = "authorized_session"
EXTERNAL_ADAPTER_ACCESS_MODE = "external_adapter"
VALID_ACCESS_MODES = {
    PUBLIC_CRAWLER_ACCESS_MODE,
    AUTHORIZED_SESSION_ACCESS_MODE,
    EXTERNAL_ADAPTER_ACCESS_MODE,
}
MAX_ROBOTS_BYTES = 512 * 1024
DEFAULT_CACHE_TTL_SECONDS = 6 * 60 * 60
FAILURE_CACHE_TTL_SECONDS = 5 * 60


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    code: str
    reason: str
    source_rule_id: str
    source_name: str
    support_level: str
    access_type: str
    platform_rule_status: str
    external_adapter_allowed: bool
    access_mode: str = PUBLIC_CRAWLER_ACCESS_MODE
    robots_status: str = "not_checked"
    robots_checked_at: str = ""

    def public_dict(self) -> dict:
        return asdict(self)


@dataclass
class _RobotsRecord:
    status: str
    checked_at: str
    fetched_monotonic: float
    http_status: Optional[int] = None
    error: str = ""
    rules: Optional["_RobotsRules"] = None


class _RobotsRules:
    """Small bounded parser implementing the matching rules needed by RFC 9309."""

    def __init__(self, groups: list[dict]):
        self.groups = groups

    @classmethod
    def parse(cls, text: str) -> "_RobotsRules":
        groups: list[dict] = []
        agents: list[str] = []
        rules: list[tuple[bool, str]] = []
        seen_rule = False

        def finish_group():
            nonlocal agents, rules, seen_rule
            if agents:
                groups.append({"agents": tuple(agents), "rules": tuple(rules)})
            agents = []
            rules = []
            seen_rule = False

        for raw_line in str(text or "").splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            field, value = line.split(":", 1)
            field = field.strip().casefold()
            value = value.strip()
            if field == "user-agent":
                if seen_rule:
                    finish_group()
                agents.append(value.casefold())
            elif field in {"allow", "disallow"} and agents:
                seen_rule = True
                if value:
                    rules.append((field == "allow", value))
        finish_group()
        return cls(groups)

    def can_fetch(self, product_token: str, url: str) -> bool:
        token = str(product_token or "").casefold()
        exact_rules: list[tuple[bool, str]] = []
        wildcard_rules: list[tuple[bool, str]] = []
        for group in self.groups:
            agents = group["agents"]
            if token in agents:
                exact_rules.extend(group["rules"])
            elif "*" in agents:
                wildcard_rules.extend(group["rules"])
        applicable = exact_rules if exact_rules else wildcard_rules
        if not applicable:
            return True

        parsed = urlparse(url)
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        matched: list[tuple[int, bool]] = []
        for allowed, pattern in applicable:
            if _robots_pattern_matches(pattern, target):
                specificity = len(pattern.replace("*", "").rstrip("$").encode("utf-8"))
                matched.append((specificity, allowed))
        if not matched:
            return True
        longest = max(item[0] for item in matched)
        return any(allowed for specificity, allowed in matched if specificity == longest)


def _robots_pattern_matches(pattern: str, target: str) -> bool:
    exact_end = pattern.endswith("$")
    core = pattern[:-1] if exact_end else pattern
    expression = re.escape(core).replace(r"\*", ".*")
    if exact_end:
        expression = f"^{expression}$"
    else:
        expression = f"^{expression}"
    try:
        return re.search(expression, target) is not None
    except re.error:
        return False


class SourceAccessPolicy:
    """Combines local source rules with cached robots.txt decisions."""

    def __init__(
        self,
        registry_path: Path | str,
        *,
        audit_path: Path | str | None = None,
        use_system_proxy: bool = False,
        fetcher: Optional[Callable[..., object]] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.registry_path = Path(registry_path)
        self.audit_path = Path(audit_path) if audit_path else None
        self.clock = clock
        self.registry = self._load_registry()
        self.cache_ttl_seconds = min(
            int(self.registry.get("robots_cache_ttl_seconds") or DEFAULT_CACHE_TTL_SECONDS),
            24 * 60 * 60,
        )
        self._cache: dict[str, _RobotsRecord] = {}
        self._lock = threading.RLock()
        self._fetcher = fetcher
        self._session = None
        if self._fetcher is None and requests is not None:
            self._session = requests.Session()
            self._session.trust_env = bool(use_system_proxy)
            self._session.max_redirects = 5
            self._fetcher = self._session.get

    def _load_registry(self) -> dict:
        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"来源规则登记无法读取: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
            raise RuntimeError("来源规则登记格式无效")
        payload.setdefault("default_rule", {})
        return payload

    def check(
        self,
        url: str,
        channel: str = "",
        access_mode: str = PUBLIC_CRAWLER_ACCESS_MODE,
    ) -> AccessDecision:
        access_mode = str(access_mode or PUBLIC_CRAWLER_ACCESS_MODE).strip()
        if access_mode not in VALID_ACCESS_MODES:
            return self._decision(
                False,
                "invalid_access_mode",
                "来源访问模式无效",
                {},
                channel,
                access_mode=access_mode,
            )
        parsed = urlparse(str(url or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return self._decision(
                False,
                "invalid_url",
                "只允许检查 HTTP/HTTPS 来源",
                {},
                channel,
                access_mode=access_mode,
            )
        if parsed.username or parsed.password:
            return self._decision(
                False,
                "embedded_credentials",
                "来源 URL 不得包含账号凭据",
                {},
                channel,
                access_mode=access_mode,
            )
        if _is_local_or_private_literal(parsed.hostname):
            return self._decision(
                False,
                "private_network_target",
                "禁止自动访问本机或私有地址",
                {},
                channel,
                access_mode=access_mode,
            )

        rule = self._match_rule(parsed.hostname)
        if access_mode == AUTHORIZED_SESSION_ACCESS_MODE:
            enabled = bool(
                rule.get(
                    "authorized_session_enabled",
                    rule.get("automation_enabled", True),
                )
            )
            disabled_code = "authorized_session_disabled"
            disabled_reason = str(
                rule.get("authorized_session_reason")
                or rule.get("automation_reason")
                or "来源规则已停用授权会话访问"
            )
        elif access_mode == EXTERNAL_ADAPTER_ACCESS_MODE:
            enabled = bool(rule.get("external_adapter_allowed", False))
            disabled_code = "external_adapter_disabled"
            disabled_reason = str(
                rule.get("external_adapter_reason")
                or "来源规则未启用外部只读适配器"
            )
        else:
            enabled = bool(rule.get("automation_enabled", True))
            disabled_code = "automation_disabled"
            disabled_reason = str(
                rule.get("automation_reason")
                or "来源规则已停用公开自动访问"
            )
        if not enabled:
            return self._decision(
                False,
                disabled_code,
                disabled_reason,
                rule,
                channel,
                access_mode=access_mode,
            )

        path = parsed.path or "/"
        denied_prefixes = tuple(rule.get("denied_path_prefixes") or ())
        if any(path.startswith(prefix) for prefix in denied_prefixes):
            return self._decision(
                False,
                "local_path_denied",
                "来源登记明确禁止该路径",
                rule,
                channel,
                access_mode=access_mode,
            )
        allowed_paths = tuple(rule.get("allowed_paths") or ())
        allowed_prefixes = tuple(rule.get("allowed_path_prefixes") or ())
        if (allowed_paths or allowed_prefixes) and not (
            path in allowed_paths
            or any(path.startswith(prefix) for prefix in allowed_prefixes)
        ):
            return self._decision(
                False,
                "path_not_registered",
                "该路径不在来源登记的允许范围内",
                rule,
                channel,
                access_mode=access_mode,
            )

        if access_mode == AUTHORIZED_SESSION_ACCESS_MODE:
            robots_required = bool(
                rule.get(
                    "authorized_session_robots_required",
                    rule.get("robots_required", True),
                )
            )
        elif access_mode == EXTERNAL_ADAPTER_ACCESS_MODE:
            robots_required = bool(
                rule.get(
                    "external_adapter_robots_required",
                    rule.get("robots_required", True),
                )
            )
        else:
            robots_required = bool(rule.get("robots_required", True))

        if not robots_required:
            if access_mode == AUTHORIZED_SESSION_ACCESS_MODE:
                code = "authorized_session_allowed"
                reason = "来源登记允许使用操作者授权会话，公开爬虫 robots 不作为该模式的前置总开关"
            elif access_mode == EXTERNAL_ADAPTER_ACCESS_MODE:
                code = "external_adapter_allowed"
                reason = "来源登记允许使用隔离的只读平台适配器"
            else:
                code = "local_rule_allowed"
                reason = "来源登记允许且无需 robots 检查"
            decision = self._decision(
                True,
                code,
                reason,
                rule,
                channel,
                access_mode=access_mode,
            )
            self._write_audit(parsed, decision)
            return decision

        robots = self._robots_record(parsed)
        if robots.status == "unreachable":
            decision = self._decision(
                False,
                "robots_unreachable",
                "robots.txt 因网络或服务器错误不可达，自动访问已暂停",
                rule,
                channel,
                robots,
                access_mode=access_mode,
            )
        elif robots.status == "rate_limited":
            decision = self._decision(
                False,
                "robots_rate_limited",
                "robots.txt 返回限流状态，自动访问已暂停",
                rule,
                channel,
                robots,
                access_mode=access_mode,
            )
        elif robots.status == "available" and robots.rules and not robots.rules.can_fetch(
            SOURCE_POLICY_PRODUCT_TOKEN, url
        ):
            decision = self._decision(
                False,
                "robots_disallowed",
                "robots.txt 明确禁止当前自动客户端访问该路径",
                rule,
                channel,
                robots,
                access_mode=access_mode,
            )
        else:
            reason = (
                "robots.txt 允许当前路径"
                if robots.status == "available"
                else "robots.txt 不存在或返回普通 4xx，按 RFC 9309 可继续访问"
            )
            decision = self._decision(
                True,
                "robots_allowed",
                reason,
                rule,
                channel,
                robots,
                access_mode=access_mode,
            )
        self._write_audit(parsed, decision)
        return decision

    def _decision(
        self,
        allowed: bool,
        code: str,
        reason: str,
        rule: dict,
        channel: str,
        robots: Optional[_RobotsRecord] = None,
        access_mode: str = PUBLIC_CRAWLER_ACCESS_MODE,
    ) -> AccessDecision:
        return AccessDecision(
            allowed=allowed,
            code=code,
            reason=reason,
            source_rule_id=str(rule.get("id") or "SRC-UNREGISTERED"),
            source_name=str(rule.get("name") or channel or "未登记来源"),
            support_level=str(rule.get("support_level") or "S2"),
            access_type=str(rule.get("access_type") or "A0"),
            platform_rule_status=str(rule.get("platform_rule_status") or "待人工核对"),
            external_adapter_allowed=bool(rule.get("external_adapter_allowed", False)),
            access_mode=access_mode,
            robots_status=robots.status if robots else "not_checked",
            robots_checked_at=robots.checked_at if robots else "",
        )

    def _match_rule(self, hostname: str) -> dict:
        normalized = str(hostname or "").strip(".").casefold()
        matches: list[tuple[int, dict]] = []
        for source in self.registry.get("sources") or []:
            for domain in source.get("domains") or []:
                target = str(domain or "").strip(".").casefold()
                if normalized == target or normalized.endswith("." + target):
                    matches.append((len(target), source))
        if matches:
            matches.sort(key=lambda item: item[0], reverse=True)
            return dict(matches[0][1])
        default = dict(self.registry.get("default_rule") or {})
        default.setdefault("id", "SRC-UNREGISTERED")
        default.setdefault("name", f"未登记域名 {normalized}")
        return default

    def _robots_record(self, parsed) -> _RobotsRecord:
        origin = f"{parsed.scheme}://{parsed.netloc.casefold()}"
        now = float(self.clock())
        with self._lock:
            cached = self._cache.get(origin)
            if cached:
                ttl = (
                    FAILURE_CACHE_TTL_SECONDS
                    if cached.status in {"unreachable", "rate_limited"}
                    else self.cache_ttl_seconds
                )
                if now - cached.fetched_monotonic < ttl:
                    return cached

        checked_at = _utc_now_iso()
        if self._fetcher is None:
            record = _RobotsRecord(
                status="unreachable",
                checked_at=checked_at,
                fetched_monotonic=now,
                error="requests unavailable",
            )
        else:
            robots_url = f"{origin}/robots.txt"
            try:
                response = self._fetcher(
                    robots_url,
                    headers={
                        "User-Agent": SOURCE_POLICY_USER_AGENT,
                        "Accept": "text/plain,*/*;q=0.1",
                    },
                    timeout=8,
                    allow_redirects=True,
                )
                status = int(getattr(response, "status_code", 0) or 0)
                if 200 <= status < 300:
                    content = bytes(getattr(response, "content", b"") or b"")[:MAX_ROBOTS_BYTES]
                    text = content.decode("utf-8", errors="replace")
                    record = _RobotsRecord(
                        status="available",
                        checked_at=checked_at,
                        fetched_monotonic=now,
                        http_status=status,
                        rules=_RobotsRules.parse(text),
                    )
                elif status == 429:
                    record = _RobotsRecord(
                        status="rate_limited",
                        checked_at=checked_at,
                        fetched_monotonic=now,
                        http_status=status,
                    )
                elif 400 <= status < 500:
                    record = _RobotsRecord(
                        status="unavailable",
                        checked_at=checked_at,
                        fetched_monotonic=now,
                        http_status=status,
                    )
                else:
                    record = _RobotsRecord(
                        status="unreachable",
                        checked_at=checked_at,
                        fetched_monotonic=now,
                        http_status=status or None,
                        error=f"HTTP {status}" if status else "invalid response",
                    )
            except Exception as exc:
                record = _RobotsRecord(
                    status="unreachable",
                    checked_at=checked_at,
                    fetched_monotonic=now,
                    error=_safe_error(exc),
                )
        with self._lock:
            self._cache[origin] = record
        return record

    def _write_audit(self, parsed, decision: AccessDecision) -> None:
        if not self.audit_path:
            return
        origin = f"{parsed.scheme}://{parsed.netloc.casefold()}"
        path_category = _path_category(parsed.path)
        key = f"{origin}|{decision.source_rule_id}|{path_category}"
        with self._lock:
            payload = {"version": 1, "decisions": {}}
            if self.audit_path.exists():
                try:
                    loaded = json.loads(self.audit_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict) and isinstance(loaded.get("decisions"), dict):
                        payload = loaded
                except (OSError, json.JSONDecodeError):
                    pass
            payload["updated_at"] = _utc_now_iso()
            payload["decisions"][key] = {
                "origin": origin,
                "path_category": path_category,
                **decision.public_dict(),
            }
            self._atomic_write(payload)

    def _atomic_write(self, payload: dict) -> None:
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.audit_path.with_name(
                f".{self.audit_path.name}.{secrets.token_hex(6)}.tmp"
            )
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temp_path, self.audit_path)
        except OSError:
            try:
                if "temp_path" in locals():
                    temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _path_category(path: str) -> str:
    parts = [part for part in str(path or "/").split("/") if part]
    return "/" if not parts else f"/{parts[0]}/…"


def _is_local_or_private_literal(hostname: str) -> bool:
    normalized = str(hostname or "").strip("[]").casefold()
    if normalized in {"localhost", "localhost.localdomain"} or normalized.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return not address.is_global


def _safe_error(exc: Exception) -> str:
    text = re.sub(r"\s+", " ", str(exc or "")).strip()
    return text[:240] if text else type(exc).__name__
