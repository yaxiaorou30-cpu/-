import base64
import http.client
import json
import shutil
import socket
import threading
import unittest
import uuid
from pathlib import Path
from urllib.parse import quote
from unittest.mock import patch

import web_app
from src.history_archive import HistoryArchiveStore
from src.system_auth import (
    LoginAttemptLimiter,
    SessionManager,
    SystemAccountStore,
    SYSTEM_ROLE,
    generate_recovery_code,
)

TEST_TEMP_ROOT = Path(__file__).resolve().parents[1] / "data"


class SystemAccountStoreTests(unittest.TestCase):
    def setUp(self):
        self.store_path = TEST_TEMP_ROOT / f".test-system-users-{uuid.uuid4().hex}.json"
        self.store = SystemAccountStore(self.store_path, iterations=100_000)

    def tearDown(self):
        self.store_path.unlink(missing_ok=True)

    def test_only_one_user_can_be_created_and_secrets_are_not_plaintext(self):
        recovery_code = generate_recovery_code()
        first = self.store.create_user(
            "民警甲",
            "Alpha-Password-2026",
            recovery_code=recovery_code,
        )

        self.assertEqual(first["role"], SYSTEM_ROLE)
        self.assertTrue(first["recovery_configured"])
        with self.assertRaisesRegex(ValueError, "只能使用一个账号"):
            self.store.create_user("民警乙", "Beta-Password-2026")
        self.assertEqual(len(self.store.list_users()), 1)
        stored_text = self.store_path.read_text(encoding="utf-8")
        self.assertNotIn("Alpha-Password-2026", stored_text)
        self.assertNotIn(recovery_code, stored_text)
        self.assertNotIn(recovery_code.replace("-", ""), stored_text)
        self.assertIn("pbkdf2_sha256", stored_text)

    def test_wrong_password_is_rejected_and_only_account_cannot_be_disabled(self):
        self.store.create_user("民警甲", "Alpha-Password-2026")
        self.assertTrue(self.store.authenticate("民警甲", "Alpha-Password-2026").ok)
        self.assertFalse(self.store.authenticate("民警甲", "wrong-password").ok)
        with self.assertRaisesRegex(ValueError, "不能停用唯一可用账号"):
            self.store.set_enabled("民警甲", False)
        self.assertTrue(self.store.authenticate("民警甲", "Alpha-Password-2026").ok)

    def test_session_logout_and_expiry_take_effect(self):
        now = [1000.0]
        self.store.create_user("民警甲", "Alpha-Password-2026")
        sessions = SessionManager(
            self.store,
            idle_timeout_seconds=10,
            absolute_timeout_seconds=30,
            clock=lambda: now[0],
        )

        token, identity = sessions.create("民警甲")
        self.assertEqual(identity, {"username": "民警甲", "role": SYSTEM_ROLE})
        now[0] = 1009.0
        self.assertIsNotNone(sessions.resolve(token))
        now[0] = 1020.0
        self.assertIsNone(sessions.resolve(token))

        token, _ = sessions.create("民警甲")
        sessions.revoke(token)
        self.assertIsNone(sessions.resolve(token))

        absolute_sessions = SessionManager(
            self.store,
            idle_timeout_seconds=100,
            absolute_timeout_seconds=10,
            clock=lambda: now[0],
        )
        token, _ = absolute_sessions.create("民警甲")
        now[0] = 1030.0
        self.assertIsNone(absolute_sessions.resolve(token))

    def test_recovery_code_resets_password_and_rotates_itself(self):
        old_code = generate_recovery_code()
        new_code = generate_recovery_code()
        self.store.create_user(
            "民警甲",
            "Alpha-Password-2026",
            recovery_code=old_code,
        )

        rejected = self.store.recover_password(
            "民警甲",
            generate_recovery_code(),
            "New-Password-2026",
            new_code,
        )
        self.assertFalse(rejected.ok)
        accepted = self.store.recover_password(
            "民警甲",
            old_code.lower().replace("-", " "),
            "New-Password-2026",
            new_code,
        )
        self.assertTrue(accepted.ok)
        self.assertFalse(self.store.authenticate("民警甲", "Alpha-Password-2026").ok)
        self.assertTrue(self.store.authenticate("民警甲", "New-Password-2026").ok)
        self.assertFalse(
            self.store.recover_password(
                "民警甲",
                old_code,
                "Third-Password-2026",
                generate_recovery_code(),
            ).ok
        )

    def test_failed_login_limiter_temporarily_blocks_key(self):
        now = [100.0]
        limiter = LoginAttemptLimiter(
            max_failures=2,
            window_seconds=60,
            lock_seconds=30,
            clock=lambda: now[0],
        )
        self.assertFalse(limiter.is_blocked("127.0.0.1", "民警甲"))
        limiter.record_failure("127.0.0.1", "民警甲")
        limiter.record_failure("127.0.0.1", "民警甲")
        self.assertTrue(limiter.is_blocked("127.0.0.1", "民警甲"))
        now[0] = 131.0
        self.assertFalse(limiter.is_blocked("127.0.0.1", "民警甲"))


