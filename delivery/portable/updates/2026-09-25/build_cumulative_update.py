"""Build the reviewed Windows 11 update from committed application files only."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
BASE_ZIP = ROOT / "delivery/portable/正式交付-20260907/AI舆情检测系统-Windows11-交付版-20260907.zip"
# Historical hashes retained after the superseded hotfix archive was removed.
HOTFIX_FILE_SHA256 = {
    "src/deepseek_report.py": "9b99f597b1bf9fa3c1b2674f2accb89c1c7c41716faee4a8add18bf66f065c0e",
    "web/static/app.js": "022c7df881cc99aa8516c5678c96baf82c2a4ad65020eee410a61894a2d916d4",
}
OUTPUT_ZIP = HERE / "AI舆情检测系统-Windows11-累计更新-20260925.zip"
BASE_SHA256 = "d74f74fdc187a67439667466cf3ffbcab05c3e3f3773e5f217a7c4ea6be5253a"
PACKAGE_FILES = (
    "config/source_access_rules.json",
    "src/collection_target.py",
    "src/crawler.py",
    "src/deepseek_report.py",
    "src/monitoring.py",
    "src/source_policy.py",
    "web/index.html",
    "web/static/app.js",
    "web/static/styles.css",
    "web_app.py",
)


def git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True
    ).stdout


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def normalized(content: bytes) -> bytes:
    return content.replace(b"\r\n", b"\n")


def main() -> None:
    if OUTPUT_ZIP.exists():
        raise SystemExit(f"Refusing to overwrite existing update: {OUTPUT_ZIP}")
    if not BASE_ZIP.is_file():
        raise SystemExit("The original delivery archive is missing")
    if sha256_file(BASE_ZIP) != BASE_SHA256:
        raise SystemExit("The original delivery archive SHA256 does not match")

    commit = git("rev-parse", "HEAD").decode("ascii").strip()
    tracked = [
        path.decode("utf-8")
        for path in git("ls-files", "-z").split(b"\0")
        if path
    ]
    application = [
        path for path in tracked
        if path == "web_app.py" or path.startswith(("src/", "web/", "config/"))
    ]
    committed = {path: git("show", f"HEAD:{path}") for path in application}
    with ZipFile(BASE_ZIP) as original:
        original_names = set(original.namelist())
        prefix = "AI舆情检测系统/"
        changed = {
            path for path, content in committed.items()
            if prefix + path not in original_names
            or normalized(original.read(prefix + path)) != normalized(content)
        }
        old_hashes = {
            path: sha256(original.read(prefix + path))
            for path in PACKAGE_FILES
            if prefix + path in original_names
        }
    if changed != set(PACKAGE_FILES):
        raise SystemExit(
            f"Application difference is not the approved file list: "
            f"missing={sorted(changed - set(PACKAGE_FILES))}, "
            f"extra={sorted(set(PACKAGE_FILES) - changed)}"
        )

    payload = {path: committed[path] for path in PACKAGE_FILES}
    payload["更新说明.txt"] = (HERE / "更新说明.txt").read_bytes()
    manifest = {
        "source_commit": commit,
        "base_delivery_sha256": BASE_SHA256,
        "target": "Windows 11 2026-09-07 delivery, with or without the 2026-09-18 DeepSeek hotfix",
        "file_sha256": {path: sha256(payload[path]) for path in PACKAGE_FILES},
        "base_file_sha256": old_hashes,
        "hotfix_file_sha256": HOTFIX_FILE_SHA256,
    }
    payload["manifest.json"] = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")

    with ZipFile(OUTPUT_ZIP, "x", compression=ZIP_DEFLATED, compresslevel=6) as update:
        for path, content in payload.items():
            update.writestr(path, content)
    with ZipFile(OUTPUT_ZIP) as update:
        if set(update.namelist()) != set(payload) or update.testzip() is not None:
            raise SystemExit("Update archive failed entry or CRC verification")
        for path, content in payload.items():
            if update.read(path) != content:
                raise SystemExit(f"Update archive content mismatch: {path}")

    digest = sha256_file(OUTPUT_ZIP)
    (HERE / "SHA256SUMS.txt").write_text(
        f"{digest}  {OUTPUT_ZIP.name}\n", encoding="utf-8"
    )
    print(f"SOURCE_COMMIT={commit}")
    print(f"FILE_COUNT={len(PACKAGE_FILES)}")
    print(f"PACKAGE_SHA256={digest}")
    print(f"PACKAGE={OUTPUT_ZIP}")


if __name__ == "__main__":
    main()
