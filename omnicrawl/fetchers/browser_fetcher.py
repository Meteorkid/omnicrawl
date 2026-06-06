"""浏览器抓取器 — 基于 Playwright，支持 JS 渲染"""

from __future__ import annotations

import time
from typing import Optional
from omnicrawl.fetchers.base import BaseFetcher, FetchMode, FetchResult
from omnicrawl.utils.logger import get_logger

logger = get_logger("browser_fetcher")


class BrowserFetcher(BaseFetcher):
    """基于 Playwright 的浏览器抓取器

    特点：
    - 完整 JS 渲染
    - 支持登录、滚动、点击等交互
    - 中等隐蔽性

    用法:
        async with BrowserFetcher() as fetcher:
            result = await fetcher.fetch("https://spa-site.com")
    """

    mode = FetchMode.BROWSER

    def __init__(
        self,
        headless: bool = True,
        user_agent: Optional[str] = None,
        viewport: dict = None,
    ):
        self._headless = headless
        self._user_agent = user_agent
        self._viewport = viewport or {"width": 1920, "height": 1080}
        self._playwright = None
        self._browser = None

    async def _ensure_browser(self):
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self._headless,
            )

    async def create_page(self, **context_kwargs):
        """创建独立的浏览器页面（公开 API）

        返回 (context, page) 元组，调用方负责关闭 context。
        用于 SmartSpider 等需要独立页面的场景。

        Args:
            **context_kwargs: 传递给 browser.new_context() 的参数
        """
        await self._ensure_browser()
        context = await self._browser.new_context(**context_kwargs)
        page = await context.new_page()
        return context, page

    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Optional[dict] = None,
        proxy: Optional[str] = None,
        timeout: float = 30.0,
        wait_for: Optional[str] = None,  # 等待特定选择器出现
        **kwargs,
    ) -> FetchResult:
        await self._ensure_browser()
        start = time.time()

        context_kwargs = {
            "viewport": self._viewport,
        }
        if self._user_agent:
            context_kwargs["user_agent"] = self._user_agent
        if proxy:
            context_kwargs["proxy"] = {"server": proxy}
        if headers:
            context_kwargs["extra_http_headers"] = headers

        context = await self._browser.new_context(**context_kwargs)
        try:
            page = await context.new_page()
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))

            if wait_for:
                await page.wait_for_selector(wait_for, timeout=int(timeout * 1000))

            html = await page.content()
            elapsed = time.time() - start

            status = resp.status if resp else 0
            resp_headers = dict(resp.headers) if resp else {}
            blocked = status in (403, 429)

            return FetchResult(
                url=page.url,
                status_code=status,
                html=html,
                headers=resp_headers,
                cookies={c["name"]: c["value"] for c in await context.cookies()},
                mode_used=self.mode,
                elapsed=elapsed,
                blocked=blocked,
            )
        finally:
            await context.close()

    async def close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def __aexit__(self, *args):
        await self.close()
