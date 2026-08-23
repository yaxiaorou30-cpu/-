import unittest

import web_app


class SiteSessionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (web_app.WEB_DIR / "index.html").read_text(encoding="utf-8")
        cls.javascript = (web_app.WEB_DIR / "static" / "app.js").read_text(encoding="utf-8")
        cls.css = (web_app.WEB_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    def test_single_url_site_session_card_is_present(self):
        self.assertEqual(self.html.count('id="siteSessionCard"'), 1)
        self.assertEqual(self.html.count('id="siteLoginUrl"'), 1)
        self.assertIn('id="siteSessionStatus"', self.html)
        self.assertIn('aria-live="polite"', self.html)
        for element_id in (
            "openSiteLoginBtn",
            "saveSiteSessionBtn",
            "closeSiteLoginBtn",
            "clearSiteSessionBtn",
        ):
            self.assertEqual(self.html.count(f'id="{element_id}"'), 1)

        card = self.html[
            self.html.index('id="siteSessionCard"') : self.html.index('id="accountGrid"')
        ]
        self.assertIn('type="url"', card)
        self.assertIn("同一域名再次保存会覆盖原会话", card)
        self.assertNotIn("账号切换", card)
        self.assertNotIn("profile_id", card)

    def test_site_actions_reuse_existing_api_with_site_url(self):
        self.assertIn("siteSessions: {}", self.javascript)
        self.assertIn("options.site_sessions || {}", self.javascript)
        self.assertIn('requestJson("/api/browser-login/start"', self.javascript)
        self.assertIn('requestJson("/api/browser-login/save"', self.javascript)
        self.assertIn('requestJson("/api/browser-login/close"', self.javascript)
        self.assertIn('requestJson("/api/accounts/clear"', self.javascript)
        self.assertGreaterEqual(self.javascript.count("JSON.stringify({ site_url: siteUrl })"), 4)
        self.assertNotIn('JSON.stringify({ site_url: siteUrl, profile:', self.javascript)

    def test_site_session_card_shows_when_login_must_be_refreshed(self):
        self.assertIn("saved.needs_relogin", self.javascript)
        self.assertIn(
            "const needsRelogin = saved.needs_relogin === true;",
            self.javascript,
        )
        self.assertIn("需要重新登录", self.javascript)
        self.assertIn("account-badge.needs-login", self.css)
        refresh_start = self.javascript.index("async function refreshAccountStatuses()")
        refresh_end = self.javascript.index("async function openLoginPage", refresh_start)
        refresh = self.javascript[refresh_start:refresh_end]
        self.assertIn("state.siteSessions = result.site_sessions || {};", refresh)
        self.assertIn("renderSiteSessionStatus();", refresh)

    def test_account_workspace_stacks_on_narrow_screens(self):
        mobile = self.css[self.css.index("@media (max-width: 820px)") :]
        single_column = mobile[mobile.index(".field-grid,") : mobile.index("{", mobile.index(".field-grid,"))]
        self.assertIn(".account-workspace", single_column)


if __name__ == "__main__":
    unittest.main()
