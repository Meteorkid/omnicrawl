"""隐身抓取器 — 基于 Scrapling StealthyFetcher，最强反检测"""

from __future__ import annotations

import time
from typing import Optional
from omnicrawl.fetchers.base import BaseFetcher, FetchMode, FetchResult
from omnicrawl.utils.logger import get_logger

logger = get_logger("stealth_fetcher")


class StealthFetcher(BaseFetcher):
    """基于 Scrapling 的隐身抓取器

    特点：
    - 自动绕过 Cloudflare Turnstile
    - Canvas/WebRTC/WebGL 指纹防护
    - Playwright 指纹清除
    - 最强反检测能力

    用法:
        async with StealthFetcher() as fetcher:
            result = await fetcher.fetch("https://cloudflare-site.com")
    """

    mode = FetchMode.STEALTH

    def __init__(
        self,
        headless: bool = True,
        block_webrtc: bool = True,
        hide_canvas: bool = True,
        block_ads: bool = True,
        google_search: bool = True,
        real_chrome: bool = False,
    ):
        self._headless = headless
        self._block_webrtc = block_webrtc
        self._hide_canvas = hide_canvas
        self._block_ads = block_ads
        self._google_search = google_search
        self._real_chrome = real_chrome
        self._fetcher = None

    def _ensure_fetcher(self):
        if self._fetcher is None:
            from scrapling.fetchers import StealthyFetcher
            self._fetcher = StealthyFetcher

    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Optional[dict] = None,
        proxy: Optional[str] = None,
        timeout: float = 60.0,
        solve_cloudflare: bool = True,
        wait_for: Optional[str] = None,
        **kwargs,
    ) -> FetchResult:
        self._ensure_fetcher()
        start = time.time()

        try:
            # 使用异步 API，避免在 asyncio 循环中使用 sync Playwright
            response = await self._fetcher.async_fetch(
                url,
                headless=self._headless,
                block_webrtc=self._block_webrtc,
                hide_canvas=self._hide_canvas,
                block_ads=self._block_ads,
                google_search=self._google_search,
                real_chrome=self._real_chrome,
                solve_cloudflare=solve_cloudflare,
                timeout=timeout,
                proxy=proxy,
                extra_headers=headers,
            )

            elapsed = time.time() - start
            status = getattr(response, "status", 0)
            blocked = status in (403, 429)

            # Scrapling Response: text 可能为空，优先用 html_content
            html = (
                (response.text if response.text else None)
                or getattr(response, "html_content", None)
                or (response.body.decode("utf-8") if isinstance(response.body, bytes) else str(response.body))
                or ""
            )
            resp_headers = dict(getattr(response, "headers", {}))
            cookies = dict(getattr(response, "cookies", {}))

            return FetchResult(
                url=getattr(response, "url", url),
                status_code=status,
                html=html,
                headers=resp_headers,
                cookies=cookies,
                mode_used=self.mode,
                elapsed=elapsed,
                blocked=blocked,
            )
        except Exception as e:
            logger.error(f"隐身请求失败: {url} - {e}")
            raise

    async def close(self):
        pass  # Scrapling 的 fetcher 是无状态的

    async def __aexit__(self, *args):
        await self.close()
