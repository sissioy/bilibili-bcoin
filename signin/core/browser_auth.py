"""
从本机浏览器 Profile 读取 B 站登录态
"""
import time
from pathlib import Path
from typing import Dict
from loguru import logger

from signin.core.config import BrowserAuthConfig
from signin.core.exceptions import AuthenticationError, ConfigurationError


class BilibiliBrowserAuth:
    """读取本机 B 站 Cookie"""

    REQUIRED_COOKIES = {
        "SESSDATA": "SESSDATA",
        "bili_jct": "BILI_JCT",
        "DedeUserID": "DEDEUSERID",
    }

    def __init__(self, config: BrowserAuthConfig):
        self.config = config

    def get_cookies(self) -> Dict[str, str]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise ConfigurationError("请先安装 playwright: pip install -r requirements.txt") from e

        playwright = sync_playwright().start()
        try:
            if self.config.profileDir:
                return self._get_cookies_from_profile(playwright)
            return self._get_cookies_from_cdp(playwright)
        finally:
            playwright.stop()

    def _get_cookies_from_profile(self, playwright) -> Dict[str, str]:
        profile_dir = Path(self.config.profileDir).expanduser()
        profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir),
                headless=False
            )
        except Exception as e:
            raise ConfigurationError(
                "无法启动 Chromium，请先执行: python -m playwright install chromium"
            ) from e
        try:
            page = self._open_auth_page(context)
            cookies = self._read_context_cookies(context)
            if self._has_required_cookies(cookies):
                return self._normalize_cookies(cookies)

            logger.info("独立浏览器 Profile 中缺少 B站登录态，请在打开的浏览器中完成登录")
            return self._wait_for_cookies(context, page)
        except Exception as e:
            if isinstance(e, (AuthenticationError, ConfigurationError)):
                raise
            raise ConfigurationError(
                f"无法从独立浏览器 Profile 获取 B站登录态: {self.config.profileDir}",
            ) from e
        finally:
            context.close()

    def _get_cookies_from_cdp(self, playwright) -> Dict[str, str]:
        page = None
        try:
            browser = playwright.chromium.connect_over_cdp(self.config.cdpUrl)
            context = self._get_context(browser)
            page = self._open_auth_page(context)
            cookies = self._read_context_cookies(context)
            if not self._has_required_cookies(cookies):
                return self._wait_for_cookies(context, page)
            return self._normalize_cookies(cookies)
        except Exception as e:
            if isinstance(e, (AuthenticationError, ConfigurationError)):
                raise
            raise ConfigurationError(
                f"无法从 Chrome 获取 B站登录态，请确认 Chrome 已用远程调试端口启动: {self.config.cdpUrl}",
            ) from e
        finally:
            if page is not None:
                page.close()

    def _open_auth_page(self, context):
        page = context.new_page()
        logger.info(f"打开 B站页面刷新浏览器登录态: {self.config.authUrl}")
        page.goto(self.config.authUrl, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1000)
        return page

    def _wait_for_cookies(self, context, page=None) -> Dict[str, str]:
        page = page or (context.pages[0] if context.pages else context.new_page())
        end_time = time.monotonic() + self.config.authWaitSeconds
        while time.monotonic() < end_time:
            cookies = self._read_context_cookies(context)
            if self._has_required_cookies(cookies):
                return self._normalize_cookies(cookies)
            page.wait_for_timeout(1000)

        raise AuthenticationError("浏览器中未检测到完整 B站登录态", platform="bilibili")

    def _get_context(self, browser):
        if not browser.contexts:
            raise ConfigurationError("Chrome 未提供可用的浏览器上下文")
        return browser.contexts[0]

    def _read_context_cookies(self, context) -> Dict[str, str]:
        urls = [
            self.config.authUrl,
            "https://api.bilibili.com",
            "https://pay.bilibili.com",
        ]
        return {
            cookie["name"]: cookie["value"]
            for cookie in context.cookies(urls)
            if cookie.get("name") and cookie.get("value")
        }

    def _has_required_cookies(self, cookies: Dict[str, str]) -> bool:
        return all(name in cookies for name in self.REQUIRED_COOKIES)

    def _normalize_cookies(self, cookies: Dict[str, str]) -> Dict[str, str]:
        missing = [name for name in self.REQUIRED_COOKIES if name not in cookies]
        if missing:
            logger.error(f"浏览器中缺少 B站登录 Cookie: {', '.join(missing)}")
            raise AuthenticationError("浏览器中未检测到完整 B站登录态", platform="bilibili")

        normalized = dict(cookies)
        normalized.update({
            target: cookies[source]
            for source, target in self.REQUIRED_COOKIES.items()
        })
        return normalized
