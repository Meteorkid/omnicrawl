"""Camoufox 抓取器 — 反检测浏览器，绕过 JS 环境检测"""

from __future__ import annotations

import time
from typing import Optional
from omnicrawl.fetchers.base import BaseFetcher, FetchMode, FetchResult
from omnicrawl.utils.logger import get_logger

logger = get_logger("camoufox_fetcher")

__all__ = ["CamoufoxFetcher"]


class CamoufoxFetcher(BaseFetcher):
    """基于 Camoufox 的反检测浏览器抓取器

    特点：
    - Firefox 内核，原生级指纹注入（非 JS 注入）
    - 浏览器实例复用，批量抓取不重复启动
    - 自动随机化 OS/设备/字体/WebGL/屏幕等指纹
    - 人类化鼠标轨迹
    - GeoIP 自动匹配代理地理位置
    - 指纹一致性检查（所有信号指向同一身份）

    用法:
        async with CamoufoxFetcher() as fetcher:
            result = await fetcher.fetch("https://51job.com")

        # 指定身份
        from omnicrawl import FingerprintConsistency
        fc = FingerprintConsistency()
        identity = fc.get_identity("chrome_macos_m1")
        async with CamoufoxFetcher(identity=identity) as fetcher:
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
        identity: Optional[object] = None,  # BrowserIdentity
        proxy: Optional[str] = None,
    ):
        self._headless = headless
        self._humanize = humanize
        self._block_webrtc = block_webrtc
        self._block_images = block_images
        self._locale = locale
        self._os = os
        self._geoip = geoip
        self._identity = identity
        self._proxy = proxy
        self._camoufox_class = None
        self._context_manager = None
        self._browser = None
        self._js_overrides: dict[str, str] = {}

    async def _ensure_browser(self):
        """确保浏览器实例存在（复用）"""
        if self._browser is not None:
            return

        # 指纹一致性：如果没有指定身份，自动选一个
        fc = None
        if self._identity is None:
            try:
                from omnicrawl.anti_detect.fingerprint_consistency import FingerprintConsistency
                fc = FingerprintConsistency()
                self._identity = fc.random_identity()
                logger.info("自动选择指纹身份: %s (%s)", self._identity.os, self._identity.browser_name)
            except Exception as e:
                logger.debug("指纹一致性模块不可用，跳过: %s", e)

        # 从身份中提取 JS 覆盖（仅 navigator 相关，webgl/canvas 由 Camoufox 原生处理）
        if self._identity is not None:
            try:
                if fc is None:
                    from omnicrawl.anti_detect.fingerprint_consistency import FingerprintConsistency
                    fc = FingerprintConsistency()
                all_overrides = fc.get_js_overrides(self._identity)
                self._js_overrides = {
                    k: v for k, v in all_overrides.items()
                    if k.startswith("navigator.")
                }
            except Exception:
                pass

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
        if self._proxy:
            kwargs["proxy"] = {"server": self._proxy}
        # 优先使用身份的 OS，其次用构造参数
        effective_os = self._os or (self._identity.os if self._identity else None)
        if effective_os:
            kwargs["os"] = effective_os

        self._context_manager = self._camoufox_class(**kwargs)
        try:
            self._browser = await self._context_manager.__aenter__()
            logger.info("Camoufox 浏览器已启动 (identity=%s)", self._identity.os if self._identity else "auto")
        except Exception:
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

            # 注入指纹一致性 JS 覆盖
            if self._js_overrides:
                js_code = self._build_fingerprint_js(self._js_overrides)
                try:
                    await page.add_init_script(js_code)
                except Exception as e:
                    logger.debug("指纹 JS 注入失败（不影响主流程）: %s", e)

            if headers:
                await page.set_extra_http_headers(headers)

            resp = await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))

            if wait_for:
                await page.wait_for_selector(wait_for, timeout=int(timeout * 1000))
            else:
                try:
                    await page.wait_for_load_state("networkidle", timeout=int(min(timeout, 30) * 1000))
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

    @staticmethod
    def _build_fingerprint_js(overrides: dict[str, str]) -> str:
        """将指纹覆盖字典转为 JS 注入代码"""
        lines = ["(function(){"]
        for prop, value in overrides.items():
            if prop.startswith("navigator."):
                key = prop.split(".", 1)[1]
                lines.append(
                    f'Object.defineProperty(navigator,"{key}",{{get:function(){{return {value};}}}});'
                )
            elif prop.startswith("webgl."):
                # Camoufox 原生处理 WebGL 指纹，无需 JS 注入
                logger.debug("跳过 webgl.* JS 覆盖（Camoufox 原生处理）: %s", prop)
            elif prop.startswith("canvas."):
                # Camoufox 原生处理 Canvas 指纹噪声，无需 JS 注入
                logger.debug("跳过 canvas.* JS 覆盖（Camoufox 原生处理）: %s", prop)
        lines.append("})();")
        return "\n".join(lines)

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
