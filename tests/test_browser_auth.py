import tempfile
import unittest
from unittest.mock import patch

from signin.core.browser_auth import BilibiliBrowserAuth
from signin.core.config import BrowserAuthConfig
from signin.core.exceptions import ConfigurationError


def make_cookie_list(values):
    return [
        {"name": name, "value": value}
        for name, value in values.items()
    ]


class FakePage:
    def __init__(self, context):
        self.context = context
        self.goto_calls = []
        self.closed = False

    def goto(self, url, wait_until=None, timeout=None):
        self.context.events.append("goto")
        self.goto_calls.append((url, wait_until, timeout))
        if self.context.cookies_after_goto is not None:
            self.context.cookie_values = self.context.cookies_after_goto

    def wait_for_timeout(self, timeout):
        self.context.events.append(f"wait:{timeout}")

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, cookie_values, cookies_after_goto=None):
        self.cookie_values = cookie_values
        self.cookies_after_goto = cookies_after_goto
        self.events = []
        self.closed = False
        self.pages = [FakePage(self)]

    def new_page(self):
        page = FakePage(self)
        self.pages.append(page)
        return page

    def cookies(self, urls):
        self.events.append("cookies")
        self.cookie_urls = urls
        return make_cookie_list(self.cookie_values)

    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, context):
        self.context = context
        self.profile_dir = None
        self.headless = None

    def launch_persistent_context(self, profile_dir, headless=False):
        self.profile_dir = profile_dir
        self.headless = headless
        return self.context


class FakePlaywright:
    def __init__(self, context):
        self.chromium = FakeChromium(context)


class BilibiliBrowserAuthTest(unittest.TestCase):
    def test_profile_launch_failure_is_configuration_error(self):
        playwright = FakePlaywright(FakeContext({}))

        def fail(profile_dir, headless=False):
            raise RuntimeError("executable missing")

        playwright.chromium.launch_persistent_context = fail

        with tempfile.TemporaryDirectory() as profile_dir:
            config = BrowserAuthConfig(profileDir=profile_dir)
            with self.assertRaises(ConfigurationError):
                BilibiliBrowserAuth(config)._get_cookies_from_profile(playwright)

    def test_profile_opens_auth_url_before_reading_cookies(self):
        old_cookies = {
            "DedeUserID": "old-mid",
            "SESSDATA": "old-sess",
            "bili_jct": "old-jct",
        }
        new_cookies = {
            "DedeUserID": "new-mid",
            "SESSDATA": "new-sess",
            "bili_jct": "new-jct",
        }
        context = FakeContext(old_cookies, cookies_after_goto=new_cookies)

        with tempfile.TemporaryDirectory() as profile_dir:
            config = BrowserAuthConfig(
                enabled=True,
                profileDir=profile_dir,
                authUrl="https://www.bilibili.com",
            )
            result = BilibiliBrowserAuth(config)._get_cookies_from_profile(FakePlaywright(context))

        self.assertLess(context.events.index("goto"), context.events.index("cookies"))
        self.assertEqual(
            result,
            {
                "DEDEUSERID": "new-mid",
                "SESSDATA": "new-sess",
                "BILI_JCT": "new-jct",
            },
        )
        self.assertTrue(context.closed)

    def test_profile_waits_for_login_when_required_cookies_are_missing(self):
        context = FakeContext({"SESSDATA": "sess"})
        expected = {
            "DEDEUSERID": "new-mid",
            "SESSDATA": "new-sess",
            "BILI_JCT": "new-jct",
        }

        with tempfile.TemporaryDirectory() as profile_dir:
            config = BrowserAuthConfig(
                enabled=True,
                profileDir=profile_dir,
                authUrl="https://www.bilibili.com",
            )
            auth = BilibiliBrowserAuth(config)
            with patch.object(auth, "_wait_for_cookies", return_value=expected) as wait:
                result = auth._get_cookies_from_profile(FakePlaywright(context))

        wait.assert_called_once_with(context, context.pages[-1])
        self.assertEqual(result, expected)
        self.assertTrue(context.closed)

    def test_cdp_uses_and_closes_a_new_page(self):
        context = FakeContext({
            "DedeUserID": "mid",
            "SESSDATA": "sess",
            "bili_jct": "jct",
        })
        original_page = context.pages[0]
        browser = type("Browser", (), {"contexts": [context]})()
        playwright = FakePlaywright(context)
        playwright.chromium.connect_over_cdp = lambda url: browser

        config = BrowserAuthConfig(cdpUrl="http://127.0.0.1:9222")
        result = BilibiliBrowserAuth(config)._get_cookies_from_cdp(playwright)

        self.assertEqual(result["DEDEUSERID"], "mid")
        self.assertFalse(original_page.closed)
        self.assertTrue(context.pages[-1].closed)

    def test_cdp_connection_failure_is_configuration_error(self):
        playwright = FakePlaywright(FakeContext({}))

        def fail(url):
            raise RuntimeError("connection refused")

        playwright.chromium.connect_over_cdp = fail

        with self.assertRaises(ConfigurationError):
            BilibiliBrowserAuth(BrowserAuthConfig())._get_cookies_from_cdp(playwright)


if __name__ == "__main__":
    unittest.main()
