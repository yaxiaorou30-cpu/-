"""Process-local, one-shot confirmations for charged AI requests."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from typing import Callable


class AiConfirmationError(ValueError):
    """The confirmation is unavailable without revealing why."""


class OneShotAiConfirmationStore:
    def __init__(
        self,
        *,
        ttl_seconds: int = 30 * 60,
        max_entries: int = 512,
        clock: Callable[[], float] = time.time,
    ):
        self.ttl_seconds = max(1, int(ttl_seconds))
        self.max_entries = max(1, int(max_entries))
        self.clock = clock
        self._entries: dict[str, dict] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()

    def issue(self, scope_token: str, session_token: str) -> str:
        scope = str(scope_token or "").strip()
        session = str(session_token or "").strip()
        if not scope or not session:
            raise AiConfirmationError("无法签发本次 AI 发送确认")
        confirmation_id = secrets.token_urlsafe(32)
        now = float(self.clock())
        entry = {
            "scope_token": scope,
            "session_digest": self._digest(session),
            "issued_at": now,
            "expires_at": now + self.ttl_seconds,
        }
        with self._lock:
            self._cleanup_locked(now)
            while len(self._entries) >= self.max_entries:
                oldest = min(
                    self._entries,
                    key=lambda key: float(self._entries[key]["issued_at"]),
                )
                self._entries.pop(oldest, None)
            self._entries[self._digest(confirmation_id)] = entry
        return confirmation_id

    def consume_once(self, confirmation_id: str, session_token: str) -> str:
        confirmation_digest = self._digest(str(confirmation_id or "").strip())
        session_digest = self._digest(str(session_token or "").strip())
        now = float(self.clock())
        with self._lock:
            entry = self._entries.get(confirmation_digest)
            if not entry:
                raise AiConfirmationError(self._generic_message())
            if float(entry["expires_at"]) <= now:
                self._entries.pop(confirmation_digest, None)
                raise AiConfirmationError(self._generic_message())
            if not hmac.compare_digest(entry["session_digest"], session_digest):
                raise AiConfirmationError(self._generic_message())
            consumed = self._entries.pop(confirmation_digest)
        return str(consumed["scope_token"])

    def _cleanup_locked(self, now: float) -> None:
        expired = [
            key
            for key, entry in self._entries.items()
            if float(entry["expires_at"]) <= now
        ]
        for key in expired:
            self._entries.pop(key, None)

    @staticmethod
    def _generic_message() -> str:
        return "本次确认已使用、已过期或不属于当前会话，请重新生成报告预览并再次确认"