class CrawlTaskOutcomeTests(unittest.TestCase):
    def test_all_policy_failures_are_reported_as_blocked(self):
        status, message = web_app.classify_crawl_task({
            "min_real_results": 1,
            "reached_min_real_results": False,
            "summary": {"real_count": 0},
            "failures": [
                {"policy_code": "robots_disallowed"},
                {"policy_code": "automation_disabled"},
            ],
        })
        self.assertEqual(status, "blocked")
        self.assertIn("访问策略", message)

    def test_acceptance_below_minimum_is_not_reported_as_complete(self):
        status, message = web_app.classify_crawl_task({
            "min_real_results": 1,
            "reached_min_real_results": False,
            "summary": {"real_count": 0},
            "failures": [{"error": "no parseable result"}],
        }, source_acceptance=True)
        self.assertEqual(status, "not_met")
        self.assertIn("验收未通过", message)

    def test_partial_results_are_not_mislabeled_as_all_sources_blocked(self):
        status, message = web_app.classify_crawl_task({
            "min_real_results": 5,
            "reached_min_real_results": False,
            "summary": {"real_count": 2},
            "failures": [{"policy_code": "robots_disallowed"}],
        })
        self.assertEqual(status, "done")
        self.assertIn("未达到最低阈值", message)

    def test_acceptance_with_real_result_passes(self):
        status, message = web_app.classify_crawl_task({
            "min_real_results": 1,
            "reached_min_real_results": True,
            "summary": {"real_count": 3},
            "failures": [],
        }, source_acceptance=True)
        self.assertEqual(status, "done")
        self.assertIn("验收通过", message)


