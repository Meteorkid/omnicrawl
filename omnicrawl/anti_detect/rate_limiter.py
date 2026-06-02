"""智能限速器 — 基于域名的自适应延时"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse
from omnicrawl.utils.logger import get_logger

logger = get_logger("rate_limiter")


class RateLimiter:
    """基于域名的智能限速器

    - 每个域名独立维护请求时间戳
    - 被封后自动增加该域名的延时
    - 支持全局并发限制

    用法:
        limiter = RateLimiter(min_delay=1.0, max_delay=10.0)
        await limiter.wait("https://example.com/page1")
    """

    def __init__(
        self,
        min_delay: float = 1.0,
        max_delay: float = 10.0,
        backoff_factor: float = 2.0,
        cooldown: float = 60.0,
        max_concurrent: int = 10,
    ):
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._backoff_factor = backoff_factor
        self._cooldown = cooldown
        self._domain_delays: dict[str, float] = {}
        self._last_request: dict[str, float] = {}
        self._block_count: dict[str, int] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

    def _get_domain(self, url: str) -> str:
        return urlparse(url).netloc

    async def wait(self, url: str) -> None:
        """等待直到可以发送请求"""
        domain = self._get_domain(url)
        delay = self._domain_delays.get(domain, self._min_delay)

        async with self._semaphore:
            last = self._last_request.get(domain, 0)
            elapsed = time.time() - last
            if elapsed < delay:
                wait_time = delay - elapsed
                logger.debug(f"限速等待 {domain}: {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
            # 在信号量内更新时间戳，避免并发竞态
            self._last_request[domain] = time.time()

    def report_blocked(self, url: str) -> None:
        """报告被封，自动增加延时"""
        domain = self._get_domain(url)
        count = self._block_count.get(domain, 0) + 1
        self._block_count[domain] = count
        new_delay = min(
            self._min_delay * (self._backoff_factor ** count),
            self._max_delay,
        )
        self._domain_delays[domain] = new_delay
        logger.warning(f"域名 {domain} 被封 {count} 次，延时调整为 {new_delay:.1f}s")

    def report_success(self, url: str) -> None:
        """报告成功，逐步恢复延时"""
        domain = self._get_domain(url)
        if domain in self._block_count and self._block_count[domain] > 0:
            self._block_count[domain] = max(0, self._block_count[domain] - 1)
            new_delay = max(
                self._min_delay,
                self._domain_delays.get(domain, self._min_delay) / self._backoff_factor,
            )
            self._domain_delays[domain] = new_delay
