#!/usr/bin/env python3
"""Create a non-destructive requirements elicitation session workspace."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path


TEMPLATES = {
    "00-context.md": "00-context.md",
    "01-stakeholders.md": "01-stakeholders.md",
    "02-session-plan.md": "02-session-plan.md",
    "03-meeting-notes.md": "03-meeting-notes.md",
    "04-evidence-ledger.csv": "04-evidence-ledger.csv",
    "05-product-brief.md": "05-product-brief.md",
    "06-requirements.md": "06-requirements.md",
    "07-open-questions.md": "07-open-questions.md",
    "08-client-confirmation.md": "08-client-confirmation.md",
}


def safe_slug(value: str) -> str:
    value = value.strip()
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value)
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-.")
    return value[:80] or "requirements-session"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="初始化需求访谈、多人会议和产品定义会话目录，不覆盖已有文件。"
    )
    parser.add_argument("--topic", required=True, help="会话主题，例如：甲方首次需求访谈")
    parser.add_argument(
        "--mode",
        default="综合需求获取",
        choices=["甲方访谈", "多人需求会议", "产品定义", "综合需求获取"],
        help="本次主要工作模式",
    )
    parser.add_argument(
        "--root",
        default="requirements",
        help="会话根目录，默认是当前项目的 requirements",
    )
    parser.add_argument("--date", default=date.today().isoformat(), help="会话日期 YYYY-MM-DD")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        session_date = date.fromisoformat(args.date).isoformat()
    except ValueError as exc:
        raise SystemExit(f"无效日期 {args.date!r}，应为 YYYY-MM-DD") from exc

    root = Path(args.root).expanduser()
    session_dir = root / f"{session_date}-{safe_slug(args.topic)}"
    session_dir.mkdir(parents=True, exist_ok=True)

    skill_dir = Path(__file__).resolve().parents[1]
    assets_dir = skill_dir / "assets"
    replacements = {
        "{{TITLE}}": args.topic,
        "{{DATE}}": session_date,
        "{{MODE}}": args.mode,
    }

    created: list[str] = []
    skipped: list[str] = []
    for template_name, output_name in TEMPLATES.items():
        source = assets_dir / template_name
        target = session_dir / output_name
        if target.exists():
            skipped.append(str(target))
            continue
        content = source.read_text(encoding="utf-8")
        for old, new in replacements.items():
            content = content.replace(old, new)
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        created.append(str(target))

    result = {
        "status": "ok",
        "session_dir": str(session_dir.resolve()),
        "created": created,
        "skipped_existing": skipped,
        "overwritten": [],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

