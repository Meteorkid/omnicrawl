"""代理验证器 — 检测代理可用性"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional
from omnicrawl.utils.logger import get_logger

logger = get_logger("proxy_validator")


@dataclass
class ProxyStatus:
    """代理状态"""
    proxy: str
    alive: bool
    latency: float = 0.0  # 延迟（秒）
    last_check: float = 0.0  # 最后检查时间
    fail_count: int = 0  # 连续失败次数
    error: str = ""


class ProxyValidator:
    """代理健康检查器

    用法:
        validator = ProxyValidator()
        status = await validator.check("http://proxy:8080")
        print(f"可用: {status.alive}, 延迟: {status.latency:.2f}s")

        # 批量检查
        results = await validator.check_all(["http://p1:8080", "http://p2:8080"])
        alive = [r for r in results if r.alive]
    """

    def __init__(
        self,
        test_url: str = "https://httpbin.org/ip",
        timeout: float = 10.0,
        max_failures: int = 3,
    ):
        self._test_url = test_url
        self._timeout = timeout
        self._max_failures = max_failures
        self._status: dict[str, ProxyStatus] = {}

    async def check(self, proxy: str) -> ProxyStatus:
        """检查单个代理是否可用"""
        from curl_cffi.requests import AsyncSession

        start = time.time()
        try:
            async with AsyncSession(impersonate="chrome") as s:
                resp = await s.get(
                    self._test_url,
                    proxies={"https": proxy, "http": proxy},
                    timeout=self._timeout,
                )
                latency = time.time() - start
                alive = resp.status_code == 200

                status = ProxyStatus(
                    proxy=proxy,
                    alive=alive,
                    latency=latency,
                    last_check=time.time(),
                    fail_count=0 if alive else (self._status.get(proxy, ProxyStatus(proxy=proxy, alive=False)).fail_count + 1),
                )
                self._status[proxy] = status

                if alive:
                    logger.debug(f"代理可用: {proxy} ({latency:.2f}s)")
                else:
                    logger.warning(f"代理不可用: {proxy} (HTTP {resp.status_code})")

                return status

        except Exception as e:
            latency = time.time() - start
            prev_fails = self._status.get(proxy, ProxyStatus(proxy=proxy, alive=False)).fail_count
            status = ProxyStatus(
                proxy=proxy,
                alive=False,
                latency=latency,
                last_check=time.time(),
                fail_count=prev_fails + 1,
                error=str(e),
            )
            self._status[proxy] = status
            logger.warning(f"代理检测失败: {proxy} - {e}")
            return status

    async def check_all(
        self,
        proxies: list[str],
        concurrency: int = 10,
    ) -> list[ProxyStatus]:
        """批量检查代理"""
        semaphore = asyncio.Semaphore(concurrency)

        async def check_one(proxy: str) -> ProxyStatus:
            async with semaphore:
                return await self.check(proxy)

        return await asyncio.gather(*[check_one(p) for p in proxies])

    def get_alive(self, proxies: list[str]) -> list[str]:
        """获取已知可用的代理列表（基于上次检查结果）"""
        return [
            p for p in proxies
            if p in self._status
            and self._status[p].alive
            and self._status[p].fail_count < self._max_failures
        ]

    def get_status(self, proxy: str) -> Optional[ProxyStatus]:
        """获取代理状态"""
        return self._status.get(proxy)

    def is_healthy(self, proxy: str) -> bool:
        """判断代理是否健康"""
        status = self._status.get(proxy)
        if status is None:
            return True  # 未检查过的代理默认健康
        return status.alive and status.fail_count < self._max_failures
