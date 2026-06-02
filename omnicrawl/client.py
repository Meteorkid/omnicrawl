"""OmniClient — 统一爬虫入口

整合三层抓取策略（HTTP → Browser → Stealth），自动降级，代理轮换，智能限速。
"""

from __future__ import annotations

import asyncio
from typing import Optional

from omnicrawl.fetchers.base import FetchMode, FetchResult
from omnicrawl.fetchers.http_fetcher import HttpFetcher
from omnicrawl.fetchers.browser_fetcher import BrowserFetcher
from omnicrawl.fetchers.camoufox_fetcher import CamoufoxFetcher
from omnicrawl.fetchers.stealth_fetcher import StealthFetcher
from omnicrawl.fingerprint.tls import TLSFingerprint
from omnicrawl.proxy.rotator import ProxyRotator
from omnicrawl.anti_detect.rate_limiter import RateLimiter
from omnicrawl.anti_detect.waf_bypass import WAFBypass
from omnicrawl.parser.markdown import MarkdownConverter
from omnicrawl.parser.html_parser import HTMLParser
from omnicrawl.utils.logger import get_logger

logger = get_logger("client")

# 被封时的降级顺序（从快到慢，从弱到强）
FALLBACK_ORDER = [FetchMode.HTTP, FetchMode.BROWSER, FetchMode.CAMOUFOX, FetchMode.STEALTH]


