import unittest
from unittest.mock import patch

import web_app


class WebAccountStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = {"version": 1, "platforms": {}}
        self.read_patch = patch.object(web_app, "read_account_store", lambda: self.store)
        self.write_patch = patch.object(web_app, "write_account_store", self.write_store)
        self.read_patch.start()
        self.write_patch.start()
        self.platform = web_app.PLATFORM_LIST[0]

    def tearDown(self):
        self.write_patch.stop()
        self.read_patch.stop()

    def write_store(self, store):
        self.store = store

    def test_task_form_uses_supported_social_strategy_and_preserves_topic(self):
        html = (web_app.WEB_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn('name="sourceStrategy" value="social"', html)
        self.assertNotIn('value="social_first"', html)
        self.assertIn("<h3>政府官方网站</h3>", html)
        self.assertIn("<strong>先查政府官网</strong>", html)
        summary = web_app.task_payload_summary(
            {
                "topic": "深圳强降雨交通影响舆情",
                "keywords": "深圳暴雨,交通中断",
                "source_strategy": "social",
            }
        )
        self.assertEqual(summary["topic"], "深圳强降雨交通影响舆情")
        self.assertEqual(summary["source_strategy"], "social")

    def test_runtime_status_and_job_log_use_global_dock(self):
        html = (web_app.WEB_DIR / "index.html").read_text(encoding="utf-8")
        css = (web_app.WEB_DIR / "static" / "styles.css").read_text(encoding="utf-8")
        javascript = (web_app.WEB_DIR / "static" / "app.js").read_text(encoding="utf-8")

        dock_start = html.index('id="globalOperationsDock"')
        self.assertGreater(dock_start, html.index("</main>"))
        for element_id in (
            "globalOperationsDock",
            "globalOperationsToggle",
            "globalOperationsBody",
            "globalRunHeadline",
            "globalLatestLog",
            "taskIdLabel",
            "progressBar",
            "eventList",
            "logBox",
        ):
            self.assertEqual(html.count(f'id="{element_id}"'), 1)

        self.assertIn("全局作业日志", html)
        self.assertIn("来源操作记录", html)
        self.assertIn(".global-operations-dock {", css)
        self.assertIn("position: fixed;", css[css.index(".global-operations-dock {") :])
        self.assertIn('els.globalLatestLog.textContent = message;', javascript)
        self.assertIn('els.globalMiniProgressBar.style.width = `${normalized}%`;', javascript)
        self.assertIn('els.globalOperationsToggle.addEventListener("click"', javascript)

    def test_platform_test_ui_requires_login_and_collection(self):
        html = (web_app.WEB_DIR / "index.html").read_text(encoding="utf-8")
        javascript = (web_app.WEB_DIR / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn('aria-label="平台实测判定含义"', html)
        self.assertIn("当前登录有效，并且本次采集到有效结果", html)
        self.assertIn("采集通过，登录未通过", html)
        self.assertIn("登录通过，采集未通过", html)
        self.assertIn("登录判定优先采用平台身份接口", html)
        self.assertIn("只检查当前页顶部或侧栏实际可见的账号控件", html)
        self.assertIn("正文作者头像、整页源码字段、Cookie", html)
        self.assertIn("passed: loginPassed && readPassed", javascript)
        self.assertIn("登录 ${loginPassed}/${cards.length}", javascript)
        self.assertIn("采集 ${readPassed}/${cards.length}", javascript)
        self.assertIn("完全通过 ${fullyPassed}/${cards.length}", javascript)
        self.assertNotIn("保存时已确认；当前身份接口", javascript)

    def test_single_account_setup_and_security_controls_are_present(self):
        login_html = (web_app.WEB_DIR / "login.html").read_text(encoding="utf-8")
        workbench_html = (web_app.WEB_DIR / "index.html").read_text(encoding="utf-8")
        javascript = (web_app.WEB_DIR / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="setupView"', login_html)
        self.assertIn('id="recoveryView"', login_html)
        self.assertIn('fetch("/api/auth/setup"', login_html)
        self.assertIn('fetch("/api/auth/recover"', login_html)
        self.assertNotIn("manage_system_users.py", login_html)
        for element_id in (
            "accountSecurityBtn",
            "accountSecurityDialog",
            "changePasswordForm",
            "recoveryCodeForm",
            "accountRecoveryResult",
        ):
            self.assertEqual(workbench_html.count(f'id="{element_id}"'), 1)
        self.assertIn('requestJson("/api/auth/change-password"', javascript)
        self.assertIn('requestJson("/api/auth/recovery-code"', javascript)
        self.assertNotIn("创建第二个账号", javascript)

    def test_report_generation_refreshes_history_counts_and_open_detail(self):
        backend = (web_app.ROOT / "web_app.py").read_text(encoding="utf-8")
        javascript = (web_app.WEB_DIR / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn('"history_catalog": build_history_catalog()', backend)
        self.assertIn("if (result.history_catalog) {", javascript)
        self.assertIn("applyHistoryCatalog(result.history_catalog);", javascript)
        self.assertIn("const selectedHistoryId = state.selectedHistoryId;", javascript)
        self.assertIn("showHistoryDetail(refreshedItem);", javascript)

    def test_task_history_keeps_reusable_conditions_without_account_secrets(self):
        entry = {
            "task_id": "safe-history",
            "status": "done",
            "created_at": "2026-08-01T08:00:00",
            "completed_at": "2026-08-01T08:05:00",
            "summary": {
                "total": 12,
                "real_count": 10,
                "stable_real_count": 4,
                "social_real_count": 6,
                "quality_conclusion": "legacy detail",
            },
            "payload": {
                "topic": "测试任务",
                "keywords": ["测试", "任务"],
                "region": "天津",
                "source_strategy": "stable_first",
                "collect_level": "快速采集",
                "time_range": "2026-07-01 至 2026-07-31",
                "stable_sources": ["天津市政府新闻发布会"],
                "social_platforms": ["微博"],
                "min_real_results": "8",
                "accounts": {
                    "微博": {
                        "username": "private-user",
                        "password": "private-password",
                        "cookie": "private-cookie",
                    }
                },
                "unexpected_secret": "legacy-secret",
            },
        }

        safe = web_app.sanitize_task_history_entry(entry)

        self.assertEqual(safe["payload"]["min_real_results"], 8)
        self.assertEqual(safe["summary"]["real_count"], 10)
        self.assertNotIn("quality_conclusion", safe["summary"])
        serialized = str(safe)
        self.assertNotIn("private-user", serialized)
        self.assertNotIn("private-password", serialized)
        self.assertNotIn("private-cookie", serialized)
        self.assertNotIn("legacy-secret", serialized)

    def test_task_payload_summary_never_copies_account_credentials(self):
        summary = web_app.task_payload_summary(
            {
                "topic": "测试任务",
                "min_real_results": "6",
                "accounts": {
                    "微博": {
                        "username": "private-user",
                        "password": "private-password",
                        "cookie": "private-cookie",
                    }
                },
            }
        )

        self.assertEqual(summary["min_real_results"], 6)
        self.assertEqual(summary["account_platforms"], ["微博"])
        serialized = str(summary)
        self.assertNotIn("private-user", serialized)
        self.assertNotIn("private-password", serialized)
        self.assertNotIn("private-cookie", serialized)

    def test_parse_keywords_supports_commas_semicolons_and_newlines(self):
        self.assertEqual(
            web_app.parse_keywords("深圳\n暴雨，交通中断；应急响应\n深圳"),
            ["深圳", "暴雨", "交通中断", "应急响应"],
        )

    def test_account_store_encrypts_secrets_and_returns_masked_status(self):
        web_app.save_platform_account(
            self.platform,
            {
                "username": "tester",
                "password": "super-secret-password",
                "cookie": "SESSDATA=super-secret-cookie",
                "note": "private note",
            },
        )

        raw = str(self.store)
        self.assertNotIn("super-secret-password", raw)
        self.assertNotIn("SESSDATA=super-secret-cookie", raw)
        self.assertEqual(self.store["platforms"][self.platform]["password"]["scheme"], "dpapi")
        self.assertEqual(self.store["platforms"][self.platform]["cookie"]["scheme"], "dpapi")

        restored = web_app.decrypt_saved_accounts()[self.platform]
        self.assertEqual(restored["password"], "super-secret-password")
        self.assertEqual(restored["cookie"], "SESSDATA=super-secret-cookie")

        status = web_app.build_saved_account_statuses()[self.platform]
        self.assertTrue(status["password_saved"])
        self.assertTrue(status["cookie_saved"])
        self.assertNotIn("super-secret-password", str(status))
        self.assertNotIn("SESSDATA=super-secret-cookie", str(status))

    def test_account_store_refuses_weak_fallback_when_dpapi_fails(self):
        with patch.object(web_app, "_dpapi_protect", side_effect=OSError("test failure")):
            with self.assertRaisesRegex(RuntimeError, "DPAPI 加密失败"):
                web_app.save_platform_account(
                    self.platform,
                    {"cookie": "must-not-be-saved-with-weak-encryption"},
                )

        self.assertNotIn(self.platform, self.store["platforms"])
        self.assertNotIn("must-not-be-saved", str(self.store))

    def test_non_windows_account_store_refuses_to_save_secrets(self):
        with patch.object(web_app.os, "name", "posix"):
            with self.assertRaisesRegex(RuntimeError, "不支持 Windows DPAPI"):
                web_app.save_platform_account(
                    self.platform,
                    {"cookie": "must-not-be-saved-outside-windows"},
                )

        self.assertNotIn(self.platform, self.store["platforms"])
        self.assertNotIn("must-not-be-saved", str(self.store))

    def test_page_input_overrides_saved_cookie_and_clear_removes_account(self):
        web_app.save_platform_account(
            self.platform,
            {"username": "saved-user", "password": "saved-password", "cookie": "saved-cookie"},
        )

        merged = web_app.sanitize_accounts(
            {self.platform: {"cookie": "page-cookie"}},
            include_saved=True,
        )
        self.assertEqual(merged[self.platform]["username"], "saved-user")
        self.assertEqual(merged[self.platform]["cookie"], "page-cookie")

        web_app.clear_platform_account(self.platform)
        self.assertNotIn(self.platform, web_app.decrypt_saved_accounts())

    def test_combined_clear_links_account_browser_profile_and_diagnostics(self):
        class FakeBrowserManager:
            def __init__(self):
                self.cleared = []

            def clear_platform_data(self, platform):
                self.cleared.append(platform)
                return {"profile_trees_removed": 1}

        class FakeDiagnosticStore:
            def __init__(self):
                self.cleared = []

            def clear_platform(self, platform):
                self.cleared.append(platform)
                return 2

        web_app.save_platform_account(self.platform, {"cookie": "saved-cookie"})
        browser = FakeBrowserManager()
        diagnostics = FakeDiagnosticStore()
        with patch.object(web_app, "BROWSER_SESSION_MANAGER", browser):
            with patch.object(web_app, "DIAGNOSTIC_STORE", diagnostics):
                result = web_app.clear_platform_authorization(self.platform)

        self.assertNotIn(self.platform, web_app.decrypt_saved_accounts())
        self.assertEqual(browser.cleared, [self.platform])
        self.assertEqual(diagnostics.cleared, [self.platform])
        self.assertEqual(result["diagnostic_files_removed"], 2)

    def test_password_only_account_does_not_confirm_login(self):
        class FakeCrawler:
            def __init__(self, use_system_proxy=False, **kwargs):
                self.account = {}
                self.anti_crawl = type("Delay", (), {"delay": lambda *args, **kwargs: None})()

            def set_account(self, platform, username="", password="", cookie="", **kwargs):
                self.account = {"username": username, "password": password, "cookie": cookie, **kwargs}

            def test_social_platform(self, platform, keyword=""):
                return {
                    "platform": platform,
                    "status": "partial",
                    "reachable": True,
                    "login_confirmed": None,
                    "parsed_count": 0,
                    "error": "",
                    "evidence": "no cookie supplied",
                    "message": "可访问",
                }

        class DummyHandler:
            def __init__(self, payload):
                self.payload = payload
                self.response = None
                self.status = None

            def read_body_json(self):
                return self.payload

            def send_json(self, payload, status=200):
                self.response = payload
                self.status = status

        web_app.save_platform_account(self.platform, {"username": "tester", "password": "password-only"})
        handler = DummyHandler({"platform": self.platform, "account": {}})
        with patch.object(web_app, "NewsCrawler", FakeCrawler):
            web_app.WebUIHandler.handle_test_account(handler)

        self.assertEqual(handler.status, 200)
        self.assertTrue(handler.response["ok"])
        self.assertIsNone(handler.response["login_confirmed"])
        self.assertEqual(handler.response["login_error"], "missing cookie")
        self.assertIn("缺少 Cookie", handler.response["evidence"])

    @unittest.skip("Chrome 会话导入入口已移除，保留旧测试仅作历史占位")
    def legacy_import_chrome_session_handler_saves_encrypted_cookie(self):
        class DummyHandler:
            def __init__(self, payload):
                self.payload = payload
                self.response = None
                self.status = None

            def read_body_json(self):
                return self.payload

            def send_json(self, payload, status=200):
                self.response = payload
                self.status = status

        def fake_import(platform, profile="Default"):
            web_app.save_platform_account(platform, {"cookie": "chrome-cookie-secret"})
            return {
                "platform": platform,
                "profile": profile,
                "cookie_count": 3,
                "failed_decrypt": 0,
                "cookie_hint": "已保存，长度 20，末尾 cret",
            }

        handler = DummyHandler({"platform": self.platform, "profile": "Default"})
        with patch.object(web_app, "import_chrome_cookies_for_platform", fake_import):
            web_app.WebUIHandler.handle_account_import_chrome(handler)

        self.assertEqual(handler.status, 200)
        self.assertTrue(handler.response["ok"])
        self.assertNotIn("chrome-cookie-secret", str(handler.response))
        self.assertNotIn("chrome-cookie-secret", str(self.store))
        self.assertEqual(web_app.decrypt_saved_accounts()[self.platform]["cookie"], "chrome-cookie-secret")

    @unittest.skip("Chrome Cookie 数据库读取逻辑已移除")
    def legacy_chrome_cookie_reader_falls_back_when_cookie_db_is_locked(self):
        class FakeTemp:
            name = str(Path.cwd() / "data" / "fake_chrome_cookie_snapshot.db")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeConn:
            def execute(self, query):
                return self

            def fetchall(self):
                return [(".example.com", "sid", "plain-cookie", b"", 0, 0)]

            def close(self):
                pass

        locked = PermissionError("[WinError 32] file is used by another process")
        locked.winerror = 32
        with patch.object(web_app.tempfile, "NamedTemporaryFile", return_value=FakeTemp()):
            with patch.object(web_app.shutil, "copy2", side_effect=locked):
                with patch.object(web_app.sqlite3, "connect", return_value=FakeConn()) as connect:
                    rows, mode = web_app.read_chrome_cookie_rows(Path("C:/locked/Cookies"))

        self.assertEqual(mode, "immutable")
        self.assertTrue(connect.call_args.args[0].startswith("file:///"))
        self.assertIn("immutable=1", connect.call_args.args[0])
        self.assertEqual(rows[0][1], "sid")

    @unittest.skip("Chrome Cookie 数据库读取逻辑已移除")
    def legacy_chrome_cookie_reader_reports_actionable_error_when_fallback_fails(self):
        class FakeTemp:
            name = str(Path.cwd() / "data" / "fake_chrome_cookie_snapshot.db")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        locked = PermissionError("[WinError 32] file is used by another process")
        locked.winerror = 32
        with patch.object(web_app.tempfile, "NamedTemporaryFile", return_value=FakeTemp()):
            with patch.object(web_app.shutil, "copy2", side_effect=locked):
                with patch.object(
                    web_app.sqlite3,
                    "connect",
                    side_effect=sqlite3.OperationalError("unable to open database file"),
                ):
                    with self.assertRaises(RuntimeError) as raised:
                        web_app.read_chrome_cookie_rows(Path("C:/locked/Cookies"))

        self.assertIn("关闭所有 Chrome 窗口", str(raised.exception))
        self.assertIn("unable to open database file", str(raised.exception))


    def test_browser_session_save_encrypts_storage_state(self):
        secret_cookie = "browser-cookie-secret"
        storage_state = {
            "cookies": [{"name": "sid", "value": secret_cookie, "domain": ".weibo.com"}],
            "origins": [{"origin": "https://weibo.com", "localStorage": [{"name": "token", "value": "secret-storage"}]}],
        }
        web_app.save_platform_browser_session(
            self.platform,
            {
                "storage_state": storage_state,
                "cookie_header": f"sid={secret_cookie}",
                "cookie_count": 1,
                "origin_count": 1,
                "has_local_storage": True,
                "login_confirmed": True,
                "evidence": "test marker",
            },
        )

        raw = str(self.store)
        self.assertNotIn(secret_cookie, raw)
        self.assertNotIn("secret-storage", raw)

        restored = web_app.decrypt_saved_accounts()[self.platform]
        self.assertEqual(restored["browser_cookie"], f"sid={secret_cookie}")
        self.assertIn("secret-storage", restored["browser_session"])

        status = web_app.build_saved_account_statuses()[self.platform]
        self.assertTrue(status["browser_session_saved"])
        self.assertTrue(status["browser_cookie_saved"])
        self.assertTrue(status["browser_login_confirmed"])
        self.assertNotIn(secret_cookie, str(status))

    def test_saved_manual_cookie_takes_priority_over_browser_session(self):
        web_app.save_platform_browser_session(
            self.platform,
            {
                "storage_state": {"cookies": []},
                "cookie_header": "sid=browser-cookie",
                "cookie_count": 1,
            },
        )
        web_app.save_platform_account(self.platform, {"cookie": "sid=manual-cookie"})

        merged = web_app.sanitize_accounts({}, include_saved=True)
        self.assertEqual(merged[self.platform]["cookie"], "sid=manual-cookie")
        self.assertEqual(merged[self.platform]["session_mode"], "manual_cookie")

    def test_browser_session_handler_saves_encrypted_cookie(self):
        class DummyHandler:
            def __init__(self, payload):
                self.payload = payload
                self.response = None
                self.status = None

            def read_body_json(self):
                return self.payload

            def send_json(self, payload, status=200):
                self.response = payload
                self.status = status

        def fake_save(platform):
            return {
                "platform": platform,
                "storage_state": {
                    "cookies": [{"name": "sid", "value": "browser-cookie-secret", "domain": ".weibo.com"}],
                    "origins": [],
                },
                "cookie_header": "sid=browser-cookie-secret",
                "cookie_count": 1,
                "origin_count": 0,
                "has_local_storage": False,
                "login_confirmed": True,
                "evidence": "test marker",
            }

        handler = DummyHandler({"platform": self.platform})
        with patch.object(web_app.BROWSER_SESSION_MANAGER, "save_session", fake_save):
            web_app.WebUIHandler.handle_browser_login_save(handler)

        self.assertEqual(handler.status, 200)
        self.assertTrue(handler.response["ok"])
        self.assertNotIn("browser-cookie-secret", str(handler.response))
        self.assertNotIn("browser-cookie-secret", str(self.store))
        self.assertEqual(
            web_app.decrypt_saved_accounts()[self.platform]["browser_cookie"],
            "sid=browser-cookie-secret",
        )
        last_test = self.store["platforms"][self.platform]["last_test"]
        self.assertEqual(last_test["status"], "login_only")
        self.assertTrue(last_test["login_passed"])
        self.assertFalse(last_test["read_passed"])
        self.assertFalse(last_test["passed"])

    def test_saved_platform_test_keeps_separate_acceptance_states(self):
        web_app.save_platform_account(self.platform, {"cookie": "saved-cookie"})

        web_app.save_account_test_result(
            self.platform,
            {
                "status": "collection_only",
                "passed": False,
                "read_passed": True,
                "login_passed": False,
                "login_confirmed": None,
                "parsed_count": 12,
                "message": "采集通过但登录未确认",
            },
        )

        last_test = web_app.build_saved_account_statuses()[self.platform]["last_test"]
        self.assertFalse(last_test["passed"])
        self.assertTrue(last_test["read_passed"])
        self.assertFalse(last_test["login_passed"])
        self.assertEqual(last_test["parsed_count"], 12)

    def test_chrome_import_entrypoint_removed(self):
        self.assertFalse(hasattr(web_app, "import_chrome_cookies_for_platform"))
        self.assertFalse(hasattr(web_app.WebUIHandler, "handle_account_import_chrome"))


if __name__ == "__main__":
    unittest.main()
