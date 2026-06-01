"""HTTP 抓取器 — 基于 curl_cffi，速度最快"""

from __future__ import annotations

import time
from typing import Optional
from omnicrawl.fetchers.base import BaseFetcher, FetchMode, FetchResult
from omnicrawl.fingerprint.tls import TLSFingerprint
from omnicrawl.utils.logger import get_logger

logger = get_logger("http_fetcher")


class HttpFetcher(BaseFetcher):
    """基于 curl_cffi 的 HTTP 抓取器

    特点：
    - TLS 指纹伪装（37+ 浏览器指纹）
    - 支持 HTTP/2、HTTP/3
    - 速度最快，适合静态页面

    用法:
        async with HttpFetcher(fingerprint="chrome") as fetcher:
            result = await fetcher.fetch("https://example.com")
    """

    mode = FetchMode.HTTP

    def __init__(
        self,
        fingerprint: str = "chrome",
        stealthy_headers: bool = True,
    ):
        self._fingerprint = TLSFingerprint(fingerprint)
        self._stealthy_headers = stealthy_headers
        self._session = None
        self._session_fingerprint: Optional[str] = None  # 追踪会话使用的指纹

    async def _ensure_session(self):
        """确保会话存在且指纹是最新的"""
        current_fp = self._fingerprint.get()
        # 指纹变更时重建会话
        if self._session is not None and self._session_fingerprint != current_fp:
            await self.close()

        if self._session is None:
            from curl_cffi.requests import AsyncSession
            self._session = AsyncSession(impersonate=current_fp)
            self._session_fingerprint = current_fp

    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Optional[dict] = None,
        proxy: Optional[str] = None,
        timeout: float = 30.0,
        **kwargs,
    ) -> FetchResult:
        await self._ensure_session()
        start = time.time()

        request_headers = {}
        if self._stealthy_headers:
            request_headers.update({
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "accept-encoding": "gzip, deflate, br",
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "none",
                "sec-fetch-user": "?1",
                "upgrade-insecure-requests": "1",
            })
        if headers:
            request_headers.update(headers)

        proxies = {"https": proxy, "http": proxy} if proxy else None

        try:
            resp = await self._session.request(
                method,
                url,
                headers=request_headers,
                proxies=proxies,
                timeout=timeout,
                **kwargs,
            )
            elapsed = time.time() - start

            # 403/429 才是 WAF 拦截，401 是认证问题，503 是服务端问题
            blocked = resp.status_code in (403, 429)

            return FetchResult(
                url=str(resp.url),
                status_code=resp.status_code,
                html=resp.text,
                headers=dict(resp.headers),
                cookies=dict(resp.cookies),
                mode_used=self.mode,
                elapsed=elapsed,
                blocked=blocked,
                _content=resp.content,
            )
        except Exception as e:
            logger.error(f"HTTP 请求失败: {url} - {e}")
            raise

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
            self._session_fingerprint = None

    async def __aexit__(self, *args):
        await self.close()
