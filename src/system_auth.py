"""Local system-account authentication shared by the Web UI and Tk GUI."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional


SYSTEM_ROLE = "民警用户"
PASSWORD_ALGORITHM = "pbkdf2_sha256"
RECOVERY_ALGORITHM = "pbkdf2_sha256"
DEFAULT_PBKDF2_ITERATIONS = 310_000
DEFAULT_IDLE_TIMEOUT_SECONDS = 30 * 60
DEFAULT_ABSOLUTE_TIMEOUT_SECONDS = 8 * 60 * 60


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_username(username: str) -> tuple[str, str]:
    display = unicodedata.normalize("NFKC", str(username or "")).strip()
    if not 2 <= len(display) <= 64:
        raise ValueError("账号长度必须为 2—64 个字符")
    if any(unicodedata.category(char).startswith("C") for char in display):
        raise ValueError("账号不能包含控制字符")
    if not re.fullmatch(r"[\w.@\-\u4e00-\u9fff]+", display, re.UNICODE):
        raise ValueError("账号只能包含中文、字母、数字、点、下划线、@ 或连字符")
    return display, display.casefold()


def validate_password(password: str, username: str = "") -> None:
    value = str(password or "")
    if not 8 <= len(value) <= 1024:
        raise ValueError("密码长度必须为 8—1024 个字符")
    if username and value.casefold() == username.casefold():
        raise ValueError("密码不能与账号相同")


def _derive_password_hash(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        int(iterations),
        dklen=32,
    )


def generate_recovery_code() -> str:
    """Return a printable 120-bit recovery code that is only shown to the user."""

    compact = base64.b32encode(secrets.token_bytes(15)).decode("ascii").rstrip("=")
    return "-".join(compact[index:index + 4] for index in range(0, len(compact), 4))


def normalize_recovery_code(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).upper()
    compact = re.sub(r"[\s-]+", "", normalized)
    if not re.fullmatch(r"[A-Z2-7]{24}", compact):
        raise ValueError("恢复码格式无效")
    return compact


def _build_secret_metadata(value: str, iterations: int, *, algorithm: str) -> dict:
    salt = secrets.token_bytes(16)
    digest = _derive_password_hash(value, salt, iterations)
    return {
        "algorithm": algorithm,
        "iterations": int(iterations),
        "salt": base64.b64encode(salt).decode("ascii"),
        "hash": base64.b64encode(digest).decode("ascii"),
    }


def _verify_secret_metadata(value: str, metadata: dict, *, algorithm: str, fallback_iterations: int) -> bool:
    try:
        salt = base64.b64decode(metadata.get("salt") or "", validate=True)
        expected = base64.b64decode(metadata.get("hash") or "", validate=True)
        iterations = int(metadata.get("iterations") or fallback_iterations)
        valid_meta = (
            metadata.get("algorithm") == algorithm
            and len(salt) >= 16
            and len(expected) == 32
            and iterations >= 100_000
        )
    except (ValueError, TypeError):
        valid_meta = False
        salt = b"\0" * 16
        expected = b"\0" * 32
        iterations = fallback_iterations
    actual = _derive_password_hash(str(value or ""), salt, iterations)
    return bool(valid_meta and hmac.compare_digest(actual, expected))


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    username: str = ""
    role: str = SYSTEM_ROLE
    reason: str = ""


class SystemAccountStore:
    """Password-hash store for the single local account allowed on a computer."""

    def __init__(self, path: Path | str, iterations: int = DEFAULT_PBKDF2_ITERATIONS):
        self.path = Path(path)
        self.iterations = int(iterations)
        self._lock = threading.RLock()

    def _empty_store(self) -> dict:
        return {"version": 2, "role": SYSTEM_ROLE, "users": {}}

    def _read(self) -> dict:
        if not self.path.exists():
            return self._empty_store()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"系统账号库无法读取: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("users", {}), dict):
            raise RuntimeError("系统账号库格式无效")
        payload.setdefault("version", 1)
        payload["role"] = SYSTEM_ROLE
        payload.setdefault("users", {})
        return payload

    def _write(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload["version"] = 2
        payload["role"] = SYSTEM_ROLE
        payload["updated_at"] = _utc_now_iso()
        temp_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(self.path.parent),
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
                temp_name = handle.name
            try:
                os.chmod(temp_name, 0o600)
            except OSError:
                pass
            os.replace(temp_name, self.path)
            temp_name = ""
        finally:
            if temp_name:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass

    @staticmethod
    def _public_user(entry: dict) -> dict:
        return {
            "username": str(entry.get("username") or ""),
            "role": SYSTEM_ROLE,
            "enabled": bool(entry.get("enabled", False)),
            "recovery_configured": bool((entry.get("recovery") or {}).get("hash")),
            "created_at": str(entry.get("created_at") or ""),
            "updated_at": str(entry.get("updated_at") or ""),
        }

    def create_user(
        self,
        username: str,
        password: str,
        *,
        enabled: bool = True,
        recovery_code: str = "",
    ) -> dict:
        display, key = normalize_username(username)
        validate_password(password, display)
        normalized_recovery = normalize_recovery_code(recovery_code) if recovery_code else ""
        now = _utc_now_iso()
        with self._lock:
            payload = self._read()
            if payload["users"]:
                raise ValueError("本机已创建系统账号，每台电脑只能使用一个账号")
            entry = {
                "username": display,
                "role": SYSTEM_ROLE,
                "enabled": bool(enabled),
                "password": _build_secret_metadata(
                    password,
                    self.iterations,
                    algorithm=PASSWORD_ALGORITHM,
                ),
                "created_at": now,
                "updated_at": now,
            }
            if normalized_recovery:
                entry["recovery"] = _build_secret_metadata(
                    normalized_recovery,
                    self.iterations,
                    algorithm=RECOVERY_ALGORITHM,
                )
            payload["users"][key] = entry
            self._write(payload)
            return self._public_user(entry)

    def list_users(self) -> list[dict]:
        with self._lock:
            payload = self._read()
            users = [self._public_user(entry) for entry in payload["users"].values()]
        return sorted(users, key=lambda item: item["username"].casefold())

    def has_users(self) -> bool:
        with self._lock:
            return bool(self._read()["users"])

    def has_enabled_users(self) -> bool:
        with self._lock:
            return any(bool(entry.get("enabled")) for entry in self._read()["users"].values())

    def single_user(self) -> Optional[dict]:
        with self._lock:
            users = list(self._read()["users"].values())
        if not users:
            return None
        enabled = [entry for entry in users if bool(entry.get("enabled"))]
        entry = enabled[0] if enabled else users[0]
        return self._public_user(entry)

    def is_enabled(self, username: str) -> bool:
        try:
            _, key = normalize_username(username)
        except ValueError:
            return False
        with self._lock:
            entry = self._read()["users"].get(key) or {}
            return bool(entry.get("enabled"))

    def authenticate(self, username: str, password: str) -> AuthResult:
        try:
            _, key = normalize_username(username)
        except ValueError:
            key = ""
        with self._lock:
            entry = self._read()["users"].get(key) if key else None
        password_ok = _verify_secret_metadata(
            str(password or ""),
            (entry or {}).get("password") or {},
            algorithm=PASSWORD_ALGORITHM,
            fallback_iterations=self.iterations,
        )
        if not entry or not password_ok:
            return AuthResult(False, reason="invalid_credentials")
        if not entry.get("enabled"):
            return AuthResult(False, reason="disabled")
        return AuthResult(True, username=str(entry.get("username") or ""))

    def set_enabled(self, username: str, enabled: bool) -> dict:
        _, key = normalize_username(username)
        with self._lock:
            payload = self._read()
            entry = payload["users"].get(key)
            if not entry:
                raise ValueError("系统账号不存在")
            other_enabled = any(
                other_key != key and bool(other.get("enabled"))
                for other_key, other in payload["users"].items()
            )
            if enabled and other_enabled:
                raise ValueError("单账号模式不能启用第二个账号")
            if not enabled and bool(entry.get("enabled")) and not other_enabled:
                raise ValueError("单账号模式不能停用唯一可用账号")
            entry["enabled"] = bool(enabled)
            entry["updated_at"] = _utc_now_iso()
            payload["users"][key] = entry
            self._write(payload)
            return self._public_user(entry)

    def change_password(self, username: str, new_password: str) -> dict:
        display, key = normalize_username(username)
        validate_password(new_password, display)
        with self._lock:
            payload = self._read()
            entry = payload["users"].get(key)
            if not entry:
                raise ValueError("系统账号不存在")
            entry["password"] = _build_secret_metadata(
                new_password,
                self.iterations,
                algorithm=PASSWORD_ALGORITHM,
            )
            entry["updated_at"] = _utc_now_iso()
            payload["users"][key] = entry
            self._write(payload)
            return self._public_user(entry)

    def set_recovery_code(self, username: str, recovery_code: str) -> dict:
        _, key = normalize_username(username)
        normalized_code = normalize_recovery_code(recovery_code)
        with self._lock:
            payload = self._read()
            entry = payload["users"].get(key)
            if not entry:
                raise ValueError("系统账号不存在")
            entry["recovery"] = _build_secret_metadata(
                normalized_code,
                self.iterations,
                algorithm=RECOVERY_ALGORITHM,
            )
            entry["updated_at"] = _utc_now_iso()
            payload["users"][key] = entry
            self._write(payload)
            return self._public_user(entry)

    def recover_password(
        self,
        username: str,
        recovery_code: str,
        new_password: str,
        new_recovery_code: str,
    ) -> AuthResult:
        try:
            display, key = normalize_username(username)
        except ValueError:
            display, key = "", ""
        try:
            normalized_code = normalize_recovery_code(recovery_code)
        except ValueError:
            normalized_code = "A" * 24
        replacement_code = normalize_recovery_code(new_recovery_code)
        with self._lock:
            payload = self._read()
            entry = payload["users"].get(key)
            recovery_ok = _verify_secret_metadata(
                normalized_code,
                (entry or {}).get("recovery") or {},
                algorithm=RECOVERY_ALGORITHM,
                fallback_iterations=self.iterations,
            )
            if not entry or not entry.get("enabled") or not recovery_ok:
                return AuthResult(False, reason="invalid_recovery")
            validate_password(new_password, display)
            entry["password"] = _build_secret_metadata(
                new_password,
                self.iterations,
                algorithm=PASSWORD_ALGORITHM,
            )
            entry["recovery"] = _build_secret_metadata(
                replacement_code,
                self.iterations,
                algorithm=RECOVERY_ALGORITHM,
            )
            entry["updated_at"] = _utc_now_iso()
            payload["users"][key] = entry
            self._write(payload)
        return AuthResult(True, username=display)


class SessionManager:
    """In-memory, revocable sessions with idle and absolute expiry."""

    def __init__(
        self,
        account_store: SystemAccountStore,
        *,
        idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS,
        absolute_timeout_seconds: int = DEFAULT_ABSOLUTE_TIMEOUT_SECONDS,
        clock: Callable[[], float] = time.time,
    ):
        self.account_store = account_store
        self.idle_timeout_seconds = int(idle_timeout_seconds)
        self.absolute_timeout_seconds = int(absolute_timeout_seconds)
        self.clock = clock
        self._sessions: dict[str, dict] = {}
        self._lock = threading.RLock()

    def create(self, username: str) -> tuple[str, dict]:
        if not self.account_store.is_enabled(username):
            raise ValueError("系统账号不可用")
        display, _ = normalize_username(username)
        now = float(self.clock())
        token = secrets.token_urlsafe(32)
        session = {
            "username": display,
            "role": SYSTEM_ROLE,
            "created_at": now,
            "last_seen": now,
        }
        with self._lock:
            self._sessions[token] = session
        return token, self._public_identity(session)

    @staticmethod
    def _public_identity(session: dict) -> dict:
        return {"username": session["username"], "role": SYSTEM_ROLE}

    def resolve(self, token: str, *, touch: bool = True) -> Optional[dict]:
        if not token:
            return None
        now = float(self.clock())
        with self._lock:
            session = self._sessions.get(token)
            if not session:
                return None
            idle_expired = now - float(session["last_seen"]) >= self.idle_timeout_seconds
            absolute_expired = now - float(session["created_at"]) >= self.absolute_timeout_seconds
            if idle_expired or absolute_expired or not self.account_store.is_enabled(session["username"]):
                self._sessions.pop(token, None)
                return None
            if touch:
                session["last_seen"] = now
            return self._public_identity(session)

    def revoke(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token or "", None)

    def revoke_user(self, username: str) -> None:
        try:
            display, _ = normalize_username(username)
        except ValueError:
            return
        with self._lock:
            for token, session in list(self._sessions.items()):
                if session.get("username", "").casefold() == display.casefold():
                    self._sessions.pop(token, None)


class LoginAttemptLimiter:
    """Small in-memory login throttle; responses remain deliberately generic."""

    def __init__(
        self,
        *,
        max_failures: int = 5,
        window_seconds: int = 5 * 60,
        lock_seconds: int = 5 * 60,
        clock: Callable[[], float] = time.time,
    ):
        self.max_failures = int(max_failures)
        self.window_seconds = int(window_seconds)
        self.lock_seconds = int(lock_seconds)
        self.clock = clock
        self._attempts: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _key(self, client: str, username: str) -> str:
        normalized = unicodedata.normalize("NFKC", str(username or "")).strip().casefold()
        return f"{client}|{normalized}"

    def is_blocked(self, client: str, username: str) -> bool:
        key = self._key(client, username)
        now = float(self.clock())
        with self._lock:
            entry = self._attempts.get(key)
            if not entry:
                return False
            blocked_until = float(entry.get("blocked_until", 0))
            if blocked_until > now:
                return True
            if blocked_until:
                self._attempts.pop(key, None)
            return False

    def record_failure(self, client: str, username: str) -> None:
        key = self._key(client, username)
        now = float(self.clock())
        with self._lock:
            entry = self._attempts.get(key) or {"first_at": now, "failures": 0, "blocked_until": 0}
            if now - float(entry["first_at"]) >= self.window_seconds:
                entry = {"first_at": now, "failures": 0, "blocked_until": 0}
            entry["failures"] = int(entry["failures"]) + 1
            if entry["failures"] >= self.max_failures:
                entry["blocked_until"] = now + self.lock_seconds
            self._attempts[key] = entry

    def clear(self, client: str, username: str) -> None:
        with self._lock:
            self._attempts.pop(self._key(client, username), None)