class OmniClient:
    """OmniCrawl 统一爬虫客户端

    核心特性：
    - 三层抓取策略自动降级（HTTP → Browser → Stealth）
    - TLS 指纹伪装（37+ 浏览器指纹）
    - 代理轮换 + 智能限速
    - WAF 绕过策略引擎
    - LLM 友好 Markdown 输出

    用法:
        # 基础用法
        client = OmniClient()
        response = await client.get("https://example.com")
        print(response.markdown)

        # 指定模式
        client = OmniClient(mode=FetchMode.STEALTH)

        # 带代理
        client = OmniClient(
            proxy_pool=["http://proxy1:8080", "http://proxy2:8080"],
        )

        # WAF 绕过模式
        client = OmniClient(waf="aliyun_waf")

        # 批量抓取
        results = await client.batch(urls, concurrency=5)
    """

    def __init__(
        self,
        mode: FetchMode = FetchMode.AUTO,
        fingerprint: str = "chrome",
        proxy_pool: Optional[list[str]] = None,
        waf: Optional[str] = None,
        min_delay: float = 1.0,
        max_retries: int = 2,
        max_concurrent: int = 10,
        auto_fallback: bool = True,
    ):
        self._mode = mode
        self._max_retries = max_retries
        self._auto_fallback = auto_fallback

        # TLS 指纹
        self._tls = TLSFingerprint(fingerprint)

        # WAF 策略
        self._waf = WAFBypass(waf) if waf else None
        if self._waf:
            self._tls.set(self._waf.get_tls_fingerprint())
            min_delay = max(min_delay, self._waf.get_min_delay())

        # 代理轮换
        self._proxy_rotator = ProxyRotator(proxy_pool) if proxy_pool else None

        # 智能限速
        self._rate_limiter = RateLimiter(min_delay=min_delay, max_concurrent=max_concurrent)

        # Markdown 转换器
        self._converter = MarkdownConverter()

        # 抓取器缓存
        self._fetchers: dict[FetchMode, object] = {}

    def _get_fetcher(self, mode: FetchMode):
        """获取或创建抓取器"""
        if mode not in self._fetchers:
            fp = self._tls.get()
            if mode == FetchMode.HTTP:
                self._fetchers[mode] = HttpFetcher(fingerprint=fp)
            elif mode == FetchMode.BROWSER:
                self._fetchers[mode] = BrowserFetcher()
            elif mode == FetchMode.CAMOUFOX:
                self._fetchers[mode] = CamoufoxFetcher()
            elif mode == FetchMode.STEALTH:
                self._fetchers[mode] = StealthFetcher()
        return self._fetchers[mode]

    def _get_proxy(self) -> Optional[str]:
        """获取下一个代理"""
        if self._proxy_rotator:
            return self._proxy_rotator.next()
        return None

    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        mode: Optional[FetchMode] = None,
        headers: Optional[dict] = None,
        proxy: Optional[str] = None,
        timeout: float = 30.0,
        **kwargs,
    ) -> FetchResult:
        """通用抓取方法（支持 GET/POST 等所有 HTTP 方法）

        Args:
            url: 目标 URL
            method: HTTP 方法（GET/POST/PUT/DELETE 等）
            mode: 指定抓取模式，None 则使用客户端默认模式
            headers: 自定义请求头
            proxy: 指定代理，None 则使用代理轮换器
            timeout: 超时时间（秒）

        Returns:
            FetchResult 包含 HTML、Markdown、状态等
        """
        target_mode = mode or self._mode
        if target_mode == FetchMode.AUTO and self._waf:
            # 有 WAF 配置时，使用推荐模式
            target_mode = self._waf.get_recommended_mode()
        elif target_mode == FetchMode.AUTO:
            target_mode = FetchMode.HTTP  # 默认从最快的开始

        proxy = proxy or self._get_proxy()
        await self._rate_limiter.wait(url)

        result = await self._fetch_with_retry(
            url,
            mode=target_mode,
            headers=headers,
            proxy=proxy,
            timeout=timeout,
            **kwargs,
        )

        # 填充 Markdown
        if not result.markdown and result.html:
            result.markdown = self._converter.convert(result.html)

        # 填充纯文本
        if not result.text and result.html:
            parser = HTMLParser(result.html)
            result.text = parser.text()

        # 更新限速器状态
        if result.blocked:
            self._rate_limiter.report_blocked(url)
        else:
            self._rate_limiter.report_success(url)

        return result

    async def get(
        self,
        url: str,
        *,
        mode: Optional[FetchMode] = None,
        headers: Optional[dict] = None,
        proxy: Optional[str] = None,
        timeout: float = 30.0,
        **kwargs,
    ) -> FetchResult:
        """GET 请求（fetch 的快捷方式）"""
        return await self.fetch(url, method="GET", mode=mode, headers=headers, proxy=proxy, timeout=timeout, **kwargs)

    async def post(
        self,
        url: str,
        *,
        data: Optional[dict] = None,
        json: Optional[dict] = None,
        mode: Optional[FetchMode] = None,
        headers: Optional[dict] = None,
        proxy: Optional[str] = None,
        timeout: float = 30.0,
        **kwargs,
    ) -> FetchResult:
        """POST 请求（fetch 的快捷方式）"""
        return await self.fetch(url, method="POST", mode=mode, headers=headers, proxy=proxy, timeout=timeout, data=data, json=json, **kwargs)

    async def _fetch_with_retry(
        self,
        url: str,
        mode: FetchMode,
        **kwargs,
    ) -> FetchResult:
        """带重试和自动降级的抓取"""
        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                return await self._fetch_with_fallback(url, mode=mode, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self._max_retries:
                    delay = 1.0 * (2 ** attempt)
                    logger.warning(f"重试 {attempt + 1}/{self._max_retries}: {e}, {delay:.1f}s 后重试")
                    await asyncio.sleep(delay)
                    self._tls.next()  # 轮换指纹
        raise last_error

    async def _fetch_with_fallback(
        self,
        url: str,
        mode: FetchMode,
        **kwargs,
    ) -> FetchResult:
        """带自动降级的抓取"""
        # 确定要尝试的模式列表
        if self._auto_fallback:
            start_idx = FALLBACK_ORDER.index(mode) if mode in FALLBACK_ORDER else 0
            modes_to_try = FALLBACK_ORDER[start_idx:]
        else:
            modes_to_try = [mode]

        last_error = None
        for try_mode in modes_to_try:
            try:
                fetcher = self._get_fetcher(try_mode)
                result = await fetcher.fetch(url, **kwargs)

                # 403/429 才认为是 WAF 拦截
                if result.blocked and result.status_code in (403, 429):
                    if try_mode != FetchMode.STEALTH:
                        logger.warning(f"[{try_mode.value}] 被拦截 (HTTP {result.status_code})，降级...")
                        self._tls.next()
                        continue
                return result

            except Exception as e:
                last_error = e
                logger.warning(f"[{try_mode.value}] 失败: {e}")
                if try_mode != modes_to_try[-1]:
                    continue

        raise last_error or RuntimeError(f"所有抓取模式均失败: {url}")

    async def batch(
        self,
        urls: list[str],
        concurrency: int = 5,
        **kwargs,
    ) -> list[FetchResult]:
        """批量抓取（忽略失败的 URL）

        Args:
            urls: URL 列表
            concurrency: 并发数

        Returns:
            成功的 FetchResult 列表
        """
        results, _ = await self.batch_with_errors(urls, concurrency=concurrency, **kwargs)
        return results

    async def batch_with_errors(
        self,
        urls: list[str],
        concurrency: int = 5,
        **kwargs,
    ) -> tuple[list[FetchResult], list[tuple[str, Exception]]]:
        """批量抓取（返回失败详情）

        Args:
            urls: URL 列表
            concurrency: 并发数

        Returns:
            (成功列表, 失败列表) — 失败列表元素为 (url, exception) 元组
        """
        semaphore = asyncio.Semaphore(concurrency)
        successes: list[FetchResult] = []
        errors: list[tuple[str, Exception]] = []

        async def fetch_one(url: str):
            async with semaphore:
                try:
                    result = await self.get(url, **kwargs)
                    successes.append(result)
                except Exception as e:
                    logger.error(f"批量抓取失败: {url} - {e}")
                    errors.append((url, e))

        await asyncio.gather(*[fetch_one(url) for url in urls])
        return successes, errors

    async def close(self):
        """关闭所有抓取器"""
        for fetcher in self._fetchers.values():
            if hasattr(fetcher, "close"):
                await fetcher.close()
        self._fetchers.clear()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
