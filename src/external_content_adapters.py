#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""隔离运行的正文与帖子详情增强器。"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Sequence


@dataclass(frozen=True)
class BridgeCommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class EnrichmentOutcome:
    adapter_name: str
    available: bool
    attempted: bool = False
    data: Dict = field(default_factory=dict)
    error: str = ""


class StdinJsonBridgeRunner:
    """通过 stdin 传入 JSON，避免 Cookie 等字段出现在进程参数中。"""

    def run(self, command: Sequence[str], payload: Dict, cwd: Path, timeout: int) -> BridgeCommandResult:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            env=env,
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            creationflags=creationflags,
            check=False,
        )
        return BridgeCommandResult(completed.returncode, completed.stdout, completed.stderr)


class IsolatedReadOnlyAdapter:
    adapter_name = ""
    action = ""

    def __init__(
        self,
        repo_dir: Path,
        bridge_script: Optional[Path] = None,
        runner: Optional[StdinJsonBridgeRunner] = None,
    ):
        self.repo_dir = Path(repo_dir)
        self.bridge_script = Path(bridge_script) if bridge_script else Path(__file__).with_name("external_readonly_bridge.py")
        self.runner = runner or StdinJsonBridgeRunner()

    @property
    def python_path(self) -> Path:
        if os.name == "nt":
            return self.repo_dir / ".venv" / "Scripts" / "python.exe"
        return self.repo_dir / ".venv" / "bin" / "python"

    def is_available(self) -> bool:
        return self.python_path.is_file() and self.bridge_script.is_file()

    def execute(self, payload: Dict, timeout: int) -> EnrichmentOutcome:
        outcome = EnrichmentOutcome(adapter_name=self.adapter_name, available=self.is_available())
        if not outcome.available:
            outcome.error = f"{self.adapter_name} runtime not found"
            return outcome
        outcome.attempted = True
        command = [str(self.python_path), str(self.bridge_script), self.action]
        try:
            result = self.runner.run(command, payload=payload, cwd=self.repo_dir, timeout=timeout)
        except subprocess.TimeoutExpired:
            outcome.error = f"{self.adapter_name} timed out after {timeout}s"
            return outcome
        except Exception as exc:
            outcome.error = f"{self.adapter_name} failed to start: {exc}"
            return outcome

        response = _decode_bridge_response(result.stdout)
        if not response:
            detail = _compact_error(result.stderr or result.stdout)
            outcome.error = f"{self.adapter_name} returned invalid response: {detail}"
            return outcome
        if result.returncode != 0 or response.get("ok") is not True:
            detail = response.get("error") or _compact_error(result.stderr)
            outcome.error = f"{self.adapter_name}: {detail or 'unknown bridge error'}"
            return outcome
        data = response.get("data")
        if not isinstance(data, dict):
            outcome.error = f"{self.adapter_name} returned non-object data"
            return outcome
        outcome.data = data
        return outcome


class Newspaper4kArticleAdapter(IsolatedReadOnlyAdapter):
    adapter_name = "newspaper4k"
    action = "newspaper_extract"

    def extract(self, html: str, url: str, language: str = "zh", timeout: int = 20) -> EnrichmentOutcome:
        return self.execute({"html": html, "url": url, "language": language}, timeout=timeout)


class AiotiebaThreadAdapter(IsolatedReadOnlyAdapter):
    adapter_name = "aiotieba"
    action = "tieba_thread"

    def fetch(
        self,
        tid: int,
        bduss: str = "",
        stoken: str = "",
        max_posts: int = 20,
        max_comments: int = 4,
        use_system_proxy: bool = False,
        timeout: int = 30,
    ) -> EnrichmentOutcome:
        return self.execute({
            "tid": int(tid),
            "bduss": bduss,
            "stoken": stoken,
            "max_posts": max_posts,
            "max_comments": max_comments,
            "include_comments": max_comments > 0,
            "use_system_proxy": use_system_proxy,
        }, timeout=timeout)


class ExternalContentAdapters:
    def __init__(self, newspaper: Newspaper4kArticleAdapter, tieba: AiotiebaThreadAdapter):
        self.newspaper = newspaper
        self.tieba = tieba

    def status(self):
        return [
            {"adapter_name": self.newspaper.adapter_name, "available": self.newspaper.is_available()},
            {"adapter_name": self.tieba.adapter_name, "available": self.tieba.is_available()},
        ]


def create_default_external_content_adapters(candidates_root: Optional[Path] = None) -> ExternalContentAdapters:
    root = Path(candidates_root) if candidates_root else Path(__file__).resolve().parents[1] / "opensource_candidates"
    bridge = Path(__file__).with_name("external_readonly_bridge.py")
    return ExternalContentAdapters(
        newspaper=Newspaper4kArticleAdapter(root / "newspaper4k", bridge_script=bridge),
        tieba=AiotiebaThreadAdapter(root / "aiotieba", bridge_script=bridge),
    )


def _decode_bridge_response(output: str) -> Dict:
    text = (output or "").lstrip("\ufeff\r\n ")
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                value, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and "ok" in value:
                return value
    return {}


def _compact_error(value: str, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[-limit:] if text else ""
