"""插件系统测试 — Plugin ABC + PluginManager + 内置插件。"""

import pytest
from unittest.mock import AsyncMock, patch

from omnicrawl.plugins.base import Plugin, PluginManager
from omnicrawl.plugins.builtin import (
    LoggingPlugin,
    StatsPlugin,
    FilterPlugin,
    TransformPlugin,
)
from omnicrawl.spider.base import Spider, CrawlSpider, SpiderItem
from omnicrawl.fetchers.base import FetchResult


# ── 测试用插件 ──

class ItemCounterPlugin(Plugin):
    name = "item_counter"

    def __init__(self):
        self.count = 0

    async def on_item(self, item):
        self.count += 1
        return item


class UrlRewritePlugin(Plugin):
    name = "url_rewrite"

    async def on_request(self, url):
        return url.replace("http://", "https://")


class DropAllPlugin(Plugin):
    name = "drop_all"

    async def on_item(self, item):
        return None


class SkipPlugin(Plugin):
    name = "skip"

    async def on_request(self, url):
        if "skip" in url:
            return None
        return url


# ── PluginManager 测试 ──

class TestPluginManager:
    def test_register(self):
        mgr = PluginManager()
        mgr.register(ItemCounterPlugin())
        assert mgr.count == 1

    def test_register_duplicate(self):
        mgr = PluginManager()
        mgr.register(ItemCounterPlugin())
        mgr.register(ItemCounterPlugin())  # 重复注册
        assert mgr.count == 1  # 不会重复

    def test_unregister(self):
        mgr = PluginManager()
        mgr.register(ItemCounterPlugin())
        assert mgr.unregister("item_counter") is True
        assert mgr.count == 0

    def test_unregister_missing(self):
        mgr = PluginManager()
        assert mgr.unregister("nope") is False

    def test_get(self):
        mgr = PluginManager()
        plugin = ItemCounterPlugin()
        mgr.register(plugin)
        assert mgr.get("item_counter") is plugin

    def test_get_missing(self):
        mgr = PluginManager()
        assert mgr.get("nope") is None

    def test_plugins_list(self):
        mgr = PluginManager()
        mgr.register(ItemCounterPlugin())
        mgr.register(UrlRewritePlugin())
        names = [p.name for p in mgr.plugins]
        assert "item_counter" in names
        assert "url_rewrite" in names


# ── 钩子分发测试 ──

