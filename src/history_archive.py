"""Local task history snapshots, recycle bin, encrypted backup, and safe restore."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shutil
import struct
import threading
import uuid
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Iterable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


ARCHIVE_VERSION = 1
BACKUP_VERSION = 1
BACKUP_MAGIC = b"AOMBACKUP1\n"
MAX_BACKUP_BYTES = 64 * 1024 * 1024
MAX_BACKUP_FILES = 10_000
MAX_BACKUP_FILE_BYTES = 64 * 1024 * 1024
_TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TRASH_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,160}$")
_FORBIDDEN_KEYS = {
    "account",
    "accounts",
    "username",
    "password",
    "cookie",
    "cookie_header",
    "browser_cookie",
    "browser_session",
    "authorization",
    "access_token",
    "refresh_token",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_json(path: Path, value) -> None:
    _atomic_write_bytes(path, _json_bytes(value))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_task_id(task_id: str) -> str:
    value = str(task_id or "").strip()
    if not _TASK_ID_PATTERN.fullmatch(value):
        raise ValueError("历史任务编号无效")
    return value


def _validate_trash_id(trash_id: str) -> str:
    value = str(trash_id or "").strip()
    if not _TRASH_ID_PATTERN.fullmatch(value):
        raise ValueError("回收站记录编号无效")
    return value


def _sanitize_tree(value):
    """Drop credential-shaped keys before history leaves the live task workspace."""
    if isinstance(value, dict):
        return {
            str(key): _sanitize_tree(item)
            for key, item in value.items()
            if str(key).casefold() not in _FORBIDDEN_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_tree(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_tree(item) for item in value]
    return value


def _contains_forbidden_key(value) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).casefold() in _FORBIDDEN_KEYS:
                return True
            if _contains_forbidden_key(item):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _safe_zip_name(name: str) -> PurePosixPath:
    value = str(name or "")
    if "\x00" in value or "\\" in value or ":" in value:
        raise ValueError("备份包含不安全的文件路径")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("备份包含不安全的文件路径")
    if path.parts[0] not in {"tasks", "task_history.json", "backup_manifest.json"}:
        raise ValueError("备份包含未允许的文件")
    if path.parts[0] == "tasks":
        if len(path.parts) < 3:
            raise ValueError("备份任务目录结构无效")
        _validate_task_id(path.parts[1])
        if len(path.parts) == 3 and path.parts[2] not in {"manifest.json", "records.json", "meta.json"}:
            raise ValueError("备份包含未允许的任务文件")
        if (
            len(path.parts) != 3
            and not (
                len(path.parts) == 4
                and path.parts[2] == "reports"
                and PurePosixPath(path.parts[3]).suffix.casefold() == ".docx"
            )
        ):
            raise ValueError("备份包含未允许的任务目录")
    elif len(path.parts) != 1:
        raise ValueError("备份文件路径无效")
    return path


def _directory_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _synchronized(method):
    def locked(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return locked


class HistoryArchiveStore:
    """Store one self-contained snapshot directory per collection task."""

    def __init__(self, project_root: Path | str):
        self.project_root = Path(project_root)
        self.root = self.project_root / "data" / "history_archive"
        self.tasks_root = self.root / "tasks"
        self.trash_root = self.root / "trash"
        self.backups_root = self.root / "backups"
        self.task_history_file = self.project_root / "data" / "task_history.json"
        self._lock = threading.RLock()

    @_synchronized
    def archive_task(
        self,
        task_id: str,
        *,
        history_entry: dict,
        records: list | None = None,
        meta: dict | None = None,
    ) -> dict:
        task_id = _validate_task_id(task_id)
        task_root = self.tasks_root / task_id
        task_root.mkdir(parents=True, exist_ok=True)
        existing = _read_json(task_root / "manifest.json", {})
        entry = _sanitize_tree(history_entry if isinstance(history_entry, dict) else {})
        safe_records = _sanitize_tree(records) if isinstance(records, list) else None
        safe_meta = _sanitize_tree(meta) if isinstance(meta, dict) else None

        if safe_records is not None:
            _atomic_write_json(task_root / "records.json", safe_records)
        if safe_meta is not None:
            _atomic_write_json(task_root / "meta.json", safe_meta)

        manifest = {
            "version": ARCHIVE_VERSION,
            "task_id": task_id,
            "status": str(entry.get("status") or existing.get("status") or ""),
            "created_at": str(entry.get("created_at") or existing.get("created_at") or ""),
            "completed_at": str(entry.get("completed_at") or existing.get("completed_at") or ""),
            "message": str(entry.get("message") or existing.get("message") or ""),
            "payload": entry.get("payload") if isinstance(entry.get("payload"), dict) else existing.get("payload", {}),
            "summary": entry.get("summary") if isinstance(entry.get("summary"), dict) else existing.get("summary", {}),
            "records_count": len(safe_records) if safe_records is not None else int(existing.get("records_count") or 0),
            "has_records": (task_root / "records.json").exists(),
            "has_meta": (task_root / "meta.json").exists(),
            "review": (safe_meta or {}).get("review") if safe_meta is not None else existing.get("review", {}),
            "reports": existing.get("reports") if isinstance(existing.get("reports"), list) else [],
            "archived_at": str(existing.get("archived_at") or _now()),
            "updated_at": _now(),
        }
        _atomic_write_json(task_root / "manifest.json", manifest)
        return manifest

    @_synchronized
    def archive_report(self, task_id: str, report_path: Path | str, metadata: dict | None = None) -> dict:
        task_id = _validate_task_id(task_id)
        source = Path(report_path)
        if not source.exists() or source.is_dir():
            raise FileNotFoundError("待归档报告不存在")
        task_root = self.tasks_root / task_id
        manifest_path = task_root / "manifest.json"
        manifest = _read_json(manifest_path, {})
        if not manifest:
            raise FileNotFoundError("报告对应的历史任务尚未归档")

        report_id = uuid.uuid4().hex[:12]
        safe_name = re.sub(r"[^0-9A-Za-z_.\-\u4e00-\u9fff]+", "_", source.name).strip("._")
        safe_name = safe_name or f"report-{report_id}.docx"
        target = task_root / "reports" / f"{report_id}-{safe_name}"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

        report = {
            "report_id": report_id,
            "filename": source.name,
            "archive_path": target.relative_to(self.project_root).as_posix(),
            "created_at": _now(),
            "size": target.stat().st_size,
            "sha256": _sha256(target.read_bytes()),
            **_sanitize_tree(metadata or {}),
        }
        reports = manifest.get("reports") if isinstance(manifest.get("reports"), list) else []
        reports.append(report)
        manifest["reports"] = reports
        manifest["updated_at"] = _now()
        _atomic_write_json(manifest_path, manifest)
        return report

    @_synchronized
    def list_tasks(self) -> list[dict]:
        if not self.tasks_root.exists():
            return []
        manifests = []
        for task_root in self.tasks_root.iterdir():
            if not task_root.is_dir() or not _TASK_ID_PATTERN.fullmatch(task_root.name):
                continue
            manifest = _read_json(task_root / "manifest.json", {})
            if manifest and manifest.get("task_id") == task_root.name:
                manifests.append(manifest)
        manifests.sort(
            key=lambda item: str(item.get("completed_at") or item.get("created_at") or ""),
            reverse=True,
        )
        return manifests

    @_synchronized
    def get_task(self, task_id: str, *, include_records: bool = False) -> dict:
        task_id = _validate_task_id(task_id)
        task_root = self.tasks_root / task_id
        manifest = _read_json(task_root / "manifest.json", {})
        if not manifest:
            raise FileNotFoundError("历史任务不存在或只有旧版任务信息")
        result = {"manifest": manifest, "meta": _read_json(task_root / "meta.json", {})}
        if include_records:
            result["records"] = _read_json(task_root / "records.json", [])
        return result

    @_synchronized
    def load_task(self, task_id: str, data_file: Path | str, meta_file: Path | str) -> dict:
        task = self.get_task(task_id, include_records=True)
        records = task.get("records")
        meta = task.get("meta")
        if not isinstance(records, list) or not isinstance(meta, dict):
            raise ValueError("该历史任务没有可恢复的正文和元数据")
        _atomic_write_json(Path(data_file), records)
        _atomic_write_json(Path(meta_file), meta)
        return {"task_id": task_id, "records_count": len(records)}

    @_synchronized
    def move_to_trash(self, task_id: str, *, deleted_by: str = "") -> dict:
        task_id = _validate_task_id(task_id)
        source = self.tasks_root / task_id
        manifest_path = source / "manifest.json"
        manifest = _read_json(manifest_path, {})
        if not manifest or not source.is_dir():
            raise FileNotFoundError("可删除的完整历史任务不存在")
        self.trash_root.mkdir(parents=True, exist_ok=True)
        trash_id = f"{task_id}-{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
        manifest["deleted_at"] = _now()
        manifest["deleted_by"] = str(deleted_by or "")
        manifest["trash_id"] = trash_id
        _atomic_write_json(manifest_path, manifest)
        os.replace(source, self.trash_root / trash_id)
        return {"task_id": task_id, "trash_id": trash_id, "deleted_at": manifest["deleted_at"]}

    @_synchronized
    def list_trash(self) -> list[dict]:
        if not self.trash_root.exists():
            return []
        items = []
        for task_root in self.trash_root.iterdir():
            if not task_root.is_dir() or not _TRASH_ID_PATTERN.fullmatch(task_root.name):
                continue
            manifest = _read_json(task_root / "manifest.json", {})
            if manifest:
                items.append({**manifest, "trash_id": task_root.name})
        items.sort(key=lambda item: str(item.get("deleted_at") or ""), reverse=True)
        return items

    @_synchronized
    def restore_from_trash(self, trash_id: str) -> dict:
        trash_id = _validate_trash_id(trash_id)
        source = self.trash_root / trash_id
        manifest_path = source / "manifest.json"
        manifest = _read_json(manifest_path, {})
        task_id = _validate_task_id(manifest.get("task_id"))
        target = self.tasks_root / task_id
        if not source.is_dir():
            raise FileNotFoundError("回收站记录不存在")
        if target.exists():
            raise FileExistsError("同编号历史任务已经存在，不能覆盖恢复")
        manifest.pop("deleted_at", None)
        manifest.pop("deleted_by", None)
        manifest.pop("trash_id", None)
        manifest["updated_at"] = _now()
        _atomic_write_json(manifest_path, manifest)
        self.tasks_root.mkdir(parents=True, exist_ok=True)
        os.replace(source, target)
        return manifest

    @_synchronized
    def purge_trash(self, trash_id: str) -> dict:
        trash_id = _validate_trash_id(trash_id)
        target = self.trash_root / trash_id
        manifest = _read_json(target / "manifest.json", {})
        if not target.is_dir():
            raise FileNotFoundError("回收站记录不存在")
        shutil.rmtree(target)
        return {"trash_id": trash_id, "task_id": str(manifest.get("task_id") or "")}

    @_synchronized
    def create_backup(self, passphrase: str) -> dict:
        password = str(passphrase or "")
        if len(password) < 8:
            raise ValueError("备份口令至少需要8个字符")
        files = list(self._backup_files())
        if not files:
            raise ValueError("当前没有可备份的历史任务")
        buffer = io.BytesIO()
        file_manifest = []
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for archive_name, data in files:
                file_manifest.append({
                    "path": archive_name,
                    "size": len(data),
                    "sha256": _sha256(data),
                })
                archive.writestr(archive_name, data)
            backup_manifest = {
                "version": BACKUP_VERSION,
                "created_at": _now(),
                "task_count": len(self.list_tasks()),
                "files": file_manifest,
            }
            archive.writestr("backup_manifest.json", _json_bytes(backup_manifest))
        plaintext = buffer.getvalue()
        if len(plaintext) > MAX_BACKUP_BYTES:
            raise ValueError("历史备份超过当前64MB安全上限，请先清理无用归档")

        salt = os.urandom(16)
        nonce = os.urandom(12)
        header = {
            "version": BACKUP_VERSION,
            "created_at": backup_manifest["created_at"],
            "kdf": "scrypt",
            "n": 32768,
            "r": 8,
            "p": 1,
            "salt": base64.b64encode(salt).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
        }
        header_bytes = json.dumps(header, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
        key = Scrypt(salt=salt, length=32, n=header["n"], r=header["r"], p=header["p"]).derive(
            password.encode("utf-8")
        )
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, header_bytes)
        payload = BACKUP_MAGIC + struct.pack(">I", len(header_bytes)) + header_bytes + ciphertext

        self.backups_root.mkdir(parents=True, exist_ok=True)
        filename = f"舆情系统历史备份_{datetime.now().strftime('%Y%m%d_%H%M%S')}.aombak"
        target = self.backups_root / filename
        _atomic_write_bytes(target, payload)
        return {
            "path": target,
            "filename": filename,
            "task_count": backup_manifest["task_count"],
            "file_count": len(file_manifest),
            "size": target.stat().st_size,
            "created_at": backup_manifest["created_at"],
        }

    @_synchronized
    def restore_backup(self, encrypted: bytes, passphrase: str) -> dict:
        archive_bytes, backup_manifest = self._decrypt_and_validate_backup(encrypted, passphrase)
        stage_parent = self.root
        stage_parent.mkdir(parents=True, exist_ok=True)
        stage = stage_parent / f".restore-staging-{uuid.uuid4().hex}"
        stage.mkdir(parents=True, exist_ok=False)
        restored = []
        skipped = []
        conflicts = []
        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
                for info in archive.infolist():
                    path = _safe_zip_name(info.filename)
                    if path.parts[0] != "tasks":
                        continue
                    target = stage.joinpath(*path.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(info))

                imported_history = json.loads(archive.read("task_history.json").decode("utf-8"))

            for staged_task in sorted((stage / "tasks").iterdir() if (stage / "tasks").exists() else []):
                task_id = _validate_task_id(staged_task.name)
                manifest = _read_json(staged_task / "manifest.json", {})
                records = _read_json(staged_task / "records.json", [])
                meta = _read_json(staged_task / "meta.json", {})
                if (
                    manifest.get("task_id") != task_id
                    or not isinstance(records, list)
                    or not isinstance(meta, dict)
                    or any(_contains_forbidden_key(item) for item in (manifest, records, meta))
                ):
                    raise ValueError("备份任务清单无效或包含凭据字段")
                for report in manifest.get("reports") or []:
                    if not isinstance(report, dict):
                        raise ValueError("备份报告清单无效")
                    archive_path = PurePosixPath(str(report.get("archive_path") or ""))
                    expected_prefix = PurePosixPath("data", "history_archive", "tasks", task_id, "reports")
                    if archive_path.parent != expected_prefix:
                        raise ValueError("备份报告路径无效")
                    report_path = staged_task / "reports" / archive_path.name
                    if (
                        not report_path.is_file()
                        or int(report.get("size") or -1) != report_path.stat().st_size
                        or str(report.get("sha256") or "") != _sha256(report_path.read_bytes())
                    ):
                        raise ValueError("备份报告文件校验失败")
                target = self.tasks_root / task_id
                if target.exists():
                    if _directory_digest(target) == _directory_digest(staged_task):
                        skipped.append(task_id)
                    else:
                        conflicts.append(task_id)
                    continue
                self.tasks_root.mkdir(parents=True, exist_ok=True)
                os.replace(staged_task, target)
                restored.append(task_id)

            current_history = _read_json(self.task_history_file, [])
            current_history = current_history if isinstance(current_history, list) else []
            imported_history = imported_history if isinstance(imported_history, list) else []
            merged = []
            seen = set()
            for entry in [*current_history, *imported_history]:
                if not isinstance(entry, dict) or _contains_forbidden_key(entry):
                    continue
                task_id = str(entry.get("task_id") or "").strip()
                if not _TASK_ID_PATTERN.fullmatch(task_id) or task_id in seen:
                    continue
                seen.add(task_id)
                merged.append(_sanitize_tree(entry))
            merged.sort(
                key=lambda item: str(item.get("completed_at") or item.get("created_at") or ""),
                reverse=True,
            )
            _atomic_write_json(self.task_history_file, merged)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
        return {
            "restored_task_ids": restored,
            "skipped_task_ids": skipped,
            "conflict_task_ids": conflicts,
            "backup_created_at": backup_manifest.get("created_at", ""),
            "history_count": len(_read_json(self.task_history_file, [])),
        }

    def _backup_files(self) -> Iterable[tuple[str, bytes]]:
        if self.tasks_root.exists():
            for path in sorted(item for item in self.tasks_root.rglob("*") if item.is_file()):
                if path.is_symlink() or path.name.endswith(".tmp"):
                    continue
                relative = path.relative_to(self.tasks_root).as_posix()
                yield f"tasks/{relative}", path.read_bytes()
        history = _read_json(self.task_history_file, [])
        safe_history = _sanitize_tree(history if isinstance(history, list) else [])
        yield "task_history.json", _json_bytes(safe_history)

    def _decrypt_and_validate_backup(self, encrypted: bytes, passphrase: str) -> tuple[bytes, dict]:
        if not isinstance(encrypted, (bytes, bytearray)) or not encrypted.startswith(BACKUP_MAGIC):
            raise ValueError("不是本系统支持的历史备份文件")
        cursor = len(BACKUP_MAGIC)
        if len(encrypted) < cursor + 4:
            raise ValueError("备份文件不完整")
        header_size = struct.unpack(">I", encrypted[cursor:cursor + 4])[0]
        cursor += 4
        if header_size <= 0 or header_size > 16 * 1024 or len(encrypted) <= cursor + header_size:
            raise ValueError("备份文件头无效")
        header_bytes = bytes(encrypted[cursor:cursor + header_size])
        cursor += header_size
        try:
            header = json.loads(header_bytes.decode("ascii"))
            if int(header.get("version")) != BACKUP_VERSION or header.get("kdf") != "scrypt":
                raise ValueError("备份版本或加密方式不受支持")
            salt = base64.b64decode(header["salt"], validate=True)
            nonce = base64.b64decode(header["nonce"], validate=True)
            if len(salt) != 16 or len(nonce) != 12:
                raise ValueError("备份加密参数不受支持")
            if int(header["n"]) != 32768 or int(header["r"]) != 8 or int(header["p"]) != 1:
                raise ValueError("备份加密参数不受支持")
            key = Scrypt(
                salt=salt,
                length=32,
                n=int(header["n"]),
                r=int(header["r"]),
                p=int(header["p"]),
            ).derive(str(passphrase or "").encode("utf-8"))
            plaintext = AESGCM(key).decrypt(nonce, bytes(encrypted[cursor:]), header_bytes)
        except (InvalidTag, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("备份口令错误或文件已损坏") from exc
        if len(plaintext) > MAX_BACKUP_BYTES:
            raise ValueError("解密后的备份超过安全上限")

        try:
            with zipfile.ZipFile(io.BytesIO(plaintext), "r") as archive:
                infos = archive.infolist()
                if len(infos) > MAX_BACKUP_FILES:
                    raise ValueError("备份文件数量超过安全上限")
                total_size = 0
                names = set()
                for info in infos:
                    path = _safe_zip_name(info.filename)
                    if info.is_dir() or info.file_size > MAX_BACKUP_FILE_BYTES:
                        raise ValueError("备份包含不受支持的目录或超大文件")
                    total_size += info.file_size
                    if total_size > MAX_BACKUP_BYTES or path.as_posix() in names:
                        raise ValueError("备份解压规模或文件名无效")
                    names.add(path.as_posix())
                backup_manifest = json.loads(archive.read("backup_manifest.json").decode("utf-8"))
                if int(backup_manifest.get("version")) != BACKUP_VERSION:
                    raise ValueError("备份清单版本不受支持")
                file_entries = [
                    item for item in backup_manifest.get("files", [])
                    if isinstance(item, dict)
                ]
                expected = {
                    str(item.get("path")): item
                    for item in file_entries
                }
                actual_names = names - {"backup_manifest.json"}
                if (
                    len(expected) != len(file_entries)
                    or set(expected) != actual_names
                    or "task_history.json" not in actual_names
                ):
                    raise ValueError("备份清单与实际文件不一致")
                for name, item in expected.items():
                    data = archive.read(name)
                    if len(data) != int(item.get("size", -1)) or _sha256(data) != item.get("sha256"):
                        raise ValueError("备份文件校验失败")
        except (KeyError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            raise ValueError("备份内容损坏或格式无效") from exc
        return plaintext, backup_manifest
