"""插件系统 — 可扩展的 Spider 钩子机制。

用法:
    from omnicrawl.plugins.base import Plugin, PluginManager

    class MyPlugin(Plugin):
        name = "my_plugin"

        async def on_item(self, item):
            item.data["processed"] = True
            return item

    spider = MySpider()
    spider.plugins.register(MyPlugin())
    items = await spider.run()
"""

from __future__ import annotations

from abc import ABC
from typing import Optional, TYPE_CHECKING

from omnicrawl.utils.logger import get_logger

if TYPE_CHECKING:
    from omnicrawl.fetchers.base import FetchResult
    from omnicrawl.spider.base import SpiderItem

logger = get_logger("plugin")


class Plugin(ABC):
    """插件基类。

    所有钩子方法都是可选的，只需覆盖感兴趣的钩子。
    返回 None 的钩子（如 on_item）会丢弃数据项。
    """

    name: str = "unnamed"

    async def on_start(self, spider) -> None:
        """Spider 开始运行时调用。"""

    async def on_finish(self, spider, stats: dict) -> None:
        """Spider 运行结束时调用。"""

    async def on_request(self, url: str) -> Optional[str]:
        """请求发出前调用。

        Args:
            url: 请求 URL

        Returns:
            修改后的 URL，或 None（跳过此请求）
        """
        return url

    async def on_response(self, url: str, result: FetchResult) -> Optional[FetchResult]:
        """收到响应后调用。

        Args:
            url: 请求 URL
            result: 抓取结果

        Returns:
            修改后的 result，或 None（丢弃此响应）
        """
        return result

    async def on_item(self, item: SpiderItem) -> Optional[SpiderItem]:
        """产出数据项时调用。

        Args:
            item: 爬取的数据项

        Returns:
            修改后的 item，或 None（丢弃此数据项）
        """
        return item

    async def on_error(self, url: str, error: Exception) -> None:
        """请求失败时调用。"""


class PluginManager:
    """插件管理器 — 注册、注销、分发插件钩子。"""

    def __init__(self):
        self._plugins: list[Plugin] = []

    def register(self, plugin: Plugin) -> None:
        """注册插件。"""
        if any(p.name == plugin.name for p in self._plugins):
            logger.warning("插件 '%s' 已注册，跳过", plugin.name)
            return
        self._plugins.append(plugin)
        logger.debug("插件已注册: %s", plugin.name)

    def unregister(self, name: str) -> bool:
        """按名称注销插件，返回是否成功。"""
        for i, p in enumerate(self._plugins):
            if p.name == name:
                self._plugins.pop(i)
                logger.debug("插件已注销: %s", name)
                return True
        return False

    def get(self, name: str) -> Optional[Plugin]:
        """按名称获取插件。"""
        for p in self._plugins:
            if p.name == name:
                return p
        return None

    @property
    def plugins(self) -> list[Plugin]:
        """已注册插件列表。"""
        return list(self._plugins)

    @property
    def count(self) -> int:
        """已注册插件数量。"""
        return len(self._plugins)

    # ── 钩子分发 ──

    async def trigger_start(self, spider) -> None:
        """分发 on_start 钩子。"""
        for p in self._plugins:
            try:
                await p.on_start(spider)
            except Exception as e:
                logger.error("插件 '%s' on_start 失败: %s", p.name, e)

    async def trigger_finish(self, spider, stats: dict) -> None:
        """分发 on_finish 钩子。"""
        for p in self._plugins:
            try:
                await p.on_finish(spider, stats)
            except Exception as e:
                logger.error("插件 '%s' on_finish 失败: %s", p.name, e)

    async def trigger_request(self, url: str) -> Optional[str]:
        """分发 on_request 钩子。返回 None 表示跳过请求。"""
        current = url
        for p in self._plugins:
            if current is None:
                return None
            try:
                current = await p.on_request(current)
            except Exception as e:
                logger.error("插件 '%s' on_request 失败: %s", p.name, e)
        return current

    async def trigger_response(self, url: str, result: FetchResult) -> Optional[FetchResult]:
        """分发 on_response 钩子。返回 None 表示丢弃响应。"""
        current = result
        for p in self._plugins:
            if current is None:
                return None
            try:
                current = await p.on_response(url, current)
            except Exception as e:
                logger.error("插件 '%s' on_response 失败: %s", p.name, e)
        return current

    async def trigger_item(self, item: SpiderItem) -> Optional[SpiderItem]:
        """分发 on_item 钩子。返回 None 表示丢弃数据项。"""
        current = item
        for p in self._plugins:
            if current is None:
                return None
            try:
                current = await p.on_item(current)
            except Exception as e:
                logger.error("插件 '%s' on_item 失败: %s", p.name, e)
        return current

    async def trigger_error(self, url: str, error: Exception) -> None:
        """分发 on_error 钩子。"""
        for p in self._plugins:
            try:
                await p.on_error(url, error)
            except Exception as e:
                logger.error("插件 '%s' on_error 失败: %s", p.name, e)