class TestHookDispatch:
    @pytest.mark.asyncio
    async def test_trigger_item_chain(self):
        """多个 on_item 钩子链式调用"""
        class AddFieldPlugin(Plugin):
            name = "add_field"
            async def on_item(self, item):
                item.data["extra"] = True
                return item

        mgr = PluginManager()
        counter = ItemCounterPlugin()
        mgr.register(counter)
        mgr.register(AddFieldPlugin())

        item = SpiderItem(data={"title": "test"}, url="https://example.com")
        result = await mgr.trigger_item(item)

        assert result is not None
        assert result.data["extra"] is True
        assert counter.count == 1

    @pytest.mark.asyncio
    async def test_trigger_item_drop(self):
        """on_item 返回 None 丢弃数据项"""
        mgr = PluginManager()
        mgr.register(DropAllPlugin())

        item = SpiderItem(data={"title": "test"}, url="https://example.com")
        result = await mgr.trigger_item(item)
        assert result is None

    @pytest.mark.asyncio
    async def test_trigger_request_rewrite(self):
        """on_request 可修改 URL"""
        mgr = PluginManager()
        mgr.register(UrlRewritePlugin())

        result = await mgr.trigger_request("http://example.com")
        assert result == "https://example.com"

    @pytest.mark.asyncio
    async def test_trigger_request_skip(self):
        """on_request 返回 None 跳过请求"""
        mgr = PluginManager()
        mgr.register(SkipPlugin())

        result = await mgr.trigger_request("http://skip.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_trigger_error(self):
        """on_error 不抛异常"""
        class ErrorPlugin(Plugin):
            name = "error"
            def __init__(self):
                self.errors = []
            async def on_error(self, url, error):
                self.errors.append((url, error))

        mgr = PluginManager()
        ep = ErrorPlugin()
        mgr.register(ep)

        await mgr.trigger_error("http://test.com", ValueError("bad"))
        assert len(ep.errors) == 1

    @pytest.mark.asyncio
    async def test_plugin_exception_does_not_break_chain(self):
        """插件异常不影响后续插件"""
        class BadPlugin(Plugin):
            name = "bad"
            async def on_item(self, item):
                raise RuntimeError("oops")

        mgr = PluginManager()
        counter = ItemCounterPlugin()
        mgr.register(BadPlugin())
        mgr.register(counter)

        item = SpiderItem(data={"title": "test"}, url="https://example.com")
        result = await mgr.trigger_item(item)

        # BadPlugin 抛异常，但 counter 仍然被调用
        assert result is not None
        assert counter.count == 1


# ── 内置插件测试 ──

class TestStatsPlugin:
    @pytest.mark.asyncio
    async def test_counts(self):
        stats = StatsPlugin()
        await stats.on_start(None)
        await stats.on_request("http://a.com")
        await stats.on_request("http://b.com")

        result = FetchResult(
            url="http://a.com", status_code=200, html="", markdown="",
            text="", headers={}, cookies={}, mode_used="http", elapsed=0.1,
        )
        await stats.on_response("http://a.com", result)
        await stats.on_item(SpiderItem(data={}, url="http://a.com"))
        await stats.on_error("http://b.com", ValueError("fail"))

        assert stats.requests == 2
        assert stats.responses == 1
        assert stats.errors == 1
        assert stats.items == 1

    @pytest.mark.asyncio
    async def test_summary(self):
        stats = StatsPlugin()
        await stats.on_request("http://a.com")
        summary = stats.summary
        assert summary["requests"] == 1


class TestFilterPlugin:
    @pytest.mark.asyncio
    async def test_deny_pattern(self):
        plugin = FilterPlugin(deny_patterns=[r"/admin"])
        assert await plugin.on_request("http://example.com/page") == "http://example.com/page"
        assert await plugin.on_request("http://example.com/admin") is None

    @pytest.mark.asyncio
    async def test_allow_pattern(self):
        plugin = FilterPlugin(allow_patterns=[r"/api/"])
        assert await plugin.on_request("http://example.com/api/data") == "http://example.com/api/data"
        assert await plugin.on_request("http://example.com/page") is None

    @pytest.mark.asyncio
    async def test_allow_and_deny(self):
        plugin = FilterPlugin(
            allow_patterns=[r"/api/"],
            deny_patterns=[r"/admin"],
        )
        assert await plugin.on_request("http://example.com/api/data") == "http://example.com/api/data"
        assert await plugin.on_request("http://example.com/api/admin") is None
        assert await plugin.on_request("http://example.com/page") is None


class TestTransformPlugin:
    @pytest.mark.asyncio
    async def test_transform(self):
        def add_tag(item):
            item.data["tag"] = "crawled"
            return item

        plugin = TransformPlugin(add_tag)
        item = SpiderItem(data={"title": "test"}, url="https://example.com")
        result = await plugin.on_item(item)
        assert result.data["tag"] == "crawled"

    @pytest.mark.asyncio
    async def test_transform_drop(self):
        plugin = TransformPlugin(lambda item: None)
        item = SpiderItem(data={"title": "test"}, url="https://example.com")
        result = await plugin.on_item(item)
        assert result is None


# ── Spider 集成测试 ──

class TestSpiderPluginIntegration:
    @pytest.mark.asyncio
    async def test_plugin_on_item_in_spider(self):
        """插件在 Spider._process_url 中被调用"""
        counter = ItemCounterPlugin()

        class SimpleSpider(Spider):
            name = "test"
            start_urls = ["https://example.com"]

            async def parse(self, response):
                yield SpiderItem(data={"title": "test"}, url=response.url)

        spider = SimpleSpider()
        spider.plugins.register(counter)

        mock_result = FetchResult(
            url="https://example.com", status_code=200, html="<html></html>",
            markdown="# Test", text="Test", headers={}, cookies={},
            mode_used="http", elapsed=0.1,
        )

        with patch("omnicrawl.OmniClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_result)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            items = await spider.run()

        assert len(items) == 1
        assert counter.count == 1

    @pytest.mark.asyncio
    async def test_plugin_drop_item_in_spider(self):
        """插件丢弃数据项"""
        class SimpleSpider(Spider):
            name = "test"
            start_urls = ["https://example.com"]

            async def parse(self, response):
                yield SpiderItem(data={"title": "test"}, url=response.url)

        spider = SimpleSpider()
        spider.plugins.register(DropAllPlugin())

        mock_result = FetchResult(
            url="https://example.com", status_code=200, html="<html></html>",
            markdown="# Test", text="Test", headers={}, cookies={},
            mode_used="http", elapsed=0.1,
        )

        with patch("omnicrawl.OmniClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_result)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            items = await spider.run()

        assert len(items) == 0  # 被插件丢弃

    @pytest.mark.asyncio
    async def test_plugin_skip_request(self):
        """插件跳过请求"""
        class SimpleSpider(Spider):
            name = "test"
            start_urls = ["http://skip.com"]

            async def parse(self, response):
                yield SpiderItem(data={"title": "test"}, url=response.url)

        spider = SimpleSpider()
        spider.plugins.register(SkipPlugin())

        with patch("omnicrawl.OmniClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            items = await spider.run()

        assert len(items) == 0  # 请求被跳过
        mock_client.get.assert_not_called()


# ── 导入测试 ──

class TestImports:
    def test_import_from_omnicrawl(self):
        from omnicrawl import Plugin, PluginManager
        from omnicrawl import LoggingPlugin, StatsPlugin, FilterPlugin, TransformPlugin
        assert Plugin is not None
        assert PluginManager is not None
