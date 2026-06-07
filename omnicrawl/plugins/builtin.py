"""内置插件 — 开箱即用的 Spider 钩子。"""

from __future__ import annotations

import time
from typing import Optional, TYPE_CHECKING

from omnicrawl.plugins.base import Plugin
from omnicrawl.utils.logger import get_logger

if TYPE_CHECKING:
    from omnicrawl.fetchers.base import FetchResult
    from omnicrawl.spider.base import SpiderItem

logger = get_logger("plugin")


class LoggingPlugin(Plugin):
    """日志插件 — 记录请求、响应、错误。"""

    name = "logging"

    def __init__(self, level: str = "info"):
        self._level = level
        self._log = get_logger("plugin.logging")

    async def on_request(self, url: str) -> Optional[str]:
        self._log.info("请求: %s", url)
        return url

    async def on_response(self, url: str, result: FetchResult) -> Optional[FetchResult]:
        self._log.info("响应: %s [%d] %.2fs", url, result.status_code, result.elapsed)
        return result

    async def on_error(self, url: str, error: Exception) -> None:
        self._log.error("失败: %s - %s", url, error)


class StatsPlugin(Plugin):
    """统计插件 — 计数请求、响应、错误、数据项。"""

    name = "stats"

    def __init__(self):
        self.requests = 0
        self.responses = 0
        self.errors = 0
        self.items = 0
        self.blocked = 0
        self._start_time: Optional[float] = None

    async def on_start(self, spider) -> None:
        self._start_time = time.monotonic()

    async def on_finish(self, spider, stats: dict) -> None:
        elapsed = time.monotonic() - self._start_time if self._start_time else 0
        self._log_stats(elapsed)

    async def on_request(self, url: str) -> Optional[str]:
        self.requests += 1
        return url

    async def on_response(self, url: str, result: FetchResult) -> Optional[FetchResult]:
        self.responses += 1
        if result.blocked:
            self.blocked += 1
        return result

    async def on_item(self, item: SpiderItem) -> Optional[SpiderItem]:
        self.items += 1
        return item

    async def on_error(self, url: str, error: Exception) -> None:
        self.errors += 1

    def _log_stats(self, elapsed: float) -> None:
        logger.info(
            "统计: 请求=%d 响应=%d 错误=%d 丢弃=%d 数据项=%d 耗时=%.1fs",
            self.requests, self.responses, self.errors, self.blocked, self.items, elapsed,
        )

    @property
    def summary(self) -> dict:
        return {
            "requests": self.requests,
            "responses": self.responses,
            "errors": self.errors,
            "items": self.items,
            "blocked": self.blocked,
        }


class FilterPlugin(Plugin):
    """过滤插件 — 按 URL 模式过滤请求。"""

    name = "filter"

    def __init__(
        self,
        allow_patterns: Optional[list[str]] = None,
        deny_patterns: Optional[list[str]] = None,
    ):
        import re
        self._allow = [re.compile(p) for p in (allow_patterns or [])]
        self._deny = [re.compile(p) for p in (deny_patterns or [])]

    async def on_request(self, url: str) -> Optional[str]:
        # deny 模式匹配则跳过
        for pattern in self._deny:
            if pattern.search(url):
                logger.debug("过滤: %s (deny %s)", url, pattern.pattern)
                return None

        # 有 allow 模式时，必须匹配至少一个
        if self._allow:
            if not any(p.search(url) for p in self._allow):
                logger.debug("过滤: %s (不在 allow 列表中)", url)
                return None

        return url


class TransformPlugin(Plugin):
    """数据转换插件 — 对数据项应用转换函数。"""

    name = "transform"

    def __init__(self, transform_fn):
        """
        Args:
            transform_fn: 接收 SpiderItem，返回修改后的 SpiderItem 或 None
        """
        self._fn = transform_fn

    async def on_item(self, item: SpiderItem) -> Optional[SpiderItem]:
        return self._fn(item)