class WebServerConcurrencyTests(unittest.TestCase):
    def test_server_disables_address_reuse(self):
        server, _ = web_app.create_server("127.0.0.1", 0)
        try:
            self.assertFalse(server.allow_reuse_address)
        finally:
            server.server_close()

    def test_idle_browser_connection_does_not_block_other_requests(self):
        server, _ = web_app.create_server("127.0.0.1", 0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        idle_connection = socket.create_connection(("127.0.0.1", port), timeout=2)
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            connection.request("GET", "/api/auth/status")
            response = connection.getresponse()
            response.read()
            connection.close()
            self.assertEqual(response.status, 200)
        finally:
            idle_connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


class WebAuthenticationAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.store_path = TEST_TEMP_ROOT / f".test-system-users-{uuid.uuid4().hex}.json"
        self.store = SystemAccountStore(
            self.store_path,
            iterations=100_000,
        )
        self.initial_recovery_code = generate_recovery_code()
        self.store.create_user(
            "民警甲",
            "Alpha-Password-2026",
            recovery_code=self.initial_recovery_code,
        )
        self.sessions = SessionManager(self.store, idle_timeout_seconds=60, absolute_timeout_seconds=600)
        self.limiter = LoginAttemptLimiter(max_failures=5)
        self.patchers = [
            patch.object(web_app, "SYSTEM_USER_STORE", self.store),
            patch.object(web_app, "SYSTEM_SESSION_MANAGER", self.sessions),
            patch.object(web_app, "LOGIN_ATTEMPT_LIMITER", self.limiter),
            patch.object(
                web_app,
                "build_latest_payload",
                return_value={"ok": True, "data": [], "total": 0, "history": []},
            ),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.server = web_app.HTTPServer(("127.0.0.1", 0), web_app.WebUIHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.store_path.unlink(missing_ok=True)

    def request(self, method, path, payload=None, cookie=""):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {}
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if cookie:
            headers["Cookie"] = cookie
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            decoded_payload = json.loads(raw.decode("utf-8")) if raw else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            decoded_payload = None
        result = {
            "status": response.status,
            "location": response.getheader("Location"),
            "set_cookie": response.getheader("Set-Cookie") or "",
            "content_disposition": response.getheader("Content-Disposition") or "",
            "payload": decoded_payload,
            "body": raw,
        }
        connection.close()
        return result

    def login(self, username, password):
        response = self.request(
            "POST",
            "/api/auth/login",
            {"username": username, "password": password},
        )
        cookie = response["set_cookie"].split(";", 1)[0]
        return response, cookie

    def test_unauthenticated_business_ui_api_and_static_assets_are_blocked(self):
        root = self.request("GET", "/")
        self.assertEqual(root["status"], 302)
        self.assertEqual(root["location"], "/login")
        self.assertEqual(self.request("GET", "/static/app.js")["status"], 302)
        api = self.request("GET", "/api/latest")
        self.assertEqual(api["status"], 401)
        self.assertEqual(api["payload"]["code"], "authentication_required")
        self.assertEqual(self.request("GET", "/api/monitors")["status"], 401)
        ai_api = self.request(
            "POST",
            "/api/report-ai-draft",
            {"confirmed_external_send": True},
        )
        self.assertEqual(ai_api["status"], 401)
        self.assertEqual(ai_api["payload"]["code"], "authentication_required")

    def test_wrong_password_is_rejected_with_generic_message(self):
        response, cookie = self.login("民警甲", "not-the-password")
        self.assertEqual(response["status"], 401)
        self.assertEqual(cookie, "")
        self.assertNotIn("wrong", response["payload"]["message"].lower())

    def test_single_user_can_access_endpoint_and_static_traversal_is_blocked(self):
        login, cookie = self.login("民警甲", "Alpha-Password-2026")
        self.assertEqual(login["status"], 200)
        self.assertEqual(login["payload"]["user"]["role"], SYSTEM_ROLE)
        self.assertIn("HttpOnly", login["set_cookie"])
        self.assertIn("SameSite=Strict", login["set_cookie"])
        self.assertIn("Max-Age=28800", login["set_cookie"])
        self.assertEqual(self.request("GET", "/api/latest", cookie=cookie)["status"], 200)

        traversal = self.request("GET", "/static/../../web_app.py", cookie=cookie)
        self.assertEqual(traversal["status"], 404)

    def test_first_run_setup_creates_one_account_and_shows_recovery_code_once(self):
        self.store_path.unlink(missing_ok=True)
        status = self.request("GET", "/api/auth/status")
        self.assertTrue(status["payload"]["setup_required"])

        setup = self.request(
            "POST",
            "/api/auth/setup",
            {
                "username": "首机民警",
                "password": "First-Run-Password-2026",
                "password_confirmation": "First-Run-Password-2026",
            },
        )
        self.assertEqual(setup["status"], 200)
        self.assertRegex(setup["payload"]["recovery_code"], r"^(?:[A-Z2-7]{4}-){5}[A-Z2-7]{4}$")
        self.assertIn("HttpOnly", setup["set_cookie"])
        cookie = setup["set_cookie"].split(";", 1)[0]
        self.assertEqual(self.request("GET", "/api/latest", cookie=cookie)["status"], 200)
        self.assertEqual(len(self.store.list_users()), 1)

        second = self.request(
            "POST",
            "/api/auth/setup",
            {
                "username": "第二账号",
                "password": "Second-Password-2026",
                "password_confirmation": "Second-Password-2026",
            },
        )
        self.assertEqual(second["status"], 409)
        saved_text = self.store_path.read_text(encoding="utf-8")
        self.assertNotIn(setup["payload"]["recovery_code"], saved_text)

    def test_password_change_revokes_existing_sessions(self):
        _, first_cookie = self.login("民警甲", "Alpha-Password-2026")
        _, second_cookie = self.login("民警甲", "Alpha-Password-2026")
        changed = self.request(
            "POST",
            "/api/auth/change-password",
            {
                "current_password": "Alpha-Password-2026",
                "new_password": "Changed-Password-2026",
                "password_confirmation": "Changed-Password-2026",
            },
            first_cookie,
        )
        self.assertEqual(changed["status"], 200)
        self.assertIn("Max-Age=0", changed["set_cookie"])
        self.assertEqual(self.request("GET", "/api/latest", cookie=first_cookie)["status"], 401)
        self.assertEqual(self.request("GET", "/api/latest", cookie=second_cookie)["status"], 401)
        self.assertEqual(self.login("民警甲", "Alpha-Password-2026")[0]["status"], 401)
        self.assertEqual(self.login("民警甲", "Changed-Password-2026")[0]["status"], 200)

    def test_logged_in_user_can_rotate_recovery_code_without_plaintext_storage(self):
        _, cookie = self.login("民警甲", "Alpha-Password-2026")
        wrong = self.request(
            "POST",
            "/api/auth/recovery-code",
            {"current_password": "wrong-password"},
            cookie,
        )
        self.assertEqual(wrong["status"], 401)

        rotated = self.request(
            "POST",
            "/api/auth/recovery-code",
            {"current_password": "Alpha-Password-2026"},
            cookie,
        )
        self.assertEqual(rotated["status"], 200)
        recovery_code = rotated["payload"]["recovery_code"]
        self.assertRegex(recovery_code, r"^(?:[A-Z2-7]{4}-){5}[A-Z2-7]{4}$")
        stored_text = self.store_path.read_text(encoding="utf-8")
        self.assertNotIn(recovery_code, stored_text)
        self.assertNotIn(recovery_code.replace("-", ""), stored_text)
        status = self.request("GET", "/api/auth/status", cookie=cookie)
        self.assertTrue(status["payload"]["recovery_configured"])

    def test_recovery_resets_password_rotates_code_and_revokes_sessions(self):
        _, old_cookie = self.login("民警甲", "Alpha-Password-2026")
        wrong = self.request(
            "POST",
            "/api/auth/recover",
            {
                "username": "民警甲",
                "recovery_code": generate_recovery_code(),
                "new_password": "Recovered-Password-2026",
                "password_confirmation": "Recovered-Password-2026",
            },
        )
        self.assertEqual(wrong["status"], 401)

        recovered = self.request(
            "POST",
            "/api/auth/recover",
            {
                "username": "民警甲",
                "recovery_code": self.initial_recovery_code,
                "new_password": "Recovered-Password-2026",
                "password_confirmation": "Recovered-Password-2026",
            },
        )
        self.assertEqual(recovered["status"], 200)
        self.assertRegex(recovered["payload"]["recovery_code"], r"^(?:[A-Z2-7]{4}-){5}[A-Z2-7]{4}$")
        self.assertEqual(self.request("GET", "/api/latest", cookie=old_cookie)["status"], 401)
        self.assertEqual(self.login("民警甲", "Alpha-Password-2026")[0]["status"], 401)
        self.assertEqual(self.login("民警甲", "Recovered-Password-2026")[0]["status"], 200)

        old_code_again = self.request(
            "POST",
            "/api/auth/recover",
            {
                "username": "民警甲",
                "recovery_code": self.initial_recovery_code,
                "new_password": "Another-Password-2026",
                "password_confirmation": "Another-Password-2026",
            },
        )
        self.assertEqual(old_code_again["status"], 401)

    def test_authenticated_download_supports_chinese_filename(self):
        _, cookie = self.login("民警甲", "Alpha-Password-2026")
        filename = f".test-全国舆情通报-{uuid.uuid4().hex}.docx"
        report_path = TEST_TEMP_ROOT / filename
        expected = b"test-docx-content"
        try:
            report_path.write_bytes(expected)
            encoded_path = quote(f"data/{filename}", safe="/")
            response = self.request("GET", f"/download?path={encoded_path}", cookie=cookie)
        finally:
            report_path.unlink(missing_ok=True)

        self.assertEqual(response["status"], 200)
        self.assertEqual(response["body"], expected)
        disposition = response["content_disposition"]
        self.assertIn("attachment;", disposition)
        self.assertIn("filename*=UTF-8''", disposition)
        self.assertIn(quote(filename, safe=""), disposition)
        disposition.encode("latin-1")

    def test_logout_revokes_session_and_requires_reauthentication(self):
        _, cookie = self.login("民警甲", "Alpha-Password-2026")
        logout = self.request("POST", "/api/auth/logout", {}, cookie=cookie)
        self.assertEqual(logout["status"], 200)
        self.assertIn("Max-Age=0", logout["set_cookie"])
        self.assertEqual(self.request("GET", "/api/latest", cookie=cookie)["status"], 401)

    def test_authenticated_history_archive_backup_delete_and_restore_flow(self):
        _, cookie = self.login("民警甲", "Alpha-Password-2026")
        project_root = TEST_TEMP_ROOT / f".test-history-api-{uuid.uuid4().hex}"
        store = HistoryArchiveStore(project_root)
        task_id = "history_api_001"
        entry = {
            "task_id": task_id,
            "status": "done",
            "created_at": "2026-08-02T10:00:00",
            "completed_at": "2026-08-02T10:05:00",
            "payload": {"topic": "接口归档验收", "keywords": ["验收"]},
            "summary": {"total": 1, "real_count": 1},
        }
        records = [{"title": "历史正文", "content": "接口验收内容", "url": "https://example.com/1"}]
        meta = {"task_id": task_id, "topic": "接口归档验收", "summary": entry["summary"]}
        data_file = project_root / "workspace" / "latest.json"
        meta_file = project_root / "workspace" / "latest_meta.json"
        try:
            store.archive_task(task_id, history_entry=entry, records=records, meta=meta)
            store.task_history_file.parent.mkdir(parents=True, exist_ok=True)
            store.task_history_file.write_text(json.dumps([entry], ensure_ascii=False), encoding="utf-8")
            with (
                patch.object(web_app, "HISTORY_ARCHIVE_STORE", store),
                patch.object(web_app, "TASK_HISTORY_FILE", store.task_history_file),
                patch.object(web_app, "DATA_FILE", data_file),
                patch.object(web_app, "META_FILE", meta_file),
            ):
                catalog = self.request("GET", "/api/task-history", cookie=cookie)
                self.assertEqual(catalog["status"], 200)
                self.assertEqual(catalog["payload"]["summary"]["full_archives"], 1)

                detail = self.request(
                    "GET",
                    f"/api/task-history/detail?id={task_id}",
                    cookie=cookie,
                )
                self.assertEqual(detail["payload"]["records"][0]["content"], "接口验收内容")

                loaded = self.request(
                    "POST",
                    "/api/task-history/load",
                    {"task_id": task_id},
                    cookie,
                )
                self.assertEqual(loaded["status"], 200)
                self.assertTrue(data_file.exists())

                backed_up = self.request(
                    "POST",
                    "/api/task-history/backup",
                    {"passphrase": "Strong-Backup-Passphrase"},
                    cookie,
                )
                self.assertEqual(backed_up["status"], 200)
                encrypted = next(store.backups_root.glob("*.aombak")).read_bytes()

                deleted = self.request(
                    "POST",
                    "/api/task-history/delete",
                    {"task_id": task_id, "confirm_task_id": task_id},
                    cookie,
                )
                self.assertEqual(deleted["payload"]["summary"]["trash_count"], 1)
                trash_id = deleted["payload"]["trash"][0]["trash_id"]
                purged = self.request(
                    "POST",
                    "/api/task-history/trash-action",
                    {"trash_id": trash_id, "action": "purge", "confirm_trash_id": trash_id},
                    cookie,
                )
                self.assertEqual(purged["payload"]["summary"]["trash_count"], 0)

                restored = self.request(
                    "POST",
                    "/api/task-history/restore",
                    {
                        "backup_base64": base64.b64encode(encrypted).decode("ascii"),
                        "passphrase": "Strong-Backup-Passphrase",
                    },
                    cookie,
                )
                self.assertEqual(restored["status"], 200)
                self.assertEqual(restored["payload"]["restore"]["restored_task_ids"], [task_id])
        finally:
            shutil.rmtree(project_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
