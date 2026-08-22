import json
import shutil
import unittest
import uuid
from pathlib import Path

from src.history_archive import HistoryArchiveStore


class HistoryArchiveTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("data") / f"_test_history_archive_{uuid.uuid4().hex}"
        self.root.mkdir(parents=True)
        self.store = HistoryArchiveStore(self.root)
        self.task_id = "task_001"
        self.entry = {
            "task_id": self.task_id,
            "status": "done",
            "created_at": "2026-08-02T10:00:00",
            "completed_at": "2026-08-02T10:05:00",
            "payload": {
                "topic": "历史归档测试",
                "keywords": ["测试"],
                "accounts": {"微博": {"cookie": "must-not-archive"}},
            },
            "summary": {"total": 1, "real_count": 1},
        }
        self.records = [{
            "title": "测试线索",
            "content": "历史正文",
            "url": "https://example.com/1",
            "cookie_header": "must-not-archive",
        }]
        self.meta = {
            "task_id": self.task_id,
            "topic": "历史归档测试",
            "review": {"reviewed_at": "2026-08-02T10:06:00", "kept_total": 1},
        }

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def archive_sample(self):
        return self.store.archive_task(
            self.task_id,
            history_entry=self.entry,
            records=self.records,
            meta=self.meta,
        )

    def test_task_snapshot_keeps_body_and_removes_credential_fields(self):
        manifest = self.archive_sample()
        archived = self.store.get_task(self.task_id, include_records=True)
        serialized = json.dumps(archived, ensure_ascii=False)

        self.assertTrue(manifest["has_records"])
        self.assertTrue(manifest["has_meta"])
        self.assertEqual(manifest["records_count"], 1)
        self.assertEqual(archived["records"][0]["content"], "历史正文")
        self.assertNotIn("must-not-archive", serialized)
        self.assertNotIn("accounts", serialized)
        self.assertNotIn("cookie_header", serialized)

    def test_report_is_copied_into_task_archive_and_listed(self):
        self.archive_sample()
        report = self.root / "report.docx"
        report.write_bytes(b"report-content")

        archived = self.store.archive_report(
            self.task_id,
            report,
            metadata={"template_id": "event_report"},
        )
        detail = self.store.get_task(self.task_id)
        archived_path = self.root / archived["archive_path"]

        self.assertTrue(archived_path.exists())
        self.assertEqual(archived_path.read_bytes(), b"report-content")
        self.assertEqual(detail["manifest"]["reports"][0]["template_id"], "event_report")

    def test_load_delete_restore_and_permanent_delete_are_scoped(self):
        self.archive_sample()
        restored_data = self.root / "workspace" / "latest.json"
        restored_meta = self.root / "workspace" / "meta.json"
        loaded = self.store.load_task(self.task_id, restored_data, restored_meta)

        self.assertEqual(loaded["records_count"], 1)
        self.assertEqual(json.loads(restored_data.read_text(encoding="utf-8"))[0]["title"], "测试线索")

        deleted = self.store.move_to_trash(self.task_id, deleted_by="民警甲")
        self.assertFalse((self.store.tasks_root / self.task_id).exists())
        self.assertEqual(len(self.store.list_trash()), 1)

        restored = self.store.restore_from_trash(deleted["trash_id"])
        self.assertEqual(restored["task_id"], self.task_id)
        deleted_again = self.store.move_to_trash(self.task_id, deleted_by="民警甲")
        purged = self.store.purge_trash(deleted_again["trash_id"])
        self.assertEqual(purged["task_id"], self.task_id)
        self.assertFalse((self.store.trash_root / deleted_again["trash_id"]).exists())

    def test_encrypted_backup_restores_to_empty_store_and_wrong_password_fails(self):
        self.archive_sample()
        self.store.task_history_file.parent.mkdir(parents=True, exist_ok=True)
        self.store.task_history_file.write_text(
            json.dumps([self.entry], ensure_ascii=False),
            encoding="utf-8",
        )
        backup = self.store.create_backup("Strong-Backup-Passphrase")
        encrypted = backup["path"].read_bytes()

        with self.assertRaisesRegex(ValueError, "口令错误|文件已损坏"):
            self.store.restore_backup(encrypted, "wrong-password")
        tampered = bytearray(encrypted)
        tampered[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "口令错误|文件已损坏"):
            self.store.restore_backup(bytes(tampered), "Strong-Backup-Passphrase")

        target_root = self.root / "restored-project"
        target_store = HistoryArchiveStore(target_root)
        result = target_store.restore_backup(encrypted, "Strong-Backup-Passphrase")
        detail = target_store.get_task(self.task_id, include_records=True)

        self.assertEqual(result["restored_task_ids"], [self.task_id])
        self.assertEqual(detail["records"][0]["content"], "历史正文")
        restored_history = json.loads(target_store.task_history_file.read_text(encoding="utf-8"))
        self.assertEqual(restored_history[0]["task_id"], self.task_id)

    def test_restore_never_overwrites_conflicting_existing_task(self):
        self.archive_sample()
        self.store.task_history_file.parent.mkdir(parents=True, exist_ok=True)
        self.store.task_history_file.write_text(json.dumps([self.entry]), encoding="utf-8")
        encrypted = self.store.create_backup("Strong-Backup-Passphrase")["path"].read_bytes()

        target_root = self.root / "conflict-project"
        target_store = HistoryArchiveStore(target_root)
        conflicting = [{"title": "本机不同内容", "content": "不得覆盖", "url": "https://local/1"}]
        target_store.archive_task(
            self.task_id,
            history_entry=self.entry,
            records=conflicting,
            meta=self.meta,
        )
        result = target_store.restore_backup(encrypted, "Strong-Backup-Passphrase")

        self.assertEqual(result["conflict_task_ids"], [self.task_id])
        detail = target_store.get_task(self.task_id, include_records=True)
        self.assertEqual(detail["records"][0]["content"], "不得覆盖")

    def test_backup_restores_archived_report_and_skips_identical_task(self):
        self.archive_sample()
        report = self.root / "通报.docx"
        report.write_bytes(b"archived-report")
        self.store.archive_report(self.task_id, report, metadata={"template_id": "event_report"})
        self.store.task_history_file.parent.mkdir(parents=True, exist_ok=True)
        self.store.task_history_file.write_text(
            json.dumps([self.entry], ensure_ascii=False),
            encoding="utf-8",
        )
        encrypted = self.store.create_backup("Strong-Backup-Passphrase")["path"].read_bytes()

        target_root = self.root / "report-restore-project"
        target_store = HistoryArchiveStore(target_root)
        first = target_store.restore_backup(encrypted, "Strong-Backup-Passphrase")
        second = target_store.restore_backup(encrypted, "Strong-Backup-Passphrase")
        manifest = target_store.get_task(self.task_id)["manifest"]
        archived_path = target_root / manifest["reports"][0]["archive_path"]

        self.assertEqual(first["restored_task_ids"], [self.task_id])
        self.assertEqual(second["skipped_task_ids"], [self.task_id])
        self.assertEqual(archived_path.read_bytes(), b"archived-report")


if __name__ == "__main__":
    unittest.main()
