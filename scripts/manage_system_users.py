#!/usr/bin/env python3
"""Emergency maintenance for the single local account; prefer the Web UI."""

import argparse
import getpass
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.system_auth import SYSTEM_ROLE, SystemAccountStore, generate_recovery_code


def prompt_password(label: str = "密码") -> str:
    first = getpass.getpass(f"{label}: ")
    second = getpass.getpass(f"再次输入{label}: ")
    if first != second:
        raise ValueError("两次输入的密码不一致")
    return first


def main() -> int:
    parser = argparse.ArgumentParser(description="单机单账号应急维护（正常操作请使用网页）")
    parser.add_argument(
        "--store",
        default=str(PROJECT_ROOT / "data" / "system_users.secure.json"),
        help="账号库位置（默认使用项目 data 目录）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", help="仅在首次运行时创建本机唯一账号")
    create.add_argument("username")
    passwd = subparsers.add_parser("passwd", help="离线修改密码（请先关闭程序）")
    passwd.add_argument("username")
    enable = subparsers.add_parser("enable", help="启用账号")
    enable.add_argument("username")
    disable = subparsers.add_parser("disable", help="停用账号")
    disable.add_argument("username")
    subparsers.add_parser("list", help="列出账号状态，不显示密码哈希")
    args = parser.parse_args()

    store = SystemAccountStore(Path(args.store))
    try:
        if args.command == "create":
            recovery_code = generate_recovery_code()
            user = store.create_user(
                args.username,
                prompt_password(),
                recovery_code=recovery_code,
            )
            print(f"已创建账号：{user['username']}（角色：{SYSTEM_ROLE}）")
            print("恢复码只显示这一次，请立即离线保存：")
            print(recovery_code)
        elif args.command == "passwd":
            user = store.change_password(args.username, prompt_password("新密码"))
            print(f"已修改密码：{user['username']}")
        elif args.command == "enable":
            user = store.set_enabled(args.username, True)
            print(f"已启用账号：{user['username']}")
        elif args.command == "disable":
            user = store.set_enabled(args.username, False)
            print(f"已停用账号：{user['username']}")
        elif args.command == "list":
            users = store.list_users()
            if not users:
                print("尚未创建系统账号")
            for user in users:
                state = "启用" if user["enabled"] else "停用"
                print(f"{user['username']}\t{SYSTEM_ROLE}\t{state}")
        return 0
    except (ValueError, RuntimeError) as exc:
        print(f"操作失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
