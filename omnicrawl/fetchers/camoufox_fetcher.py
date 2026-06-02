"""Camoufox 抓取器 — 反检测浏览器，绕过 JS 环境检测"""

from __future__ import annotations

import time
from typing import Optional
from omnicrawl.fetchers.base import BaseFetcher, FetchMode, FetchResult
from omnicrawl.utils.logger import get_logger

logger = get_logger("camoufox_fetcher")


class CamoufoxFetcher(BaseFetcher):
    """基于 Camoufox 的反检测浏览器抓取器

    特点：
    - Firefox 内核，原生级指纹注入（非 JS 注入）
    - 浏览器实例复用，批量抓取不重复启动
    - 自动随机化 OS/设备/字体/WebGL/屏幕等指纹
    - 人类化鼠标轨迹
    - GeoIP 自动匹配代理地理位置

    用法:
        async with CamoufoxFetcher() as fetcher:
            result = await fetcher.fetch("https://51job.com")
    """

    mode = FetchMode.CAMOUFOX

    def __init__(
        self,
        headless: bool = True,
        humanize: bool = True,
        block_webrtc: bool = True,
        block_images: bool = False,
        locale: str = "zh-CN",
        os: Optional[str] = None,
        geoip: bool = True,
    ):
        self._headless = headless
        self._humanize = humanize
        self._block_webrtc = block_webrtc
        self._block_images = block_images
        self._locale = locale
        self._os = os
        self._geoip = geoip
        self._camoufox_class = None
        self._context_manager = None
        self._browser = None

    async def _ensure_browser(self):
        """确保浏览器实例存在（复用）"""
        if self._browser is not None:
            return

        if self._camoufox_class is None:
            from camoufox.async_api import AsyncCamoufox
            self._camoufox_class = AsyncCamoufox

        kwargs = {
            "headless": self._headless,
            "humanize": self._humanize,
            "block_webrtc": self._block_webrtc,
            "block_images": self._block_images,
            "locale": self._locale,
            "geoip": self._geoip,
        }
        if self._os:
            kwargs["os"] = self._os

        self._context_manager = self._camoufox_class(**kwargs)
        try:
            self._browser = await self._context_manager.__aenter__()
            logger.info("Camoufox 浏览器已启动")
        except Exception:
            # __aenter__ 失败时清理 _context_manager
            self._context_manager = None
            raise

    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Optional[dict] = None,
        proxy: Optional[str] = None,
        timeout: float = 60.0,
        wait_for: Optional[str] = None,
        **kwargs,
    ) -> FetchResult:
        await self._ensure_browser()
        start = time.time()
        page = None

        try:
            page = await self._browser.new_page()

            if headers:
                await page.set_extra_http_headers(headers)

            resp = await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))

            if wait_for:
                await page.wait_for_selector(wait_for, timeout=int(timeout * 1000))
            else:
                try:
                    await page.wait_for_load_state("networkidle", timeout=min(int(timeout * 1000), 10000))
                except Exception:
                    pass

            html = await page.content()
            elapsed = time.time() - start

            status = resp.status if resp else 0
            resp_headers = dict(resp.headers) if resp else {}
            cookies_list = await page.context.cookies()
            cookies = {c["name"]: c["value"] for c in cookies_list}
            blocked = status in (403, 429)

            return FetchResult(
                url=resp.url if resp else url,
                status_code=status,
                html=html,
                headers=resp_headers,
                cookies=cookies,
                mode_used=self.mode,
                elapsed=elapsed,
                blocked=blocked,
            )
        except Exception as e:
            logger.error(f"Camoufox 请求失败: {url} - {e}")
            raise
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass  # 页面关闭失败不影响主流程

    async def close(self):
        """关闭浏览器实例"""
        if self._context_manager:
            try:
                await self._context_manager.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Camoufox 浏览器关闭异常: {e}")
            self._browser = None
            self._context_manager = None
            logger.info("Camoufox 浏览器已关闭")

    async def __aexit__(self, *args):
        await self.close()
